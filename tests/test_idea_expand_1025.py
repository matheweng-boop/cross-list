"""Owner request 25 Oct 2026: "Expand this idea" under each idea on Research & ideas and on the report page, owner
only, asked once; it shows in Site data > Requests (kind idea), the Overview count and the daily inbox, and turns into
"Expanded" with a link once the run has written the "Applications in depth" section."""

from datetime import UTC, date, datetime

from sqlalchemy import select

from app.models import IdeaRequest
from app.services import idea_requests as ir
from app.services import inbox
from app.services import reports as rp

BTN = "Expand this idea"
HINT = "a deeper look at the applications before a business case"


def _slug() -> str:
    return rp.reports()[0]["slug"]


def _ask(c, slug, note="Focus on robotics", back=""):
    return c.post(f"/manage/ideas/{slug}/expand", data={"note": note, "back": back}, follow_redirects=False)


def test_owner_sees_the_button_with_its_hint_and_a_guest_does_not(owner, make_guest):
    slug = _slug()
    for path in ("/business/reports", f"/business/reports/{slug}"):
        html = owner.get(path).text
        assert BTN in html and HINT in html and f'action="/manage/ideas/{slug}/expand"' in html, path
        assert 'class="dict small" hidden' in html  # dictation, shown by the script where the browser has it
    guest, _ = make_guest()
    for path in ("/business/reports", f"/business/reports/{slug}"):
        r = guest.get(path)
        assert r.status_code == 200 and BTN not in r.text and "/manage/ideas/" not in r.text, path
    assert _ask(guest, slug).status_code == 403  # owner only, never captured as guest input


def test_request_is_stored_once_and_the_button_is_replaced(client, session):
    slug = _slug()
    r = _ask(client, slug, back="/business/reports?view=type")
    assert r.status_code == 303 and r.headers["location"] == f"/business/reports?view=type#exp-{slug}"
    row = session.scalar(select(IdeaRequest).where(IdeaRequest.slug == slug))
    assert row.status == "new" and row.note == "Focus on robotics" and row.title == rp.report(slug)["title"]
    today = datetime.now(UTC).strftime("%d %b %Y")
    for path in ("/business/reports", f"/business/reports/{slug}"):
        html = client.get(path).text
        assert f'action="/manage/ideas/{slug}/expand"' not in html, path
        assert f"Expansion requested {today}" in html and "Note: Focus on robotics" in html, path
    assert _ask(client, slug).status_code == 409  # double click or an old tab
    assert len(session.scalars(select(IdeaRequest)).all()) == 1
    assert _ask(client, "no-such-report").status_code == 404


def test_request_in_requests_tab_overview_and_inbox(client, session):
    slug = _slug()
    _ask(client, slug)
    page = client.get("/manage/requests").text
    assert "Idea expansion</span>" in page and rp.report(slug)["title"] in page and "Focus on robotics" in page
    idea = client.get("/manage/requests?kind=idea").text
    assert 'class="fchip on" href="/manage/requests?kind=idea"' in idea and "Idea expansions <small>1</small>" in idea
    ov = client.get("/manage/overview").text
    assert 'href="/manage/requests?kind=idea"><b>1</b><span>idea to expand</span>' in ov
    text = inbox.collect(session, date.today())
    assert "## Idea expansion requests" in text
    line = next(x for x in text.splitlines() if f"] {slug}:" in x)
    assert "[new]" in line and "note: Focus on robotics" in line
    # the status select on the Requests tab marks it done
    rid = session.scalar(select(IdeaRequest.id))
    assert client.post(f"/manage/ideas/requests/{rid}", data={"status": "bogus"}).status_code == 400
    r = client.post(f"/manage/ideas/requests/{rid}", data={"status": "done"}, follow_redirects=False)
    assert r.status_code == 303
    assert "idea to expand" not in client.get("/manage/overview").text


def test_done_request_shows_expanded_with_the_link(client, session):
    slug = _slug()
    _ask(client, slug)
    row = session.scalar(select(IdeaRequest))
    ir.set_status(session, row, "done")
    row.done_at = datetime(2026, 10, 26, 18, 0, tzinfo=UTC)
    session.commit()
    for path in ("/business/reports", f"/business/reports/{slug}"):
        html = client.get(path).text
        assert "Expanded 26 Oct 2026 · see section" in html, path
        assert f'href="/business/reports/{slug}#applications-in-depth"' in html, path
        assert f'action="/manage/ideas/{slug}/expand"' not in html and "Expansion requested" not in html, path


def test_expanded_date_in_reports_yaml_marks_the_request_done(client, session, monkeypatch):
    """The daily run marks a request done in the repository: `expanded: <date>` on the report's entry."""
    slug = _slug()
    _ask(client, slug)
    real = rp.reports
    monkeypatch.setattr(rp, "reports", lambda: tuple({**r, "expanded": date(2026, 10, 26)} if r["slug"] == slug
                                                     else r for r in real()))  # fmt: skip
    assert "Expanded 26 Oct 2026" in client.get(f"/business/reports/{slug}").text
    session.expire_all()
    assert session.scalar(select(IdeaRequest)).status == "done"
    assert ir.open_count(session) == 0
