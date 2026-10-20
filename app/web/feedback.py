"""Floating feedback button (every page) and the daily feedback digest in Data management."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import SiteFeedback
from app.services import feedback as fb
from app.web import nav
from app.web.routes import templates

router = APIRouter()


def page_label(path: str, heading: str = "") -> str:
    """Section › page (› heading) for a path, as the navigation names it."""
    st = nav.state(path.split("?")[0])
    parts = [st["crumbs"][0][0], st["crumbs"][1][0]]
    if heading and heading.strip() not in parts:
        parts.append(heading.strip()[:120])
    return " › ".join(parts)


@router.post("/site-feedback")
def send_feedback(payload: dict = Body(...), session: Session = Depends(get_session)):
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Write something first")
    path = str(payload.get("path") or "/")[:500]
    if not path.startswith("/"):
        path = "/"
    kind = str(payload.get("kind") or "idea")
    item = SiteFeedback(
        text=text[:4000], kind=kind if kind in fb.KINDS else "idea", path=path,
        page=page_label(path, str(payload.get("heading") or ""))[:300],
        selection=(str(payload.get("selection") or "").strip()[:1000] or None),
        author=(str(payload.get("author") or "").strip()[:100] or None),
        client=(str(payload.get("client") or "").strip()[:40] or None),
    )  # fmt: skip
    session.add(item)
    session.commit()
    return {"ok": True, "id": item.id, "page": item.page}


@router.get("/site-feedback/mine")
def my_feedback(client: str = "", session: Session = Depends(get_session)):
    """The last items sent from this browser, with their status and response."""
    if not client:
        return JSONResponse([])
    rows = session.scalars(select(SiteFeedback).where(SiteFeedback.client == client[:40])
                           .order_by(SiteFeedback.created_at.desc()).limit(8))  # fmt: skip
    return [{"text": r.text[:200], "page": r.page, "status": fb.STATUSES.get(r.status, r.status),
             "response": r.response, "date": f"{r.created_at:%Y-%m-%d}"} for r in rows]  # fmt: skip


@router.get("/site-feedback/context")
def feedback_context(path: str = "/", heading: str = ""):
    return {"page": page_label(path, heading)}


@router.get("/manage/feedback", response_class=HTMLResponse)
def feedback_digest(request: Request, day: str = "", session: Session = Depends(get_session)):
    days = fb.days(session)
    try:
        d = date.fromisoformat(day) if day else (days[0][0] if days else datetime.now(UTC).date())
    except ValueError:
        raise HTTPException(400, "Bad date") from None
    ctx = {"days": days, "digest": fb.digest(session, d), "kinds": fb.KINDS, "statuses": fb.STATUSES}
    return templates.TemplateResponse(request, "manage/feedback.html", ctx)


@router.get("/manage/feedback/digest.txt", response_class=PlainTextResponse)
def feedback_digest_text(day: str = "", session: Session = Depends(get_session)):
    d = date.fromisoformat(day) if day else datetime.now(UTC).date()
    return fb.digest_text(fb.digest(session, d))


@router.post("/manage/feedback/respond")
def feedback_respond(ids: str = Form(...), status: str = Form(...), response: str = Form(""), day: str = Form(""),
                     session: Session = Depends(get_session)):  # fmt: skip
    try:
        fb.respond(session, [int(x) for x in ids.split(",") if x.strip().isdigit()], status, response[:4000])
    except ValueError:
        raise HTTPException(400, "Unknown status") from None
    session.commit()
    return RedirectResponse(f"/manage/feedback?day={day}" if day else "/manage/feedback", status_code=303)
