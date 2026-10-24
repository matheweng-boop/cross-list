"""Blank-form crawler (24 Oct 2026): every form on every menu page, sent the way a browser sends it with nothing filled
in, must give a page, never a 422 or a server error.

A price-estimate bug reached the live site although every test passed: a blank number field (``released=``) gave the
"value the page cannot use" page. These tests read the forms out of the rendered HTML, so a new form is covered as
soon as it is on a page. They run as the local owner (no site password); the sign-in gate itself is tested elsewhere.
"""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import pytest

from app.web.nav import NAV, TABS, UTILITY
from tests.conftest import solve_pow

# Forms that delete data or change people, passkeys, invites or sign-in: never sent blind (the owner would lose data,
# or the test would lock itself out). Matched against the form's action path.
SKIP_ACTIONS = ("/delete", "/remove", "/cancel", "/manage/people", "/owner/", "/invite/", "/passkey/", "/login",
                "/logout")  # fmt: skip

# a few detail pages next to the menu pages, each the first link of its kind on a list page: (list page, link pattern)
DETAIL_LINKS = (("/find?q=SR", r"/parts/\d+"), ("/library", r"/library/(?!sources)[\w-]+"),
                ("/business/reports", r"/business/reports/(?!method|questions)[\w-]+"),
                ("/business/competitors", r"/business/competitors/[\w-]+"))  # fmt: skip
# more detail pages with forms, sent when the list page links one: a part review, a block diagram, a band, a case
MORE_LINKS = (("/reviews", r"/reviews/(?!suggest|request)[\w-]+"), ("/blocks", r"/blocks/\d+"),
              ("/rf-bands", r"/rf-bands/[\w-]+"), ("/business/cases", r"/business/cases/\d+"),
              ("/business/applications", r"/business/applications/\d+"))  # fmt: skip


class _Forms(HTMLParser):
    """The forms of a page with the fields a browser would send, including fields tied to a form with form="id"."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms: list[dict] = []
        self._by_id: dict[str, dict] = {}
        self._orphans: list[tuple[str, dict]] = []  # (form id, field) for fields outside their form
        self._form: dict | None = None
        self._select: dict | None = None
        self._option: dict | None = None
        self._textarea: dict | None = None

    def _add(self, a: dict, field: dict) -> None:
        if a.get("form"):
            self._orphans.append((a["form"], field))
        elif self._form is not None:
            self._form["fields"].append(field)

    def handle_starttag(self, tag, attrs):
        a = {k: (v if v is not None else "") for k, v in attrs}
        if tag == "form":
            hx = next(((m, a[f"hx-{m}"]) for m in ("get", "post") if a.get(f"hx-{m}")), None)  # an HTMX form
            method, action = hx or (a.get("method", "get").lower(), a.get("action", ""))
            self._form = {"action": action, "method": method, "enctype": a.get("enctype", ""), "fields": []}
            self.forms.append(self._form)
            if a.get("id"):
                self._by_id[a["id"]] = self._form
        elif tag in ("input", "button", "select", "textarea") and (self._form is not None or a.get("form")):
            kind = a.get("type", "submit" if tag == "button" else "text").lower()
            field = {"tag": tag, "type": kind, "name": a.get("name", ""), "value": a.get("value", ""),
                     "checked": "checked" in a, "disabled": "disabled" in a, "options": [], "a": a}  # fmt: skip
            if tag == "select":
                self._select = field
            elif tag == "textarea":
                self._textarea = field
            self._add(a, field)
        elif tag == "option" and self._select is not None:
            self._option = {"value": a.get("value"), "text": "", "selected": "selected" in a,
                            "disabled": "disabled" in a}  # fmt: skip
            self._select["options"].append(self._option)

    def handle_endtag(self, tag):
        if tag == "form":
            self._form = None
        elif tag == "select":
            self._select = self._option = None
        elif tag == "option":
            self._option = None
        elif tag == "textarea":
            self._textarea = None

    def handle_data(self, data):
        if self._option is not None:
            self._option["text"] += data
        elif self._textarea is not None:
            self._textarea["value"] += data

    def close(self):
        super().close()
        for fid, field in self._orphans:
            if fid in self._by_id:
                self._by_id[fid]["fields"].append(field)


def _range_default(a: dict) -> str:
    lo, hi = float(a.get("min") or 0), float(a.get("max") or 100)
    mid = lo if hi < lo else (lo + hi) / 2
    return str(int(mid)) if mid == int(mid) else str(mid)


def browser_payload(form: dict, submitter: dict | None) -> list[tuple[str, str]]:
    """The name/value pairs a browser sends for the form left as rendered: text empty or at its value attribute,
    selects at the selected (or first) option, checkboxes and radios only when checked, plus the button pressed."""
    out = []
    for f in form["fields"]:
        if not f["name"] or f["disabled"]:
            continue
        if f["tag"] == "select":
            opts = [o for o in f["options"] if not o["disabled"]] or f["options"]
            chosen = [o for o in opts if o["selected"]]
            if not chosen and "multiple" not in f["a"] and opts:
                chosen = opts[:1]
            out += [(f["name"], o["value"] if o["value"] is not None else o["text"].strip()) for o in chosen]
        elif f["tag"] == "textarea":
            out.append((f["name"], f["value"].removeprefix("\n")))
        elif f["type"] in ("submit", "image", "button", "reset", "file"):
            continue
        elif f["type"] in ("checkbox", "radio"):
            if f["checked"]:
                out.append((f["name"], f["value"] or "on"))
        elif f["type"] == "range":
            out.append((f["name"], f["value"] or _range_default(f["a"])))
        else:
            out.append((f["name"], f["value"]))
    if submitter is not None and submitter["name"]:
        out.append((submitter["name"], submitter["value"]))
    return out


def submitters(form: dict) -> list[dict | None]:
    """Each distinct submit button (they can carry a name, formaction or formmethod); None when there is none."""
    buttons = [f for f in form["fields"] if f["type"] in ("submit", "image") and not f["disabled"]]
    seen, out = set(), []
    for b in buttons:
        key = (b["name"], b["value"], b["a"].get("formaction"), b["a"].get("formmethod"))
        if key not in seen:
            seen.add(key)
            out.append(b)
    return out or [None]


def detail_pages(client) -> list[str]:
    """A part and its walk-through, a library topic, a report and a competitor profile."""
    out = []
    for page, pattern in DETAIL_LINKS:
        found = re.search(f'href="({pattern})"', client.get(page).text)
        assert found, (page, pattern)
        out.append(found.group(1))
    more = [re.search(f'href="({pattern})"', client.get(page).text) for page, pattern in MORE_LINKS]
    return out[:1] + [out[0] + "/walk"] + out[1:] + [m.group(1) for m in more if m]


def menu_pages() -> list[str]:
    hrefs = [href for _key, _label, items in (*NAV, UTILITY) for _l, href, _d in items]
    hrefs += [href for group in TABS for _l, href in group]
    return list(dict.fromkeys(hrefs))


def send(client, page: str, form: dict, submitter: dict | None):
    a = submitter["a"] if submitter else {}
    action = urljoin("http://testserver" + page, a.get("formaction") or form["action"] or page)
    method = (a.get("formmethod") or form["method"]).lower()
    data = browser_payload(form, submitter)
    names = {n for n, _ in data}
    if "pow_challenge" in names:  # a proof of work, as the page's script would solve it
        data = [(n, v) for n, v in data if n not in ("pow_challenge", "pow_nonce")] + list(solve_pow(client).items())
    split = urlsplit(action)
    path = split.path
    if method == "get":
        return path, client.get(path, params=data, follow_redirects=True)
    files = None
    enctype = (a.get("formenctype") or form["enctype"]).lower()
    file_fields = [f["name"] for f in form["fields"] if f["type"] == "file" and f["name"] and not f["disabled"]]
    if enctype == "multipart/form-data" and file_fields:
        files = [(n, ("", b"", "application/octet-stream")) for n in file_fields]
    url = path + (f"?{split.query}" if split.query else "")
    fields: dict[str, list[str]] = {}
    for n, v in data:
        fields.setdefault(n, []).append(v)
    return path, client.post(url, data=fields, files=files, follow_redirects=True)


def _signature(page: str, form: dict, sub: dict | None) -> tuple:
    """Forms repeated per row (one per task, item or request) differ only in the number in their action: send one."""
    a = sub["a"] if sub else {}
    action = re.sub(r"\d+", "N", urlsplit(a.get("formaction") or form["action"] or page).path)
    fields = tuple(sorted((f["name"], f["type"]) for f in form["fields"] if f["name"]))
    return action, a.get("formmethod") or form["method"], fields, (sub or {}).get("name"), (sub or {}).get("value")


def crawl(client, pages: list[str]) -> tuple[list[str], list[str], int]:
    failures, skipped, sent, seen = [], [], 0, set()
    for page in pages:
        r = client.get(page)
        assert r.status_code == 200, (page, r.status_code)
        title = re.search(r"<title>(.*?)</title>", r.text, re.S)
        assert title and "<" not in title.group(1), (page, "markup in the <title>")  # verify.html had a <script> there
        parser = _Forms()
        parser.feed(r.text)
        parser.close()
        for form in parser.forms:
            for sub in submitters(form):
                target = (sub["a"].get("formaction") if sub else None) or form["action"] or page
                method = ((sub["a"].get("formmethod") if sub else None) or form["method"]).lower()
                if method != "get" and any(s in urlsplit(target).path for s in SKIP_ACTIONS):  # a GET changes nothing
                    skipped.append(f"{page}: {target}")
                    continue
                if (sig := _signature(page, form, sub)) in seen:
                    continue
                seen.add(sig)
                path, resp = send(client, page, form, sub)
                sent += 1
                if resp.status_code == 422 or resp.status_code >= 500:
                    failures.append(f"{page} -> {(sub['a'].get('formmethod') if sub else None) or form['method']} "
                                    f"{path}: {resp.status_code}")  # fmt: skip
    return failures, skipped, sent


def seed_rows(client) -> None:
    """One row of each kind that has its own per-row form on a Data management page (answer, status, remove), so
    those forms are on the pages too: feedback, requests, an upload, a shortlist item, a guest and an open invite."""
    from sqlalchemy.orm import Session

    from app.auth.session import new_handle
    from app.db import get_engine
    from app.models import Account

    ok = (200, 303)
    assert client.post("/site-feedback", json={"text": "Blank-form test", "path": "/parts"}).status_code in ok
    assert client.post("/requests", data={"mpns": "XYZ123"}, follow_redirects=False).status_code in ok
    assert client.post("/blocks/area-request", data={"area": "Drones"}, follow_redirects=False).status_code in ok
    assert client.post("/api/blocks/feedback", json={"message": "A block is missing"}).status_code in ok
    assert client.post("/manage/uploads", data={"explanation": "A note"}, follow_redirects=False).status_code in ok
    assert client.post("/reviews/request", data={"mpn": "SR8641", "question": "Why?"},
                       follow_redirects=False).status_code in ok  # fmt: skip
    assert client.post("/business/shortlist", data={"origin": "idea", "key": "Test idea"},
                       follow_redirects=False).status_code in ok  # fmt: skip
    from app.auth.passkeys import new_invite

    with Session(get_engine()) as s:
        s.add(Account(name="Anna Guest", role="guest", handle=new_handle()))
        new_invite(s, "Ben Invited", "")
        s.commit()


@pytest.fixture
def owner_client(client, tmp_path, monkeypatch):
    """The local owner (no site password), with uploads kept in the test's own folder and a row of each kind."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path / "var")
    seed_rows(client)
    return client


def test_every_menu_form_sent_blank_gives_a_page(owner_client):
    failures, skipped, sent = crawl(owner_client, menu_pages())
    print(f"\nsent {sent} forms; skipped {len(skipped)}:\n  " + "\n  ".join(sorted(set(skipped))))
    assert sent > 20
    assert not failures, "\n".join(failures)


def test_detail_page_forms_sent_blank_give_a_page(owner_client):
    pages = detail_pages(owner_client)
    failures, skipped, sent = crawl(owner_client, pages)
    print("\n" + "\n".join(pages))
    assert sent > 3
    assert not failures, "\n".join(failures)


def test_the_crawler_sends_what_a_browser_sends():
    """The parser itself: blank text, the selected option, checked boxes only, the pressed button, form="id" fields."""
    page = """<form id="f" action="/x" method="post"><input name="a"><input name="n" type="number" value="">
      <select name="s"><option value="1">one</option><option value="2" selected>two</option></select>
      <select name="t"><option>first</option></select><input type="checkbox" name="c"><input type="checkbox" name="d"
      checked value="y"><input name="off" disabled value="z"><textarea name="m">
hi</textarea><button name="go" value="save">Save</button><input type="file" name="f"></form>
      <input form="f" name="outside" value="o"><form hx-get="/h"><input name="q"></form>"""
    p = _Forms()
    p.feed(page)
    p.close()
    first, htmx = p.forms
    assert (first["method"], first["action"], htmx["method"], htmx["action"]) == ("post", "/x", "get", "/h")
    assert browser_payload(first, submitters(first)[0]) == [
        ("a", ""), ("n", ""), ("s", "2"), ("t", "first"), ("d", "y"), ("m", "hi"), ("outside", "o"), ("go", "save")
    ]  # fmt: skip


def test_the_price_estimate_form_is_among_those_sent_blank(owner_client):
    """The form that broke on 23 Oct is found, and its number fields go out blank (released=, pins=)."""
    p = _Forms()
    p.feed(owner_client.get("/pricing/estimate").text)
    p.close()
    est = next(f for f in p.forms if f["action"] == "/pricing/estimate")
    data = browser_payload(est, submitters(est)[0])
    assert ("released", "") in data and ("pins", "") in data
