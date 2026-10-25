"""Shareable > Presentation builder (owner, 25 Oct 2026): pick topics and their technical knowledge, order the
sections, preview the slides one by one, save as PDF. The selection lives in the address (?s=...), so a deck can be
bookmarked and shared; guests build and preview, only the owner saves decks (with the edited titles and texts)."""

from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth.session import signed_in_owner
from app.db import get_session
from app.services import presentation as pr
from app.services import presentation_pptx as pp
from app.services import site_guard, uploads
from app.services import tech_overview_edit as te
from app.web.routes import templates

router = APIRouter()
URL = pr.URL
DONE = {"saved": "Saved.", "deleted": "Presentation deleted.", "gone": "That presentation no longer exists."}


def _owner(request: Request) -> str:
    p = signed_in_owner(request)
    if p is None:
        raise HTTPException(403, "Only the owner can save presentations.")
    return p.name or "Owner"


def _deck(request: Request, session: Session) -> dict | None:
    s = request.query_params.get("deck", "")
    return pr.get_deck(session, pr.slug(s)) if s else None


def _ids(request: Request, deck: dict | None) -> list[str]:
    raw = ",".join(request.query_params.getlist("s"))
    if not raw and deck:
        raw = deck.get("s", "")
    return pr.parse(raw)


def _builder(request: Request, session: Session, ids: list[str], deck: dict | None, errors: dict | None = None,
             message: str = "", status: int = 200):  # fmt: skip
    is_owner = signed_in_owner(request) is not None
    picked_topics = set(pr.selected_topics(ids))
    for sid in ids:  # a selected note opens the topics it belongs to
        if sid.startswith("note."):
            picked_topics |= {t["id"] for t in pr.topic_index().values() if sid[5:] in t["notes"]}
    titles = {sid: pr.section_title(sid) for sid in pr.all_section_ids()}
    return templates.TemplateResponse(request, "shareable/presentation.html", {
        "groups": pr.groups(), "general": pr.GENERAL, "kinds": pr.KINDS, "notes": pr.note, "ids": ids,
        "picked_topics": picked_topics, "titles": titles, "deck": deck or {}, "owner": is_owner,
        "decks": pr.decks(session) if is_owner else [], "left_out": pr.left_out(), "errors": errors or {},
        "message": message or DONE.get(request.query_params.get("done", ""), ""), "s": pr.query(ids),
        "limits": {"title": pr.TITLE_MAX, "text": pr.TEXT_MAX, "name": pr.NAME_MAX},
        "defaults": {"title": pr.DEFAULT_TITLE, "closing": pr.DEFAULT_CLOSING, "contact": pr.DEFAULT_CONTACT},
    }, status_code=status)  # fmt: skip


@router.get(URL, response_class=HTMLResponse)
def builder(request: Request, session: Session = Depends(get_session)):
    deck = _deck(request, session)
    return _builder(request, session, _ids(request, deck), deck)


def _view(request: Request, session: Session) -> dict:
    """What the preview and the PowerPoint download share: the slides, the deck title, watermark and logo."""
    deck = _deck(request, session)
    ids = _ids(request, deck)
    ovals = te.values(te.overrides(session))
    opts = te.view_options(ovals, request.query_params)
    q = {"s": pr.query(ids)} | ({"deck": deck["slug"]} if deck else {})
    return {"slides": pr.build(ids, deck), "deck_title": (deck or {}).get("title") or pr.DEFAULT_TITLE,
            "today": date.today(), "vals": ovals, "logo": te.logo_of(session, ovals), "wm_text": opts["wm_text"],
            "wm": opts["wm"], "s": pr.query(ids), "deck_slug": (deck or {}).get("slug", ""),
            "back": f"{URL}?{urlencode(q, safe=',')}",
            "pptx": f"{URL}/pptx?{urlencode(q | {'wm': opts['wm']}, safe=',')}"}  # fmt: skip


@router.get(URL + "/preview", response_class=HTMLResponse)
def preview(request: Request, session: Session = Depends(get_session)):
    """The slides, one at a time on screen (Previous / Next, arrow keys, swipe, thumbnails, full screen) and one per
    16:9 page when printed."""
    v = _view(request, session)
    return templates.TemplateResponse(request, "shareable/presentation_preview.html", v | {
        "total": len(v["slides"]), "watermarks": te.WATERMARKS})  # fmt: skip


def _logo_bytes(up) -> bytes | None:
    """The header logo for PowerPoint: PNG / JPEG / GIF only (an SVG logo would need a converter; left out)."""
    if up is None or up.content_type not in ("image/png", "image/jpeg", "image/gif"):
        return None
    path = uploads.path_of(up.file_name)
    return path.read_bytes() if path else None


@router.get(URL + "/pptx")
def pptx(request: Request, session: Session = Depends(get_session)):
    """The preview's slides as an editable PowerPoint file (same address parameters as the preview)."""
    v = _view(request, session)
    if not v["slides"]:
        return RedirectResponse(v["back"], status_code=303)
    data = pp.build(v["slides"], v["deck_title"], v["today"], v["wm_text"], _logo_bytes(v["logo"]))
    found = [h for t in pp.texts(data) for x in t for h in site_guard.hits(x)]
    if found:  # never expected: every slide already passed the word check
        raise HTTPException(409, "This presentation cannot be downloaded: it failed the public-safe word check.")
    name = pp.filename(v["deck_title"])
    return Response(data, media_type=pp.MEDIA_TYPE, headers={
        "Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "private, no-store"})  # fmt: skip


def _form_deck(form) -> dict:
    def one(k: str, n: int) -> str:
        return " ".join(str(form.get(k) or "").split())[:n]

    ids = pr.parse(str(form.get("s") or ""))
    titles = {}
    for sid in ids:
        t = one(f"t.{sid}", pr.TITLE_MAX)
        if t and t != pr.section_title(sid):
            titles[sid] = t
    return {"name": one("name", pr.NAME_MAX), "s": pr.query(ids), "title": one("title", pr.TITLE_MAX),
            "subtitle": one("subtitle", pr.TITLE_MAX), "closing": one("closing", pr.TEXT_MAX),
            "contact": one("contact", pr.TITLE_MAX), "titles": titles}  # fmt: skip


@router.post(URL + "/save", response_class=HTMLResponse)
async def save(request: Request, session: Session = Depends(get_session)):
    author = _owner(request)
    d = _form_deck(await request.form())
    errors = pr.check_deck(d)
    if errors:
        return _builder(request, session, pr.parse(d["s"]), d, errors, "Not saved: see the marked fields.", 400)
    s = pr.save_deck(session, d, author)
    session.commit()
    return RedirectResponse(f"{URL}?{urlencode({'deck': s, 's': d['s'], 'done': 'saved'}, safe=',')}",
                            status_code=303)  # fmt: skip


@router.post(URL + "/delete")
async def delete(request: Request, session: Session = Depends(get_session)):
    _owner(request)
    form = await request.form()
    ok = pr.delete_deck(session, pr.slug(str(form.get("deck") or "")))
    session.commit()
    return RedirectResponse(f"{URL}?done={'deleted' if ok else 'gone'}", status_code=303)
