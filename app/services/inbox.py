"""Everything the owner said on the site since a day, as one text for the daily update run (GET /api/inbox).

Site feedback (grouped as in the daily digest), cross verdicts, diagram and technology feedback, data-review answers
(agree / disagree, yes / no, with comments), questions asked on reports with their answers and the technology review
requests and application area requests (all open ones, and those closed since the day). Requested volumes,
customers and markets are left out on purpose: they stay on the site.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AreaRequest,
    BlockFeedback,
    CrossFeedback,
    DataReview,
    Part,
    ReportQuestion,
    SiteFeedback,
    TechFeedback,
    VerifyTask,
    aware,
)
from app.services import feedback as fb
from app.services import guest_input
from app.services.verify import SOURCE_ANSWERS


def _since(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _when(dt: datetime) -> str:
    return aware(dt).strftime("%Y-%m-%d %H:%M")


def _one_line(text: str | None) -> str:
    return " ".join((text or "").split())


def _new(session: Session, model, start: datetime) -> list:
    """Rows of ``model`` created since ``start``, oldest first."""
    return session.scalars(select(model).where(model.created_at >= start).order_by(model.created_at)).unique().all()


def _section(title: str, lines: list[str]) -> list[str]:
    """A heading and its lines; "None." when there are none."""
    return [title, *(lines or ["None."])]


def collect(session: Session, since: date, until: date | None = None) -> str:
    """The text, newest day last; ``until`` is inclusive (default: today)."""
    until = until or datetime.now(UTC).date()
    start = _since(since)
    out = [f"# BizDev inbox {since:%Y-%m-%d} to {until:%Y-%m-%d}"]

    days = [since + timedelta(days=i) for i in range((until - since).days + 1)]
    texts = [fb.digest_text(d) for d in (fb.digest(session, day) for day in days) if d["n"]]
    out.append("\n## Site feedback\n")
    out.append("\n".join(texts) if texts else "None.\n")

    crosses = _new(session, CrossFeedback, start)
    ids = {i for c in crosses for i in (c.reference_id, c.candidate_id)}
    mpn = dict(session.execute(select(Part.id, Part.mpn).where(Part.id.in_(ids)))) if ids else {}
    out += _section("## Cross verdicts\n", [f"- {_when(c.created_at)} {c.verdict.value}: "
                    f"{mpn.get(c.reference_id, c.reference_id)} -> {mpn.get(c.candidate_id, c.candidate_id)}"
                    f"{' · ' + _one_line(c.note) if c.note else ''}" for c in crosses])  # fmt: skip

    blocks = _new(session, BlockFeedback, start)
    out += _section("\n## Block diagram feedback\n", [f"- {_when(b.created_at)} [{b.status}] "
                    f"{b.diagram_name or b.diagram_id or ''}{' / ' + b.target if b.target else ''}: "
                    f"{_one_line(b.message)}" for b in blocks])  # fmt: skip

    tech = _new(session, TechFeedback, start)
    out += _section("\n## Technology feedback\n", [f"- {_when(t.created_at)} [{t.status}] {t.kind} {t.topic or ''}: "
                    f"{_one_line(t.text)}" for t in tech])  # fmt: skip

    reviews = _new(session, DataReview, start)
    out += _section("\n## Review answers (data quality, TAM, cases, library, price calls)\n",
                    [f"- {_when(r.created_at)} {r.dataset} / {r.key}: {r.verdict}"
                     f"{' · ' + _one_line(r.comment) if r.comment else ''}" for r in reviews])  # fmt: skip

    # Verify next › Sources (weekly link and source check): ok / fix it / remove, with where it is
    src = session.scalars(select(VerifyTask).where(VerifyTask.kind == "sources", VerifyTask.done_at >= start)
                          .order_by(VerifyTask.done_at)).all()  # fmt: skip
    out.append("\n## Source check answers\n")
    out.append("Fix it: replace the dead link with the publisher's current page (polite rules) or read the source and "
               "drop the marker. Remove: take the link or the figure out. Checked, OK: drop the marker.\n")  # fmt: skip
    for t in src:
        d = t.detail or {}
        what = d.get("url") if d.get("what") == "link" else f"“{_one_line(d.get('text'))}”"
        out.append(f"- {_when(t.done_at)} {SOURCE_ANSWERS.get(t.status, t.status)}: {d.get('label', '')} {what}"
                   f" · page {d.get('page') or '–'} · {d.get('file')}:{d.get('line')}"
                   f"{' (' + str(d.get('entry')) + ')' if d.get('entry') else ''}"
                   f"{' · ' + _one_line(t.note) if t.note else ''}")  # fmt: skip
    if not src:
        out.append("None.")

    asked = _new(session, ReportQuestion, start)
    answered = session.scalars(select(ReportQuestion).where(ReportQuestion.reviewed_at >= start,
                                                            ReportQuestion.created_at < start)).all()  # fmt: skip
    out += _section("\n## Questions on reports\n", [f"- {_when(q.created_at)} [{q.status}] {q.slug}: "
                    f"{_one_line(q.text)}{' · answer: ' + _one_line(q.answer) if q.answer else ''}"
                    for q in [*asked, *answered]])  # fmt: skip

    # every open request (the run writes the review), and those closed since the last pull
    from app.services import reviews as rv

    rq = [e for e in rv.requests(session)
          if e["status"] in ("new", "in_progress") or aware(e["row"].created_at) >= start]  # fmt: skip
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

    # application areas asked for in the library: every open one, and those closed since the last pull
    areas = [a for a in session.scalars(select(AreaRequest).order_by(AreaRequest.created_at))
             if a.status in ("new", "planned") or aware(a.updated_at or a.created_at) >= start]  # fmt: skip
    out.append("\n## Application area requests\n")
    out.append("Research a few documents per run; add diagrams to the library and set the status on "
               "Data management > Site data > Requests (/manage/requests?kind=area).\n")  # fmt: skip
    out += [f"- {_when(a.created_at)} [{a.status}] {_one_line(a.area)}{' · why: ' + _one_line(a.why) if a.why else ''}"
            f"{' · ' + a.author if a.author else ''}" for a in areas] or ["None."]  # fmt: skip

    # guest input: only what the owner approved (already applied, with names); pending items only as a count
    guests = guest_input.inbox_lines(session, start)
    out += guests
    approved = not guests[2].startswith("None.")

    # Shareable > Technology overview: the owner's edits (kept in the database), changed automatic numbers, comments
    from app.services import tech_overview_edit

    overview = tech_overview_edit.inbox_lines(session, start)
    out.append("\n## Technology overview (Shareable)\n")
    out.append(
        "The owner's edits live in the database; never reset them. Answer each open comment in "
        "data/business/tech_overview_answers.yaml (comment, block, text, reply; public-safe check applies).\n"
    )
    out += overview or ["None."]

    n_site = session.scalar(select(SiteFeedback.id).where(SiteFeedback.created_at >= start).limit(1))
    # open requests are work too
    if not any([n_site, crosses, blocks, tech, reviews, src, asked, answered, rq, areas, approved, overview]):
        out.append("\nNothing new since the last pull.")
    return "\n".join(out) + "\n"
