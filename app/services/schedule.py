"""Scheduled business case reviews (Future growth > Business cases): topics pushed from Research & ideas, from a
preliminary case in the Products walk-through or from the shortlist. A business case is started from this list.

Shared contract: POST /business/schedule with form fields title (required), source (free text, e.g.
"research:<report slug>" or "prelim:<draft id>"), note, part and volume (optional), next (a local path to return
to). The same source (or, without a source, the same title) updates the existing entry instead of adding one."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Case, ScheduledReview

STATUSES = {"scheduled": "Scheduled", "started": "Case started", "done": "Reviewed"}
SOURCE_LABELS = {"research": "Research & ideas", "prelim": "Preliminary case", "shortlist": "Shortlist",
                 "idea": "New ideas"}  # fmt: skip


def _clip(v, n: int) -> str | None:
    return str(v or "").strip()[:n] or None


def find(session: Session, title: str, source: str | None) -> ScheduledReview | None:
    if source:
        return session.scalar(select(ScheduledReview).where(ScheduledReview.source == source))
    same = func.lower(ScheduledReview.title) == title.lower()
    return session.scalar(select(ScheduledReview).where(ScheduledReview.source.is_(None), same))


def schedule(session: Session, title: str, source: str = "", note: str = "", part: str = "",
             volume: str = "") -> ScheduledReview:  # fmt: skip
    """Add the topic, or update the entry with the same source (title, and any note, part or volume given)."""
    title = str(title or "").strip()[:200]
    if not title:
        raise ValueError("title is required")
    src = _clip(source, 120)
    item = find(session, title, src)
    if item is None:
        item = ScheduledReview(title=title, source=src)
        session.add(item)
    item.title = title
    for field, value, n in (("note", note, 4000), ("part", part, 100), ("volume", volume, 60)):
        if _clip(value, n):
            setattr(item, field, _clip(value, n))
    if item.status == "done":  # pushed again after a review: back on the list
        item.status = "scheduled"
    item.updated_at = datetime.now(UTC)
    session.commit()
    return item


def items(session: Session, open_only: bool = False) -> list[ScheduledReview]:
    q = select(ScheduledReview).order_by(ScheduledReview.created_at.desc(), ScheduledReview.id.desc())
    rows = list(session.scalars(q))
    return [r for r in rows if r.status != "done"] if open_only else rows


def by_source(session: Session, prefix: str) -> dict[str, ScheduledReview]:
    """Entries whose source starts with "<prefix>:", by the rest (e.g. research -> {report slug: entry})."""
    q = select(ScheduledReview).where(ScheduledReview.source.like(f"{prefix}:%"))
    return {r.source.split(":", 1)[1]: r for r in session.scalars(q)}


def source_label(source: str | None) -> str:
    kind = (source or "").split(":", 1)[0]
    return SOURCE_LABELS.get(kind, source or "Added by hand")


def source_link(source: str | None) -> str | None:
    kind, _, rest = (source or "").partition(":")
    if kind == "research" and rest:
        return f"/business/reports/{rest}"
    return None


def link_case(session: Session, item_id: int, case: Case) -> None:
    item = session.get(ScheduledReview, item_id)
    if item is not None:
        item.case_id, item.status = case.id, "started"


def unlink_case(session: Session, case_id: int) -> None:
    for it in session.scalars(select(ScheduledReview).where(ScheduledReview.case_id == case_id)):
        it.case_id, it.status = None, "scheduled"
