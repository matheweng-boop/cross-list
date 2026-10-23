"""Data management > People & invites (invite links, guests and their passkeys) and Guest input (the owner's review
of everything guests sent). Owner only: the gate refuses guests on /manage."""

from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passkeys import new_invite
from app.auth.session import aware, now
from app.db import get_engine, get_session
from app.models import Account, ExternalSubmission, Invite
from app.services import guest_input
from app.web.routes import templates

router = APIRouter()


def _people_ctx(session: Session) -> dict:
    guests = session.scalars(select(Account).where(Account.role == "guest").order_by(Account.disabled,
                                                                                     Account.created_at)).all()
    invites = session.scalars(select(Invite).order_by(Invite.created_at.desc()).limit(50)).all()
    t = now()
    rows = [{"i": i, "state": "used" if i.used_at else ("expired" if aware(i.expires_at) <= t else "open")}
            for i in invites]  # fmt: skip
    return {"guests": guests, "invites": rows}


@router.get("/manage/people", response_class=HTMLResponse)
def people(request: Request, msg: str = "", session: Session = Depends(get_session)):
    return templates.TemplateResponse(request, "manage/people.html", {**_people_ctx(session), "msg": msg[:200]})


@router.post("/manage/people/invite", response_class=HTMLResponse)
def invite(request: Request, name: str = Form(...), note: str = Form(""), session: Session = Depends(get_session)):
    """Creates the link and shows it once (only its SHA-256 is kept)."""
    if not name.strip():
        raise HTTPException(400, "Give the person's name")
    inv, token = new_invite(session, name, note)
    session.commit()
    link = f"{str(request.base_url).rstrip('/')}/invite/{token}"
    ctx = {**_people_ctx(session), "msg": "", "new_link": link, "new_name": inv.name}
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
    return RedirectResponse(f"/manage/people?msg={quote(acct.name + ' was removed')}", status_code=303)


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
