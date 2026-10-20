"""Cross requests: parts that still need to be added and crossed."""

import re

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import CrossRequest, Part
from app.partnumbers import normalize_pn
from app.web.routes import templates

router = APIRouter()
STATUSES = {"open": "Open", "in_progress": "In progress", "done": "Done", "cannot": "Cannot cross"}


def _part_for(session: Session, mpn: str) -> Part | None:
    key = normalize_pn(mpn)
    for p in session.scalars(select(Part).where(Part.mpn.ilike(f"{mpn.strip()[:4]}%"))).unique():
        if normalize_pn(p.mpn) == key:
            return p
    return None


@router.get("/requests", response_class=HTMLResponse)
def requests_page(request: Request, session: Session = Depends(get_session)):
    rows = session.scalars(select(CrossRequest).order_by(CrossRequest.created_at.desc())).all()
    order = list(STATUSES)
    rows = sorted(rows, key=lambda r: order.index(r.status) if r.status in order else 9)
    found = {r.id: _part_for(session, r.mpn) for r in rows}
    return templates.TemplateResponse(request, "requests.html", {"rows": rows, "found": found, "statuses": STATUSES})


@router.post("/requests")
def add_requests(
    mpns: str = Form(...), manufacturer: str = Form(""), note: str = Form(""), back: str = Form(""),
    session: Session = Depends(get_session),
):  # fmt: skip
    open_keys = {
        normalize_pn(r.mpn) for r in session.scalars(select(CrossRequest).where(CrossRequest.status != "done"))
    }
    for mpn in [t.strip() for t in re.split(r"[,;\n\t]+", mpns) if t.strip()][:200]:
        if normalize_pn(mpn) in open_keys:
            continue
        session.add(CrossRequest(mpn=mpn[:100], manufacturer=manufacturer.strip() or None, note=note.strip() or None))
        open_keys.add(normalize_pn(mpn))
    session.commit()
    return RedirectResponse(back if back.startswith("/") else "/requests", status_code=303)


@router.post("/requests/{request_id}")
def update_request(
    request_id: int, status: str = Form(""), delete: str = Form(""), session: Session = Depends(get_session)
):
    r = session.get(CrossRequest, request_id)
    if r is not None:
        if delete:
            session.delete(r)
        elif status in STATUSES:
            r.status = status
        session.commit()
    return RedirectResponse("/requests", status_code=303)


@router.get("/requests.txt", response_class=PlainTextResponse)
def requests_text(session: Session = Depends(get_session)):
    """Open requests as plain text, to paste into a conversation with Claude."""
    rows = session.scalars(
        select(CrossRequest).where(CrossRequest.status.in_(["open", "in_progress"])).order_by(CrossRequest.created_at)
    ).all()
    lines = ["Please add these parts to BizDev and program their crosses:"]
    for r in rows:
        extra = "; ".join(x for x in (r.manufacturer, r.note) if x)
        lines.append(f"- {r.mpn}{f' ({extra})' if extra else ''}")
    return "\n".join(lines) + "\n"
