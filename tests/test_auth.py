"""Signing in: who sees what, invites, passkey ceremonies (py_webauthn's verify functions mocked), sessions,
the proof of work and the login throttling."""

import re
from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import passkeys
from app.auth.session import COOKIE, guard, now
from app.db import get_engine
from app.models import Account, Invite, PasskeyCredential, WebauthnChallenge
from tests.conftest import sign_in_owner, solve_pow


@pytest.fixture
def fake_webauthn(monkeypatch):
    state = {"reg": [], "auth": [], "count": 5}

    def reg(**kw):
        state["reg"].append(kw)
        return SimpleNamespace(credential_id=f"cred-{len(state['reg'])}".encode(), credential_public_key=b"pk",
                               sign_count=0)  # fmt: skip

    def auth(**kw):
        state["auth"].append(kw)
        return SimpleNamespace(new_sign_count=state["count"])

    monkeypatch.setattr(passkeys, "verify_registration_response", reg)
    monkeypatch.setattr(passkeys, "verify_authentication_response", auth)
    return state


def _cred(raw_id: str = "x", handle: str | None = None) -> dict:
    resp = {"clientDataJSON": "e30", "attestationObject": "AA", "transports": ["internal"]}
    if handle:
        resp["userHandle"] = handle
    return {"id": raw_id, "rawId": raw_id, "type": "public-key", "response": resp}


def _invite(owner, name="Anna Guest") -> str:
    page = owner.post("/manage/people/invite", data={"name": name, "note": "RF engineer"}).text
    return re.search(r"/invite/([A-Za-z0-9_-]+)", page).group(1)


def _accept(c, token):
    o = c.post(f"/invite/{token}/options", json=solve_pow(c))
    assert o.status_code == 200, o.text
    return c.post(f"/invite/{token}/verify", json={"credential": _cred()})


# --- who sees what -------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/", "/parts", "/manage/overview", "/business/method", "/owner/passkeys"])
def test_anonymous_is_sent_to_sign_in(locked, path):
    r = locked.get(path, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")


def test_anonymous_writes_and_api_are_refused(locked, session):
    assert locked.post("/requests", data={"mpns": "SR8641"}).status_code == 401
    assert locked.post("/api/blocks/designs", json={"name": "x", "data": {}}).status_code == 401
    assert locked.get("/api/parts").status_code == 401
    assert locked.post("/owner/passkeys/options").status_code == 401
    assert locked.post("/manage/people/invite", data={"name": "Eve"}).status_code == 401
    assert session.scalar(select(Invite.id)) is None


def test_only_sign_in_paths_are_open(locked):
    for path in ("/login", "/login/pow", "/robots.txt", "/healthz", "/static/auth.js"):
        assert locked.get(path).status_code == 200, path
    assert locked.get("/invite/" + "a" * 43).status_code == 404  # unknown invite: a page, no site content
    assert locked.get("/loginx", follow_redirects=False).status_code == 303
    assert locked.get("/api/inboxes", follow_redirects=False).status_code == 401
    assert locked.get("/invite/short", follow_redirects=False).status_code == 303


def test_owner_sees_everything(owner):
    for path in ("/parts", "/manage/overview", "/manage/people", "/manage/guest-input", "/owner/passkeys"):
        assert owner.get(path).status_code == 200, path
    page = owner.get("/parts").text
    assert "Data management" in page and "My passkeys" in page and "(guest)" not in page


def test_tampered_or_old_cookies_are_refused(locked, make_guest):
    guest, gid = make_guest()
    value = guest.cookies.get(COOKIE)
    forged = value.replace(".guest.", ".owner.")
    c = TestClient(locked.app)
    for bad in (forged, "deadbeef" * 8, value[:-2] + "00"):
        c.cookies.set(COOKIE, bad)
        assert c.get("/parts", follow_redirects=False).status_code == 303


def test_cookie_flags(locked):
    r = sign_in_owner(locked)
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "max-age" in cookie
    r = locked.post("/login", data={"password": "s3cret", **solve_pow(locked)}, follow_redirects=False,
                    headers={"x-forwarded-proto": "https"})  # fmt: skip
    assert r.status_code == 303


# --- invites ----------------------------------------------------------------------------------------------------------
def test_invite_lifecycle(owner, session, fake_webauthn):
    token = _invite(owner)
    inv = session.scalar(select(Invite))
    assert inv.token_sha256 == passkeys.token_hash(token) and token not in repr(inv.__dict__)
    assert abs((inv.expires_at - inv.created_at) - timedelta(days=7)) < timedelta(seconds=5)
    newcomer = TestClient(owner.app)
    page = newcomer.get(f"/invite/{token}")
    assert page.status_code == 200 and "Anna Guest" in page.text and "Create my passkey" in page.text
    assert "passkey" in page.text and "fingerprint" in page.text
    r = _accept(newcomer, token)
    assert r.status_code == 200 and r.json()["ok"]
    assert "You are signed in as Anna Guest (guest)" in newcomer.get("/parts").text
    session.expire_all()
    acct = session.scalar(select(Account).where(Account.role == "guest"))
    assert acct.name == "Anna Guest" and len(acct.passkeys) == 1
    assert acct.passkeys[0].transports == ["internal"]
    assert session.scalar(select(Invite)).used_at is not None
    assert fake_webauthn["reg"][0]["expected_rp_id"] == "localhost"
    assert fake_webauthn["reg"][0]["expected_origin"] == "http://localhost"
    # used once: the link is dead now
    other = TestClient(owner.app)
    assert other.get(f"/invite/{token}").status_code == 404
    assert other.post(f"/invite/{token}/options", json=solve_pow(other)).status_code == 404
    assert other.post(f"/invite/{token}/verify", json={"credential": _cred()}).status_code == 400
    people = owner.get("/manage/people").text
    assert "Anna Guest" in people and "not used yet" in people and "used " in people


def test_expired_and_cancelled_invites(owner, session, fake_webauthn):
    token = _invite(owner)
    inv = session.scalar(select(Invite))
    inv.expires_at = now() - timedelta(seconds=1)
    session.commit()
    c = TestClient(owner.app)
    assert c.get(f"/invite/{token}").status_code == 404
    assert c.post(f"/invite/{token}/options", json=solve_pow(c)).status_code == 404
    token2 = _invite(owner, "Bob")
    inv2 = session.scalar(select(Invite).where(Invite.name == "Bob"))
    owner.post(f"/manage/people/invites/{inv2.id}/cancel")
    assert c.get(f"/invite/{token2}").status_code == 404
    assert session.scalar(select(Account).where(Account.role == "guest")) is None


def test_invite_used_twice_in_parallel_creates_one_guest(owner, session, fake_webauthn):
    token = _invite(owner)
    a, b = TestClient(owner.app), TestClient(owner.app)
    assert a.post(f"/invite/{token}/options", json=solve_pow(a)).status_code == 200
    assert b.post(f"/invite/{token}/options", json=solve_pow(b)).status_code == 200
    assert a.post(f"/invite/{token}/verify", json={"credential": _cred()}).status_code == 200
    assert b.post(f"/invite/{token}/verify", json={"credential": _cred()}).status_code == 400
    session.expire_all()
    assert len(session.scalars(select(Account).where(Account.role == "guest")).all()) == 1


def test_options_ask_for_a_discoverable_passkey(owner):
    token = _invite(owner)
    c = TestClient(owner.app)
    o = c.post(f"/invite/{token}/options", json=solve_pow(c)).json()
    sel = o["authenticatorSelection"]
    assert sel["residentKey"] == "required" and sel["userVerification"] == "preferred"
    assert o["rp"]["id"] == "localhost" and o["user"]["name"] == "Anna Guest" and len(o["challenge"]) >= 43
    assert c.post(f"/invite/{token}/options", json={}).status_code == 400  # no proof of work


# --- passkey sign-in -----------------------------------------------------------------------------------------------
def _guest_with_key(owner, fake_webauthn) -> tuple[str, str]:
    token = _invite(owner)
    _accept(TestClient(owner.app), token)
    with Session(get_engine()) as s:
        pk = s.scalar(select(PasskeyCredential))
        return pk.credential_id, pk.account.handle


def _login(c, cred_id, handle=None):
    assert c.post("/passkey/login/options", json=solve_pow(c)).status_code == 200
    return c.post("/passkey/login/verify", json={"credential": _cred(cred_id, handle), "next": "/parts"})


def test_passkey_login_and_sign_count(owner, fake_webauthn, session):
    cred_id, handle = _guest_with_key(owner, fake_webauthn)
    c = TestClient(owner.app)
    o = c.post("/passkey/login/options", json=solve_pow(c)).json()
    assert o["userVerification"] == "preferred" and o["allowCredentials"] == [] and o["rpId"] == "localhost"
    r = c.post("/passkey/login/verify", json={"credential": _cred(cred_id, handle), "next": "/parts"})
    assert r.status_code == 200 and r.json() == {"ok": True, "next": "/parts"}
    assert "(guest)" in c.get("/parts").text
    assert fake_webauthn["auth"][0]["credential_current_sign_count"] == 0
    session.expire_all()
    pk = session.scalar(select(PasskeyCredential))
    assert pk.sign_count == 5 and pk.last_used_at is not None
    # a counter that goes back means a copied key
    fake_webauthn["count"] = 3
    assert _login(TestClient(owner.app), cred_id, handle).status_code == 401


def test_challenge_works_once_and_expires(owner, fake_webauthn, session):
    cred_id, handle = _guest_with_key(owner, fake_webauthn)
    c = TestClient(owner.app)
    c.post("/passkey/login/options", json=solve_pow(c))
    nonce = c.cookies.get(passkeys.WA_COOKIE)
    assert c.post("/passkey/login/verify", json={"credential": _cred(cred_id, handle)}).status_code == 200
    c2 = TestClient(owner.app)
    c2.cookies.set(passkeys.WA_COOKIE, nonce)
    assert c2.post("/passkey/login/verify", json={"credential": _cred(cred_id, handle)}).status_code == 400
    # expired
    c3 = TestClient(owner.app)
    c3.post("/passkey/login/options", json=solve_pow(c3))
    session.execute(WebauthnChallenge.__table__.update().values(expires_at=now() - timedelta(seconds=1)))
    session.commit()
    assert c3.post("/passkey/login/verify", json={"credential": _cred(cred_id, handle)}).status_code == 400
    # no challenge from this browser at all
    assert TestClient(owner.app).post("/passkey/login/verify", json={"credential": _cred(cred_id)}).status_code == 400


def test_unknown_wrong_user_or_removed_credentials_are_refused(owner, fake_webauthn, session):
    cred_id, handle = _guest_with_key(owner, fake_webauthn)
    assert _login(TestClient(owner.app), "unknown-id").status_code == 401
    assert _login(TestClient(owner.app), cred_id, "b3RoZXI").status_code == 401  # userHandle of someone else
    guest = session.scalar(select(Account).where(Account.role == "guest"))
    guest.disabled = True
    session.commit()
    assert _login(TestClient(owner.app), cred_id, handle).status_code == 401


def test_failed_verification_is_refused(owner, fake_webauthn, monkeypatch):
    cred_id, handle = _guest_with_key(owner, fake_webauthn)

    def boom(**kw):
        raise ValueError("bad signature")

    monkeypatch.setattr(passkeys, "verify_authentication_response", boom)
    c = TestClient(owner.app)
    assert _login(c, cred_id, handle).status_code == 401
    assert c.get("/parts", follow_redirects=False).status_code == 303


def test_removing_a_guest_signs_them_out_at_once(owner, fake_webauthn, session):
    token = _invite(owner)
    g = TestClient(owner.app)
    _accept(g, token)
    assert g.get("/parts").status_code == 200
    acct = session.scalar(select(Account).where(Account.role == "guest"))
    r = owner.post(f"/manage/people/{acct.id}/remove", follow_redirects=False)
    assert r.status_code == 303
    assert g.get("/parts", follow_redirects=False).status_code == 303
    session.expire_all()
    assert session.scalar(select(PasskeyCredential.id)) is None
    assert "(removed)" in owner.get("/manage/people").text


def test_owner_passkeys(owner, fake_webauthn, session):
    o = owner.post("/owner/passkeys/options").json()
    assert o["authenticatorSelection"]["residentKey"] == "required"
    r = owner.post("/owner/passkeys/verify", json={"credential": _cred()})
    assert r.status_code == 200, r.text
    pk = session.scalar(select(PasskeyCredential))
    assert pk.account.role == "owner"
    # the owner's passkey signs in as the owner
    c = TestClient(owner.app)
    assert _login(c, pk.credential_id, pk.account.handle).status_code == 200
    assert "Data management" in c.get("/parts").text
    # and can be removed again
    assert owner.post(f"/owner/passkeys/{pk.id}/delete", follow_redirects=False).status_code == 303
    session.expire_all()
    assert session.scalar(select(PasskeyCredential.id)) is None


def test_owner_registration_needs_its_own_challenge(owner, fake_webauthn):
    assert owner.post("/owner/passkeys/verify", json={"credential": _cred()}).status_code == 400


# --- proof of work and throttling ------------------------------------------------------------------------------------
def test_proof_of_work_is_needed_and_works_once(locked):
    r = locked.post("/login", data={"password": "s3cret"}, follow_redirects=False)
    assert r.status_code == 400 and "browser check" in r.text
    pow_ = solve_pow(locked)
    assert locked.post("/login", data={"password": "s3cret", **pow_}, follow_redirects=False).status_code == 303
    locked.cookies.clear()
    assert locked.post("/login", data={"password": "s3cret", **pow_}, follow_redirects=False).status_code == 400
    bad = {**solve_pow(locked), "pow_nonce": "nope"}
    assert locked.post("/login", data={"password": "s3cret", **bad}, follow_redirects=False).status_code == 400
    forged = solve_pow(locked)
    forged["pow_challenge"] = forged["pow_challenge"][:-1] + ("0" if forged["pow_challenge"][-1] != "0" else "1")
    assert locked.post("/login", data={"password": "s3cret", **forged}, follow_redirects=False).status_code == 400
    assert locked.post("/passkey/login/options", json={}).status_code == 400


def test_failed_logins_lock_the_address(locked, caplog):
    for _ in range(guard.FAILURES):
        r = locked.post("/login", data={"password": "wrong-pass", **solve_pow(locked)}, follow_redirects=False)
        assert r.status_code == 401
    r = sign_in_owner(locked)
    assert r.status_code == 429 and "15 minutes" in r.text
    assert "sign-in failed" in caplog.text and "wrong-pass" not in caplog.text
    guard.reset()
    assert sign_in_owner(locked).status_code == 303


def test_attempts_per_address_are_limited(locked, monkeypatch):
    monkeypatch.setattr(guard, "ATTEMPTS", 3)
    for _ in range(3):
        assert locked.post("/passkey/login/options", json=solve_pow(locked)).status_code == 200
    assert locked.post("/passkey/login/options", json=solve_pow(locked)).status_code == 429
    assert sign_in_owner(locked).status_code == 429


def test_global_slowdown_when_failures_spike(locked, monkeypatch):
    monkeypatch.setattr(guard, "SPIKE", 2)
    assert guard.slowdown() == 0
    for ip in ("a", "b", "c"):
        guard.failed(ip, "password")
    assert guard.slowdown() == guard.SLOWDOWN
