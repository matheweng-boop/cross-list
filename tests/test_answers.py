"""Answers to the Questions to ask (owner, 2 Nov 2026; app/services/answers.py): an answer box under every business-unit
and customer question of a case or research report, with who answered, the date and the owner's sharing switch.
Internal answers reach the owner's own view only: never a guest, a Shareable, an export or the inbox text (a count);
shareable ones go to the inbox in full after the data-protection screen. Edits keep their history; 12 months kept."""

import html
import io
import re
import zipfile
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Answer, AnswerVersion, DataReview, ExternalSubmission
from app.services import answers, prelim
from app.services import reports as rp

CASE, CASE_Q = "auto-uwb-15-4ab", "q-bu-ab"  # a business case and one of its business-unit questions
REPORT, REPORT_Q = "filters-1-11ghz", "q-bu-passband"  # a research report (no case) and one of its questions
WARN = "Don't record confidential figures or plans; summarise instead"


def _add(client, slug, key, text, who="", sharing="internal"):
    data = {"key": key, "text": text, "who": who, "sharing": sharing}
    r = client.post(f"/business/reports/{slug}/answers", data=data, follow_redirects=False)
    assert r.status_code == 303, r.text
    return int(re.search(r"saved=(\d+)", r.headers["location"]).group(1))


def _page(client, slug):
    return html.unescape(client.get(f"/business/reports/{slug}").text)


# ---- the questions ---------------------------------------------------------------------------------------------------
def test_every_report_and_case_lists_its_questions_with_unique_ids():
    """The opener first, then the case's (or questions_to_ask.yaml's) questions; ids unique per report; the file
    names only research reports without a case."""
    for r in rp.reports():
        qs = answers.questions(r["slug"])
        ids = [q["id"] for q in qs]
        assert len(ids) == len(set(ids)), r["slug"]
        assert all(q["text"] and q["group"] in ("bu", "customer") for q in qs), r["slug"]
        if r.get("bu_opener"):
            assert qs[0]["id"] == rp.OPENER_ID and qs[0]["opener"]
    for slug in answers._file():
        assert rp.report(slug) is not None and prelim.raw(slug) is None, slug
    research = [r["slug"] for r in rp.reports() if prelim.raw(r["slug"]) is None]
    assert all(len(answers.questions(s)) > 1 for s in research), "every research report has questions to ask"


# ---- model, form and page --------------------------------------------------------------------------------------
def test_an_answer_is_saved_internal_with_who_and_date(client, session):
    for slug, key in ((CASE, CASE_Q), (REPORT, REPORT_Q), (REPORT, rp.OPENER_ID)):
        page = _page(client, slug)
        box = page.split(f'id="i-{key}"', 1)[1][:3000]
        assert WARN in box and 'name="text"' in box and "<textarea" in box and 'name="who"' in box
        assert "🔒 Internal only" in box and "✅ Can be shared" in box
        assert re.search(r'value="internal"\s+checked', box), "internal is the default"
    aid = _add(client, CASE, CASE_Q, "No 15.4ab project yet.\nAsk again in Q1.", who="UWB BU product line")
    a = session.get(Answer, aid)
    assert (a.sharing, a.who, a.question, a.slug, a.author) == ("internal", "UWB BU product line", CASE_Q, CASE, None)
    assert a.question_text.startswith("Does legacy Qorvo UWB") and a.created_at.date() == datetime.now(UTC).date()
    page = _page(client, CASE)
    assert "No 15.4ab project yet." in page and "UWB BU product line" in page  # the owner sees it all
    assert "Add another answer" in page.split(f'id="i-{CASE_Q}"', 1)[1][:4000]
    # blank or unknown: refused with a page, nothing stored
    n = session.scalar(select(Answer.id).order_by(Answer.id.desc()))
    bad = client.post(f"/business/reports/{CASE}/answers", data={"key": CASE_Q, "text": "  "})
    assert bad.status_code == 400 and "Write the answer first" in bad.text
    assert client.post(f"/business/reports/{CASE}/answers", data={"key": "nope", "text": "x"}).status_code == 404
    assert client.post("/business/reports/nope/answers", data={"key": CASE_Q, "text": "x"}).status_code == 404
    assert client.post(f"/business/reports/{CASE}/answers",
                       data={"key": CASE_Q, "text": "x", "sharing": "public"}).status_code == 400  # fmt: skip
    assert session.scalar(select(Answer.id).order_by(Answer.id.desc())) == n


def test_the_old_answer_button_now_stores_an_internal_answer(client, session):
    r = client.post(f"/business/reports/{REPORT}/react", data={"key": rp.OPENER_ID, "verdict": "answer",
                                                               "comment": "BU likes it", "author": "Boss"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    a = session.scalars(select(Answer).where(Answer.slug == REPORT)).one()
    assert (a.text, a.sharing, a.question) == ("BU likes it", "internal", rp.OPENER_ID)
    assert session.scalar(select(DataReview.id).where(DataReview.dataset == prelim.dataset(REPORT))) is None
    # a question takes an answer only (no agree / reset on it)
    assert client.post(f"/business/reports/{CASE}/react", data={"key": CASE_Q, "verdict": "agree"}).status_code == 400


# ---- the switch and the edit history -------------------------------------------------------------------------------
def test_sharing_switch_and_edit_keep_the_history(client, session):
    aid = _add(client, CASE, CASE_Q, "First words", who="BU")
    back = f"/business/reports/{CASE}#ans-{aid}"
    r = client.post(f"/manage/answers/{aid}/sharing", data={"sharing": "shared", "back": back}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == back
    assert client.post(f"/manage/answers/{aid}/sharing", data={"sharing": "everyone"}).status_code == 400
    assert client.post("/manage/answers/999999/sharing", data={"sharing": "shared"}).status_code == 404
    r = client.post(f"/manage/answers/{aid}/edit", data={"text": "Better words", "who": "BU lead", "back": back},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    session.expire_all()
    a = session.get(Answer, aid)
    assert (a.text, a.who, a.sharing) == ("Better words", "BU lead", "shared")
    old = session.scalars(select(AnswerVersion).where(AnswerVersion.answer_id == aid).order_by(AnswerVersion.id)).all()
    assert [(v.text, v.sharing, v.change) for v in old] == [("First words", "internal", "switched to ✅ Can be shared"),
                                                            ("First words", "shared", "edited")]  # fmt: skip
    # the same text again changes nothing
    client.post(f"/manage/answers/{aid}/edit", data={"text": "Better words", "who": "BU lead"})
    assert len(session.scalars(select(AnswerVersion).where(AnswerVersion.answer_id == aid)).all()) == 2
    card = _page(client, CASE).split(f'id="ans-{aid}"', 1)[1][:5000]
    assert "edited" in card and "Earlier versions (2)" in card and "First words" in card
    assert 'aria-pressed="true">✅ Can be shared' in card
    assert client.post(f"/manage/answers/{aid}/edit", data={"text": ""}).status_code == 400


# ---- the data-protection screen ------------------------------------------------------------------------------------
def test_a_flagged_shareable_answer_is_held_until_released(client, session):
    assert answers.screen("Plain public answer: they use two chips.") == []
    assert "looks like a price or quote" in answers.screen("They pay $0.80 per unit")
    assert any("confidential" in w for w in answers.screen("This is confidential"))
    assert any("e-mail" in w for w in answers.screen("ask jane@example.com"))
    assert answers.screen("A preliminary plan", "")
    aid = _add(client, CASE, CASE_Q, "Confidential: tape-out next spring", sharing="shared")
    a = session.get(Answer, aid)
    assert answers.is_held(a) and not answers.guest_visible(a)
    card = _page(client, CASE).split(f'id="ans-{aid}"', 1)[1][:3000]
    assert "Held for your look" in card and "confidential" in card
    assert client.post(f"/manage/answers/{aid}/release", follow_redirects=False).status_code == 303
    session.expire_all()
    a = session.get(Answer, aid)
    assert not answers.is_held(a) and answers.guest_visible(a)
    client.post(f"/manage/answers/{aid}/edit", data={"text": "Confidential again", "sharing": "shared"})
    session.expire_all()
    assert answers.is_held(session.get(Answer, aid)), "a new text is screened again"


# ---- owner vs guests -------------------------------------------------------------------------------------------------
def test_guests_never_see_internal_or_held_answers(owner, make_guest, session):
    internal = _add(owner, CASE, CASE_Q, "INTERNAL-7731 stays with the owner", who="Secret Person")
    shared = _add(owner, CASE, CASE_Q, "SHARED-4410 may be shared", who="Named Person", sharing="shared")
    held = _add(owner, CASE, "q-bu-mms", "HELD-5521 confidential numbers", sharing="shared")
    assert answers.is_held(session.get(Answer, held))
    owner_page = _page(owner, CASE)
    assert all(t in owner_page for t in ("INTERNAL-7731", "SHARED-4410", "HELD-5521", "Secret Person"))
    guest, _ = make_guest("Anna Guest")
    page = _page(guest, CASE)
    assert "SHARED-4410" in page  # shareable and screened: guests see it, like other owner input
    for hidden in ("INTERNAL-7731", "HELD-5521", "Secret Person", "Named Person", "Earlier versions",
                   f"/manage/answers/{shared}/"):  # fmt: skip
        assert hidden not in page, hidden
    assert "🔒 Internal only" not in page  # no switch for a guest: the owner chooses
    assert guest.get("/manage/answers").status_code == 403
    for action in ("sharing", "edit", "release"):
        assert guest.post(f"/manage/answers/{internal}/{action}", data={"sharing": "shared", "text": "x"}
                          ).status_code == 403  # fmt: skip
    session.expire_all()
    assert session.get(Answer, internal).sharing == "internal"


def test_a_guest_answer_waits_for_review_and_lands_internal(owner, make_guest, session):
    from app.services import guest_input

    guest, _ = make_guest("Anna Guest")
    r = guest.post(f"/business/reports/{REPORT}/answers", data={"key": REPORT_Q, "text": "GUEST-8812 says wider",
                                                                 "who": "Filter BU", "sharing": "shared"},
                   follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and session.scalar(select(Answer.id)) is None
    sub = session.scalars(select(ExternalSubmission)).one()
    assert sub.kind == "Answer to a question to ask"
    assert owner.post(f"/manage/guest-input/{sub.id}", data={"act": "approve"}, follow_redirects=False
                      ).status_code == 303  # fmt: skip
    session.expire_all()
    a = session.scalars(select(Answer)).one()
    assert (a.sharing, a.author, a.text) == ("internal", "Anna Guest", "GUEST-8812 says wider")  # the owner chooses
    lines = "\n".join(guest_input.inbox_lines(session, datetime.now(UTC) - timedelta(days=1)))
    assert "GUEST-8812" not in lines and "kept internal" in lines
    assert "GUEST-8812" not in _page(guest, REPORT) and "GUEST-8812" in _page(owner, REPORT)


# ---- the inbox: a count for internal answers, the full text for shareable ones ---------------------------------------
def test_inbox_counts_internal_answers_and_quotes_shareable_ones(client, session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "inbox_token", "k" * 40)
    _add(client, CASE, CASE_Q, "INTERNAL-1203 do not use")
    _add(client, REPORT, REPORT_Q, "INTERNAL-1204 do not use either", who="Filter BU")
    _add(client, REPORT, "q-bu-standalone", "SHARED-3307 they keep standalone filters", who="Filter BU",
         sharing="shared")  # fmt: skip
    _add(client, CASE, "q-bu-cost", "HELD-9902 costs $1.20 per unit", sharing="shared")
    text = client.get("/api/inbox", headers={"Authorization": "Bearer " + "k" * 40}).text
    section = text.split("## Questions to ask: answers", 1)[1].split("\n## ", 1)[0]
    assert "INTERNAL-1203" not in text and "INTERNAL-1204" not in text
    assert "Internal answers (owner only, the text stays on the site): 2 new, 0 changed" in section
    assert f"{REPORT} / q-bu-standalone (new)" in section and "SHARED-3307 they keep standalone filters" in section
    assert "from: Filter BU" in section
    assert "HELD-9902" not in text and "[held by the data-protection screen: looks like a price or quote" in section
    assert "Nothing new since the last pull." not in text


# ---- never in a Shareable or an export -------------------------------------------------------------------------------
def _texts(resp) -> str:
    """The words of a response, also inside a zipped Office file (xlsx, pptx)."""
    body = resp.content
    if body[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(body)) as z:
            return "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist())
    return html.unescape(body.decode("utf-8", "replace"))


def test_internal_answers_are_in_no_shareable_and_no_export(client, session):
    """Every Shareable page and download, and every text or file export without parameters: the internal answer's
    words are in none of them (the owner's own report page shows them)."""
    _add(client, CASE, CASE_Q, "INTERNAL-6060 owner only", who="WHO-6060")
    _add(client, REPORT, rp.OPENER_ID, "INTERNAL-6061 owner only too")
    assert "INTERNAL-6060" in _page(client, CASE)
    urls = {"/shareable", "/shareable/pack", "/shareable/technology-overview", "/shareable/synergies",
            "/shareable/automotive", "/shareable/presentation", "/business/reports/questions.txt",
            "/manage/feedback/digest.txt", "/business/quality/todo.txt", "/requests.txt",
            "/business/capabilities/feedback.txt", "/blocks/feedback.txt", f"/business/reports/{CASE}/background",
            "/cross-list.xlsx?parts=SR8641"}  # fmt: skip
    for path, ops in client.get("/openapi.json").json()["paths"].items():  # every route, also in included routers
        if "get" in ops and "{" not in path and (
                path.startswith(("/shareable", "/api/")) or re.search(r"\.(txt|xlsx|csv|md|json|pdf|pptx)$", path)):
            urls.add(path)
    assert len(urls) > 20
    seen = 0
    for url in sorted(urls):
        r = client.get(url)
        if r.status_code != 200:
            continue
        seen += 1
        words = _texts(r)
        assert "INTERNAL-606" not in words and "WHO-6060" not in words, url
    assert seen >= 8


# ---- the overview ----------------------------------------------------------------------------------------------------
def test_answers_overview_filters_and_lists_open_questions_first(client, session):
    a1 = _add(client, CASE, CASE_Q, "Overview internal one")
    a2 = _add(client, REPORT, REPORT_Q, "Overview shared one", sharing="shared")
    page = html.unescape(client.get("/manage/answers").text)
    assert page.index("Still open") < page.index("Overview internal one")
    assert f'href="/business/reports/{CASE}#i-{CASE_Q}"' in page and f'href="/business/reports/{REPORT}#i-q-bu-' in page
    assert f"#i-{CASE_Q}" in page.split('id="all-answers"', 1)[1]  # each answer links to its question
    assert f"/business/reports/{CASE}#i-q-bu-mms" in page.split('id="all-answers"', 1)[0]  # still open, linked
    shared = html.unescape(client.get("/manage/answers?sharing=shared").text)
    assert "Overview shared one" in shared and "Overview internal one" not in shared
    internal = html.unescape(client.get("/manage/answers?sharing=internal").text)
    assert "Overview internal one" in internal and "Overview shared one" not in internal
    one = html.unescape(client.get(f"/manage/answers?report={REPORT}").text)
    assert "Overview shared one" in one and "Overview internal one" not in one
    assert f"#i-{CASE_Q}" not in one.split('id="all-answers"', 1)[0]  # open questions of that report only
    assert client.get("/manage/answers?sharing=bogus&report=nope").status_code == 200
    assert {a1, a2} <= {a.id for a in answers.overview(session)["answers"]}


# ---- the move of the old answers and the retention ------------------------------------------------------------------
def test_migration_moves_old_answers_in_as_internal(client, session):
    old = datetime(2026, 10, 25, 9, 30, tzinfo=UTC)
    rows = [DataReview(dataset=prelim.dataset(CASE), key=CASE_Q, verdict="answered", comment="Old case answer",
                       author="Boss", created_at=old),
            DataReview(dataset=prelim.dataset(REPORT), key=rp.OPENER_ID, verdict="answered",
                       comment="Old opener answer", created_at=old),
            DataReview(dataset=prelim.dataset(CASE), key="q-bu-mms", verdict="answered", comment=None, created_at=old),
            DataReview(dataset=prelim.dataset(CASE), key="f-mms-fw", verdict="correct", comment="not a question")]
    session.add_all(rows)
    session.commit()
    assert answers.migrate(session) == 3
    got = {(a.slug, a.question): a for a in session.scalars(select(Answer))}
    a = got[(CASE, CASE_Q)]
    assert (a.text, a.sharing, a.author, a.created_at.replace(tzinfo=UTC)) == ("Old case answer", "internal", "Boss",
                                                                               old)  # fmt: skip
    assert got[(REPORT, rp.OPENER_ID)].text == "Old opener answer" and got[(REPORT, rp.OPENER_ID)].sharing == "internal"
    assert got[(CASE, "q-bu-mms")].text == answers.NO_TEXT
    left = session.scalars(select(DataReview).where(DataReview.dataset.like("case:%"))).all()
    assert [(r.key, r.verdict) for r in left] == [("f-mms-fw", "correct")]  # other reactions stay
    assert answers.migrate(session) == 0 and len(session.scalars(select(Answer)).all()) == 3  # runs once
    assert "Old case answer" not in client.get("/manage/reviews").text  # no longer in the review queue


def test_answers_are_kept_twelve_months_after_their_last_change(session):
    new = answers.add(session, CASE, CASE_Q, "Recent")
    old = answers.add(session, CASE, "q-bu-mms", "Old", when=datetime(2025, 9, 1, tzinfo=UTC))
    answers.set_sharing(session, new.id, "shared")
    old_id, new_id = old.id, new.id
    assert answers.purge(session, today=date(2026, 11, 2)) == 1
    with Session(get_engine()) as s:
        assert s.get(Answer, old_id) is None and s.get(Answer, new_id) is not None
    assert answers.purge(session, today=date(2026, 11, 2)) == 0
    later = datetime.now(UTC).date() + timedelta(days=400)
    assert answers.purge(session, today=later) == 1
    assert session.scalar(select(AnswerVersion.id)) is None  # versions go with it


@pytest.mark.parametrize("slug", [CASE, REPORT])
def test_questions_to_ask_section_heads_the_answer_boxes(client, slug):
    page = _page(client, slug)
    section = page.split('id="questions-to-ask"', 1)[1]
    assert "Start here:" in section and section.count(WARN) == len(answers.questions(slug))
    assert "Answer it under" in page and 'href="#questions-to-ask"' in page
