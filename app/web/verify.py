"""Verify next (Data management): the owner's small verification batch, refilled per kind when it is done."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.services import verify
from app.web.routes import templates

router = APIRouter()


@router.get("/manage/verify", response_class=HTMLResponse)
def verify_page(request: Request, session: Session = Depends(get_session)):
    new = verify.assign(session)
    ctx = {"board": verify.board(session), "kinds": verify.KINDS, "batch": verify.BATCH, "new": new,
           "topics": verify.DATA_TOPICS}  # fmt: skip
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
