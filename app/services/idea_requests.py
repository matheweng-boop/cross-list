""""Expand this idea" requests on Research & ideas (owner, 25 Oct 2026): one per report, owner only. The daily run
adds an "Applications in depth" section to the report (docs/daily_update.md) and marks the request done: either on
Data management > Site data > Requests, or in the repository with `expanded: <date>` on the report's entry in
data/business/reports.yaml (applied to the request the next time it is read, see sync)."""

from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import IdeaRequest

STATUSES = {"new": "Requested", "done": "Expanded", "declined": "Declined"}
OPEN = ("new",)
ANCHOR = "applications-in-depth"  # id of the section the run adds to the report body


class AlreadyRequested(Exception):
    pass


def sync(session: Session) -> None:
    """Open requests whose report carries `expanded: <date>` in reports.yaml become done on that date."""
    from app.services import reports as rp

    rows = session.scalars(select(IdeaRequest).where(IdeaRequest.status.in_(OPEN))).all()
    if not rows:
        return
    done = {r["slug"]: r["expanded"] for r in rp.reports() if r.get("expanded")}
    changed = False
    for row in rows:
        day = done.get(row.slug)
        if day:
            try:
                day = day if isinstance(day, date) else date.fromisoformat(str(day))
            except ValueError:
                continue
            row.status, row.done_at, changed = "done", datetime.combine(day, time(12), UTC), True
    if changed:
        session.commit()


def by_slug(session: Session) -> dict[str, IdeaRequest]:
    sync(session)
    return {r.slug: r for r in session.scalars(select(IdeaRequest))}


def get(session: Session, slug: str) -> IdeaRequest | None:
    sync(session)
    return session.scalar(select(IdeaRequest).where(IdeaRequest.slug == slug))


def add(session: Session, slug: str, title: str, note: str = "") -> IdeaRequest:
    """Store the request; AlreadyRequested when this report has one (any status), so it is asked once only."""
    if get(session, slug) is not None:
        raise AlreadyRequested(slug)
    row = IdeaRequest(slug=slug, title=title[:300], note=note.strip()[:2000] or None)
    session.add(row)
    try:
        session.commit()
    except IntegrityError:  # two submits at once
        session.rollback()
        raise AlreadyRequested(slug) from None
    return row


def set_status(session: Session, row: IdeaRequest, status: str) -> None:
    if status not in STATUSES:
        raise ValueError(status)
    row.status = status
    row.done_at = datetime.now(UTC) if status == "done" else None
    session.commit()


def open_count(session: Session) -> int:
    sync(session)
    return sum(1 for r in session.scalars(select(IdeaRequest)) if r.status in OPEN)
