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
# types that may be empty: idea expansions (none requested yet), open questions (none while all are settled) and
# datasheet families (they come from the owner's Right / Wrong answers, app/services/families.py) and patent changes
# (only when the quarterly patent re-check records a change)
WITH_ITEMS = [t for t in digest.TYPES if t not in ("expansion", "question", "family", "patent-change")]


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
    digest._all.cache_clear(), digest._index.cache_clear()
    try:
        x = digest.gist_for("expansion", r0["slug"])
        assert x and x["gist"] and x["href"].endswith("#applications-in-depth") and x["date"] == date(2026, 10, 26)
    finally:
        digest._all.cache_clear(), digest._index.cache_clear()


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
    html = client.get("/manage/to-confirm?q=Evidence+PoL+LDO").text
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


# ---- evidence: one card per function, patents machine-checked (owner, 26 Oct 2026: "I can't check patents") --------
def _fns() -> set[str]:
    from app.services import opportunity as op

    return {fn for t in digest.EVIDENCE_ASPECTS for fn, e in op.evidence(t).items() if isinstance(e, dict)}


def test_one_evidence_card_per_function_and_no_patent_items():
    rows = [r for r in digest.items() if r["type"] == "evidence"]
    assert len(_fns()) == 69 and len(rows) == 69  # was 5 × 69 + 22 platforms + 7 automotive = 374 items
    assert {r["key"] for r in rows} == {f"evidence:{fn}" for fn in _fns()}
    for r in rows:
        assert digest.words(r["gist"]) <= digest.MAX_WORDS and 1 <= len(r["abstract"]) <= 3, r["key"]
        assert r["abstract"][0].startswith("Path:") and r["abstract"][1].startswith("Manufacturing:"), r["key"]
        assert "competitor technology" in r["abstract"][1] and r["abstract"][2].startswith("Trend:"), r["key"]
    # no patent item is put to the owner: none of the old patent keys, no patent change while nothing changed
    keys = {r["key"] for r in digest.items()}
    assert not any(k.startswith(("evidence:patents/", "evidence:platforms/", "evidence:automotive/")) for k in keys)
    assert not any(r["type"] == "patent-change" for r in digest.items())
    # patents are shown read-only on the card
    ldo = digest.by_key()["evidence:pol_ldo"]
    assert ldo["patents"] == "Patents: strong · checked automatically, 19 Oct 2026; indicative, not reviewed."


def test_evidence_card_in_the_feed_shows_patents_read_only(client):
    html = client.get("/manage/to-confirm?type=evidence").text
    assert html.count('class="tc-card"') == 60  # the first page of 69
    assert "checked automatically, 19 Oct 2026; indicative, not reviewed. Nothing to confirm here." in html
    page = client.get("/business/evidence/pol_ldo").text
    assert str(escape(digest.gist_for("evidence", "pol_ldo")["gist"])) in page


def test_patent_change_item_appears_only_on_change(monkeypatch, client):
    """The quarterly re-check writes a `changed:` block on a patents.yaml entry; only then is there a patent item."""
    real, changes = digest._load, {}

    def load(path):
        d = real(path)
        if path.name == "patents.yaml":
            d = {**d, **{fn: {**d[fn], "changed": ch} for fn, ch in changes.items()}}
        return d

    def items_after(**ch):
        changes.clear(), changes.update(ch)
        digest._all.cache_clear(), digest._index.cache_clear()
        return [r for r in digest.items() if r["type"] == "patent-change"]

    monkeypatch.setattr(digest, "_load", load)
    try:
        got = items_after(pol_ldo={"date": "2027-01-20", "old_depth": "strong", "new_depth": "little",
                                   "note": "Quarterly re-run: 14 families left after a query fix."})  # fmt: skip
        assert [r["key"] for r in got] == ["patent-change:pol_ldo@2027-01-20"]
        assert "strong → little" in got[0]["gist"] and digest.words(got[0]["gist"]) <= digest.MAX_WORDS
        assert got[0]["href"] == "/business/evidence/pol_ldo"
        html = client.get("/manage/to-confirm?type=patent-change").text
        assert html.count('class="tc-card"') == 1 and "Patent change: PoL LDO" in html
        # a failed check with the depth unchanged is a change too
        got = items_after(adc={"date": "2027-01-20", "old_depth": "some", "new_depth": "some",
                               "check": "US12345678B2 no longer resolves"})  # fmt: skip
        assert [r["key"] for r in got] == ["patent-change:adc@2027-01-20"]
        assert "a check failed" in got[0]["gist"] and "no longer resolves" in " ".join(got[0]["abstract"])
        # no `changed:` block, or an empty one: no item
        assert items_after() == [] and items_after(pol_ldo={}) == []
    finally:
        digest._all.cache_clear(), digest._index.cache_clear()


def _old(session, fn, topic, verdict, comment=None):
    session.add(DataReview(dataset="digest", key=f"evidence:{topic}/{fn}", verdict=verdict, comment=comment))
    session.commit()


def test_old_per_aspect_answers_carry_over(client, session):
    """Answers on the old keys ("evidence:path/<fn>" ...) are kept and count for the one card."""
    n0 = digest.open_count(session)
    for t in digest.EVIDENCE_ASPECTS:  # all four old items of the LDO confirmed -> the card counts as confirmed
        _old(session, "pol_ldo", t, "confirmed")
    _old(session, "pol_ldo", "patents", "confirmed")  # an old patent answer changes nothing
    st = digest.states(session)
    assert st["evidence:pol_ldo"]["state"] == digest.CONFIRMED and st["evidence:pol_ldo"]["carried"]
    assert digest.open_count(session) == n0 - 1
    confirmed = client.get("/manage/to-confirm?tab=confirmed&type=evidence").text
    assert 'data-key="evidence:pol_ldo"' in confirmed and "you confirmed all of its old evidence items" in confirmed
    # three of four confirmed and one ignored: still open, the ignored aspect is shown
    fn = sorted(_fns() - {"pol_ldo"})[0]
    for t in ("path", "competitor_tech", "trends"):
        _old(session, fn, t, "confirmed")
    _old(session, fn, "foundry", "ignored")
    _old(session, fn, "trends", "comment", "check the 2027 outlook")
    e = digest.states(session)[f"evidence:{fn}"]
    assert e["state"] == digest.OPEN and e["ignored_aspects"] == ["manufacturing"]
    assert e["comments"][0]["text"].startswith("check the 2027 outlook")
    assert any("(old market trend item)" in h["label"] for h in e["history"])
    html = client.get("/manage/to-confirm?type=evidence&n=100").text
    card = html.split(f'data-key="evidence:{fn}"', 1)[1].split('class="tc-card"', 1)[0]
    assert "You ignored the old manufacturing item" in card and "check the 2027 outlook" in card
    assert "History (5)" in card
    # the card's own answer wins over the carried one; the old rows are never changed or deleted
    client.post("/manage/to-confirm/act", data={"key": "evidence:pol_ldo", "action": "undo"})
    assert digest.states(session)["evidence:pol_ldo"]["state"] == digest.OPEN
    old = session.scalars(select(DataReview).where(DataReview.key.like("evidence:%/%"))).all()
    assert len(old) == 10
