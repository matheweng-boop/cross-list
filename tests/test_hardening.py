"""Hardening of 23 Oct 2026: Telegram alerts, owner confirmation (step-up), invite and guest limits, "Remove all
guests" and the password sign-in switch."""

import logging
import re
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import passkeys, stepup
from app.auth.session import COOKIE, guard
from app.config import get_settings
from app.models import Account, Invite, PasskeyCredential
from app.services import notify
from tests.conftest import sign_in_owner, solve_pow


@pytest.fixture
def wa(monkeypatch):
    """Fake WebAuthn checks (the browser part is not tested here)."""
    n = {"reg": 0}

    def reg(**kw):
        n["reg"] += 1
        return SimpleNamespace(credential_id=f"cred-{n['reg']}".encode(), credential_public_key=b"pk", sign_count=0)

    monkeypatch.setattr(passkeys, "verify_registration_response", reg)
    monkeypatch.setattr(passkeys, "verify_authentication_response", lambda **kw: SimpleNamespace(new_sign_count=0))
    return n


def _cred(raw_id="x"):
    return {"id": raw_id, "rawId": raw_id, "type": "public-key",
            "response": {"clientDataJSON": "e30", "attestationObject": "AA"}}  # fmt: skip


def _invite(c, name="Anna Guest"):
    return c.post("/manage/people/invite", data={"name": name, "note": ""}, follow_redirects=False)


def _token(r) -> str:
    return re.search(r"/invite/([A-Za-z0-9_-]+)", r.text).group(1)


def _accept(app, token) -> TestClient:
    g = TestClient(app)
    assert g.post(f"/invite/{token}/options", json=solve_pow(g)).status_code == 200
    r = g.post(f"/invite/{token}/verify", json={"credential": _cred()})
    assert r.status_code == 200, r.text
    return g


def _add_owner_key(c):
    assert c.post("/owner/passkeys/options").status_code == 200
    assert c.post("/owner/passkeys/verify", json={"credential": _cred()}).status_code == 200


def _unconfirm(c):
    c.cookies.delete(stepup.STEPUP_COOKIE)


def _owner_keys(s):
    return s.scalars(select(PasskeyCredential).join(Account).where(Account.role == "owner")).all()


# --- notify ----------------------------------------------------------------------------------------------------------
def test_notify_skips_when_not_configured(monkeypatch, caplog):
    called = []
    monkeypatch.setattr(notify, "_call", lambda *a, **k: called.append(a))
    monkeypatch.setattr(notify, "_start", lambda target, *args: target(*args))
    with caplog.at_level(logging.INFO, "crosslist.notify"):
        assert notify.alert("Invite created for Anna.") is False
    assert called == [] and "not set" in caplog.text


def test_notify_never_fails_and_hides_the_token(monkeypatch, caplog):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "BOTTOKEN123")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")

    def boom(token, method, _timeout=60, **params):
        assert _timeout <= 3
        raise RuntimeError(f"timed out at /bot{token}/{method}")

    monkeypatch.setattr(notify, "_call", boom)
    monkeypatch.setattr(notify, "_start", lambda target, *args: target(*args))
    assert notify.alert("hello") is True  # no exception reaches the caller
    assert "BOTTOKEN123" not in caplog.text and "not sent" in caplog.text


def test_alerts_carry_no_links_or_tokens(alerts):
    notify.alert("see https://cross-list.onrender.com/invite/abc and /invite/" + "x" * 43)
    assert alerts == ["BizDev: see [removed] and [removed]"]


def test_alert_runs_in_the_background(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "T")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    started = []
    monkeypatch.setattr(notify, "_start", lambda target, *args: started.append(args))
    t = time.monotonic()
    assert notify.alert("x") and time.monotonic() - t < 0.5 and len(started) == 1


def test_every_event_sends_an_alert_without_secrets(locked, alerts, wa, session):
    owner = locked
    assert sign_in_owner(owner).status_code == 303
    assert "signed in with the password" in alerts[-1]
    r = _invite(owner, "Anna Guest")
    token = _token(r)
    assert "Invite created for Anna Guest, valid until" in alerts[-1]
    g = _accept(owner.app, token)
    assert "Guest Anna Guest" in alerts[-1] and "registered a passkey" in alerts[-1]
    _add_owner_key(owner)
    assert "added a passkey" in alerts[-1]
    pk = _owner_keys(session)[0]
    assert owner.post(f"/owner/passkeys/{pk.id}/delete", follow_redirects=False).status_code == 303
    assert "removed a passkey" in alerts[-1]
    gid = session.scalar(select(Account.id).where(Account.role == "guest"))
    owner.post(f"/manage/people/{gid}/remove", follow_redirects=False)
    assert "removed guest Anna Guest" in alerts[-1]
    assert g.get("/parts", follow_redirects=False).status_code == 303
    text = "\n".join(alerts)
    for secret in (token, "BOTTOKEN123", "s3cret", "http", "/invite/", COOKIE):
        assert secret not in text


def test_lockout_sends_an_alert(locked, alerts):
    for _ in range(guard.FAILURES):
        locked.post("/login", data={"password": "nope", **solve_pow(locked)}, follow_redirects=False)
    assert sum("locked" in a for a in alerts) == 1 and "nope" not in "".join(alerts)


# --- step-up ---------------------------------------------------------------------------------------------------------
def test_invite_and_passkey_removal_need_a_fresh_confirmation(owner, wa, session):
    _add_owner_key(owner)
    _unconfirm(owner)
    r = _invite(owner, "Bob")
    assert r.status_code == 303 and r.headers["location"].startswith("/owner/confirm?next=")
    assert "name%3DBob" in r.headers["location"]
    pk = _owner_keys(session)[0]
    r = owner.post(f"/owner/passkeys/{pk.id}/delete", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/owner/confirm")
    session.expire_all()
    assert session.scalar(select(Invite.id)) is None and len(_owner_keys(session)) == 1
    assert "Confirm it is you" in owner.get(r.headers["location"]).text
    # wrong password: still not confirmed
    owner.post("/owner/confirm/password", data={"password": "bad", "next": "/manage/people"})
    assert _invite(owner).status_code == 303
    r = owner.post("/owner/confirm/password", data={"password": "s3cret", "next": "/manage/people?name=Bob"},
                   follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"] == "/manage/people?name=Bob"
    assert 'value="Bob"' in owner.get(r.headers["location"]).text
    assert _invite(owner, "Bob").status_code == 200


def test_confirmation_expires_after_5_minutes(owner, monkeypatch, session):
    real = time.time
    monkeypatch.setattr(stepup, "time", SimpleNamespace(time=lambda: real() + stepup.STEPUP_TTL + 1))
    assert _invite(owner).headers["location"].startswith("/owner/confirm")
    monkeypatch.setattr(stepup, "time", SimpleNamespace(time=lambda: real() + stepup.STEPUP_TTL - 30))
    assert _invite(owner).status_code == 200


def test_a_stolen_session_cookie_alone_is_not_enough(owner):
    thief = TestClient(owner.app)
    thief.cookies.set(COOKIE, owner.cookies.get(COOKIE))
    assert thief.get("/manage/people").status_code == 200  # the cookie still opens pages
    r = _invite(thief)
    assert r.status_code == 303 and r.headers["location"].startswith("/owner/confirm")
    assert thief.post("/manage/people/remove-all", follow_redirects=False).headers["location"].startswith(
        "/owner/confirm")


def test_confirm_with_a_passkey(owner, wa, session, make_guest):
    _add_owner_key(owner)
    _unconfirm(owner)
    o = owner.post("/owner/confirm/options").json()
    assert [c["id"] for c in o["allowCredentials"]] == [_owner_keys(session)[0].credential_id]
    # a credential that is not the owner's is refused
    assert owner.post("/owner/confirm/verify", json={"credential": _cred("someone-else")}).status_code == 401
    assert _invite(owner).status_code == 303
    owner.post("/owner/confirm/options")
    cred = _owner_keys(session)[0].credential_id
    r = owner.post("/owner/confirm/verify", json={"credential": _cred(cred), "next": "/manage/people"})
    assert r.status_code == 200 and r.json()["next"] == "/manage/people"
    assert _invite(owner).status_code == 200
    # a guest cannot reach the confirmation at all
    g, _ = make_guest()
    assert g.post("/owner/confirm/options").status_code == 403


# --- limits ----------------------------------------------------------------------------------------------------------
def test_open_invite_limit(owner, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_open_invites", 2)
    assert _invite(owner, "A").status_code == 200 and _invite(owner, "B").status_code == 200
    r = _invite(owner, "C")
    assert r.status_code == 303 and "Limit+reached" in r.headers["location"].replace("%20", "+")
    page = owner.get(r.headers["location"]).text
    assert "Limit reached: 2 invite links are still open (at most 2)" in page
    assert "<b>2</b> of at most 2 open invite links" in page


def test_guest_limit(owner, wa, monkeypatch, make_guest):
    s = get_settings()
    monkeypatch.setattr(s, "max_guests", 2)
    token = _token(_invite(owner, "A"))
    make_guest("G1")
    page = owner.get("/manage/people").text
    assert "<b>1</b> of at most 2 guests" in page and "fill the 2 guest places" in page
    assert "Limit" in _invite(owner, "B").headers["location"]  # 1 guest + 1 open invite = 2 places
    make_guest("G2")
    g = TestClient(owner.app)
    assert g.post(f"/invite/{token}/options", json=solve_pow(g)).status_code == 200
    r = g.post(f"/invite/{token}/verify", json={"credential": _cred()})
    assert r.status_code == 409 and "full" in r.json()["detail"]
    assert "there are 2 guests (at most 2)" in owner.get("/manage/people").text


def test_settings_defaults():
    s = get_settings()
    assert s.max_open_invites == 5 and s.max_guests == 10 and s.password_login == ""


# --- remove all guests -----------------------------------------------------------------------------------------------
def test_remove_all_guests(owner, wa, session, alerts):
    _add_owner_key(owner)
    g1 = _accept(owner.app, _token(_invite(owner, "A")))
    g2 = _accept(owner.app, _token(_invite(owner, "B")))
    _invite(owner, "C")  # stays open until removed
    assert "Remove all guests" in owner.get("/manage/people").text
    _unconfirm(owner)
    assert owner.post("/manage/people/remove-all", follow_redirects=False).headers["location"].startswith(
        "/owner/confirm")
    owner.post("/owner/confirm/password", data={"password": "s3cret", "next": "/manage/people"})
    before = len(alerts)
    r = owner.post("/manage/people/remove-all", follow_redirects=False)
    assert r.status_code == 303 and "All guests removed" in owner.get(r.headers["location"]).text
    session.expire_all()
    assert all(a.disabled for a in session.scalars(select(Account).where(Account.role == "guest")))
    assert len(session.scalars(select(PasskeyCredential)).all()) == 1  # only the owner's
    assert passkeys.open_invites(session) == 0
    for g in (g1, g2):
        assert g.get("/parts", follow_redirects=False).status_code == 303
    assert len(alerts) == before + 1 and "2 signed out, 2 passkeys deleted, 1 open invites" in alerts[-1]
    assert owner.get("/parts").status_code == 200  # the owner stays signed in


# --- password sign-in switch -----------------------------------------------------------------------------------------
def test_password_switch_needs_two_passkeys(owner, wa, session, alerts):
    r = owner.post("/owner/password-login", data={"allow": "off"}, follow_redirects=False)
    assert "at least 2" in owner.get(r.headers["location"]).text
    assert "you have 0" in owner.get("/owner/passkeys").text
    _add_owner_key(owner)
    owner.post("/owner/password-login", data={"allow": "off"})
    session.expire_all()
    assert stepup.password_switch(session)
    _add_owner_key(owner)
    _unconfirm(owner)
    r = owner.post("/owner/password-login", data={"allow": "off"}, follow_redirects=False)
    assert r.headers["location"].startswith("/owner/confirm")  # step-up first
    owner.post("/owner/confirm/options")
    owner.post("/owner/confirm/verify", json={"credential": _cred(_owner_keys(session)[0].credential_id)})
    r = owner.post("/owner/password-login", data={"allow": "off"}, follow_redirects=False)
    assert "switched+off" in r.headers["location"] and alerts[-1].endswith("switched password sign-in off.")
    session.expire_all()
    assert not stepup.password_allowed(session)
    # the sign-in page has no password field and the server refuses the password
    c = TestClient(owner.app)
    page = c.get("/login").text
    assert 'name="password"' not in page and "passkey-login" in page
    r = c.post("/login", data={"password": "s3cret", "next": "/", **solve_pow(c)}, follow_redirects=False)
    assert r.status_code == 403 and COOKIE not in r.cookies
    # nor does it confirm with the password
    assert "switched off" in owner.post("/owner/confirm/password", data={"password": "s3cret"}).text
    # with 2 passkeys and the password off, the owner cannot drop below 2
    pk = _owner_keys(session)[0]
    r = owner.post(f"/owner/passkeys/{pk.id}/delete", follow_redirects=False)
    assert "at least 2 passkeys" in owner.get(r.headers["location"]).text
    session.expire_all()
    assert len(_owner_keys(session)) == 2
    # switching on again
    owner.post("/owner/password-login", data={"allow": "on"})
    assert alerts[-1].endswith("switched password sign-in on.")
    assert 'name="password"' in c.get("/login").text


def test_force_on_from_the_environment(owner, monkeypatch, session):
    stepup.set_password_switch(session, False)
    session.commit()
    c = TestClient(owner.app)
    assert 'name="password"' not in c.get("/login").text
    monkeypatch.setattr(get_settings(), "password_login", "force-on")
    assert 'name="password"' in c.get("/login").text
    assert sign_in_owner(c).status_code == 303
    assert "forced on by CROSSLIST_PASSWORD_LOGIN=force-on" in c.get("/owner/passkeys").text
