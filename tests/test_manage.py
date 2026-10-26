"""Data management: the Overview, Site data (Verify next, Requests), TAM review, the feedback window and the
methodology page."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import (
    AreaRequest,
    BlockFeedback,
    CrossRequest,
    DataReview,
    FeedbackAttachment,
    TamEstimate,
    Upload,
    VerifyTask,
)
from app.services import quality, tam
from app.web import nav

# ---- from tests/test_fb1021_manage.py --------------------------------------------------------------------------------
# Data management, owner feedback 21 Oct: TAM estimates instead of Commercial inputs, a file in the Feedback window,
# the Verify next pop-up, yes / no review questions, the compact Overview and the public-sources statement.

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# ---- 1. TAM estimates ------------------------------------------------------------------------------------------
def test_tam_examples_come_with_sources_and_are_labelled():
    rows = tam.researched()
    assert len(rows) >= 5 and len({e["key"] for e in rows}) == len(rows)
    for e in rows:
        assert e["value"] and e["year"] and e["source"]["publisher"] and e["quality"] and e["example"]
        assert not e["source"]["url"] or e["source"]["url"].startswith("https://")


def test_tam_page_review_and_add(client, session):
    labels = [i[0] for i in dict((k, v) for k, _, v in nav.NAV)["growth"]]  # owner, 23 Oct 2026: Future growth
    assert "TAM estimates" in labels and "Commercial inputs" not in labels
    r = client.get("/business/data", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/business/tam"
    html = client.get("/business/tam").text
    assert "TAM estimates" in html and "Market Research Future" in html and "example from research notes" in html
    assert "Source quality" in html and 'aria-current="page"' in html
    # a single estimate (members of a combined topic are no longer separate review items; owner, 25 Oct 2026)
    key = next(e["key"] for e in tam.researched() if e["fn"] != "am_fm_tuner"
               and e["key"] not in tam.applied())  # applied ones are locked
    r = client.post("/business/tam/review", data={"key": key, "answer": "disagree", "comment": "counts modules"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    row = session.scalar(select(DataReview).where(DataReview.dataset == "tam", DataReview.key == key))
    assert row.verdict == "wrong" and row.comment == "counts modules"
    assert "you disagree" in client.get("/business/tam").text
    assert client.post("/business/tam/review", data={"key": "nope", "answer": "agree"}).status_code == 400
    # add one: nothing is estimated, the dollar value is only read from the text
    assert "error=" in client.post("/business/tam", data={"product": "X"}, follow_redirects=False).headers["location"]
    client.post("/business/tam", data={"product": "Automotive UWB front ends", "value": "$420 M", "year": "2025",
                                       "region": "Global", "source_publisher": "Example Research",
                                       "source_url": "javascript:alert(1)", "quality": "press release"})  # fmt: skip
    t = session.scalar(select(TamEstimate))
    assert t.usd == 420e6 and t.year == 2025 and t.source_url is None
    assert "Automotive UWB front ends" in client.get("/business/tam").text
    assert tam.parse_usd("$1.4 B") == 1.4e9 and tam.parse_usd("$400–500 M") == 400e6 and tam.parse_usd("n/a") is None


# ---- 2. a file in the Feedback window ---------------------------------------------------------------------------
def test_feedback_with_a_file(client, session, tmp_uploads):
    assert 'name="file"' in client.get("/").text  # the Feedback window has the file field on every page
    sent = {"text": "This diagram is wrong", "path": "/blocks", "client": "abc"}
    fid = client.post("/site-feedback", json=sent).json()["id"]
    files = {"file": ("shot.png", PNG, "image/png")}
    assert client.post(f"/site-feedback/{fid}/file", data={"client": "other"}, files=files).status_code == 404
    bad = client.post(f"/site-feedback/{fid}/file", data={"client": "abc"}, files={"file": ("x.svg", b"<svg>", "x")})
    assert bad.status_code == 400 and "PNG" in bad.json()["detail"]
    r = client.post(f"/site-feedback/{fid}/file", data={"client": "abc"}, files=files)
    assert r.status_code == 200 and r.json()["ok"]
    link = session.scalar(select(FeedbackAttachment).where(FeedbackAttachment.feedback_id == fid))
    u = session.get(Upload, link.upload_id)
    assert u.content_type == "image/png" and u.original_name == "shot.png" and (tmp_uploads / u.file_name).exists()
    digest = client.get("/manage/feedback").text
    assert "Attached:" in digest and f"/manage/uploads/{u.id}/file" in digest
    assert client.get(f"/manage/uploads/{u.id}/file").content == PNG
    assert "Feedback: This diagram is wrong" in client.get("/manage/uploads").text  # the Uploads page still lists it


# ---- 3. Verify next: comparison and answer in one pop-up --------------------------------------------------------
def test_verify_cross_popup(client, session, real):
    html = client.get("/manage/verify").text
    crosses = session.scalars(select(VerifyTask).where(VerifyTask.kind == "cross", VerifyTask.status == "open")).all()
    assert crosses
    t = crosses[0]
    assert f'<dialog class="vd" id="vd-{t.id}"' in html and f'data-dialog="vd-{t.id}"' in html
    dialog = html.split(f'id="vd-{t.id}"', 1)[1].split("</dialog>", 1)[0]
    assert "vd-spec" in dialog and "vd-side" in dialog and "compare-table" in dialog
    assert f'action="/manage/verify/{t.id}"' in dialog and 'name="note"' in dialog


# ---- 4. review queue as yes / no questions ----------------------------------------------------------------------
def test_questions_are_specific_yes_no(client, session):
    html = client.get("/business/quality").text
    assert 'id="questions"' in html and "Questions for you" in html
    queue = html.split('id="questions"', 1)[1].split('id="research"', 1)[0]
    assert "confidence" not in queue.lower() and ">Submit<" in queue and 'name="comment"' in queue
    assert ">Yes<" not in queue and ">No<" not in queue  # owner, 25 Oct 2026: a comment, no yes / no
    assert "Review status per dataset" not in html
    from app.services import opportunity as op

    apps = op.with_status(op.applications(), op.makers(session), op.company("combined")[2])
    qs = quality.questions(session, apps)
    assert qs and all(q["question"].endswith("?") and q["check"] for q in qs)
    assert any(q["dataset"] == "tam" and "Does " in q["question"] for q in qs)
    comp = quality.ask("competition", "pol_ldo", "PoL LDO", {"vendors": ["TI", "ADI"]})
    assert comp["question"] == "Do these companies sell a PoL LDO today: TI, ADI?"
    entry = {"outlook": "growing", "note": "EVs", "check": {"evidence": ["https://x.org/a - page"]}}
    trend = quality.ask("trends", "gate_driver", "Gate driver", entry)
    assert "gate driver" in trend["question"] and trend["links"] == [("x.org", "https://x.org/a")]
    assert "Open the source" in trend["check"]
    # answering: a comment becomes a review row of the item (being checked by the daily run)
    q = next(q for q in qs if q["dataset"] != "tam")
    answer = {"dataset": q["dataset"], "key": q["key"], "comment": "one more supplier"}
    r = client.post("/business/quality/answer", data=answer, follow_redirects=False)
    assert r.status_code == 303 and f"#q-{q['dataset']}-{q['key']}" in r.headers["location"]
    row = session.scalar(select(DataReview).where(DataReview.dataset == q["dataset"], DataReview.key == q["key"]))
    assert row.verdict == "comment" and row.comment == "one more supplier"
    unknown = {"dataset": "x", "key": "y", "comment": "hm"}
    assert client.post("/business/quality/answer", data=unknown).status_code == 400


# ---- 5. compact overview at the front of Data management --------------------------------------------------------
def test_overview_first_in_data_management(client):
    # owner, 25 Oct 2026: To confirm (every research item as one sentence) is first; the Overview follows it
    assert [i[1] for i in nav.UTILITY[2][:2]] == ["/manage/to-confirm", "/manage/overview"]
    html = client.get("/manage/overview").text
    assert 'class="ov-table"' in html and "TAM estimates" in html and "Technology rating" in html
    assert "open in Verify next" in html and 'aria-current="page"' in html
    assert '<a href="/manage/to-confirm" class="utility' in client.get("/").text  # the Data management link


# ---- 6. methodology: public sources and polite collection -------------------------------------------------------
def test_method_states_public_sources(client):
    html = client.get("/business/method").text
    head = html.split('id="public"', 1)[1][:1500]
    assert "public sources" in head and "No confidential company data" in head
    assert "robots.txt" in head and "one request at a time" in head and "never logs in" in head


# ---- from tests/test_requests_overview_1024.py -----------------------------------------------------------------------
# Owner request 24 Oct 2026: the Overview opens with a "Waiting for you" to-do list, and Site data has one Requests tab
# for part requests, diagram feedback and area requests (5 tabs instead of 7).


def _seed(session):
    t = datetime.now(UTC)
    session.add_all(
        [
            CrossRequest(mpn="ZQ1234", note="for customer A", created_at=t - timedelta(hours=3)),
            CrossRequest(mpn="ZQ9999", status="done", created_at=t - timedelta(hours=4)),
            BlockFeedback(
                message="Add a boost stage",
                diagram_name="Inverter",
                target="Gate driver",
                created_at=t - timedelta(hours=2),
            ),
            AreaRequest(area="Robotics", why="Humanoid robots", created_at=t - timedelta(hours=1)),
        ]
    )
    session.commit()


# ---- Requests tab ---------------------------------------------------------------------------------------------------
def test_site_data_has_five_tabs_and_requests_is_highlighted(client):
    tabs = next(g for g in nav.TABS if g[0][1] == "/manage/verify")
    assert [lbl for lbl, _ in tabs] == ["Verify next", "Review queue", "Requests", "Site feedback", "Guest input"]
    for path in ("/manage/requests", "/requests", "/blocks/feedback", "/blocks/area-requests"):
        st = nav.state(path)
        assert st["section"] == "manage" and st["item"] == "/manage/verify", path
    assert nav.state("/manage/requests")["active_tab"] == "/manage/requests"
    page = client.get("/manage/requests").text
    for label in ("Requests", "Site data"):  # the tab and the menu item
        assert f'aria-current="page" class="on">{label}<' in page
    assert nav.page_title("/manage/requests").startswith("Requests – Data management")


def test_requests_lists_all_three_kinds_newest_first_and_filters(client, session):
    _seed(session)
    html = client.get("/manage/requests").text
    for text in ("ZQ1234</b>", "for customer A", "Add a boost stage", "Gate driver", "Robotics", "Humanoid robots"):
        assert text in html, text
    for label in ("Part request</span>", "Diagram feedback</span>", "Area request</span>"):
        assert label in html
    assert "ZQ9999" not in html  # done: only with "Open and closed"
    assert html.index("Robotics") < html.index("Add a boost stage") < html.index("ZQ1234</b>")  # newest first
    part = client.get("/manage/requests?kind=part").text
    assert "ZQ1234</b>" in part and "Robotics" not in part and "Add a boost stage" not in part
    assert 'class="fchip on" href="/manage/requests?kind=part"' in part
    assert "Add a boost stage" in client.get("/manage/requests?kind=diagram").text
    area = client.get("/manage/requests?kind=area").text
    assert "Robotics" in area and "ZQ1234</b>" not in area
    every = client.get("/manage/requests?kind=part&show=all").text
    assert "ZQ9999" in every and "ZQ1234" in every
    assert client.get("/manage/requests?kind=nonsense").status_code == 200  # unknown kind: all


def test_requests_actions_post_to_their_own_handlers(client, session):
    _seed(session)
    req = session.scalar(select(CrossRequest).where(CrossRequest.mpn == "ZQ1234"))
    fb = session.scalar(select(BlockFeedback))
    area = session.scalar(select(AreaRequest))
    html = client.get("/manage/requests").text
    assert f'action="/requests/{req.id}"' in html and f'action="/blocks/area-requests/{area.id}"' in html
    form = html.split(f'action="/blocks/feedback/{fb.id}" class="fb-del"', 1)[1].split("</form>", 1)[0]
    assert 'data-confirm="Delete this diagram feedback for good?"' in form and 'name="delete"' in form
    assert 'data-confirm="Delete the request for ZQ1234?"' in html and "confirm(f.dataset.confirm)" in html
    assert 'action="/requests" class="request-form"' in html  # adding part requests still works here

    r = client.post(f"/requests/{req.id}", data={"status": "in_progress"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/manage/requests?kind=part"  # one hop
    r = client.post(f"/blocks/area-requests/{area.id}", data={"status": "planned"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/manage/requests?kind=area"
    r = client.post(f"/blocks/feedback/{fb.id}", data={"status": "agreed"})  # follows to the Requests tab
    assert r.status_code == 200 and "/manage/requests?kind=diagram" in str(r.url)
    session.expire_all()
    assert (req.status, area.status, fb.status) == ("in_progress", "planned", "agreed")
    assert client.post(f"/blocks/feedback/{fb.id}", data={"delete": "1"}).status_code == 200
    assert "Add a boost stage" not in client.get("/manage/requests").text
    r = client.post("/requests", data={"mpns": "ZQ7777", "back": "/manage/requests?kind=part"}, follow_redirects=False)
    assert r.headers["location"] == "/manage/requests?kind=part"


@pytest.mark.parametrize("old,kind", [("/requests", "part"), ("/blocks/feedback", "diagram"),
                                      ("/blocks/area-requests", "area")])  # fmt: skip
def test_old_request_urls_redirect_to_the_requests_tab(client, old, kind):
    r = client.get(old, follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == f"/manage/requests?kind={kind}"
    assert client.get(old).status_code == 200


def test_requests_tab_is_owner_only(make_guest):
    guest, _ = make_guest()
    for path in ("/manage/requests", "/manage/requests?kind=part", "/requests", "/blocks/feedback"):
        assert guest.get(path, follow_redirects=False).status_code == 403, path


# ---- Overview: Waiting for you --------------------------------------------------------------------------------------
ZERO = {"part_requests": 0, "diagram_feedback": 0, "area_requests": 0, "feedback": 0, "guest": 0,
        "review_requests": 0, "uploads": 0}  # fmt: skip


def test_todo_lines_counts_links_and_zero_lines_hidden(session, monkeypatch):
    from app.services import maintenance, runs
    from app.web.verify import todo

    monkeypatch.setattr(runs, "open_questions", lambda: [])
    monkeypatch.setattr(maintenance, "items", lambda s: [])
    assert todo(session, ZERO, {}, 0) == []
    lines = todo(session, ZERO | {"part_requests": 1, "guest": 3}, {"sources": 2, "cross": 3, "data": 0}, 1)
    assert lines == [(2, "sources to check", "/manage/verify#sources"),
                     (3, "crosses to verify", "/manage/verify#cross"),
                     (1, "part request", "/manage/requests?kind=part"),
                     (3, "guest inputs to review", "/manage/guest-input"),
                     (1, "TAM figure to review", "/business/tam")]  # fmt: skip
    monkeypatch.setattr(runs, "open_questions", lambda: ["A", "B"])
    monkeypatch.setattr(maintenance, "items", lambda s: [{"type": "evidence", "status": "open"},
                                                          {"type": "evidence", "status": "confirmed"},
                                                          {"type": "missing_product", "status": "open"}])  # fmt: skip
    lines = todo(session, ZERO | {"diagram_feedback": 2, "area_requests": 1}, {}, 0)
    assert (2, "diagram feedback items to review", "/manage/requests?kind=diagram") in lines
    assert (1, "new area request", "/manage/requests?kind=area") in lines
    assert (1, "review queue item", "/manage/reviews?status=open") in lines  # requests have their own line
    assert (2, "open questions for you", "/manage/feedback#questions") in lines


def test_overview_shows_waiting_for_you_first(client, session):
    _seed(session)
    html = client.get("/manage/overview").text
    assert html.index("Waiting for you") < html.index("Today and at a glance") < html.index("Raw data")
    todo = html.split('id="ov-todo"', 1)[1].split("</ul>", 1)[0]
    assert '<a href="/manage/requests?kind=part"><b>1</b><span>part request</span></a>' in todo
    assert '<a href="/manage/requests?kind=diagram"><b>1</b><span>diagram feedback to review</span></a>' in todo
    assert '<a href="/manage/requests?kind=area"><b>1</b><span>new area request</span></a>' in todo
    assert "<b>0</b>" not in todo and "/manage/guest-input" not in todo  # nothing pending: no line
    assert "open part requests" in html and "Skyworks and Qorvo parts" in html  # the earlier content stays


def test_overview_says_nothing_waiting(client, monkeypatch):
    import app.web.verify as v

    monkeypatch.setattr(v, "todo", lambda *a: [])
    html = client.get("/manage/overview").text
    assert "Nothing waiting." in html and 'id="ov-todo"' not in html


def test_guest_never_sees_the_overview_or_its_lines(make_guest, owner, session):
    _seed(session)
    guest, _ = make_guest()
    assert guest.get("/manage/overview", follow_redirects=False).status_code == 403
    page = guest.get("/parts").text
    assert "Waiting for you" not in page and 'href="/manage/overview"' not in page
    assert "Waiting for you" in owner.get("/manage/overview").text
