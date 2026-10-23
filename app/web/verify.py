"""Data management: the Overview (review status per data set, what is waiting) and Verify next (the owner's small
verification batch, refilled per kind when it is done)."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.matching.rules import get_rules
from app.models import (
    AreaRequest,
    BlockFeedback,
    ChangeEvent,
    CrossFeedback,
    CrossRequest,
    Datasheet,
    Manufacturer,
    Part,
    SiteFeedback,
    Upload,
    VerifyTask,
)
from app.services import guest_input, quality, tam, verify
from app.services.compare import compare_parts
from app.web.routes import templates

router = APIRouter()
BERLIN = ZoneInfo("Europe/Berlin")


@router.get("/manage/overview", response_class=HTMLResponse)
def overview(request: Request, session: Session = Depends(get_session)):
    """A compact start page for Data management: what waits for the owner, and review status per data set."""
    verify.assign(session)  # the next batch is ready, so the count below is what Verify next shows
    n_open = dict(session.execute(select(VerifyTask.kind, func.count()).where(VerifyTask.status == "open")
                                  .group_by(VerifyTask.kind)).all())  # fmt: skip
    waiting = {
        "verify": sum(n_open.values()),
        "feedback": session.scalar(select(func.count()).select_from(SiteFeedback).where(SiteFeedback.status == "new")),
        "uploads": session.scalar(select(func.count()).select_from(Upload).where(Upload.status == "new")),
        "guest": guest_input.pending_count(session),
    }
    waiting.update(overview_counts(session))
    t = tam.counts(session)
    stats = quality.stats(session)
    stats.append({"name": "tam", "label": "TAM estimates", "n_items": t["n"], "verified": t["agree"],
                  "disputed": t["disagree"], "unverified": t["open"], "src_ok": t["n"] - t["no_link"], "src_corr": 0,
                  "src_no": t["no_link"], "low": 0})  # fmt: skip
    split = ", ".join(f"{n} {verify.KINDS.get(k, k).lower()}" for k, n in sorted(n_open.items()))
    ctx = {"waiting": waiting, "stats": stats, "tam": t, "raw": raw_status(session), "verify_split": split}
    return templates.TemplateResponse(request, "manage/overview.html", ctx)


def _count(session: Session, model, *where) -> int:
    return session.scalar(select(func.count()).select_from(model).where(*where)) or 0


def overview_counts(session: Session, now: datetime | None = None) -> dict[str, int]:
    """What came in today and the open requests (owner, 23 Oct 2026: everything on one page). "Today" is the calendar
    day in Berlin, where the owner and the daily run are."""
    from app.services import reviews as rv

    now = now or datetime.now(UTC)
    start = datetime.combine(now.astimezone(BERLIN).date(), time(0), BERLIN).astimezone(UTC)
    return {
        "feedback_today": _count(session, SiteFeedback, SiteFeedback.created_at >= start),
        "part_requests": _count(session, CrossRequest, CrossRequest.status.in_(("open", "in_progress"))),
        "diagram_feedback": _count(session, BlockFeedback, BlockFeedback.status == "open"),
        "area_requests": _count(session, AreaRequest, AreaRequest.status == "new"),
        "review_requests": sum(e["status"] in ("new", "in_progress") for e in rv.requests(session)),
    }


def raw_status(session: Session) -> dict:
    """The raw data behind the site: parts, datasheets and the newest import, library diagrams and systems."""
    from app.services import blocks
    from app.services import systems as sy

    ours = select(Manufacturer.id).where(Manufacturer.name.in_(("Skyworks", "Qorvo")))
    week = datetime.now(UTC) - timedelta(days=7)
    return {
        "parts": _count(session, Part),
        "ours": _count(session, Part, Part.manufacturer_id.in_(ours)),
        "makers": _count(session, Manufacturer),
        "datasheets": _count(session, Datasheet),
        "last_datasheet": session.scalar(select(func.max(Datasheet.imported_at))),
        "changes_week": _count(session, ChangeEvent, ChangeEvent.detected_at >= week),
        "diagrams": len(blocks.templates()),
        "systems": len(sy.systems()),
        "subsystems": sum(len(s["subsystems"]) for s in sy.systems()),
        "unassigned": len(sy.unassigned()),
    }


@router.get("/manage/site-data")
def site_data():
    """Data management > Site data opens on its first tab, Verify next."""
    return RedirectResponse("/manage/verify", status_code=307)


def _cross_compare(session: Session, t: VerifyTask) -> dict | None:
    """The spec comparison of a cross task (competitor part as the baseline) and the earlier comments on the pair."""
    d = t.detail or {}
    ref, cand = session.get(Part, d.get("ref") or 0), session.get(Part, d.get("cand") or 0)
    if ref is None or cand is None:
        return None
    try:
        comparison = compare_parts([ref, cand], ref, get_rules(ref.family))
    except KeyError:  # no parameter rules for the family: the links to the datasheets still work
        return None
    notes = list(session.scalars(select(CrossFeedback).where(CrossFeedback.reference_id == ref.id,
                                                             CrossFeedback.candidate_id == cand.id)))  # fmt: skip
    return {"c": comparison, "notes": notes}


@router.get("/manage/verify", response_class=HTMLResponse)
def verify_page(request: Request, session: Session = Depends(get_session)):
    new = verify.assign(session)
    board = verify.board(session)
    compares = {t.id: _cross_compare(session, t) for t in board["shown"]["cross"]}
    ctx = {"board": board, "kinds": verify.KINDS, "batch": verify.BATCH, "new": new, "topics": verify.DATA_TOPICS,
           "compares": compares}  # fmt: skip
    return templates.TemplateResponse(request, "verify.html", ctx)


@router.post("/manage/verify/{task_id:int}")
def verify_done(task_id: int, result: str = Form(...), note: str = Form(""), author: str = Form(""),
                session: Session = Depends(get_session)):  # fmt: skip
    if result not in ("ok", "wrong"):
        raise HTTPException(400, "Unknown result")
    try:
        t = verify.complete(session, task_id, result == "ok", note, author)
    except ValueError as e:
        raise HTTPException(404, "No open task") from e
    return RedirectResponse(f"/manage/verify#{t.kind}", status_code=303)


@router.get("/manage/schedule", response_class=HTMLResponse)
def schedule_page(request: Request, session: Session = Depends(get_session)):
    """Everything that is processed and how often, and what tonight's run will pick up."""
    from app.services import runs

    ctx = {"groups": runs.by_frequency(), "tonight": runs.tonight(), "q": runs.queue(session),
           "questions": runs.open_questions()}  # fmt: skip
    return templates.TemplateResponse(request, "manage/schedule.html", ctx)
