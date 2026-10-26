"""Data management › To confirm (owner only, /manage is the owner's): every research item boiled down to a gist,
newest first, with Read (the abstract), Confirm, Ignore and a comment. See app/services/digest.py."""

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_engine, get_session
from app.services import digest
from app.web.routes import templates

router = APIRouter()
TABS = {"open": "To confirm", "confirmed": "Confirmed", "ignored": "Ignored"}
PAGE = 60  # cards per page; "Show more" adds the next ones


def _count() -> int:
    """Open items for the Data management badge (one small query; 0 when the database is not reachable)."""
    try:
        with Session(get_engine()) as s:
            return digest.open_count(s)
    except Exception:  # noqa: BLE001 - a badge must never break a page
        return 0


templates.env.globals["to_confirm_count"] = _count
templates.env.globals["gist_for"] = digest.gist_for
templates.env.globals["gist_list"] = digest.gist_list
templates.env.globals["patent_line"] = digest.patent_line  # machine-checked patent depth (owner, 26 Oct 2026)
templates.env.globals["checked_auto"] = digest.checked_label


@router.get("/manage/to-confirm", response_class=HTMLResponse)
def to_confirm(request: Request, tab: str = "open", type: str = "", q: str = "", n: int = PAGE,
               session: Session = Depends(get_session)):  # fmt: skip
    tab = tab if tab in TABS else "open"
    typ = type if type in digest.TYPES else ""
    f = digest.feed(session, tab, typ, q)
    n = max(PAGE, min(n, 5000))
    ctx = {"f": f, "cards": f["cards"][:n], "more": len(f["cards"]) - n, "n": n, "tab": tab, "typ": typ, "q": q,
           "tabs": TABS, "types": digest.TYPES, "words": digest.MAX_WORDS,
           "here": "/manage/to-confirm?" + urlencode({k: v for k, v in (("tab", tab), ("type", typ), ("q", q)) if v})}
    return templates.TemplateResponse(request, "manage/to_confirm.html", ctx)  # fmt: skip


@router.post("/manage/to-confirm/act")
def act(request: Request, key: str = Form(...), action: str = Form(...), comment: str = Form(""),
        back: str = Form("/manage/to-confirm"), session: Session = Depends(get_session)):  # fmt: skip
    from app.auth.session import principal

    p = principal(request)
    try:
        digest.act(session, key, action, comment, author=getattr(p, "name", "") or "")
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    if request.headers.get("X-Requested-With") == "fetch":
        return JSONResponse({"ok": True, "open": digest.open_count(session)})
    back = back if back.startswith("/manage/to-confirm") else "/manage/to-confirm"
    return RedirectResponse(back, status_code=303)
