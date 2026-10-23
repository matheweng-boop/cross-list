"""The sign-in gate: only signed-in people see anything.

The owner signs in with the site password (the backup, unless switched off) or a passkey; invited guests with a
passkey. Off when CROSSLIST_SITE_PASSWORD is empty (local use: everyone is the owner). Guests read every page except
Data management; anything a guest sends is stored for the owner's review (app/services/guest_input.py) instead of
being applied.
"""

import asyncio
import html
from urllib.parse import quote, urlsplit

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.auth import access, stepup
from app.auth.session import (
    COOKIE,
    OWNER,
    REPLAY,
    Principal,
    account_from_cookie,
    client_ip,
    ensure_owner,
    guard,
    pow_check,
    pow_issue,
    principal,
    set_login_cookie,
)
from app.config import get_settings
from app.db import get_engine, get_session
from app.models import Account
from app.services import guest_input, notify
from app.web.urls import local_path

FLASH = "crosslist_flash"
FAIL_DELAY = 1.0  # seconds a wrong password waits (slows guessing)

router = APIRouter()


def _principal_for(request: Request) -> Principal | None:
    with Session(get_engine()) as s:
        acct = account_from_cookie(s, request.cookies.get(COOKIE, ""))
        if acct is None and not get_settings().site_password:
            acct = ensure_owner(s)  # local use without a password: the owner
            s.commit()
        return Principal(acct.id, acct.name, acct.role) if acct else None


def _refuse_guest(request: Request) -> object:
    msg = "This part of the site (Data management) is for the owner only."
    if request.headers.get("HX-Request") or request.url.path.startswith("/api/"):
        return PlainTextResponse(msg, status_code=403)
    from app.web.routes import templates

    return templates.TemplateResponse(request, "error_status.html", {"title": "Owner only", "message": msg},
                                      status_code=403)  # fmt: skip


def _back(request: Request) -> str:
    ref = urlsplit(request.headers.get("referer", ""))
    if ref.netloc and ref.netloc != request.url.netloc:
        return "/"
    return local_path(ref.path + (f"?{ref.query}" if ref.query else ""), "/") if ref.path else "/"


async def _capture(request: Request, p: Principal):
    with Session(get_engine()) as s:
        sub = await guest_input.capture(request, s, p.id, p.name)
        sub_id = sub.id
    wants_json = (request.url.path.startswith("/api/") or "application/json" in request.headers.get("accept", "")
                  or request.headers.get("content-type", "").startswith("application/json")
                  or request.url.path.startswith("/site-feedback"))  # fmt: skip
    if wants_json:
        return JSONResponse({"ok": True, "review": True, "id": f"r{sub_id}", "message": guest_input.MESSAGE,
                             "state": "pending"})  # fmt: skip
    if request.headers.get("HX-Request"):
        return HTMLResponse(f'<p class="banner" role="status">{html.escape(guest_input.MESSAGE)}</p>')
    resp = RedirectResponse(_back(request), status_code=303)
    resp.set_cookie(FLASH, "review", max_age=120, httponly=True, samesite="lax", secure=request.url.scheme == "https")
    return resp


class PasswordGate(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        replay = request.scope.get(REPLAY)
        if replay:  # the owner approved a guest item: the stored request runs as the owner's own
            request.state.principal = Principal(0, str(replay.get("author") or "Guest"), OWNER)
            return await call_next(request)
        if access.is_open(path):
            request.state.principal = None
            return await call_next(request)
        p = _principal_for(request)
        if p is None:
            if request.headers.get("HX-Request") or path.startswith("/api/") or request.method not in ("GET", "HEAD"):
                return PlainTextResponse("Sign in required", status_code=401)
            target = path + (f"?{request.url.query}" if request.url.query else "")
            return RedirectResponse(f"/login?next={quote(target)}", status_code=303)
        request.state.principal = p
        if p.is_guest:
            if access.owner_only(path, request.method):
                return _refuse_guest(request)
            if request.method not in access.SAFE_METHODS and not guest_input.is_compute_only(path):
                return await _capture(request, p)
        resp = await call_next(request)
        if request.cookies.get(FLASH) and request.method == "GET" and resp.headers.get("content-type", "").startswith(
            "text/html"
        ):
            resp.delete_cookie(FLASH)
        return resp


def _safe_next(next_url: str) -> str:
    return local_path(next_url, "/")


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>Sign in – BizDev</title>
<link rel="stylesheet" href="/static/vendor/pico.min.css"><link rel="stylesheet" href="/static/app.css"></head>
<body><main class="container auth-page">
<h1>BizDev</h1>{error}
{password}<button type="button" class="secondary" id="passkey-login" data-next="{next}">Sign in with a passkey</button>
<p class="small auth-first">First time? Sign in with your password once, then add a passkey under My passkeys.
Guests: use the invite link you received.</p>
<p class="small muted" id="auth-msg" aria-live="polite"></p>
<p class="small muted">A passkey is a sign-in key kept by your phone or computer (unlocked with your fingerprint,
face or
 PIN). No password to remember.</p>
</main><script src="/static/auth.js" defer></script></body></html>"""


PASSWORD_FORM = """<form method="post" action="/login" id="pw-form" data-pow>
<input type="hidden" name="next" value="{next}">
<input type="hidden" name="pow_challenge"><input type="hidden" name="pow_nonce">
<input type="password" name="password" placeholder="Password" autocomplete="current-password" aria-label="Password"
 required autofocus>
<button type="submit">Sign in</button></form>
<p class="auth-or small muted">or</p>
"""


def _password_allowed() -> bool:
    with Session(get_engine()) as s:
        return stepup.password_allowed(s)


def _page(error: str = "", next_url: str = "/", status: int = 200) -> HTMLResponse:
    err = f'<p class="banner" role="alert">{html.escape(error)}</p>' if error else ""
    nxt = html.escape(_safe_next(next_url), quote=True)
    pw = PASSWORD_FORM.format(next=nxt) if _password_allowed() else ""
    return HTMLResponse(PAGE.format(error=err, password=pw, next=nxt), status_code=status)


def password_failed(ip: str) -> None:
    """A wrong password: counted for the lock, and the owner is told when the address gets locked."""
    if guard.failed(ip, "password"):
        notify.alert(f"Password sign-in locked for 15 minutes after repeated failures from address {ip}.")


@router.get("/login", response_class=HTMLResponse)
def login_page(next: str = "/"):
    return _page(next_url=next)


@router.get("/login/pow")
def login_pow():
    """A fresh proof-of-work challenge for the sign-in and invite pages (valid 5 minutes, works once)."""
    return JSONResponse(pow_issue(), headers={"Cache-Control": "no-store"})


@router.post("/login")
async def login(request: Request, password: str = Form(""), next: str = Form("/"), pow_challenge: str = Form(""),
                pow_nonce: str = Form("")):  # fmt: skip
    s = get_settings()
    ip = client_ip(request)
    why = guard.refuse(ip)
    if why:
        return _page(why, next, 429)
    await asyncio.sleep(guard.slowdown())
    with Session(get_engine()) as db:
        if not pow_check(db, pow_challenge, pow_nonce):
            return _page("The browser check did not finish. Wait a moment and press Sign in again.", next, 400)
        if not s.site_password:
            return RedirectResponse(_safe_next(next), status_code=303)
        if not stepup.password_allowed(db):
            guard.failed(ip, "password-off")
            return _page("Password sign-in is switched off. Sign in with a passkey.", next, 403)
        if _same(password, s.site_password):
            owner = ensure_owner(db)
            db.commit()
            resp = RedirectResponse(_safe_next(next), status_code=303)
            set_login_cookie(resp, request, owner)
            stepup.set_confirmed(resp, request, owner)
            notify.alert(f"The owner signed in with the password (address {ip}).")
            return resp
    password_failed(ip)
    await asyncio.sleep(FAIL_DELAY)
    return _page("Wrong password.", next, 401)


def _same(a: str, b: str) -> bool:
    import hmac

    return hmac.compare_digest(a.encode(), b.encode())


@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE)
    resp.delete_cookie(stepup.STEPUP_COOKIE)
    return resp


# --- owner confirmation (step-up) ------------------------------------------------------------------------------------
@router.get("/owner/confirm", response_class=HTMLResponse)
def confirm_page(request: Request, next: str = "/manage/people", msg: str = "",
                 session: Session = Depends(get_session)):  # fmt: skip
    from app.web.routes import templates

    p = principal(request)
    if p is None or not p.is_owner:
        return PlainTextResponse("Only the owner can do this.", status_code=403)
    ctx = {"next": _safe_next(next), "msg": msg[:200], "password": stepup.password_allowed(session),
           "has_passkeys": stepup.owner_passkey_count(session, p.id) > 0,
           "left": stepup.seconds_left(request, session)}  # fmt: skip
    return templates.TemplateResponse(request, "manage/confirm.html", ctx, headers={"Cache-Control": "no-store"})


@router.post("/owner/confirm/password")
async def confirm_password(request: Request, password: str = Form(""), next: str = Form("/manage/people")):
    """Confirm with the password (only while password sign-in is allowed)."""
    p = principal(request)
    if p is None or not p.is_owner:
        return PlainTextResponse("Only the owner can do this.", status_code=403)
    ip = client_ip(request)
    why = guard.refuse(ip)
    if why:
        return RedirectResponse(stepup.confirm_url(next, why), status_code=303)
    s = get_settings()
    with Session(get_engine()) as db:
        if not stepup.password_allowed(db) or not s.site_password:
            return RedirectResponse(stepup.confirm_url(next, "Password sign-in is switched off. Use a passkey."),
                                    status_code=303)  # fmt: skip
        if _same(password, s.site_password):
            owner = db.get(Account, p.id)
            resp = RedirectResponse(_safe_next(next), status_code=303)
            if owner is not None:
                stepup.set_confirmed(resp, request, owner)
            return resp
    password_failed(ip)
    await asyncio.sleep(FAIL_DELAY)
    return RedirectResponse(stepup.confirm_url(next, "Wrong password."), status_code=303)
