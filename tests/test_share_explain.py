"""Shareable > Explanation (owner, 27 Oct 2026: "another button next to the shareable pages where I can click preview or
I can read the explanation"): owner only, opens in the lightbox, the full block table for the four system briefs, a
short note for the other documents, and never part of the shared page, the PDF, the PowerPoint or the merged file.
The browser click is in tests/test_browser.py."""

import re
from html import unescape

import pytest

from app.auth import access
from app.services import presentation_pptx as pp
from app.services import share_explain as sx
from app.services import share_pdf as spdf
from app.services import share_reports as sr
from app.services import share_systems as sy
from app.web import routes

SYSTEMS = ("uwb", "v2x", "gnss", "radio")


def flat(text: str) -> str:
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", text)).split())


def explain_lines(key: str) -> list[str]:
    """The texts only the explanation carries (long enough to be unmistakable)."""
    x = sx.build(key)
    lines = [*x.get("short", []), *x.get("changes", []), *x.get("limits", []), *x["built_from"], *x["checks"]]
    return [" ".join(t.split()) for t in lines if len(t) > 40]


def test_the_owner_sees_an_explanation_button_for_every_document(client):
    html = client.get("/shareable").text
    for key, e in sr.registry().items():
        row = re.search(rf'<li class="sh-row">(?:(?!</li>).)*value="{key}"(?:(?!</li>).)*</li>', html, re.S)
        assert row, key
        r = row.group(0)
        assert ">Preview</a>" in r and f'href="{e.url}/explain"' in r, key
        a = re.search(r'<a [^>]*href="[^"]+/explain"[^>]*>Explanation</a>', r)
        assert a and "data-lightbox=" in a.group(0) and 'role="button"' in a.group(0), key
        # next to Preview: the button follows it in the same group of actions
        acts = r.split('class="sh-acts"', 1)[1]
        assert acts.index(">Preview</a>") < acts.index(">Explanation</a>")
        assert client.get(f"{e.url}/explain").status_code == 200, key


def test_guests_do_not_see_the_button_and_get_403(make_guest):
    g, _ = make_guest()
    html = g.get("/shareable").text
    assert "/explain" not in html and ">Explanation<" not in html
    for e in sr.registry().values():
        assert g.get(f"{e.url}/explain", follow_redirects=False).status_code == 403, e.key
        assert g.get(f"{e.url}/explain?embed=1", follow_redirects=False).status_code == 403, e.key
    assert access.owner_only("/shareable/uwb/explain", "GET") and access.owner_only("/shareable/drones/explain", "GET")
    assert not access.owner_only("/shareable/uwb", "GET")


def test_the_owner_with_a_password_reads_it(owner):
    r = owner.get("/shareable/radio/explain")
    assert r.status_code == 200 and "Block by block" in r.text


def test_unknown_document_is_404(client):
    assert client.get("/shareable/nothing-here/explain").status_code == 404


@pytest.mark.parametrize("key", SYSTEMS)
def test_each_brief_explains_every_block_for_both_companies(client, key):
    r = client.get(f"/shareable/{key}/explain?embed=1")
    assert r.status_code == 200
    html = r.text
    assert re.search(r'<body class="[^"]*\bembed\b', html)  # the lightbox shows the explanation alone
    for h in ("In short", "Block by block", "What we changed and why", "Blocks without a part",
              "Limits and open points", "Sources"):  # fmt: skip
        assert f">{h}</h2>" in html, h
    table = html.split('class="sx-table"', 1)[1].split("</table>", 1)[0]
    assert "<th>Block</th><th>Skyworks</th><th>Qorvo</th><th>Note</th>" in table
    b = sr.registry()[key].build()
    rows = re.findall(r"<tr class=\"sx-row-", table)
    assert len(rows) == len(b["diagram"]["at"])  # every block of the diagram
    assert table.count('data-l="Skyworks"') == len(rows) == table.count('data-l="Qorvo"')
    cov = sy.coverage(key)
    for ref, label in b["diagram"]["at"].items():
        assert unescape(label) in unescape(table), label
        for co in sy.COMPANIES:
            for f in cov[ref][co]:
                assert f["kind"] in sy.KINDS
                assert flat(f["why"])[:30] in flat(table), (ref, co)
    for word in ("Automotive", "Bundle option", "Nothing that fits"):
        assert f">{word}</span>" in table
    for p in b["core"] + b["peripherals"]:  # parts on the document in bold
        assert f"<b><code>{p['mpn']}</code></b>" in table, p["mpn"]
    text = flat(html)
    x = sx.build(key)
    assert x["changes"] and all(" ".join(c.split()) in text for c in x["changes"])
    assert "At most 6 rows per slide" in text and "checked 27 Oct 2026" in text
    for g in x["gaps"]:
        assert flat(g["label"]) in text
    assert "/business/reports/" in html  # the research reports the words come from


def test_the_open_points_are_listed():
    v2x = " ".join(sx.build("v2x")["limits"])
    assert "QPF1003Q" in v2x and "Not confirmed" in v2x
    uwb = sx.build("uwb")
    assert "QPF4554Q" in " ".join(uwb["limits"]) and "QM14070" in " ".join(uwb["limits"])
    assert any(t.startswith("Estimate (est)") for t in uwb["limits"])
    radio = sx.build("radio")
    assert any("antenna tuner" in g["qorvo"] or "discontinued" in g["qorvo"] for g in radio["gaps"])


@pytest.mark.parametrize("key", ["overview", "synergies", "automotive"])
def test_the_other_documents_get_a_short_explanation(client, key):
    html = client.get(sr.registry()[key].url + "/explain").text
    for h in ("What it is built from", "Its checks", "Known limits"):
        assert f">{h}</h2>" in html, h
    assert "Block by block" not in html
    text = flat(html)
    assert "Word check" in text and "Site guard" in text and "Page budget" in text
    assert all(" ".join(b.split()) in text for b in sx.build(key)["built_from"])


def test_nothing_specific_says_so_plainly(client, monkeypatch):
    monkeypatch.setattr(sx, "curated", lambda: {})
    html = client.get("/shareable/synergies/explain").text
    assert html.count(sx.NONE_YET) == 3  # built from, checks, limits


def test_the_explanation_is_not_a_shareable_document(client):
    for e in sr.registry().values():
        assert not routes._shareable_document(f"{e.url}/explain")
    assert routes._shareable_document("/shareable/uwb")
    html = client.get("/shareable/uwb/explain").text
    assert 'class="site-foot"' in html  # a site page (the lightbox hides the frame with ?embed=1)
    assert "Internal" in html


def test_the_explanation_never_reaches_the_pdf_the_powerpoint_or_the_shared_page(client):
    keys = list(sr.registry())
    lines = {k: explain_lines(k) for k in keys}
    assert all(lines[k] for k in keys)
    pdf = client.get(f"/shareable/pdf?r={','.join(keys)}")  # the merged file
    assert pdf.status_code == 200
    pdf_text = " ".join(" ".join(spdf.texts(pdf.content)).split())
    deck = client.get(f"/shareable/pptx?r={','.join(keys)}")
    assert deck.status_code == 200
    deck_text = " ".join(" ".join(x for s in pp.texts(deck.content) for x in s).split())
    for marker in ("In short", "Block by block", "What we changed", "Recorded but not shown", "only you see this"):
        assert marker not in pdf_text and marker not in deck_text, marker
    for k in keys:
        page = flat(client.get(sr.registry()[k].url).text)
        for line in lines[k]:
            assert line not in pdf_text and line not in deck_text and line not in page, (k, line)
        assert "/explain" not in client.get(sr.registry()[k].url).text
        single = client.get(f"/shareable/pdf?r={k}")
        assert not [x for x in lines[k] if x in " ".join(" ".join(spdf.texts(single.content)).split())]


def test_the_lightbox_may_frame_the_explanation_and_every_document(client):
    """The lightbox is an iframe on the same site: every document and its explanation may be framed by this site only
    (the system briefs included); their edit pages and the rest stay unframeable."""
    for e in sr.registry().values():
        for path in (e.url + "?embed=1", e.url + "/explain?embed=1"):
            r = client.get(path)
            assert r.status_code == 200, path
            assert r.headers["x-frame-options"] == "SAMEORIGIN", path
            assert "frame-ancestors 'self'" in r.headers["content-security-policy"], path
    for path in ("/shareable/uwb/edit", "/shareable/nothing/explain", "/shareable"):
        r = client.get(path, follow_redirects=False)
        assert r.headers["x-frame-options"] == "DENY", path
