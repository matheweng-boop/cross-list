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
from app.services import share_reports as sr
from app.services import tech_overview_edit as te
from app.services.text import round_count
from app.web.routes import templates

router = APIRouter()
templates.env.filters.setdefault("rounded", round_count)  # counts on the Shareable reports: 4,132 -> "4,000+"
URL = "/shareable/technology-overview"
EDIT = URL + "/edit"

# the one list on /shareable (owner, 25 Oct 2026): key in the combined PDF, name, one short line, its page
REPORT_LIST = (("overview", "Technology overview", "The Skyworks + Qorvo portfolio: platforms, markets, families.",
                URL),
               ("synergies", "Skyworks + Qorvo synergies", "For management: capabilities, overlap, where they combine.",
                "/shareable/synergies"),
               ("automotive", "Automotive", "Technologies in the car, applications and AEC-Q pairs.",
                "/shareable/automotive"))  # fmt: skip
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
    """One page: the reports in a list (preview each, tick the ones to combine), a watermark, Build a PDF (the ticked
    reports in one print view) and Build a presentation (the topic builder). Nothing
    is ticked unless the address carries the last choice (?r=...)."""
    q = request.query_params
    reports = [(key, label, line, sr.PAGES[key], href, href + "/edit") for key, label, line, href in REPORT_LIST]
    return templates.TemplateResponse(request, "shareable/index.html", {
        "reports": reports, "picked": sr.pack_selection(",".join(q.getlist("r"))),
        "owner": signed_in_owner(request) is not None, "wm": q.get("wm", "none"),
        "watermarks": te.WATERMARKS})  # fmt: skip


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


# ---- the management reports (owner, 25 Oct 2026): Skyworks + Qorvo synergies and Automotive -----------------------
# Same editing as the Technology overview (tech_overview_edit with the report's key); guests read, only the owner edits.
BODIES = {"synergies": "shareable/_synergies.html", "automotive": "shareable/_automotive.html"}


def _report(slug: str) -> te.Report:
    rep = sr.REPORTS.get(slug)
    if rep is None:
        raise HTTPException(404, "No such page.")
    return rep


def _build(rep: te.Report) -> dict:
    return sr.build_synergies() if rep.key == "synergies" else sr.build_automotive()


def _report_ctx(request: Request, session: Session, rep: te.Report, edit: bool = False, ov: dict | None = None,
                wm: dict | None = None) -> dict:  # fmt: skip
    """Everything a report body needs: its values (the owner's edits over the defaults), the shared logo and header
    options (set on the Technology overview), the watermark of this view."""
    te.apply_answers(session, sr.SYNERGIES if rep.key == "synergies" else sr.AUTOMOTIVE)
    session.commit()
    ov = te.overrides(session, rep) if ov is None else ov
    vals = te.values(ov, rep)
    ovals = te.values(te.overrides(session))
    vals.update({k: ovals[k] for k in ("hdr.logo_align", "hdr.logo_size")})
    wm = wm or te.view_options(ovals, request.query_params)
    o = {"wm": wm["wm"], "wm_text": wm["wm_text"], "pages": sr.PAGES[rep.key]}
    return {"t": _build(rep), "today": date.today(), "vals": vals, "edit": edit, "o": o, "specs": rep.specs(),
            "over": set(ov), "errors": {}, "message": "", "logo": te.logo_of(session, ovals), "ip_note": sr.PATENT_NOTE,
            "watermarks": te.WATERMARKS, "page_url": rep.url, "edit_url": rep.url + "/edit", "body": BODIES[rep.key],
            "wm_error": wm["wm_error"]}  # fmt: skip


def _report_page(request: Request, session: Session, rep: te.Report, edit: bool, ov: dict | None = None,
                 errors: dict | None = None, message: str = "", status: int = 200):  # fmt: skip
    ctx = _report_ctx(request, session, rep, edit, ov)
    ctx["errors"] = errors or {}
    ctx["message"] = message or DONE.get(request.query_params.get("done", ""), "")
    if ctx["wm_error"]:
        ctx["message"] = f"No watermark: {ctx['wm_error']}"
    if edit:
        ctx.update(history=te.history(session, rep=rep), comments=te.comments(session, rep=rep),
                   auto=lambda fid, shown: te.auto_value(fid, shown, rep), para_limits=rep.para_limits,
                   owners=te.OWNERS)  # fmt: skip
    return templates.TemplateResponse(request, "shareable/report.html", ctx, status_code=status)


def _rback(rep: te.Report, done: str, anchor: str = "") -> RedirectResponse:
    return RedirectResponse(f"{rep.url}/edit?done={done}{'#' + anchor if anchor else ''}", status_code=303)


@router.get("/shareable/pack", response_class=HTMLResponse)
def shareable_pack(request: Request, session: Session = Depends(get_session)):
    """The combined PDF: ?r=overview,synergies,automotive (in this order), &wm= for the watermark (an old &focus= is
    ignored: the market focus page was removed, owner 25 Oct 2026). Page numbers run through the whole PDF; the
    sources come once, at the end."""
    q = request.query_params
    keys = sr.pack_selection(",".join(q.getlist("r"))) or list(sr.PACK_ORDER)
    te.apply_answers(session)
    session.commit()
    ovals = te.values(te.overrides(session))
    opts = te.view_options(ovals, q)
    pages = {k: sr.PAGES[k] for k in keys}
    total, offset = sum(pages.values()), 0
    ctxs = {}
    for k in keys:
        if k == "overview":
            ctxs[k] = {"t": tech_overview.build(), "today": date.today(), "vals": ovals, "edit": False, "o": opts,
                       "specs": te.specs(), "over": set(), "errors": {}, "message": "", "watermarks": te.WATERMARKS,
                       "logo": te.logo_of(session, ovals)}  # fmt: skip
        else:
            ctxs[k] = _report_ctx(request, session, sr.REPORTS[k], wm=opts)
        ctxs[k].update(pack_offset=offset, pack_total=total, pack_sources_later=k != keys[-1], request=request,
                       signed_in=lambda _r: None)  # fmt: skip
        offset += pages[k]
    last = keys[-1]
    if len(keys) > 1 and last != "overview":
        reps = [k for k in keys if k != "overview"]
        ctxs[last]["pack_sources"] = sr.sources(reps, {k: ctxs[k]["vals"] for k in reps})
    bodies = []
    for k in keys:
        if k == "overview":
            html = templates.get_template("shareable/tech_overview.html").render(ctxs[k])
            start, end = html.find('<section class="to-page"'), html.rfind("</section>")
            bodies.append(html[start:end + len("</section>")] if start >= 0 else "")
        else:
            bodies.append(templates.get_template(BODIES[k]).render(ctxs[k]))
    titles = ["Technology overview" if k == "overview" else sr.REPORTS[k].label for k in keys]
    query = f"r={','.join(keys)}&wm={opts['wm']}"
    return templates.TemplateResponse(request, "shareable/pack.html", {
        "bodies": bodies, "titles": titles, "total": total, "wm_text": opts["wm_text"], "keys": keys,
        "query": query})  # fmt: skip


@router.get("/shareable/{slug}", response_class=HTMLResponse)
def shareable_report(slug: str, request: Request, session: Session = Depends(get_session)):
    return _report_page(request, session, _report(slug), edit=False)


@router.get("/shareable/{slug}/edit", response_class=HTMLResponse)
def shareable_report_edit(slug: str, request: Request, session: Session = Depends(get_session)):
    rep = _report(slug)
    _owner(request)
    return _report_page(request, session, rep, edit=True)


@router.post("/shareable/{slug}/edit", response_class=HTMLResponse)
async def shareable_report_save(slug: str, request: Request, session: Session = Depends(get_session)):
    rep = _report(slug)
    author = _owner(request)
    form = await request.form()
    data = {k: [str(v) for v in form.getlist(k)] for k in form.keys()}
    r = te.save(session, data, (data.get("op") or [""])[0], author, rep)
    if r["errors"]:
        session.rollback()
        return _report_page(request, session, rep, True, r["new"], r["errors"], r["message"], 400)
    session.commit()
    return _rback(rep, "saved" if r["saved"] else "nochange")


@router.post("/shareable/{slug}/edit/undo")
def shareable_report_undo(slug: str, request: Request, session: Session = Depends(get_session)):
    rep = _report(slug)
    _owner(request)
    had = te.current(session, rep) is not None
    te.undo(session, rep)
    session.commit()
    return _rback(rep, "undone" if had else "nothing")


@router.post("/shareable/{slug}/edit/reset")
async def shareable_report_reset(slug: str, request: Request, session: Session = Depends(get_session)):
    rep = _report(slug)
    author = _owner(request)
    form = await request.form()
    everything, fid = form.get("all") == "1", str(form.get("field") or "")
    before = te.overrides(session, rep)
    te.reset(session, fid, everything, author, rep)
    session.commit()
    changed = before != te.overrides(session, rep)
    return _rback(rep, ("resetall" if everything else "reset") if changed else "nothing", "" if everything else fid)


@router.post("/shareable/{slug}/edit/comment")
async def shareable_report_comment(slug: str, request: Request, session: Session = Depends(get_session)):
    rep = _report(slug)
    author = _owner(request)
    form = await request.form()
    block = str(form.get("block") or "")
    msg = te.add_comment(session, block, str(form.get(f"ctext.{block}") or ""), author, rep)
    if not msg.startswith("Comment saved"):
        session.rollback()
        return _report_page(request, session, rep, True, errors={block: msg}, message="Comment not saved.", status=400)
    session.commit()
    return _rback(rep, "comment", block)


@router.post("/shareable/{slug}/edit/resolve")
async def shareable_report_resolve(slug: str, request: Request, session: Session = Depends(get_session)):
    rep = _report(slug)
    _owner(request)
    form = await request.form()
    try:
        cid = int(str(form.get("cid") or "0"))
    except ValueError:
        cid = 0
    msg = te.resolve(session, cid, str(form.get(f"reply.{cid}") or ""), rep)
    session.commit()
    return _rback(rep, "resolved" if msg == "Comment resolved." else "gone")
