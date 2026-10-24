"""Cross requests: parts that still need to be added and crossed; and Data management > Site data > Requests, one list
of part requests, diagram feedback and application area requests (owner, 24 Oct 2026). Each kind keeps its own table
and its own POST handlers; this page only shows them together."""

import re

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import AreaRequest, BlockFeedback, CrossRequest, Part
from app.partnumbers import normalize_pn
from app.web.routes import templates
from app.web.urls import local_path

router = APIRouter()
STATUSES = {"open": "Open", "in_progress": "In progress", "done": "Done", "cannot": "Cannot cross"}


def _part_for(session: Session, mpn: str) -> Part | None:
    key = normalize_pn(mpn)
    for p in session.scalars(select(Part).where(Part.mpn.ilike(f"{mpn.strip()[:4]}%"))).unique():
        if normalize_pn(p.mpn) == key:
            return p
    return None


# kind -> label, and the statuses that count as open; the status names and labels stay with each kind's handler
KINDS = {"part": "Part request", "diagram": "Diagram feedback", "area": "Area request"}
OPEN = {"part": ("open", "in_progress"), "diagram": ("open", "agreed"), "area": ("new", "planned")}


@router.get("/requests")
def requests_page():
    """The old Part requests page: now the Requests tab, filtered to part requests."""
    return RedirectResponse("/manage/requests?kind=part", status_code=307)


@router.get("/manage/requests", response_class=HTMLResponse)
def all_requests(request: Request, kind: str = "", show: str = "", session: Session = Depends(get_session)):
    """Part requests, diagram feedback and area requests in one list, newest first; open ones unless show=all."""
    from app.web.blocks import AREA_STATUSES, FEEDBACK_STATUS

    kind = kind if kind in KINDS else ""
    show = "all" if show == "all" else ""
    rows = [("part", r) for r in session.scalars(select(CrossRequest))]
    rows += [("diagram", f) for f in session.scalars(select(BlockFeedback))]
    rows += [("area", a) for a in session.scalars(select(AreaRequest))]
    counts = {k: sum(1 for kk, r in rows if kk == k and r.status in OPEN[k]) for k in KINDS}
    if not show:
        rows = [(k, r) for k, r in rows if r.status in OPEN[k]]
    if kind:
        rows = [(k, r) for k, r in rows if k == kind]
    rows.sort(key=lambda kr: (kr[1].created_at is not None, kr[1].created_at or 0, kr[1].id), reverse=True)
    found = {r.id: _part_for(session, r.mpn) for k, r in rows if k == "part"}
    statuses = {"part": STATUSES, "diagram": FEEDBACK_STATUS, "area": AREA_STATUSES}
    ctx = {"rows": rows, "found": found, "statuses": statuses, "kinds": KINDS, "kind": kind, "show": show,
           "counts": counts}  # fmt: skip
    return templates.TemplateResponse(request, "manage/requests.html", ctx)


@router.post("/requests")
def add_requests(
    mpns: str = Form(""), manufacturer: str = Form(""), note: str = Form(""), back: str = Form(""),
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
    return RedirectResponse(local_path(back, "/manage/requests?kind=part"), status_code=303)


@router.post("/requests/{request_id}")
def update_request(
    request_id: int, status: str = Form(""), delete: str = Form(""), session: Session = Depends(get_session)
):
    r = session.get(CrossRequest, request_id)
    if r is None:
        raise HTTPException(404, "Request not found")
    if delete:
        session.delete(r)
    elif status in STATUSES:
        r.status = status
    session.commit()
    return RedirectResponse("/manage/requests?kind=part", status_code=303)


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
