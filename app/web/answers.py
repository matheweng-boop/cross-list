"""Answers to the "Questions to ask" (owner, 2 Nov 2026; app/services/answers.py): saving an answer from a report or
case page, the owner's edit, sharing switch and release, and Data management › Answers.

A new answer goes to /business/reports/<slug>/answers, so a guest's answer is held for the owner's review like all
guest input (and lands as internal once approved: the sharing is the owner's choice). Editing, switching and releasing
live under /manage/answers, which only the owner can send (app/auth/access.py)."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.session import REPLAY, signed_in_owner
from app.db import get_session
from app.services import answers
from app.services import reports as rp
from app.web.routes import templates
from app.web.urls import local_path

router = APIRouter()


def _back(form, default: str) -> str:
    return local_path(str(form.get("back") or ""), default)


@router.post("/business/reports/{slug}/answers")
async def answer_add(request: Request, slug: str, session: Session = Depends(get_session)):
    """A new answer under a question. Only the owner's own request sets the sharing; an approved guest item (a replay)
    and anything else is internal."""
    if rp.report(slug) is None:
        raise HTTPException(404, "Report not found")
    form = await request.form()
    key = str(form.get("key") or "")
    replay = request.scope.get(REPLAY)
    owner = signed_in_owner(request) is not None and not replay
    sharing = str(form.get("sharing") or answers.INTERNAL) if owner else answers.INTERNAL
    author = str((replay or {}).get("author") or "") or None
    try:
        a = answers.add(session, slug, key, str(form.get("text") or ""), str(form.get("who") or ""), sharing, author)
    except KeyError:
        raise HTTPException(404, "Unknown question") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(f"/business/reports/{slug}?saved={a.id}#i-{key}", status_code=303)


def _owner(request: Request) -> None:
    if signed_in_owner(request) is None:  # the gate already refuses guests here; this keeps it so without the gate
        raise HTTPException(403, "Only the owner can change an answer.")


@router.post("/manage/answers/{aid:int}/edit")
async def answer_edit(request: Request, aid: int, session: Session = Depends(get_session)):
    _owner(request)
    form = await request.form()
    try:
        a = answers.edit(session, aid, str(form.get("text") or ""), str(form.get("who") or ""),
                         str(form.get("sharing") or "") or None)  # fmt: skip
    except KeyError:
        raise HTTPException(404, "Answer not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(_back(form, f"/business/reports/{a.slug}#ans-{a.id}"), status_code=303)


@router.post("/manage/answers/{aid:int}/sharing")
async def answer_sharing(request: Request, aid: int, session: Session = Depends(get_session)):
    _owner(request)
    form = await request.form()
    try:
        a = answers.set_sharing(session, aid, str(form.get("sharing") or ""))
    except KeyError:
        raise HTTPException(404, "Answer not found") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(_back(form, f"/business/reports/{a.slug}#ans-{a.id}"), status_code=303)


@router.post("/manage/answers/{aid:int}/release")
async def answer_release(request: Request, aid: int, session: Session = Depends(get_session)):
    _owner(request)
    form = await request.form()
    try:
        a = answers.release(session, aid)
    except KeyError:
        raise HTTPException(404, "Answer not found") from None
    return RedirectResponse(_back(form, f"/business/reports/{a.slug}#ans-{a.id}"), status_code=303)


@router.get("/manage/answers", response_class=HTMLResponse)
def answers_overview(request: Request, sharing: str = "", report: str = "", session: Session = Depends(get_session)):
    """Data management › Answers: every answer across all reports, filtered by sharing and report, open questions
    first, each linked to its question."""
    sharing = sharing if sharing in (*answers.SHARING, "held") else ""
    report = report if rp.report(report) else ""
    ctx = {"ov": answers.overview(session, sharing, report), "sharing": sharing, "report": report,
           "labels": answers.SHARING, "groups": dict(answers.groups()), "warning": answers.WARNING,
           "here": str(request.url.path) +
           (f"?{request.url.query}" if request.url.query else "")}  # fmt: skip
    return templates.TemplateResponse(request, "manage/answers.html", ctx)
