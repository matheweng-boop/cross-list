"""Floating feedback button (every page) and the daily feedback digest in Data management."""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import FeedbackAttachment, SiteFeedback, Upload
from app.services import feedback as fb
from app.services import uploads as up
from app.web import nav
from app.web.routes import templates

router = APIRouter()
MAX_FILES = 3


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


@router.post("/site-feedback/{item_id:int}/file")
async def attach_file(item_id: int, client: str = Form(""), file: UploadFile = File(...),
                      session: Session = Depends(get_session)):  # fmt: skip
    """A picture or PDF sent with a feedback item, from the browser that sent the item. Stored like Data management >
    Uploads (same limits, same folder) and linked to the item."""
    def refuse(status: int, why: str) -> JSONResponse:  # JSON, so the Feedback window can say why
        return JSONResponse({"detail": why}, status_code=status)

    item = session.get(SiteFeedback, item_id)
    if item is None or not client or item.client != client[:40]:
        return refuse(404, "Feedback not found")
    if session.scalar(select(func.count()).select_from(FeedbackAttachment)
                      .where(FeedbackAttachment.feedback_id == item_id)) >= MAX_FILES:  # fmt: skip
        return refuse(400, f"At most {MAX_FILES} files per feedback")
    data = await file.read(up.MAX_BYTES + 1)
    if not data:
        return refuse(400, "The file is empty")
    try:
        stored, ctype = up.store(data)
    except ValueError as e:
        return refuse(400, str(e))
    u = Upload(
        title=f"Feedback: {item.text[:80]}"[:200], kind="picture" if ctype.startswith("image/") else "document",
        topic=(item.page or item.path)[:200], author=item.author, file_name=stored,
        original_name=(file.filename or "")[:200] or None, content_type=ctype, size=len(data),
        explanation=f"Sent with the Feedback button on {item.path}: {item.text}"[:20000],
    )  # fmt: skip
    session.add(u)
    session.flush()
    session.add(FeedbackAttachment(feedback_id=item.id, upload_id=u.id))
    session.commit()
    return {"ok": True, "upload": u.id, "name": u.original_name}


def attachments(session: Session, ids: list[int]) -> dict[int, list[Upload]]:
    """Files sent with these feedback items: feedback id -> uploads."""
    out: dict[int, list[Upload]] = {}
    if not ids:
        return out
    q = (select(FeedbackAttachment.feedback_id, Upload).join(Upload, Upload.id == FeedbackAttachment.upload_id)
         .where(FeedbackAttachment.feedback_id.in_(ids)).order_by(Upload.id))  # fmt: skip
    for fid, u in session.execute(q):
        out.setdefault(fid, []).append(u)
    return out


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
    digest = fb.digest(session, d)
    files = attachments(session, [i for g in digest["groups"] for i in g["ids"]])
    ctx = {"days": days, "digest": digest, "kinds": fb.KINDS, "statuses": fb.STATUSES, "files": files}
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
