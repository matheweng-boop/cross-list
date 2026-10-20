"""Pre-lim product ideas and reports: a list (data/business/reports.yaml), each with a body template, an optional
background template (<slug>.background.html: the detail behind the report) and questions asked on its page."""

from datetime import UTC, date, datetime, timedelta
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import ReportQuestion
from app.services.feedback import similar_text

FILE = PROJECT_ROOT / "data" / "business" / "reports.yaml"
BODIES = PROJECT_ROOT / "app" / "web" / "templates" / "business" / "reports"
KINDS = {"report": "Report", "idea": "Product idea"}
STATUSES = {"draft": "Draft, not reviewed", "reviewed": "Reviewed", "archived": "Archived"}
FEASIBILITY = {  # product ideas: how far from today's portfolio (0 = not scored, e.g. a report)
    1: ("Close to the portfolio", "Firmware, packaging or existing dies"),
    2: ("In between", "A new chip from technology we already have"),
    3: ("Out of the box", "New technology or a market nobody plays in yet"),
}


@lru_cache
def reports() -> tuple[dict, ...]:
    rows = (yamlio.load(FILE.read_text()) or {}).get("reports") or [] if FILE.exists() else []
    rows = [{**r, "app_type": r.get("app_type") or "Other", "feasibility": int(r.get("feasibility") or 0)}
            for r in rows if (BODIES / f"{r['slug']}.html").exists()]  # fmt: skip
    return tuple(sorted(rows, key=lambda r: str(r.get("date") or ""), reverse=True))


def report(slug: str) -> dict | None:
    return next((r for r in reports() if r["slug"] == slug), None)


def has_background(slug: str) -> bool:
    return (BODIES / f"{slug}.background.html").exists()


# --- questions asked on a report, reviewed once a day ---------------------------------------------------------------

Q_STATUSES = {"new": "Waiting for review", "good": "Good question", "duplicate": "Duplicate", "dropped": "Set aside"}


def ask(session: Session, slug: str, text: str, author: str = "") -> ReportQuestion:
    q = ReportQuestion(slug=slug, text=text.strip()[:2000], author=author.strip()[:100] or None)
    session.add(q)
    session.commit()
    return q


def questions(session: Session, slug: str) -> list[ReportQuestion]:
    """Questions shown under a report: everything except set-aside ones, answered first."""
    rows = session.scalars(select(ReportQuestion).where(ReportQuestion.slug == slug, ReportQuestion.status != "dropped")
                           .order_by(ReportQuestion.created_at))  # fmt: skip
    return sorted(rows, key=lambda q: (not q.answer, q.status == "duplicate"))


def question_days(session: Session, limit: int = 30) -> list[tuple[date, int, int]]:
    """Days with questions, newest first: (day, asked, still waiting for review)."""
    per: dict[date, list[int]] = {}
    for created, status in session.execute(select(ReportQuestion.created_at, ReportQuestion.status)):
        d = (created if created.tzinfo else created.replace(tzinfo=UTC)).date()
        per.setdefault(d, [0, 0])
        per[d][0] += 1
        per[d][1] += status == "new"
    return [(d, n, o) for d, (n, o) in sorted(per.items(), reverse=True)][:limit]


def review(session: Session, day: date) -> dict:
    """One day's questions, each with the likely duplicates: earlier questions on the same report, or the same day's."""
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    end = start + timedelta(days=1)
    items = list(session.scalars(select(ReportQuestion).where(ReportQuestion.created_at >= start,
                                                               ReportQuestion.created_at < end)
                                 .order_by(ReportQuestion.created_at)))  # fmt: skip
    open_ = ReportQuestion.status.in_(("new", "good"))
    earlier = list(session.scalars(select(ReportQuestion).where(ReportQuestion.created_at < start, open_)))
    rows = []
    for i, q in enumerate(items):
        same = [x for x in earlier + items[:i] if x.slug == q.slug and similar_text(q.text, x.text, 0.6)]
        rows.append({"q": q, "report": report(q.slug), "like": same})
    return {"day": day, "rows": rows, "waiting": sum(1 for q in items if q.status == "new")}


def decide(session: Session, qid: int, status: str, answer: str = "", duplicate_of: int | None = None) -> None:
    if status not in Q_STATUSES:
        raise ValueError(status)
    q = session.get(ReportQuestion, qid)
    if q is None:
        raise KeyError(qid)
    q.status, q.answer = status, answer.strip()[:4000] or None
    q.duplicate_of = duplicate_of if status == "duplicate" else None
    q.reviewed_at = datetime.now(UTC) if status != "new" else None
    session.commit()


def review_text(d: dict) -> str:
    lines = [f"BizDev report questions {d['day']:%Y-%m-%d}: {len(d['rows'])} asked, {d['waiting']} waiting for review"]
    for row in d["rows"]:
        q = row["q"]
        lines.append(f"\n#{q.id} [{Q_STATUSES[q.status]}] ({q.slug}) {q.text.strip()}")
        for x in row["like"]:
            lines.append(f"  like #{x.id}: {x.text.strip()[:120]}")
        if q.answer:
            lines.append(f"  answer: {q.answer}")
    return "\n".join(lines) + "\n"
