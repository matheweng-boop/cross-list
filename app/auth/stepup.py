"""Owner confirmation ("step-up") and the owner's password sign-in switch.

Sensitive owner actions (creating an invite, removing a passkey, removing all guests, switching password sign-in)
need a fresh confirmation: a passkey or the password within the last 5 minutes. The confirmation is a separate signed
cookie that lives 5 minutes and names the owner's account and session version, so a stolen session cookie alone is not
enough. Signing in as the owner counts as a confirmation.

Password sign-in can be switched off on the site (only with at least 2 owner passkeys).
CROSSLIST_PASSWORD_LOGIN=force-on turns it back on from the Render dashboard (the way back in if all passkeys are lost).
"""

import hashlib
import hmac
import time
from urllib.parse import quote

from fastapi import Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.session import OWNER, principal, site_key
from app.config import get_settings
from app.models import Account, PasskeyCredential, SiteSetting
from app.web.urls import local_path

STEPUP_COOKIE = "crosslist_confirm"
STEPUP_TTL = 300
PASSWORD_KEY = "password_login"
FORCE_ON = "force-on"


def _key() -> bytes | None:
    base = site_key()
    return hmac.new(base, b"crosslist:stepup", hashlib.sha256).digest() if base else None


def _sign(body: str, key: bytes) -> str:
    return hmac.new(key, body.encode(), hashlib.sha256).hexdigest()


def set_confirmed(resp, request: Request, account: Account) -> None:
    """Mark the owner as freshly confirmed in this browser for 5 minutes."""
    key = _key()
    if key is None or account.role != OWNER:
        return
    body = f"u1.{account.id}.{account.session_version}.{int(time.time())}"
    resp.set_cookie(STEPUP_COOKIE, f"{body}.{_sign(body, key)}", max_age=STEPUP_TTL, httponly=True, samesite="strict",
                    secure=request.url.scheme == "https", path="/")  # fmt: skip


def seconds_left(request: Request, session: Session) -> int:
    """How long the owner's last confirmation still counts (0: confirm again). Local use without a password: always."""
    if not get_settings().site_password:
        return STEPUP_TTL
    p = principal(request)
    key = _key()
    value = request.cookies.get(STEPUP_COOKIE, "")
    if p is None or not p.is_owner or key is None or not value:
        return 0
    body, _, sig = value.rpartition(".")
    if not body or not hmac.compare_digest(sig, _sign(body, key)):
        return 0
    parts = body.split(".")
    if len(parts) != 4 or parts[0] != "u1":
        return 0
    try:
        aid, sv, issued = int(parts[1]), int(parts[2]), int(parts[3])
    except ValueError:
        return 0
    acct = session.get(Account, aid)
    if aid != p.id or acct is None or acct.disabled or acct.role != OWNER or acct.session_version != sv:
        return 0
    age = time.time() - issued
    return int(STEPUP_TTL - age) if 0 <= age < STEPUP_TTL else 0


def confirm_url(back: str, why: str = "") -> str:
    url = f"/owner/confirm?next={quote(local_path(back, '/'))}"
    return url + (f"&msg={quote(why)}" if why else "")


def require(request: Request, session: Session, back: str) -> RedirectResponse | None:
    """None when the owner confirmed in the last 5 minutes, else a redirect to the confirmation page."""
    if seconds_left(request, session) > 0:
        return None
    return RedirectResponse(confirm_url(back, "Confirm it is you first (needed at most every 5 minutes)."),
                            status_code=303)  # fmt: skip


# --- password sign-in switch -----------------------------------------------------------------------------------------
def password_forced() -> bool:
    return get_settings().password_login.strip().lower() == FORCE_ON


def password_switch(session: Session) -> bool:
    """The owner's choice on the site (default: allowed)."""
    row = session.get(SiteSetting, PASSWORD_KEY)
    return row is None or row.value != "off"


def password_allowed(session: Session) -> bool:
    """Whether password sign-in works now: the owner's choice, or forced on by CROSSLIST_PASSWORD_LOGIN=force-on."""
    return password_forced() or password_switch(session)


def set_password_switch(session: Session, allowed: bool) -> None:
    row = session.get(SiteSetting, PASSWORD_KEY)
    if row is None:
        session.add(SiteSetting(key=PASSWORD_KEY, value="on" if allowed else "off"))
    else:
        row.value = "on" if allowed else "off"


def owner_passkey_count(session: Session, account_id: int) -> int:
    return session.scalar(select(func.count()).select_from(PasskeyCredential)
                          .where(PasskeyCredential.account_id == account_id)) or 0  # fmt: skip


MIN_PASSKEYS_WITHOUT_PASSWORD = 2


def why_cannot_switch_off(session: Session, account_id: int) -> str:
    n = owner_passkey_count(session, account_id)
    if n >= MIN_PASSKEYS_WITHOUT_PASSWORD:
        return ""
    return (f"Password sign-in can be switched off only when you have at least {MIN_PASSKEYS_WITHOUT_PASSWORD} "
            f"passkeys (you have {n}), so that losing one device does not lock you out.")  # fmt: skip
