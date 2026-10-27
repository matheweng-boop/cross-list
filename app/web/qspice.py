"""Engineering knowledge › QSPICE library (owner, 27 Oct 2026) and Data management › AI services (later).

/qspice: the forum design discussions filterable by function, "Seen in practice" notes, how-tos, common fixes, models
for our parts and the Ask box (a GET keyword search, so guests can search too; only the owner's unanswered questions
are stored, screened). See app/services/qspice.py. /manage/ai-services is the owner's (all of /manage is)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.auth.session import signed_in_owner
from app.db import get_session
from app.services import qspice, vocab
from app.web.routes import templates

router = APIRouter()


@router.get("/qspice", response_class=HTMLResponse)
def library(request: Request, fn: str = "", q: str = "", session: Session = Depends(get_session)):
    q = q.strip()[: qspice.MAX_QUESTION]
    hits = qspice.ask(q) if q else []
    owner = signed_in_owner(request) is not None
    stored = False
    if q and not qspice.answered(hits) and owner:
        stored = qspice.store(session, q) is not None
    fns = qspice.function_counts()
    fn = fn if fn in {f for f, _, _ in fns} else ""
    ctx = {"q": q, "hits": hits, "answered": qspice.answered(hits), "stored": stored, "owner": owner,
           "fn": fn, "fns": fns, "topics": qspice.topics(fn), "practice": qspice.practice(fn),
           "help": qspice.help_items(), "fixes": qspice.fixes(), "models": qspice.models(),
           "answers": qspice.answers(), "meta": qspice.data().get("source") or {}, "label": vocab.fn_label,
           "unanswered": qspice.unanswered(session)[:20] if owner else []}  # fmt: skip
    return templates.TemplateResponse(request, "engineering/qspice.html", ctx)


@router.get("/manage/ai-services", response_class=HTMLResponse)
def ai_services(request: Request):
    from app.services import ai_services as ai

    return templates.TemplateResponse(request, "manage/ai_services.html", {"d": ai.data(), "status": ai.STATUS})
