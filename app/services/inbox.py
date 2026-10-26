"""Everything the owner said on the site since a day, as one text for the daily update run (GET /api/inbox).

Site feedback (grouped as in the daily digest), cross verdicts, diagram and technology feedback, data-review answers
(agree / disagree, yes / no, with comments), the Data quality comments still being checked, questions asked on
reports with their answers and the technology review requests and application area requests (all open ones, and
those closed since the day). Requested volumes, customers and markets are left out on purpose: they stay on the site.
"""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AreaRequest,
    BlockFeedback,
    CrossFeedback,
    DataReview,
    IdeaRequest,
    Part,
    ReportQuestion,
    SiteFeedback,
    TechFeedback,
    VerifyTask,
    aware,
)
from app.services import feedback as fb
from app.services import guest_input, review_history
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


def _earlier(session: Session, r) -> str:
    """Up to two earlier answers to the same item, so the daily run sees a change of mind."""
    note = review_history.earlier_note(review_history.history(session, r.dataset, r.key, n=6), before_id=r.id)
    return f"\n  {note}" if note else ""


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
    mpn = dict(session.execute(select(Part.id, Part.mpn).where(Part.id.in_(ids))).all()) if ids else {}
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

    from app.services import crosslist, digest, families, refmatch

    # the To confirm feed has its own section below (Confirm / Ignore are counted, comments listed)
    own = (refmatch.FEEDBACK, digest.DATASET, crosslist.DATASET, families.DATASET)  # sections of their own
    reviews = [r for r in _new(session, DataReview, start) if r.dataset not in own]
    out += _section("\n## Review answers (data quality, TAM, cases, library, price calls)\n",
                    [f"- {_when(r.created_at)} {r.dataset} / {r.key}: {r.verdict}"
                     f"{' · ' + _one_line(r.comment) if r.comment else ''}{_earlier(session, r)}"
                     for r in reviews])  # fmt: skip

    # Products › Cross a list: pairs marked Wrong (fix data or rules) and Right (known answers; owner, 26 Oct 2026)
    cx = crosslist.inbox_lines(session, start)
    out += cx
    cx_new = any(x.startswith("- ") for x in cx)
    # datasheet families flagged for a re-read (every one still open) and family verdicts (owner, 26 Oct 2026)
    fam = families.inbox_lines(session, start)
    out += fam
    cx_new = cx_new or any(x.startswith("- ") for x in fam)
    # Cross a list › "Update cross-lists": parts queued for a datasheet lookup (also read by the hourly lookup run)
    from app.services import crosslist_lookups

    lookups = crosslist_lookups.inbox_lines(session)
    out += lookups
    cx_new = cx_new or lookups[-1] != "None."
    # lifetime volume estimates sent with those lookups: a count only, never values (owner's safeguard, 26 Oct 2026)
    from app.services import demand

    n_vol = demand.new_count(session, since)
    out.append(f"\nLifetime volume entries (owner only, values stay on the site): {n_vol} new volume "
               f"entr{'y' if n_vol == 1 else 'ies'}.")  # fmt: skip

    # the owner's answers on the reference designs matched to the library diagrams (owner, 25 Oct 2026: matching
    # "based on feedback"): the run looks for patterns and tunes app/services/refmatch.py (docs/daily_update.md)
    out.append("\n## Reference design feedback\n")
    rf = [r for r in _new(session, DataReview, start) if r.dataset == refmatch.FEEDBACK]
    if rf:
        out.append("Doesn't fit = the design (or the suggested block) does not belong to the diagram; Fits = "
                   "confirmed; reset = back to the rules. When several Doesn't fit answers share a pattern, tune "
                   "the thresholds or stop-words in app/services/refmatch.py and re-run scripts/match_refdesigns.py.\n")
    for r in rf:
        out.append(refmatch.inbox_line(r, _when(r.created_at)))
    if not rf:
        out.append("None.")

    # Data quality comments still being checked (every open one, not only new ones): the run checks each, then
    # records it in data/business/quality_checked.yaml so the owner gets the second round (owner, 25 Oct 2026)
    from app.services import quality

    dq = quality.inbox_lines(session)
    out += dq
    dq_open = dq[-1] != "None."

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

    # "Expand this idea" on Research & ideas: every open one, and those closed since the last pull
    ideas = [i for i in session.scalars(select(IdeaRequest).order_by(IdeaRequest.created_at))
             if i.status == "new" or aware(i.updated_at or i.created_at) >= start]  # fmt: skip
    out.append("\n## Idea expansion requests\n")
    out.append("Add an \"Applications in depth\" section to each report (docs/daily_update.md), then set the status "
               "to Expanded on Data management > Site data > Requests (/manage/requests?kind=idea).\n")  # fmt: skip
    out += [f"- {_when(i.created_at)} [{i.status}] {i.slug}: {_one_line(i.title)}"
            f"{' · note: ' + _one_line(i.note) if i.note else ''}" for i in ideas] or ["None."]  # fmt: skip

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
    from app.services import share_reports  # the other Shareable reports: same storage and answers file

    out += [x for rep in share_reports.REPORTS.values() for x in tech_overview_edit.inbox_lines(session, start, rep)]

    # Data management › Data flow (owner, 26 Oct 2026): the owner's chart changes against data/manage/data_flow.yaml
    from app.services import data_flow

    flow = data_flow.inbox_lines(session, start)
    out += flow
    flow_new = flow[-1] != "None." and not flow[-1].startswith("No new save")

    # report and case market figures that no longer match the TAM (data/business/tam_links.yaml)
    from app.services import tam_links

    tam_todo = tam_links.inbox_lines(session)
    out += tam_todo
    tam_changes = tam_todo[-1] != "None."
    from app.services import radio_market  # prices the owner must enter before the radio market can be computed

    out += radio_market.inbox_lines(session)

    # Data management > To confirm (owner, 25 Oct 2026): counts since the last pull and the comments to act on
    to_confirm = digest.inbox_lines(session, start)
    out += to_confirm
    tc_comments = to_confirm[-1] != "None."

    n_site = session.scalar(select(SiteFeedback.id).where(SiteFeedback.created_at >= start).limit(1))
    # open requests are work too
    if not any([n_site, crosses, blocks, tech, reviews, dq_open, src, asked, answered, rq, areas, ideas, approved,
                overview, tam_changes, tc_comments, cx_new, flow_new]):
        out.append("\nNothing new since the last pull.")
    return "\n".join(out) + "\n"
