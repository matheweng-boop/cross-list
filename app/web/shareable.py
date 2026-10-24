"""Shareable: public pages ready to share outside the company or save as PDF (owner, 24 Oct 2026). Guests read them
too (app/auth/access.py does not list /shareable as owner-only); editing the Technology overview is the owner's alone
(/shareable/technology-overview/edit is owner-only in access.py, and every edit route checks again)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth.session import signed_in_owner
from app.db import get_session
from app.services import logo, tech_overview, uploads
from app.services import tech_overview_edit as te
from app.web import nav
from app.web.routes import templates

router = APIRouter()
URL = "/shareable/technology-overview"
EDIT = URL + "/edit"

# a line more per card on the landing page than the menu's short description
BLURBS = {URL: "Four A4 pages on the Skyworks + Qorvo portfolio: technology platforms, end markets and product "
          "families."}  # fmt: skip
# what the page says after an edit action (?done=...); only these texts can appear
DONE = {"saved": "Saved.", "nochange": "Nothing changed.", "undone": "Undone: the page shows the version before.",
        "reset": "Back to the default.", "resetall": "Everything is back to the defaults (Undo brings it back).",
        "nothing": "Nothing to undo or reset.", "comment": "Comment saved: the next daily run rewrites this text.",
        "resolved": "Comment resolved.", "gone": "That paragraph or comment no longer exists.",
        "logo": "Logo added (Undo or Remove logo takes it out).", "logoremoved": "Logo removed."}  # fmt: skip


def _owner(request: Request) -> str:
    p = signed_in_owner(request)
    if p is None:
        raise HTTPException(403, "Only the owner can edit this page.")
    return p.name or "Owner"


def _back(done: str, anchor: str = "") -> RedirectResponse:
    return RedirectResponse(f"{EDIT}?done={done}{'#' + anchor if anchor else ''}", status_code=303)


@router.get("/shareable", response_class=HTMLResponse)
def shareable(request: Request):
    section = next(s for s in nav.NAV if s[0] == "shareable")
    items = [(label, href, BLURBS.get(href, desc)) for label, href, desc in section[2]]
    return templates.TemplateResponse(request, "shareable/index.html", {"items": items})


def _page(request: Request, session: Session, edit: bool, ov: dict | None = None, errors: dict | None = None,
          message: str = "", status: int = 200):  # fmt: skip
    te.apply_answers(session)  # the daily run's answers to comments (applied once each)
    session.commit()
    ov = te.overrides(session) if ov is None else ov
    vals = te.values(ov)
    opts = te.view_options(vals, request.query_params)
    message = message or DONE.get(request.query_params.get("done", ""), "")
    if opts["wm_error"]:
        message = f"No watermark: {opts['wm_error']}"
    ctx = {"t": tech_overview.build(), "today": date.today(), "vals": vals, "edit": edit, "o": opts,
           "specs": te.specs(), "over": set(ov), "errors": errors or {}, "message": message,
           "watermarks": te.WATERMARKS, "logo": te.logo_of(session, vals)}  # fmt: skip
    if edit:
        ctx.update(history=te.history(session), comments=te.comments(session), auto=te.auto_value,
                   para_limits=te.para_limits, owners=te.OWNERS, edit_url=EDIT)  # fmt: skip
    return templates.TemplateResponse(request, "shareable/tech_overview.html", ctx, status_code=status)


@router.get(URL, response_class=HTMLResponse)
def technology_overview(request: Request, session: Session = Depends(get_session)):
    return _page(request, session, edit=False)


@router.get(EDIT, response_class=HTMLResponse)
def technology_overview_edit(request: Request, session: Session = Depends(get_session)):
    _owner(request)
    return _page(request, session, edit=True)


@router.post(EDIT, response_class=HTMLResponse)
async def technology_overview_save(request: Request, session: Session = Depends(get_session)):
    author = _owner(request)
    form = await request.form()
    data = {k: [str(v) for v in form.getlist(k)] for k in form.keys()}
    op = (data.get("op") or [""])[0]  # a paragraph moved up or down or deleted (the browser asked to confirm)
    r = te.save(session, data, op, author)
    if r["errors"]:
        session.rollback()
        return _page(request, session, edit=True, ov=r["new"], errors=r["errors"], message=r["message"], status=400)
    session.commit()
    return _back("saved" if r["saved"] else "nochange")


@router.post(EDIT + "/undo")
def technology_overview_undo(request: Request, session: Session = Depends(get_session)):
    _owner(request)
    had = te.current(session) is not None
    te.undo(session)
    session.commit()
    return _back("undone" if had else "nothing")


@router.post(EDIT + "/reset")
async def technology_overview_reset(request: Request, session: Session = Depends(get_session)):
    author = _owner(request)
    form = await request.form()
    everything = form.get("all") == "1"
    fid = str(form.get("field") or "")
    before = te.overrides(session)
    te.reset(session, fid, everything, author)
    session.commit()
    changed = before != te.overrides(session)
    return _back(("resetall" if everything else "reset") if changed else "nothing", "" if everything else fid)


@router.post(EDIT + "/logo")
async def technology_overview_logo(request: Request, session: Session = Depends(get_session)):
    """Add (or replace) the header logo: PNG, JPG or SVG up to 1 MB, checked by content; an SVG is cleaned."""
    author = _owner(request)
    form = await request.form()
    upload = form.get("logo")
    data = await upload.read(logo.MAX_BYTES + 1) if hasattr(upload, "read") else b""
    try:
        up = logo.store(session, data, getattr(upload, "filename", "") or "", author)
    except ValueError as e:
        session.rollback()
        return _page(request, session, edit=True, errors={"hdr.logo": str(e)}, message="Logo not added.", status=400)
    te.set_logo(session, up.id, author)
    session.commit()
    return _back("logo", "f-hdr.logo")


@router.post(EDIT + "/logo/remove")
def technology_overview_logo_remove(request: Request, session: Session = Depends(get_session)):
    author = _owner(request)
    if "hdr.logo" not in te.overrides(session):
        return _back("nothing")
    te.set_logo(session, None, author)
    session.commit()
    return _back("logoremoved", "f-hdr.logo")


@router.get("/shareable/logo/{upload_id:int}")
def shareable_logo(upload_id: int, session: Session = Depends(get_session)):
    """A header logo (only uploads stored as one), as an image that can run nothing."""
    up = logo.get(session, upload_id)
    path = uploads.path_of(up.file_name) if up else None
    if path is None:
        raise HTTPException(404, "No such logo.")
    return FileResponse(path, media_type=up.content_type, headers={
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
        "X-Content-Type-Options": "nosniff", "Cache-Control": "private, max-age=3600"})  # fmt: skip


@router.post(EDIT + "/comment")
async def technology_overview_comment(request: Request, session: Session = Depends(get_session)):
    author = _owner(request)
    form = await request.form()
    block = str(form.get("block") or "")
    msg = te.add_comment(session, block, str(form.get(f"ctext.{block}") or ""), author)
    if not msg.startswith("Comment saved"):
        session.rollback()
        return _page(request, session, edit=True, errors={block: msg}, message="Comment not saved.", status=400)
    session.commit()
    return _back("comment", block)


@router.post(EDIT + "/resolve")
async def technology_overview_resolve(request: Request, session: Session = Depends(get_session)):
    _owner(request)
    form = await request.form()
    try:
        cid = int(str(form.get("cid") or "0"))
    except ValueError:
        cid = 0
    msg = te.resolve(session, cid, str(form.get(f"reply.{cid}") or ""))
    session.commit()
    return _back("resolved" if msg == "Comment resolved." else "gone")
