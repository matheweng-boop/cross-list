"""Products › Cross a list: paste part numbers, get the two result columns per part and an Excel download. Nothing
pasted is stored (app/services/crosslist.py); only the owner's Right / Wrong answers on a shown pair are."""

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.auth.session import principal, signed_in_owner
from app.db import get_session
from app.matching.rules import load_all_rules
from app.services import crosslist as cl
from app.services import export
from app.web.routes import XLSX, templates

router = APIRouter()
MAX_CHARS = 60_000


def _ctx(request: Request, text: str, session: Session) -> dict:
    entries, over = cl.parse(text)
    rows = cl.cross_list(session, entries) if entries else []
    families = sorted({r.part.family for r in rows if r.part})
    return {"text": text, "rows": rows, "sum": cl.summary(rows), "over": over, "max_lines": cl.MAX_LINES,
            "submitted": bool(text.strip()), "owner": signed_in_owner(request) is not None,
            "privacy": cl.PRIVACY_NOTE, "precheck": cl.PRECHECK_NOTE, "how": cl.HOW_NOTE, "lights": cl.LIGHTS,
            "light_help": cl.LIGHT_HELP, "accuracy": cl.accuracy(), "header": cl.EXPORT_HEADER,
            "cells": cl.export_cells, "kinds": cl.TYPE_KIND,
            "p1": {f: cl.p1_labels(f) for f in families},
            "p1_all": {f: cl.p1_labels(f) for f in load_all_rules()}}  # fmt: skip


@router.get("/cross-list", response_class=HTMLResponse)
def page(request: Request, session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "cross_list.html", _ctx(request, "", session))


@router.post("/cross-list", response_class=HTMLResponse)
def run(request: Request, parts: str = Form(""), session: Session = Depends(get_session)):
    """Compute only: the pasted list is read, crossed and shown; nothing is written."""
    ctx = _ctx(request, parts[:MAX_CHARS], session)
    return templates.TemplateResponse(request, "cross_list.html", ctx)


@router.post("/cross-list.xlsx")
def download(parts: str = Form(""), lights: str = Form(""), session: Session = Depends(get_session)):
    """The table as shown: every row, or only the rows of the light chosen on the page ("Export shown rows")."""
    entries, over = cl.parse(parts[:MAX_CHARS])
    rows = cl.cross_list(session, entries)
    sm = cl.summary(rows)
    want = lights if lights in cl.LIGHTS else ""
    if want:
        rows = [r for r in rows if r.light == want]
    name = f"cross-list-{date.today():%Y-%m-%d}.xlsx"
    body = export.cross_list_xlsx(rows, sm, over, cl.accuracy(), cl.LIGHTS.get(want, ""))
    return Response(body, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/cross-list/feedback", response_class=HTMLResponse)
def feedback(request: Request, their: str = Form(...), ours: str = Form(...), verdict: str = Form(...),
             comment: str = Form(""), session: Session = Depends(get_session)):  # fmt: skip
    """The owner's Right / Wrong on one shown pair (guests never get here: an owner action, app/auth/access.py)."""
    if signed_in_owner(request) is None:
        raise HTTPException(403, "Only the owner can mark a cross right or wrong.")
    if verdict not in cl.VERDICTS or not their.strip() or not ours.strip():
        raise HTTPException(400, "Choose Right or Wrong.")
    if verdict == "wrong" and not comment.strip():  # nothing stored; the form stays
        return HTMLResponse('<span class="cx-need">Say what is wrong in the comment, then press Wrong again.</span>')
    p = principal(request)
    cl.record(session, their, ours, verdict, comment, p.name if p else None)
    msg = "✓ Verified – thanks." if verdict == "right" else "Marked wrong – sent to the next daily update."
    return HTMLResponse(f'<span class="cx-saved">{msg}</span>')
