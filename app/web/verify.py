"""Data management: the Overview (review status per data set, what is waiting) and Verify next (the owner's small
verification batch, refilled per kind when it is done)."""

import threading
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import count, get_engine, get_session
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


_ASSIGN = threading.Lock()  # one new Verify next batch at a time (Overview in the background, Verify next itself)


def _assign(session: Session) -> list[str]:
    with _ASSIGN:
        return verify.assign(session)


def _assign_later() -> None:
    """Prepare the next Verify next batch after the Overview is sent: picking one takes seconds (site check, 24 Oct
    2026), so the Overview no longer waits for it; Verify next shows it, the Overview counts it on the next visit."""
    with Session(get_engine()) as s:
        _assign(s)


@router.get("/manage/overview", response_class=HTMLResponse)
def overview(request: Request, background: BackgroundTasks, session: Session = Depends(get_session)):
    """A compact start page for Data management: what waits for the owner, and review status per data set."""
    n_open = dict(session.execute(select(VerifyTask.kind, func.count()).where(VerifyTask.status == "open")
                                  .group_by(VerifyTask.kind)).all())  # fmt: skip
    if any(k not in n_open for k in verify.BATCH):
        background.add_task(_assign_later)
    waiting = {
        "verify": sum(n_open.values()),
        "feedback": count(session, SiteFeedback, SiteFeedback.status == "new"),
        "uploads": count(session, Upload, Upload.status == "new"),
        "guest": guest_input.pending_count(session),
    }
    waiting.update(overview_counts(session))
    t = tam.counts(session)
    stats = quality.stats(session)
    stats.append({"name": "tam", "label": "TAM estimates", "n_items": t["n"], "verified": t["agree"],
                  "disputed": t["disagree"], "unverified": t["open"], "src_ok": t["n"] - t["no_link"], "src_corr": 0,
                  "src_no": t["no_link"], "low": 0})  # fmt: skip
    split = ", ".join(f"{n} {verify.KINDS.get(k, k).lower()}" for k, n in sorted(n_open.items()))
    ctx = {"waiting": waiting, "stats": stats, "tam": t, "raw": raw_status(session), "verify_split": split,
           "todo": todo(session, waiting, n_open, t["open"])}  # fmt: skip
    return templates.TemplateResponse(request, "manage/overview.html", ctx)


def overview_counts(session: Session, now: datetime | None = None) -> dict[str, int]:
    """What came in today and the open requests (owner, 23 Oct 2026: everything on one page). "Today" is the calendar
    day in Berlin, where the owner and the daily run are."""
    from app.services import reviews as rv

    now = now or datetime.now(UTC)
    start = datetime.combine(now.astimezone(BERLIN).date(), time(0), BERLIN).astimezone(UTC)
    return {
        "feedback_today": count(session, SiteFeedback, SiteFeedback.created_at >= start),
        "part_requests": count(session, CrossRequest, CrossRequest.status.in_(("open", "in_progress"))),
        "diagram_feedback": count(session, BlockFeedback, BlockFeedback.status == "open"),
        "area_requests": count(session, AreaRequest, AreaRequest.status == "new"),
        "review_requests": sum(e["status"] in ("new", "in_progress") for e in rv.requests(session)),
    }


def _n(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


# review queue types with no line of their own on the to-do list (requests and TAM have theirs)
_QUEUE_TYPES = ("specification", "mapping", "qualification", "evidence")
_QUEUE_DONE = {"done", "confirmed", "rejected", "cannot", "agreed"}  # as the Review queue's "Open" filter


def todo(session: Session, waiting: dict, n_open: dict, tam_open: int) -> list[tuple[int, str, str]]:
    """The owner's to-do list at the top of the Overview (owner, 24 Oct 2026): (count, label after the count, link to
    the exact place to act), only lines with something waiting. Uses the counts the Overview already has."""
    from app.services import maintenance, runs

    queue = sum(i["type"] in _QUEUE_TYPES and i["status"] not in _QUEUE_DONE for i in maintenance.items(session))
    v = n_open.get
    lines = [
        (v("sources", 0), _n(v("sources", 0), "source to check", "sources to check"), "/manage/verify#sources"),
        (v("cross", 0), _n(v("cross", 0), "cross to verify", "crosses to verify"), "/manage/verify#cross"),
        (v("diagram", 0), _n(v("diagram", 0), "block diagram to verify", "block diagrams to verify"),
         "/manage/verify#diagram"),
        (v("data", 0), _n(v("data", 0), "data item to verify", "data items to verify"), "/manage/verify#data"),
        (waiting["part_requests"], _n(waiting["part_requests"], "part request", "part requests"),
         "/manage/requests?kind=part"),
        (waiting["diagram_feedback"], _n(waiting["diagram_feedback"], "diagram feedback to review",
                                         "diagram feedback items to review"), "/manage/requests?kind=diagram"),
        (waiting["area_requests"], _n(waiting["area_requests"], "new area request", "new area requests"),
         "/manage/requests?kind=area"),
        (waiting["feedback"], _n(waiting["feedback"], "new site feedback item", "new site feedback items"),
         "/manage/feedback"),
        (waiting["guest"], _n(waiting["guest"], "guest input to review", "guest inputs to review"),
         "/manage/guest-input"),
        (queue, _n(queue, "review queue item", "review queue items"), "/manage/reviews?status=open"),
        (waiting["review_requests"], _n(waiting["review_requests"], "part review requested", "part reviews requested"),
         "/reviews#requested"),
        (waiting["uploads"], _n(waiting["uploads"], "new upload", "new uploads"), "/manage/uploads?status=new"),
        (tam_open, _n(tam_open, "TAM figure to review", "TAM figures to review"), "/business/tam"),
        (len(q := runs.open_questions()), _n(len(q), "open question for you", "open questions for you"),
         "/manage/feedback#questions"),
    ]  # fmt: skip
    return [line for line in lines if line[0] > 0]


def raw_status(session: Session) -> dict:
    """The raw data behind the site: parts, datasheets and the newest import, library diagrams and systems."""
    from app.services import blocks
    from app.services import systems as sy

    ours = select(Manufacturer.id).where(Manufacturer.name.in_(("Skyworks", "Qorvo")))
    week = datetime.now(UTC) - timedelta(days=7)
    return {
        "parts": count(session, Part),
        "ours": count(session, Part, Part.manufacturer_id.in_(ours)),
        "makers": count(session, Manufacturer),
        "datasheets": count(session, Datasheet),
        "last_datasheet": session.scalar(select(func.max(Datasheet.imported_at))),
        "changes_week": count(session, ChangeEvent, ChangeEvent.detected_at >= week),
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
    new = _assign(session)
    board = verify.board(session)
    compares = {t.id: _cross_compare(session, t) for t in board["shown"]["cross"]}
    ctx = {"board": board, "kinds": verify.KINDS, "batch": verify.BATCH, "new": new, "topics": verify.DATA_TOPICS,
           "compares": compares, "answers": verify.SOURCE_ANSWERS}  # fmt: skip
    return templates.TemplateResponse(request, "verify.html", ctx)


@router.post("/manage/verify/{task_id:int}")
def verify_done(task_id: int, result: str = Form(...), note: str = Form(""), author: str = Form(""),
                session: Session = Depends(get_session)):  # fmt: skip
    if result not in ("ok", "wrong", *verify.SOURCE_ANSWERS):
        raise HTTPException(400, "Unknown result")
    task = session.get(VerifyTask, task_id)
    is_source = task is not None and task.kind == "sources"
    if task is not None and result not in (verify.SOURCE_ANSWERS if is_source else ("ok", "wrong")):
        raise HTTPException(400, "Unknown result")  # fix / remove are Sources answers only
    try:
        answer = result if is_source else None
        t = verify.complete(session, task_id, result == "ok", note, author, answer)
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
