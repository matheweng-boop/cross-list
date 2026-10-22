"""Data management: the Overview (review status per data set, what is waiting) and Verify next (the owner's small
verification batch, refilled per kind when it is done)."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.matching.rules import get_rules
from app.models import CrossFeedback, Part, SiteFeedback, Upload, VerifyTask
from app.services import quality, tam, verify
from app.services.compare import compare_parts
from app.web.routes import templates

router = APIRouter()


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
    }
    t = tam.counts(session)
    stats = quality.stats(session)
    stats.append({"name": "tam", "label": "TAM estimates", "n_items": t["n"], "verified": t["agree"],
                  "disputed": t["disagree"], "unverified": t["open"], "src_ok": t["n"] - t["no_link"], "src_corr": 0,
                  "src_no": t["no_link"], "low": 0})  # fmt: skip
    ctx = {"waiting": waiting, "stats": stats, "tam": t}
    return templates.TemplateResponse(request, "manage/overview.html", ctx)


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
    compares = {t.id: _cross_compare(session, t) for t in board["open"]["cross"]}
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
