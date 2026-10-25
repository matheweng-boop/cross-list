"""Gists, abstracts and Data management › To confirm (owner, 25 Oct 2026: "boil it down to the most simple idea or
abstract, then I can decide if I want to read or ignore it, then I can confirm it")."""

from datetime import UTC, date, datetime

import pytest
from markupsafe import escape
from sqlalchemy import select

from app.models import DataReview
from app.services import digest, inbox, site_guard
from app.web import nav

# every type that has items in the data today (an idea expansion appears once a report has `expanded:`)
WITH_ITEMS = [t for t in digest.TYPES if t != "expansion"]


def _n_open() -> int:
    """All items less the TAM answers already applied (those count as confirmed)."""
    from app.services import tam

    return len(digest.items()) - sum(f"tam:{k}" in digest.by_key() for k in tam.applied())


def test_every_item_type_has_entries_with_short_gists():
    rows = digest.items()
    by_type = {t: [r for r in rows if r["type"] == t] for t in digest.TYPES}
    for t in WITH_ITEMS:
        assert by_type[t], f"no {t} items"
    for r in rows:
        assert r["gist"].strip(), r["key"]
        assert digest.words(r["gist"]) <= digest.MAX_WORDS, (r["key"], r["gist"])
        assert len(r["abstract"]) <= 3 and r["title"] and r["href"].startswith("/"), r["key"]
    assert len({r["key"] for r in rows}) == len(rows)  # keys are unique


def test_written_gists_cover_the_research_items_and_pass_the_site_guard():
    rows = digest.items()
    must = ("report", "case", "background", "review", "idea", "competitor", "risk", "tam", "tam-topic")
    for r in rows:
        if r["type"] in must:
            assert not r["auto"], f"{r['key']} needs a written gist"
            assert len(r["abstract"]) >= 2, r["key"]
        if not r["auto"]:
            text = " ".join([r["gist"], *r["abstract"]])
            assert not site_guard.hits(text), (r["key"], site_guard.hits(text))
    # auto summaries are marked (the daily run rewrites them)
    assert any(r["auto"] for r in rows if r["type"] == "evidence")


def test_expansion_items_come_from_reports_marked_expanded(monkeypatch):
    from app.services import reports as rp

    base = rp.reports()
    r0 = {**base[0], "expanded": "2026-10-26"}
    monkeypatch.setattr(rp, "reports", lambda: (r0, *base[1:]))
    digest._all.cache_clear()
    try:
        x = digest.gist_for("expansion", r0["slug"])
        assert x and x["gist"] and x["href"].endswith("#applications-in-depth") and x["date"] == date(2026, 10, 26)
    finally:
        digest._all.cache_clear()


def test_first_sentence_is_cut_to_25_words():
    s = digest.first_sentence(" ".join(f"w{i}" for i in range(40)) + ". Second.")
    assert digest.words(s) == 25 and s.endswith("…")
    assert digest.first_sentence("<b>One</b> thing. Two things.") == "One thing."


def test_feed_page_and_menu(client):
    assert nav.UTILITY[2][0] == ("To confirm", "/manage/to-confirm",
                                 "Every research item in one sentence: read, confirm or ignore")
    html = client.get("/manage/to-confirm").text
    n = _n_open()
    assert 'class="tc-feed"' in html and "Full text →" in html and ">Confirm</button>" in html
    assert f'data-count="open">{n}<' in html
    assert 'data-to-confirm-count' in client.get("/parts").text  # the count badge on Data management
    # type chips and search narrow the list; nothing is pre-filtered otherwise
    risk = client.get("/manage/to-confirm?type=risk").text
    assert risk.count('class="tc-card"') == sum(r["type"] == "risk" for r in digest.items())
    found = client.get("/manage/to-confirm?q=Novosense").text
    assert "Competitor profile: Novosense" in found and "Automotive GNSS" not in found


def _state(session, key):
    return digest.states(session).get(key, {}).get("state", digest.OPEN)


def test_confirm_ignore_undo_and_comment(client, session):
    key = "case:auto-uwb-cpd"
    r = client.post("/manage/to-confirm/act", data={"key": key, "action": "confirm"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/manage/to-confirm")
    assert _state(session, key) == digest.CONFIRMED
    assert key not in client.get("/manage/to-confirm?type=case").text
    assert key in client.get("/manage/to-confirm?tab=confirmed").text
    client.post("/manage/to-confirm/act", data={"key": key, "action": "undo"})
    assert _state(session, key) == digest.OPEN and key in client.get("/manage/to-confirm?type=case").text
    r = client.post("/manage/to-confirm/act", data={"key": key, "action": "ignore"},
                    headers={"X-Requested-With": "fetch"})  # fmt: skip
    assert r.json()["ok"] and r.json()["open"] == _n_open() - 1
    assert key in client.get("/manage/to-confirm?tab=ignored").text
    assert client.get("/business/reports/auto-uwb-cpd").status_code == 200  # ignored is not deleted
    client.post("/manage/to-confirm/act", data={"key": key, "action": "comment", "comment": "dive deeper on radar"})
    assert _state(session, key) == digest.IGNORED  # a comment does not change the state
    rows = session.scalars(select(DataReview).where(DataReview.dataset == "digest")).all()
    assert [x.verdict for x in rows] == ["confirmed", "open", "ignored", "comment"]  # append-only history
    assert "History (4)" in client.get("/manage/to-confirm?tab=ignored").text
    # bad input changes nothing
    assert client.post("/manage/to-confirm/act", data={"key": "x:y", "action": "confirm"}).status_code == 400
    assert client.post("/manage/to-confirm/act", data={"key": key, "action": "comment"}).status_code == 400
    assert client.post("/manage/to-confirm/act", data={"key": key, "action": "delete"}).status_code == 400


def test_answer_elsewhere_is_shown_and_applied_counts_as_confirmed(client, session):
    session.add(DataReview(dataset="trends", key="pol_ldo", verdict="correct"))
    session.commit()
    html = client.get("/manage/to-confirm?q=Market+trend+LDO").text
    assert "You agree" in html and "on its page" in html  # still in the feed until confirmed here
    applied = client.get("/manage/to-confirm?tab=confirmed&type=tam").text
    assert "applied, so it counts as confirmed" in applied  # tam_applied.yaml entries


def test_inbox_section(client, session):
    client.post("/manage/to-confirm/act", data={"key": "risk:timing-mems", "action": "confirm"})
    client.post("/manage/to-confirm/act", data={"key": "risk:power-poe", "action": "ignore"})
    client.post("/manage/to-confirm/act", data={"key": "risk:uwb-combo", "action": "comment", "comment": "check Apple"})
    text = inbox.collect(session, datetime.now(UTC).date())
    sec = text.split("## To confirm: comments", 1)[1]
    assert "confirmed since then: 1" in sec and "ignored since then: 1" in sec
    assert f"Waiting in the feed: {_n_open() - 2}" in sec
    assert "risk:uwb-combo" in sec and "check Apple" in sec
    reviews = text.split("## Review answers", 1)[1].split("##", 1)[0]
    assert "digest" not in reviews  # not repeated under Review answers
    assert "Nothing new since the last pull." not in text


def test_gist_on_item_pages(client):
    for path, typ, ident in (("/business/reports/auto-hv-hot-swap", "report", "auto-hv-hot-swap"),
                             ("/business/reports/auto-uwb-cpd", "case", "auto-uwb-cpd"),
                             ("/business/reports/auto-uwb-cpd/background", "background", "auto-uwb-cpd"),
                             ("/reviews/qorvo-dw3000-uwb", "review", "qorvo-dw3000-uwb"),
                             ("/business/competitors/sitime", "competitor", "sitime")):  # fmt: skip
        html = client.get(path).text
        g = digest.gist_for(typ, ident)
        assert 'class="gist-box"' in html and str(escape(g["gist"])) in html, path
        first_h2 = html.find("<h2", html.index("<main"))
        assert first_h2 == -1 or html.index('class="gist-box"') < first_h2, path  # before the long text
    risks = client.get("/business/risks").text
    assert str(escape(digest.gist_for("risk", "timing-mems")["gist"])) in risks
    cards = client.get("/business/reports").text
    assert str(escape(digest.gist_for("case", "auto-uwb-cpd")["gist"])) in cards


@pytest.mark.parametrize("method,path", [("get", "/manage/to-confirm"), ("post", "/manage/to-confirm/act")])
def test_guests_never_see_the_feed(method, path, make_guest, session):
    guest, _ = make_guest()
    r = guest.post(path, data={"key": "risk:power-poe", "action": "ignore"}) if method == "post" else guest.get(path)
    assert r.status_code == 403
    assert session.scalar(select(DataReview.id).where(DataReview.dataset == "digest")) is None
    assert "data-to-confirm-count" not in guest.get("/parts").text
