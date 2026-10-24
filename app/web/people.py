"""Data management > People & invites (invite links, guests and their passkeys) and Guest input (the owner's review
of everything guests sent). Owner only: the gate refuses guests on /manage."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.auth import stepup
from app.auth.passkeys import active_guests, new_invite, open_invites
from app.auth.session import GUEST, now
from app.config import get_settings
from app.db import get_engine, get_session
from app.models import Account, ExternalSubmission, Invite, PasskeyCredential, aware
from app.services import guest_input, notify
from app.web.routes import templates

router = APIRouter()


def _limit_reached(session: Session) -> str:
    """Why no new invite can be made now ("" when one can)."""
    s = get_settings()
    n_open, n_guests = open_invites(session), active_guests(session)
    if n_open >= s.max_open_invites:
        return (f"Limit reached: {n_open} invite links are still open (at most {s.max_open_invites}). Wait until one "
                "is used or expires, or cancel one.")  # fmt: skip
    if n_guests >= s.max_guests:
        return f"Limit reached: there are {n_guests} guests (at most {s.max_guests}). Remove someone first."
    if n_guests + n_open >= s.max_guests:
        return (f"Limit reached: {n_guests} guests and {n_open} open invite links already fill the {s.max_guests} "
                "guest places. Cancel an invite or remove a guest first.")  # fmt: skip
    return ""


def _people_ctx(session: Session, request: Request | None = None) -> dict:
    guests = session.scalars(
        select(Account).where(Account.role == "guest").order_by(Account.disabled, Account.created_at)
    ).all()
    invites = session.scalars(select(Invite).order_by(Invite.created_at.desc()).limit(50)).all()
    t = now()
    rows = [{"i": i, "state": "used" if i.used_at else ("expired" if aware(i.expires_at) <= t else "open")}
            for i in invites]  # fmt: skip
    s = get_settings()
    return {"guests": guests, "invites": rows, "n_open": open_invites(session), "n_guests": active_guests(session),
            "max_open": s.max_open_invites, "max_guests": s.max_guests, "limit_msg": _limit_reached(session),
            "confirmed": stepup.seconds_left(request, session) if request else 0}  # fmt: skip


@router.get("/manage/people", response_class=HTMLResponse)
def people(request: Request, msg: str = "", name: str = "", session: Session = Depends(get_session)):
    ctx = {**_people_ctx(session, request), "msg": msg[:300], "prefill": name[:100]}
    return templates.TemplateResponse(request, "manage/people.html", ctx)


@router.post("/manage/people/invite", response_class=HTMLResponse)
def invite(request: Request, name: str = Form(...), note: str = Form(""), session: Session = Depends(get_session)):
    """Creates the link and shows it once (only its SHA-256 is kept)."""
    if not name.strip():
        raise HTTPException(400, "Give the person's name")
    if (r := stepup.require(request, session, f"/manage/people?name={quote(name.strip()[:100])}")) is not None:
        return r
    if why := _limit_reached(session):
        return RedirectResponse(f"/manage/people?msg={quote(why)}", status_code=303)
    inv, token = new_invite(session, name, note)
    session.commit()
    notify.alert(f"Invite created for {inv.name}, valid until {aware(inv.expires_at):%Y-%m-%d %H:%M} UTC.")
    link = f"{str(request.base_url).rstrip('/')}/invite/{token}"
    ctx = {**_people_ctx(session, request), "msg": "", "new_link": link, "new_name": inv.name}
    return templates.TemplateResponse(request, "manage/people.html", ctx, headers={"Cache-Control": "no-store"})


@router.post("/manage/people/invites/{invite_id:int}/cancel")
def cancel_invite(invite_id: int, session: Session = Depends(get_session)):
    inv = session.get(Invite, invite_id)
    if inv is None:
        raise HTTPException(404, "Invite not found")
    if inv.used_at is None:
        inv.expires_at = now()
        session.commit()
    return RedirectResponse("/manage/people?msg=Invite+cancelled", status_code=303)


@router.post("/manage/people/{account_id:int}/remove")
def remove_guest(account_id: int, session: Session = Depends(get_session)):
    """Removes a guest: their passkeys are deleted and every session they have ends at once."""
    acct = session.get(Account, account_id)
    if acct is None or acct.role != "guest":
        raise HTTPException(404, "Guest not found")
    acct.disabled = True
    acct.session_version += 1
    acct.passkeys.clear()
    session.commit()
    notify.alert(f"The owner removed guest {acct.name}.")
    return RedirectResponse(f"/manage/people?msg={quote(acct.name + ' was removed')}", status_code=303)


@router.post("/manage/people/remove-all")
def remove_all_guests(request: Request, session: Session = Depends(get_session)):
    """Disables every guest, deletes their passkeys, cancels open invites and ends their sessions (one alert)."""
    if (r := stepup.require(request, session, "/manage/people")) is not None:
        return r
    t = now()
    guest_ids = select(Account.id).where(Account.role == GUEST)
    n_guests = active_guests(session)
    n_keys = session.execute(delete(PasskeyCredential).where(PasskeyCredential.account_id.in_(guest_ids))).rowcount
    session.execute(update(Account).where(Account.role == GUEST)
                    .values(disabled=True, session_version=Account.session_version + 1))  # fmt: skip
    n_inv = session.execute(update(Invite).where(Invite.used_at.is_(None), Invite.expires_at > t)
                            .values(expires_at=t)).rowcount  # fmt: skip
    session.commit()
    notify.alert(f"The owner removed all guests: {n_guests} signed out, {n_keys} passkeys deleted, "
                 f"{n_inv} open invites cancelled.")  # fmt: skip
    msg = (f"All guests removed: {n_guests} guests signed out, {n_keys} passkeys deleted, {n_inv} open invites "
           "cancelled.")  # fmt: skip
    return RedirectResponse(f"/manage/people?msg={quote(msg)}", status_code=303)


@router.get("/manage/guest-input", response_class=HTMLResponse)
def guest_input_page(request: Request, msg: str = "", session: Session = Depends(get_session)):
    pending = session.scalars(select(ExternalSubmission).where(ExternalSubmission.status.in_(("pending", "approving")))
                              .order_by(ExternalSubmission.created_at)).all()  # fmt: skip
    done = session.scalars(select(ExternalSubmission).where(ExternalSubmission.status.in_(("approved", "rejected")))
                           .order_by(ExternalSubmission.reviewed_at.desc()).limit(30)).all()  # fmt: skip
    ctx = {"pending": pending, "done": done, "shown": guest_input.shown, "msg": msg[:300]}
    return templates.TemplateResponse(request, "manage/guest_input.html", ctx)


@router.post("/manage/guest-input/{sub_id:int}")
async def review_guest_input(request: Request, sub_id: int, act: str = Form(...), note: str = Form("")):
    """Approve (replays the item through the owner's own route, with the guest's name) or reject (nothing changes)."""

    if act == "approve":
        _, msg = await guest_input.approve(request.app, lambda: Session(get_engine(), expire_on_commit=False), sub_id,
                                           note)  # fmt: skip
    elif act == "reject":
        with Session(get_engine()) as s:
            msg = "Rejected: nothing was changed." if guest_input.reject(s, sub_id, note) else "Already reviewed."
    else:
        raise HTTPException(400, "Unknown action")
    return RedirectResponse(f"/manage/guest-input?msg={quote(msg)}", status_code=303)
