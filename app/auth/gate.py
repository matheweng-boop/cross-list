"""Single-password gate for a hosted, single-user site.

Off when CROSSLIST_SITE_PASSWORD is empty (local use). Passkey sign-in with user
accounts replaces this later; get_current_user stays the place that knows who is in.
"""

import asyncio
import hashlib
import hmac
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.config import get_settings

COOKIE = "crosslist_auth"
MAX_AGE = 30 * 24 * 3600
OPEN_PATHS = ("/login", "/healthz", "/static/")

router = APIRouter()


def _token() -> str:
    s = get_settings()
    key = (s.secret_key or s.site_password).encode()
    # Changing the password signs everyone out.
    return hmac.new(key, b"crosslist:" + s.site_password.encode(), hashlib.sha256).hexdigest()


def is_signed_in(request: Request) -> bool:
    return hmac.compare_digest(request.cookies.get(COOKIE, ""), _token())


class PasswordGate(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not get_settings().site_password or request.url.path.startswith(OPEN_PATHS) or is_signed_in(request):
            return await call_next(request)
        if request.headers.get("HX-Request") or request.url.path.startswith("/api/"):
            return PlainTextResponse("Sign in required", status_code=401)
        target = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(f"/login?next={quote(target)}", status_code=303)


def _safe_next(next_url: str) -> str:
    return next_url if next_url.startswith("/") and not next_url.startswith("//") else "/"


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Sign in – BizDev</title>
<link rel="stylesheet" href="/static/vendor/pico.min.css"><link rel="stylesheet" href="/static/app.css"></head>
<body><main class="container" style="max-width:24rem;padding-top:15vh">
<h1>BizDev</h1>{error}
<form method="post" action="/login"><input type="hidden" name="next" value="{next}">
<input type="password" name="password" placeholder="Password" autocomplete="current-password" required autofocus>
<button type="submit">Sign in</button></form></main></body></html>"""


@router.get("/login", response_class=HTMLResponse)
def login_page(next: str = "/"):
    return PAGE.format(error="", next=_safe_next(next).replace('"', "%22"))


@router.post("/login")
async def login(request: Request, password: str = Form(""), next: str = Form("/")):
    s = get_settings()
    if not s.site_password or hmac.compare_digest(password.encode(), s.site_password.encode()):
        resp = RedirectResponse(_safe_next(next), status_code=303)
        resp.set_cookie(
            COOKIE, _token(), max_age=MAX_AGE, httponly=True, samesite="lax", secure=request.url.scheme == "https"
        )
        return resp
    await asyncio.sleep(1)  # slow down guessing
    error = '<p class="banner">Wrong password.</p>'
    return HTMLResponse(PAGE.format(error=error, next=_safe_next(next).replace('"', "%22")), status_code=401)


@router.get("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE)
    return resp
