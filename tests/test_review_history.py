"""Review history (owner, 25 Oct 2026: "Keep a history of the last 5 review answers") and the lock on TAM answers
already worked into a report (owner, 25 Oct 2026)."""

import re
from datetime import UTC, datetime, timedelta

import pytest

from app.config import get_settings
from app.models import DataReview
from app.services import review_history as rh
from app.services import tam
from tests.test_browser import overflow, page  # noqa: F401  (the browser fixture)

T0 = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)


def _answers(session, dataset, key, verdicts, author="Mat"):
    for i, v in enumerate(verdicts):
        session.add(DataReview(dataset=dataset, key=key, verdict=v, comment=f"answer {i}", author=author,
                               created_at=T0 + timedelta(days=i)))  # fmt: skip
    session.commit()


def _open_key() -> str:
    return next(e["key"] for e in tam.researched() if e["key"] not in tam.applied())


def test_helper_returns_at_most_five_newest_first(session):
    _answers(session, "path", "tvs_esd", ["correct", "wrong", "unsure", "correct", "wrong", "correct", "wrong"])
    rows = rh.history(session, "path", "tvs_esd")
    assert len(rows) == 5
    assert [r["comment"] for r in rows] == ["answer 6", "answer 5", "answer 4", "answer 3", "answer 2"]
    assert rows[0]["label"] == "disagree" and rows[1]["label"] == "agree"
    assert rh.history(session, "path", "nothing") == []
    assert rh.label("price", "ok") == "in the band" and rh.label("case:radio-tuner-next", "closer") == "move closer"


def test_tam_item_with_six_answers_shows_five_earlier_and_newest_counts(client, session):
    key = _open_key()
    _answers(session, "tam", key, ["wrong", "wrong", "wrong", "wrong", "wrong", "correct"])
    assert {e["key"]: e for e in tam.estimates(session)}[key]["review"]["verdict"] == "agree"  # newest = current
    html = client.get("/business/tam").text
    card = html[html.index(f'id="t-{key}"') :]
    card = card[: card.index("</article>")]
    assert "you agree" in card and "History (5)" in card
    assert card.count("<li>") == 5 and "answer 0" in card and "answer 5" not in card.split("History (5)")[1]
    assert "23 Oct 2026" in card or "22 Oct 2026" in card  # date as "24 Oct 2026"
    assert 'name="answer" value="agree"' in card  # not applied: still answerable


def test_by_function_ignores_disagreed_figures_by_the_newest_verdict(client, session, monkeypatch):
    monkeypatch.setattr(tam, "applied", lambda: {})
    _answers(session, "tam", "tuner-ic-mrfr", ["correct", "wrong"])
    assert tam.by_function(session)["am_fm_tuner"]["high"] < 2.31e9  # newest is disagree: dropped
    session.add(DataReview(dataset="tam", key="tuner-ic-mrfr", verdict="correct", created_at=T0 + timedelta(days=9)))
    session.commit()
    assert tam.by_function(session)["am_fm_tuner"]["high"] == 2.31e9  # changed mind: counts again


def test_inbox_notes_earlier_answers(client, session, monkeypatch):
    monkeypatch.setattr(get_settings(), "inbox_token", "k" * 40)
    now = datetime.now(UTC)
    session.add(DataReview(dataset="trends", key="efuse_hotswap", verdict="correct", comment="consensus on CAGR",
                           created_at=now - timedelta(days=30)))  # fmt: skip
    session.add(DataReview(dataset="trends", key="efuse_hotswap", verdict="unsure",
                           created_at=now - timedelta(days=20)))  # fmt: skip
    session.add(DataReview(dataset="trends", key="efuse_hotswap", verdict="wrong", comment="changed my mind",
                           created_at=now))  # fmt: skip
    session.commit()
    text = client.get("/api/inbox", headers={"Authorization": "Bearer " + "k" * 40}).text
    line = text[text.index("trends / efuse_hotswap: wrong · changed my mind") :]
    note = line.splitlines()[1]
    assert note.strip().startswith("earlier: ") and "unsure" in note and "agree · 'consensus on CAGR'" in note
    assert note.index("unsure") < note.index("agree")  # newest earlier answer first


def test_guest_sees_no_authors_and_no_owner_only_comments(session, make_guest):
    _answers(session, "path", "tvs_esd", ["correct", "wrong"], author="Owner Name")
    guest, _ = make_guest()
    html = guest.get("/business/evidence/tvs_esd").text
    assert "History (2)" in html and "answer 1" in html and "Owner Name" not in html
    rows = rh.history(session, "path", "tvs_esd")
    assert rh.for_viewer(rows, "tam", guest=True)[0]["comment"] == ""  # owner-only dataset: no comments
    assert rh.for_viewer(rows, "tam", guest=False)[0]["author"] == "Owner Name"
    assert guest.get("/business/tam", follow_redirects=False).status_code in (302, 303, 403, 404)


def test_owner_sees_authors(session, owner):
    _answers(session, "path", "tvs_esd", ["correct"], author="Owner Name")
    assert "Owner Name" in owner.get("/business/evidence/tvs_esd").text


def test_long_comments_are_cut_with_more(client, session):
    session.add(DataReview(dataset="path", key="tvs_esd", verdict="correct", comment="x " * 80))
    session.commit()
    html = client.get("/business/evidence/tvs_esd").text
    assert '<details class="rh-more"><summary>more</summary>' in html


# ---- applied TAM answers are locked -------------------------------------------------------------------------------
def test_applied_record_matches_the_22_oct_work():
    a = tam.applied()
    assert {"tuner-ic-datahorizzon", "tuner-ic-mrfr", "digital-radio-tuner-marketintelo", "tuner-ic-emergen"} <= set(a)
    assert {"current-sensor-mm", "cpd-system-ksm", "auto-wifi-modules"} <= set(a)  # owner confirmed, 25 Oct 2026
    assert a["tuner-ic-emergen"]["verdict"] == "disagree"
    case = {"label": "radio-tuner-next", "href": "/business/reports/radio-tuner-next"}
    assert case in a["tuner-ic-mrfr"]["applied_in"]
    known = {e["key"] for e in tam.researched()}
    assert set(a) <= known


def test_applied_item_has_no_buttons_and_refuses_a_new_verdict(client, session):
    _answers(session, "tam", "tuner-ic-mrfr", ["unsure", "correct"])
    html = client.get("/business/tam").text
    card = html[html.index('id="t-tuner-ic-mrfr"') :]
    card = card[: card.index("</article>")]
    assert 'name="answer"' not in card and "Applied 22 Oct 2026" in card
    assert 'href="/business/reports/radio-tuner-next"' in card and "History (1)" in card
    n = session.query(DataReview).count()
    r = client.post("/business/tam/review", data={"key": "tuner-ic-mrfr", "answer": "disagree"}, follow_redirects=False)
    assert r.status_code == 409 and "already worked into a report" in r.text
    r = client.post("/business/quality/answer", data={"dataset": "tam", "key": "tuner-ic-mrfr", "comment": "no"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 409
    assert session.query(DataReview).count() == n
    # an unapplied item still takes answers
    key = _open_key()
    assert client.post("/business/tam/review", data={"key": key, "answer": "agree"},
                       follow_redirects=False).status_code == 303  # fmt: skip
    assert re.search(rf'id="t-{re.escape(key)}"[\s\S]*?name="answer" value="agree"', client.get("/business/tam").text)


def test_history_shows_on_case_library_and_review_boxes(client, session):
    from app.services import library, prelim
    from app.services import reviews as rv

    item = "t-ref"
    assert item in prelim.item_ids("radio-tuner-next")
    prelim.react(session, "radio-tuner-next", item, "disagree", "first thought")
    prelim.react(session, "radio-tuner-next", item, "agree", "second thought")
    html = client.get("/business/reports/radio-tuner-next").text
    box = html[html.index(f'id="i-{item}"') :]
    assert "History (1)" in box[: box.index("</form>")] and "first thought" in box

    key = next(t["key"] for t in library.topics() if library.item_ids(t["key"]))
    lit = sorted(library.item_ids(key))[0]
    library.react(session, key, lit, "agree", "lib one")
    library.react(session, key, lit, "disagree", "lib two")
    assert "History (1)" in client.get(f"/library/{key}").text

    r = rv.all_reviews()[0]
    rk = sorted(rv.item_keys(r))[0]
    rv.react(session, r["slug"], rk, "agree", "rv one")
    rv.react(session, r["slug"], rk, "disagree", "rv two")
    assert "History (1)" in client.get(f"/reviews/{r['slug']}").text


@pytest.mark.browser
def test_history_opens_without_overflow_on_a_phone(page):  # noqa: F811
    """Answers posted in the browser show as "History (n)"; opened, with a long comment and "more", the TAM page stays
    within 390 px (the page fixture re-opens every visited page at 390 px too)."""
    key = _open_key()
    long = "a long comment about coverage and the forecast years that keeps going " * 4
    for answer, comment in (("disagree", long), ("disagree", "short"), ("agree", "now fine")):
        r = page.request.post("/business/tam/review", form={"key": key, "answer": answer, "comment": comment})
        assert r.ok
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"/business/tam#t-{key}")
    card = page.locator(f"#t-{key}")
    card.locator(".rv-hist > summary").click()
    card.locator(".rh-more > summary").first.click()
    assert card.locator(".rv-hist li").count() >= 2
    assert overflow(page) <= 1
