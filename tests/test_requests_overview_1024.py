"""Owner request 24 Oct 2026: the Overview opens with a "Waiting for you" to-do list, and Site data has one Requests tab
for part requests, diagram feedback and area requests (5 tabs instead of 7)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import AreaRequest, BlockFeedback, CrossRequest
from app.web import nav


def _seed(session):
    t = datetime.now(UTC)
    session.add_all([CrossRequest(mpn="ZQ1234", note="for customer A", created_at=t - timedelta(hours=3)),
                     CrossRequest(mpn="ZQ9999", status="done", created_at=t - timedelta(hours=4)),
                     BlockFeedback(message="Add a boost stage", diagram_name="Inverter", target="Gate driver",
                                   created_at=t - timedelta(hours=2)),
                     AreaRequest(area="Robotics", why="Humanoid robots", created_at=t - timedelta(hours=1))])
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
    assert r.status_code == 303
    r = client.post(f"/blocks/area-requests/{area.id}", data={"status": "planned"}, follow_redirects=False)
    assert r.status_code == 303
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
