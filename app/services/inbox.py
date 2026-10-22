"""Everything the owner said on the site since a day, as one text for the daily update run (GET /api/inbox).

Site feedback (grouped as in the daily digest), cross verdicts, diagram and technology feedback, data-review answers
(agree / disagree, yes / no, with comments), questions asked on reports with their answers and the technology review
requests (all open ones, and those closed since the day). Requested volumes,
customers and markets are left out on purpose: they stay on the site.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    BlockFeedback,
    CrossFeedback,
    DataReview,
    Part,
    ReportQuestion,
    SiteFeedback,
    TechFeedback,
)
from app.services import feedback as fb


def _since(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _when(dt: datetime) -> str:
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).strftime("%Y-%m-%d %H:%M")


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _one_line(text: str | None) -> str:
    return " ".join((text or "").split())


def collect(session: Session, since: date, until: date | None = None) -> str:
    """The text, newest day last; ``until`` is inclusive (default: today)."""
    until = until or datetime.now(UTC).date()
    start = _since(since)
    out = [f"# BizDev inbox {since:%Y-%m-%d} to {until:%Y-%m-%d}"]

    days = [since + timedelta(days=i) for i in range((until - since).days + 1)]
    texts = [fb.digest_text(d) for d in (fb.digest(session, day) for day in days) if d["n"]]
    out.append("\n## Site feedback\n")
    out.append("\n".join(texts) if texts else "None.\n")

    crosses = session.scalars(select(CrossFeedback).where(CrossFeedback.created_at >= start)
                              .order_by(CrossFeedback.created_at)).unique().all()  # fmt: skip
    ids = {i for c in crosses for i in (c.reference_id, c.candidate_id)}
    mpn = dict(session.execute(select(Part.id, Part.mpn).where(Part.id.in_(ids)))) if ids else {}
    out.append("## Cross verdicts\n")
    out += [f"- {_when(c.created_at)} {c.verdict.value}: {mpn.get(c.reference_id, c.reference_id)} -> "
            f"{mpn.get(c.candidate_id, c.candidate_id)}{' · ' + _one_line(c.note) if c.note else ''}"
            for c in crosses] or ["None."]  # fmt: skip

    blocks = session.scalars(select(BlockFeedback).where(BlockFeedback.created_at >= start)
                             .order_by(BlockFeedback.created_at)).all()  # fmt: skip
    out.append("\n## Block diagram feedback\n")
    out += [f"- {_when(b.created_at)} [{b.status}] {b.diagram_name or b.diagram_id or ''}"
            f"{' / ' + b.target if b.target else ''}: {_one_line(b.message)}" for b in blocks] or ["None."]  # fmt: skip

    tech = session.scalars(select(TechFeedback).where(TechFeedback.created_at >= start)
                           .order_by(TechFeedback.created_at)).all()  # fmt: skip
    out.append("\n## Technology feedback\n")
    out += [f"- {_when(t.created_at)} [{t.status}] {t.kind} {t.topic or ''}: {_one_line(t.text)}" for t in tech] or [
        "None."
    ]

    reviews = session.scalars(select(DataReview).where(DataReview.created_at >= start)
                              .order_by(DataReview.created_at)).all()  # fmt: skip
    out.append("\n## Review answers (data quality, TAM, cases, library, price calls)\n")
    out += [f"- {_when(r.created_at)} {r.dataset} / {r.key}: {r.verdict}"
            f"{' · ' + _one_line(r.comment) if r.comment else ''}" for r in reviews] or ["None."]  # fmt: skip

    asked = session.scalars(select(ReportQuestion).where(ReportQuestion.created_at >= start)
                            .order_by(ReportQuestion.created_at)).all()  # fmt: skip
    answered = session.scalars(select(ReportQuestion).where(ReportQuestion.reviewed_at >= start,
                                                            ReportQuestion.created_at < start)).all()  # fmt: skip
    out.append("\n## Questions on reports\n")
    out += [f"- {_when(q.created_at)} [{q.status}] {q.slug}: {_one_line(q.text)}"
            f"{' · answer: ' + _one_line(q.answer) if q.answer else ''}"
            for q in [*asked, *answered]] or ["None."]  # fmt: skip

    # every open request (the run writes the review), and those closed since the last pull
    from app.services import reviews as rv

    rq = [e for e in rv.requests(session)
          if e["status"] in ("new", "in_progress") or _aware(e["row"].created_at) >= start]  # fmt: skip
    rq.sort(key=lambda e: e["row"].created_at)
    out.append("\n## Technology review requests\n")
    out.append("Open requests get a review written as data/reviews/<slug>.yaml (format: data/reviews/_format.yaml).\n")
    for e in rq:
        x = e["row"]
        out.append(f"- {_when(x.created_at)} [{e['status']}] {x.mpn}: {_one_line(x.question)}"
                   f"{' · application: ' + _one_line(x.application) if x.application else ''}"
                   f"{' · review: /reviews/' + e['review']['slug'] if e['review'] else ''}")  # fmt: skip
    if not rq:
        out.append("None.")

    n_site = session.scalar(select(SiteFeedback.id).where(SiteFeedback.created_at >= start).limit(1))
    if not any([n_site, crosses, blocks, tech, reviews, asked, answered, rq]):  # open requests are work too
        out.append("\nNothing new since the last pull.")
    return "\n".join(out) + "\n"
