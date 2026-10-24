"""Passkeys (WebAuthn, py_webauthn): sign in without a username, a guest's first passkey from an invite link, and
the owner's own passkeys.

Challenges are random, stored server-side (only the SHA-256 of a nonce kept in a cookie of this browser), work once and
expire after 5 minutes. Passkeys are discoverable (resident) credentials with user verification "preferred".
"""

import asyncio
import hashlib
import hmac
import html
import secrets
from datetime import timedelta
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.auth import stepup
from app.auth.session import (
    GUEST,
    OWNER,
    client_ip,
    guard,
    new_handle,
    now,
    pow_check,
    principal,
    set_login_cookie,
)
from app.config import get_settings
from app.db import get_engine, get_session
from app.models import Account, Invite, PasskeyCredential, WebauthnChallenge, aware
from app.services import notify
from app.web.urls import local_path

router = APIRouter()
WA_COOKIE = "crosslist_wa"
CHALLENGE_TTL = 300
MAX_OPEN_CHALLENGES = 1000
INVITE_DAYS = 7


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_invite(session: Session, name: str, note: str = "") -> tuple[Invite, str]:
    """A one-time invite; the token is returned once and only its SHA-256 is stored."""
    token = secrets.token_urlsafe(32)
    inv = Invite(token_sha256=token_hash(token), name=name.strip()[:100] or "Guest", note=note.strip()[:2000] or None,
                 expires_at=now() + timedelta(days=INVITE_DAYS))  # fmt: skip
    session.add(inv)
    session.flush()
    return inv, token


def open_invites(session: Session) -> int:
    """Invite links that are unused and unexpired."""
    return session.scalar(select(func.count()).select_from(Invite)
                          .where(Invite.used_at.is_(None), Invite.expires_at > now())) or 0  # fmt: skip


def active_guests(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(Account)
                          .where(Account.role == GUEST, Account.disabled.is_(False))) or 0  # fmt: skip


def valid_invite(session: Session, token: str) -> Invite | None:
    digest = token_hash(token)
    inv = session.scalar(select(Invite).where(Invite.token_sha256 == digest))
    if inv is None or not hmac.compare_digest(inv.token_sha256, digest):
        return None
    if inv.used_at is not None or aware(inv.expires_at) <= now():
        return None
    return inv


# --- challenges ------------------------------------------------------------------------------------------------------
def _store_challenge(session: Session, resp: Response, request: Request, purpose: str, **bind) -> bytes:
    session.execute(delete(WebauthnChallenge).where(WebauthnChallenge.expires_at < now()))
    if old := request.cookies.get(WA_COOKIE):  # the pages fetch options ahead and refresh them: one per browser
        session.execute(delete(WebauthnChallenge).where(WebauthnChallenge.nonce_sha256 == token_hash(old)))
    if session.scalar(select(func.count()).select_from(WebauthnChallenge)) >= MAX_OPEN_CHALLENGES:
        raise HTTPException(429, "Too many sign-ins in progress. Try again in a few minutes.")
    nonce = secrets.token_urlsafe(32)
    challenge = secrets.token_bytes(32)
    session.add(WebauthnChallenge(nonce_sha256=token_hash(nonce), challenge=challenge, purpose=purpose,
                                  expires_at=now() + timedelta(seconds=CHALLENGE_TTL), **bind))  # fmt: skip
    session.commit()
    resp.set_cookie(WA_COOKIE, nonce, max_age=CHALLENGE_TTL, httponly=True, samesite="strict",
                    secure=request.url.scheme == "https", path="/")  # fmt: skip
    return challenge


def _take_challenge(session: Session, request: Request, purpose: str) -> WebauthnChallenge | None:
    """The challenge this browser was given, removed at once (single use); None when missing or expired."""
    nonce = request.cookies.get(WA_COOKIE, "")
    if not nonce:
        return None
    row = session.scalar(select(WebauthnChallenge).where(WebauthnChallenge.nonce_sha256 == token_hash(nonce)))
    if row is None:
        return None
    session.delete(row)
    session.commit()
    if row.purpose != purpose or aware(row.expires_at) <= now():
        return None
    return row


def _json_options(options, resp: Response) -> Response:
    resp.body = options_to_json(options).encode()
    resp.headers["content-length"] = str(len(resp.body))
    resp.headers["cache-control"] = "no-store"
    return resp


def _fail(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "detail": message}, status_code=status)


async def _body(request: Request) -> dict:
    try:
        data = await request.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _creation_options(rp_handle: str, name: str, exclude: list[PasskeyCredential], challenge: bytes):
    s = get_settings()
    return generate_registration_options(
        rp_id=s.rp_id, rp_name="BizDev", user_id=base64url_to_bytes(rp_handle), user_name=name, user_display_name=name,
        challenge=challenge, timeout=CHALLENGE_TTL * 1000,
        authenticator_selection=AuthenticatorSelectionCriteria(resident_key=ResidentKeyRequirement.REQUIRED,
                                                               user_verification=UserVerificationRequirement.PREFERRED),
        exclude_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id)) for c in exclude],
    )  # fmt: skip


def _register(session: Session, row: WebauthnChallenge, credential: dict, account: Account) -> PasskeyCredential:
    s = get_settings()
    v = verify_registration_response(credential=credential, expected_challenge=row.challenge, expected_rp_id=s.rp_id,
                                     expected_origin=s.origin, require_user_verification=False)  # fmt: skip
    cred_id = bytes_to_base64url(v.credential_id)
    if session.scalar(select(PasskeyCredential).where(PasskeyCredential.credential_id == cred_id)) is not None:
        raise ValueError("This passkey is already registered.")
    transports = (credential.get("response") or {}).get("transports")
    pk = PasskeyCredential(account=account, credential_id=cred_id, public_key=v.credential_public_key,
                           sign_count=v.sign_count, transports=transports if isinstance(transports, list) else None)
    session.add(pk)
    return pk


async def _limited(request: Request) -> JSONResponse | None:
    why = guard.refuse(client_ip(request))
    if why:
        return _fail(why, 429)
    await asyncio.sleep(guard.slowdown())
    return None


# --- sign in with a passkey (owner or guest), no username -------------------------------------------------------------
@router.post("/passkey/login/options")
async def login_options(request: Request):
    if (r := await _limited(request)) is not None:
        return r
    data = await _body(request)
    with Session(get_engine()) as s:
        if not pow_check(s, str(data.get("pow_challenge") or ""), str(data.get("pow_nonce") or "")):
            return _fail("The browser check did not finish. Try again.")
        resp = Response(media_type="application/json")
        challenge = _store_challenge(s, resp, request, "login")
    opts = generate_authentication_options(rp_id=get_settings().rp_id, challenge=challenge,
                                           timeout=CHALLENGE_TTL * 1000,
                                           user_verification=UserVerificationRequirement.PREFERRED)  # fmt: skip
    return _json_options(opts, resp)


@router.post("/passkey/login/verify")
async def login_verify(request: Request):
    if (r := await _limited(request)) is not None:
        return r
    ip = client_ip(request)
    data = await _body(request)
    credential = data.get("credential")
    with Session(get_engine()) as s:
        row = _take_challenge(s, request, "login")
        if row is None or not isinstance(credential, dict):
            guard.failed(ip, "passkey")
            return _fail("The sign-in took too long or was already used. Try again.")
        cred_id = str(credential.get("rawId") or credential.get("id") or "")
        pk = s.scalar(select(PasskeyCredential).where(PasskeyCredential.credential_id == cred_id))
        if pk is None or pk.account.disabled:
            guard.failed(ip, "passkey")
            return _fail("This passkey is not known here (or was removed). Ask the owner for a new invite.", 401)
        handle = (credential.get("response") or {}).get("userHandle")
        if handle and handle.rstrip("=") != pk.account.handle.rstrip("="):
            guard.failed(ip, "passkey")
            return _fail("This passkey does not belong to the account it names.", 401)
        s_ = get_settings()
        try:
            v = verify_authentication_response(credential=credential, expected_challenge=row.challenge,
                                               expected_rp_id=s_.rp_id, expected_origin=s_.origin,
                                               credential_public_key=pk.public_key,
                                               credential_current_sign_count=pk.sign_count,
                                               require_user_verification=False)  # fmt: skip
        except Exception:
            guard.failed(ip, "passkey")
            return _fail("The passkey could not be checked. Try again.", 401)
        if pk.sign_count and v.new_sign_count and v.new_sign_count <= pk.sign_count:
            guard.failed(ip, "passkey-counter")
            return _fail("This passkey looks copied (its counter went back). Sign-in refused.", 401)
        pk.sign_count, pk.last_used_at = v.new_sign_count, now()
        account = pk.account
        s.commit()
        resp = JSONResponse({"ok": True, "next": local_path(str(data.get("next") or "/"), "/")})
        set_login_cookie(resp, request, account)
        stepup.set_confirmed(resp, request, account)
        resp.delete_cookie(WA_COOKIE)
        return resp


# --- invite: a guest creates their first passkey ---------------------------------------------------------------------
INVITE_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>Invitation – BizDev</title>
<link rel="stylesheet" href="/static/vendor/pico.min.css"><link rel="stylesheet" href="/static/app.css"></head>
<body><main class="container auth-page">
<h1>BizDev</h1>{body}
</main><script src="/static/auth.js" defer></script></body></html>"""


def _invite_page(body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(INVITE_PAGE.format(body=body), status_code=status, headers={"Cache-Control": "no-store"})


GONE = ('<p>This invite link is no longer valid: it was used already, it expired (links work 7 days) or it was '
        'cancelled.</p><p>Ask the owner for a new link.</p>')  # fmt: skip


@router.get("/invite/{token}", response_class=HTMLResponse)
def invite_page(token: str, request: Request):
    with Session(get_engine()) as s:
        inv = valid_invite(s, token)
        if inv is None:
            guard.failed(client_ip(request), "invite")
            return _invite_page(GONE, 404)
        name = html.escape(inv.name)
    body = f"""<p>Hello {name}, you are invited to BizDev.</p>
<p>To sign in you create a <b>passkey</b>: a sign-in key that your phone or computer keeps for you and unlocks with
your fingerprint, face or screen PIN. There is no password to remember, and the key never leaves your device.</p>
<p class="small muted">As a guest you can read every page and use the comment, vote, request and feedback fields.
The owner reviews what you send before it is used.</p>
<button type="button" id="invite-create" data-token="{html.escape(token, quote=True)}">Create my passkey</button>
<p class="small muted" id="auth-msg" aria-live="polite"></p>
<p class="small muted">This link works once and for 7 days. Later, sign in at <a href="/login">the sign-in page</a> with
“Sign in with a passkey”.</p>"""
    return _invite_page(body)


@router.post("/invite/{token}/options")
async def invite_options(token: str, request: Request):
    if (r := await _limited(request)) is not None:
        return r
    data = await _body(request)
    with Session(get_engine()) as s:
        if not pow_check(s, str(data.get("pow_challenge") or ""), str(data.get("pow_nonce") or "")):
            return _fail("The browser check did not finish. Try again.")
        inv = valid_invite(s, token)
        if inv is None:
            guard.failed(client_ip(request), "invite")
            return _fail("This invite link is no longer valid. Ask the owner for a new one.", 404)
        handle, name = new_handle(), inv.name
        resp = Response(media_type="application/json")
        challenge = _store_challenge(s, resp, request, "invite", invite_id=inv.id, handle=handle)
    opts = _creation_options(handle, name, [], challenge)
    return _json_options(opts, resp)


@router.post("/invite/{token}/verify")
async def invite_verify(token: str, request: Request):
    if (r := await _limited(request)) is not None:
        return r
    ip = client_ip(request)
    data = await _body(request)
    credential = data.get("credential")
    with Session(get_engine()) as s:
        row = _take_challenge(s, request, "invite")
        inv = valid_invite(s, token)
        if row is None or inv is None or row.invite_id != inv.id or not row.handle or not isinstance(credential, dict):
            guard.failed(ip, "invite")
            return _fail("This invite link is no longer valid, or the step took too long. Reload the page.", 400)
        if active_guests(s) >= get_settings().max_guests:
            return _fail("The guest list is full for now. Ask the owner to make room and send a new link.", 409)
        account = Account(name=inv.name, role="guest", handle=row.handle)
        s.add(account)
        try:
            _register(s, row, credential, account)
        except Exception as e:
            s.rollback()
            guard.failed(ip, "invite")
            msg = str(e) if isinstance(e, ValueError) and "already" in str(e) else "The passkey could not be created."
            return _fail(msg + " Try again.", 400)
        claimed = s.execute(update(Invite).where(Invite.id == inv.id, Invite.used_at.is_(None))
                            .values(used_at=now())).rowcount  # fmt: skip
        if not claimed:
            s.rollback()
            return _fail("This invite link was just used. Ask the owner for a new one.", 409)
        s.flush()
        s.execute(update(Invite).where(Invite.id == inv.id).values(account_id=account.id))
        s.commit()
        notify.alert(f"Guest {account.name} used their invite and registered a passkey.")
        resp = JSONResponse({"ok": True, "next": "/"})
        set_login_cookie(resp, request, account)
        resp.delete_cookie(WA_COOKIE)
        return resp


# --- the owner's own passkeys ----------------------------------------------------------------------------------------
def _owner(request: Request, session: Session) -> Account:
    p = principal(request)
    if p is None or p.role != OWNER or not p.id:
        raise HTTPException(403, "Only the owner can manage the owner's passkeys.")
    acct = session.get(Account, p.id)
    if acct is None:
        raise HTTPException(403, "Sign in again.")
    return acct


@router.get("/owner/passkeys", response_class=HTMLResponse)
def owner_passkeys(request: Request, msg: str = "", session: Session = Depends(get_session)):
    from app.web.routes import templates

    acct = _owner(request, session)
    ctx = {"account": acct, "keys": acct.passkeys, "msg": msg[:200], "locked": bool(get_settings().site_password),
           "pw_switch": stepup.password_switch(session), "pw_forced": stepup.password_forced(),
           "pw_why_not": stepup.why_cannot_switch_off(session, acct.id),
           "confirmed": stepup.seconds_left(request, session)}  # fmt: skip
    return templates.TemplateResponse(request, "manage/passkeys.html", ctx)


@router.post("/owner/passkeys/options")
def owner_options(request: Request, session: Session = Depends(get_session)):
    acct = _owner(request, session)
    resp = Response(media_type="application/json")
    challenge = _store_challenge(session, resp, request, "owner", account_id=acct.id)
    opts = _creation_options(acct.handle, f"{acct.name} (BizDev owner)", list(acct.passkeys), challenge)
    return _json_options(opts, resp)


@router.post("/owner/passkeys/verify")
async def owner_verify(request: Request, session: Session = Depends(get_session)):
    acct = _owner(request, session)
    data = await _body(request)
    credential = data.get("credential")
    row = _take_challenge(session, request, "owner")
    if row is None or row.account_id != acct.id or not isinstance(credential, dict):
        return _fail("The step took too long. Try again.")
    try:
        _register(session, row, credential, acct)
    except Exception as e:
        session.rollback()
        return _fail((str(e) if isinstance(e, ValueError) else "The passkey could not be added.") + " Try again.")
    session.commit()
    notify.alert(f"The owner added a passkey (now {stepup.owner_passkey_count(session, acct.id)}).")
    resp = JSONResponse({"ok": True, "next": "/owner/passkeys?msg=Passkey+added"})
    resp.delete_cookie(WA_COOKIE)
    return resp


@router.post("/owner/passkeys/{key_id:int}/delete")
def owner_delete(key_id: int, request: Request, session: Session = Depends(get_session)):
    acct = _owner(request, session)
    pk = session.get(PasskeyCredential, key_id)
    if pk is None or pk.account_id != acct.id:
        raise HTTPException(404, "Passkey not found")
    if (r := stepup.require(request, session, "/owner/passkeys")) is not None:
        return r
    left = len(acct.passkeys) - 1
    if not stepup.password_switch(session) and left < stepup.MIN_PASSKEYS_WITHOUT_PASSWORD:
        msg = ("Password sign-in is off, so you need at least 2 passkeys. Add another passkey or switch password "
               "sign-in on first.")  # fmt: skip
        return RedirectResponse(f"/owner/passkeys?msg={quote(msg)}", status_code=303)
    session.delete(pk)
    session.commit()
    notify.alert(f"The owner removed a passkey (now {left}).")
    return RedirectResponse("/owner/passkeys?msg=Passkey+removed", status_code=303)


@router.post("/owner/password-login")
def owner_password_switch(request: Request, allow: str = Form(...), session: Session = Depends(get_session)):
    """Allow or refuse password sign-in (needs a fresh confirmation; off only with at least 2 passkeys)."""
    acct = _owner(request, session)
    if (r := stepup.require(request, session, "/owner/passkeys")) is not None:
        return r
    on = allow == "on"
    if not on and (why := stepup.why_cannot_switch_off(session, acct.id)):
        return RedirectResponse(f"/owner/passkeys?msg={quote(why)}", status_code=303)
    if on == stepup.password_switch(session):
        return RedirectResponse("/owner/passkeys?msg=Nothing+changed", status_code=303)
    stepup.set_password_switch(session, on)
    session.commit()
    state = "on" if on else "off"
    notify.alert(f"The owner switched password sign-in {state}.")
    return RedirectResponse(f"/owner/passkeys?msg=Password+sign-in+switched+{state}", status_code=303)


# --- owner confirmation with a passkey (step-up) ---------------------------------------------------------------------
@router.post("/owner/confirm/options")
def confirm_options(request: Request, session: Session = Depends(get_session)):
    acct = _owner(request, session)
    if not acct.passkeys:
        return _fail("You have no passkey yet. Confirm with the password, or add a passkey first.")
    resp = Response(media_type="application/json")
    challenge = _store_challenge(session, resp, request, "confirm", account_id=acct.id)
    opts = generate_authentication_options(
        rp_id=get_settings().rp_id, challenge=challenge, timeout=CHALLENGE_TTL * 1000,
        user_verification=UserVerificationRequirement.PREFERRED,
        allow_credentials=[PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
                           for c in acct.passkeys],
    )  # fmt: skip
    return _json_options(opts, resp)


@router.post("/owner/confirm/verify")
async def confirm_verify(request: Request, session: Session = Depends(get_session)):
    acct = _owner(request, session)
    ip = client_ip(request)
    if why := guard.refuse(ip):
        return _fail(why, 429)
    data = await _body(request)
    credential = data.get("credential")
    row = _take_challenge(session, request, "confirm")
    if row is None or row.account_id != acct.id or not isinstance(credential, dict):
        return _fail("The step took too long. Try again.")
    cred_id = str(credential.get("rawId") or credential.get("id") or "")
    pk = session.scalar(select(PasskeyCredential).where(PasskeyCredential.credential_id == cred_id))
    if pk is None or pk.account_id != acct.id:
        guard.failed(ip, "confirm")
        return _fail("This passkey is not one of yours.", 401)
    s_ = get_settings()
    try:
        v = verify_authentication_response(credential=credential, expected_challenge=row.challenge,
                                           expected_rp_id=s_.rp_id, expected_origin=s_.origin,
                                           credential_public_key=pk.public_key,
                                           credential_current_sign_count=pk.sign_count,
                                           require_user_verification=False)  # fmt: skip
    except Exception:
        guard.failed(ip, "confirm")
        return _fail("The passkey could not be checked. Try again.", 401)
    if pk.sign_count and v.new_sign_count and v.new_sign_count <= pk.sign_count:
        guard.failed(ip, "confirm-counter")
        return _fail("This passkey looks copied (its counter went back). Refused.", 401)
    pk.sign_count, pk.last_used_at = v.new_sign_count, now()
    session.commit()
    resp = JSONResponse({"ok": True, "next": local_path(str(data.get("next") or "/manage/people"), "/")})
    stepup.set_confirmed(resp, request, acct)
    resp.delete_cookie(WA_COOKIE)
    return resp
