"""Answers to the "Questions to ask" (owner, 2 Nov 2026; app/services/answers.py): saving an answer from a report or
case page, the owner's edit, sharing switch and release, and Data management › Answers.

A new answer goes to /business/reports/<slug>/answers, so a guest's answer is held for the owner's review like all
guest input (and lands as internal once approved: the sharing is the owner's choice). Editing, switching and releasing
live under /manage/answers, which only the owner can send (app/auth/access.py).

Segment questions (owner, 9 Nov 2026; app/services/segment_questions.py): each system and sub-system of the Systems
library has its page /library/questions/<system>[/<sub-system>]; a new answer goes to
/library/questions/<system>/answers (the sub-system as a form field), with the same guest rules."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.session import REPLAY, signed_in_owner
from app.db import get_session
from app.services import answers
from app.services import reports as rp
from app.services import segment_questions as sq
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


def _add(request: Request, session: Session, slug: str, form) -> answers.Answer:
    """Save a new answer: only the owner's own request sets the sharing; a replayed guest item lands internal."""
    replay = request.scope.get(REPLAY)
    owner = signed_in_owner(request) is not None and not replay
    sharing = str(form.get("sharing") or answers.INTERNAL) if owner else answers.INTERNAL
    author = str((replay or {}).get("author") or "") or None
    try:
        return answers.add(session, slug, str(form.get("key") or ""), str(form.get("text") or ""),
                           str(form.get("who") or ""), sharing, author)  # fmt: skip
    except KeyError:
        raise HTTPException(404, "Unknown question") from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@router.post("/library/questions/{system}/answers")
async def segment_answer_add(request: Request, system: str, session: Session = Depends(get_session)):
    """A new answer to a segment's question (the system's own, or a sub-system's when the form names one)."""
    form = await request.form()
    sub = str(form.get("sub") or "").strip()
    key = f"{system}/{sub}" if sub else system
    if sq.segment(key) is None:
        raise HTTPException(404, "Segment not found")
    a = _add(request, session, sq.slug_of(key), form)
    return RedirectResponse(f"{sq.href(a.slug)}?saved={a.id}#i-{a.question}", status_code=303)


def _segment_page(request: Request, session: Session, key: str):
    from app.services import systems as sy

    seg = sq.segment(key)
    if seg is None:
        raise HTTPException(404, "Segment not found")
    s = sy.get(seg["system"])
    x = sy.sub(seg["system"], seg["sub"]) if seg["sub"] else None
    subs = [] if x else [{"key": y["key"], "title": y["title"], "n": len(sq.questions(f"{s['key']}/{y['key']}")),
                          "href": f"/library/questions/{s['key']}/{y['key']}"} for y in s["subsystems"]]  # fmt: skip
    from app.services import library

    titles = {t["key"]: t["title"] for t in library.topics()}
    deep = [{"key": k, "title": titles[k]} for k in (x or {}).get("topics", []) if k in titles]
    ctx = {"seg": seg, "system": s, "sub": x, "subs": subs, "deep": deep, "reports": sq.reports(key),
           "qa": answers.page(session, request, sq.slug_of(key)), "tabs": sq.TABS, "ask": sq.ASK,
           "here": str(request.url.path)}  # fmt: skip
    return templates.TemplateResponse(request, "library/questions.html", ctx)


@router.get("/library/questions/{system}", response_class=HTMLResponse)
def segment_questions_system(request: Request, system: str, session: Session = Depends(get_session)):
    """A system's cross-cutting Questions to ask, with links to each sub-system's."""
    return _segment_page(request, session, system)


@router.get("/library/questions/{system}/{sub}", response_class=HTMLResponse)
def segment_questions_sub(request: Request, system: str, sub: str, session: Session = Depends(get_session)):
    """A sub-system's Questions to ask: customer, developers and business unit, each with its answer box."""
    from app.services import systems as sy

    new = sy.resolve(system, sub)
    if new and new != sub:  # a retired sub-system key (owner, 9 Nov 2026: Data center regrouped)
        return RedirectResponse(f"/library/questions/{system}/{new}", status_code=301)
    return _segment_page(request, session, f"{system}/{sub}")


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
    return RedirectResponse(_back(form, f"{answers.href(a.slug)}#ans-{a.id}"), status_code=303)


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
    return RedirectResponse(_back(form, f"{answers.href(a.slug)}#ans-{a.id}"), status_code=303)


@router.post("/manage/answers/{aid:int}/release")
async def answer_release(request: Request, aid: int, session: Session = Depends(get_session)):
    _owner(request)
    form = await request.form()
    try:
        a = answers.release(session, aid)
    except KeyError:
        raise HTTPException(404, "Answer not found") from None
    return RedirectResponse(_back(form, f"{answers.href(a.slug)}#ans-{a.id}"), status_code=303)


@router.get("/manage/answers", response_class=HTMLResponse)
def answers_overview(request: Request, sharing: str = "", report: str = "", segment: str = "",
                     session: Session = Depends(get_session)):  # fmt: skip
    """Data management › Answers: every answer across all reports and segments, filtered by sharing, report and
    segment, open questions first, each linked to its question."""
    sharing = sharing if sharing in (*answers.SHARING, "held") else ""
    report = report if rp.report(report) else ""
    segment = segment if sq.segment(segment) else ""
    ctx = {"ov": answers.overview(session, sharing, report, segment), "sharing": sharing, "report": report,
           "segment": segment, "labels": answers.SHARING,
           "groups": dict(sq.GROUPS) | dict(answers.groups(case=False)), "warning": answers.WARNING,
           "here": str(request.url.path) +
           (f"?{request.url.query}" if request.url.query else "")}  # fmt: skip
    return templates.TemplateResponse(request, "manage/answers.html", ctx)
