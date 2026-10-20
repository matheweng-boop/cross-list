"""Data management > Uploads: add pictures, block diagrams, documents and explanations; view and file them."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Upload
from app.services import uploads as up
from app.web.routes import templates

router = APIRouter()


def _get(session: Session, upload_id: int) -> Upload:
    u = session.get(Upload, upload_id)
    if u is None:
        raise HTTPException(404, "Not found")
    return u


@router.get("/manage/uploads", response_class=HTMLResponse)
def uploads_page(request: Request, kind: str = "", status: str = "", error: str = "",
                 session: Session = Depends(get_session)):  # fmt: skip
    q = select(Upload).order_by(Upload.created_at.desc())
    if kind in up.KINDS:
        q = q.where(Upload.kind == kind)
    if status in up.STATUSES:
        q = q.where(Upload.status == status)
    ctx = {"rows": list(session.scalars(q)), "kinds": up.KINDS, "statuses": up.STATUSES, "kind": kind,
           "status": status, "error": error, "max_mb": up.MAX_BYTES // (1024 * 1024)}  # fmt: skip
    return templates.TemplateResponse(request, "manage/uploads.html", ctx)


@router.post("/manage/uploads")
async def add_upload(
    title: str = Form(""), kind: str = Form("picture"), explanation: str = Form(""), topic: str = Form(""),
    source: str = Form(""), author: str = Form(""), file: UploadFile | None = File(None),
    session: Session = Depends(get_session),
):  # fmt: skip
    data = await file.read(up.MAX_BYTES + 1) if file is not None and file.filename else b""
    if not data and not explanation.strip():
        return RedirectResponse("/manage/uploads?error=Add+a+file+or+write+an+explanation", status_code=303)
    stored, ctype = None, None
    if data:
        try:
            stored, ctype = up.store(data)
        except ValueError as e:
            return RedirectResponse(f"/manage/uploads?error={str(e).replace(' ', '+')}", status_code=303)
    u = Upload(
        title=(title.strip() or (file.filename if data and file else "") or explanation.strip()[:60])[:200],
        kind=kind if kind in up.KINDS else "picture", explanation=explanation.strip()[:20000] or None,
        topic=topic.strip()[:200] or None, source=source.strip()[:500] or None, author=author.strip()[:100] or None,
        file_name=stored, original_name=(file.filename or "")[:200] if data and file else None,
        content_type=ctype, size=len(data) or None,
    )  # fmt: skip
    session.add(u)
    session.commit()
    return RedirectResponse(f"/manage/uploads/{u.id}", status_code=303)


@router.get("/manage/uploads/{upload_id:int}", response_class=HTMLResponse)
def upload_detail(request: Request, upload_id: int, session: Session = Depends(get_session)):
    ctx = {"u": _get(session, upload_id), "kinds": up.KINDS, "statuses": up.STATUSES}
    return templates.TemplateResponse(request, "manage/upload.html", ctx)


@router.get("/manage/uploads/{upload_id:int}/file")
def upload_file(upload_id: int, session: Session = Depends(get_session)):
    u = _get(session, upload_id)
    path = up.path_of(u.file_name or "")
    if path is None:
        raise HTTPException(404, "No file")
    inline = (
        "inline" if (u.content_type or "").startswith("image/") or u.content_type == "application/pdf" else "attachment"
    )
    headers = {"X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=86400"}
    return FileResponse(path, media_type=u.content_type, filename=u.original_name or path.name,
                        content_disposition_type=inline, headers=headers)  # fmt: skip


@router.post("/manage/uploads/{upload_id:int}")
def update_upload(upload_id: int, title: str = Form(...), kind: str = Form(...), explanation: str = Form(""),
                  topic: str = Form(""), source: str = Form(""), status: str = Form("new"), note: str = Form(""),
                  session: Session = Depends(get_session)):  # fmt: skip
    u = _get(session, upload_id)
    u.title = title.strip()[:200] or u.title
    u.kind = kind if kind in up.KINDS else u.kind
    u.explanation, u.topic = explanation.strip()[:20000] or None, topic.strip()[:200] or None
    u.source, u.note = source.strip()[:500] or None, note.strip()[:4000] or None
    u.status = status if status in up.STATUSES else u.status
    session.commit()
    return RedirectResponse(f"/manage/uploads/{u.id}", status_code=303)


@router.post("/manage/uploads/{upload_id:int}/delete")
def delete_upload(upload_id: int, session: Session = Depends(get_session)):
    u = _get(session, upload_id)
    up.remove(u.file_name)
    session.delete(u)
    session.commit()
    return RedirectResponse("/manage/uploads", status_code=303)
