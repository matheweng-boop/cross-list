"""Passkeys on an iPhone (23 Oct 2026): the WebAuthn call runs inside the tap, options are fetched ahead, and the owner
is pointed to "My passkeys"."""

import re
from pathlib import Path

from sqlalchemy import select

from app.models import WebauthnChallenge
from tests.conftest import solve_pow
from tests.test_hardening import _add_owner_key, _invite, _token, wa  # noqa: F401  (wa is a fixture)

AUTH_JS = Path(__file__).resolve().parent.parent / "app" / "web" / "static" / "auth.js"
BANNER = "Set up a passkey on this device"


def test_banner_for_an_owner_without_passkeys(owner, wa):  # noqa: F811
    page = owner.get("/business").text
    assert BANNER in page and 'href="/owner/passkeys"' in page and "Set up now" in page
    assert BANNER not in owner.get("/owner/passkeys").text  # the button is right there
    owner.cookies.set("crosslist_pk_nudge", "off")  # dismissed for the session
    assert BANNER not in owner.get("/business").text
    owner.cookies.delete("crosslist_pk_nudge")
    _add_owner_key(owner)
    assert BANNER not in owner.get("/business").text


def test_no_banner_for_guests_or_signed_out(locked, make_guest):
    g, _ = make_guest()
    assert BANNER not in g.get("/business").text
    assert BANNER not in locked.get("/login").text


def test_my_passkeys_link_and_setup_help(owner):
    page = owner.get("/business").text
    assert re.search(r'<a href="/owner/passkeys" class="my-keys[^"]*"><svg', page)
    keys = owner.get("/owner/passkeys").text
    assert keys.index('id="owner-add-passkey"') < keys.index("Password sign-in")
    assert "iCloud" in keys and "Windows Hello" in keys and "QR code is only for signing in" in keys


def test_sign_in_page_note(locked):
    page = locked.get("/login").text
    assert "First time? Sign in with your password once, then add a passkey under My passkeys." in page
    assert "Guests: use the invite link you received." in page


def _open(session):
    session.expire_all()
    return session.scalars(select(WebauthnChallenge)).all()


def test_options_fetched_ahead_stay_single_use(owner, wa, session):  # noqa: F811
    # a refresh replaces this browser's earlier challenge instead of piling them up
    for _ in range(3):
        assert owner.post("/owner/passkeys/options").status_code == 200
    assert len(_open(session)) == 1
    from tests.test_hardening import _cred

    assert owner.post("/owner/passkeys/verify", json={"credential": _cred("a")}).status_code == 200
    assert _open(session) == []
    r = owner.post("/owner/passkeys/verify", json={"credential": _cred("b")})  # the same challenge again
    assert r.status_code == 400 and "too long" in r.json()["detail"]


def test_login_and_invite_options_stay_single_use(owner, wa, session):  # noqa: F811
    from fastapi.testclient import TestClient

    from tests.test_hardening import _cred

    g = TestClient(owner.app)
    assert g.post("/passkey/login/options", json=solve_pow(g)).status_code == 200
    assert g.post("/passkey/login/options", json=solve_pow(g)).status_code == 200
    assert len(_open(session)) == 1
    g.post("/passkey/login/verify", json={"credential": _cred("unknown")})
    assert _open(session) == []
    r = g.post("/passkey/login/verify", json={"credential": _cred("unknown")})
    assert "took too long or was already used" in r.json()["detail"]

    token = _token(_invite(owner))
    h = TestClient(owner.app)
    assert h.post(f"/invite/{token}/options", json=solve_pow(h)).status_code == 200
    assert h.post(f"/invite/{token}/verify", json={"credential": _cred("g1")}).status_code == 200
    assert h.post(f"/invite/{token}/verify", json={"credential": _cred("g2")}).status_code == 400


def _click_handlers(js: str) -> list[str]:
    """The body of every click handler that calls navigator.credentials."""
    out = []
    for m in re.finditer(r'addEventListener\("click",', js):
        body = js[m.end() :]
        depth, end = 0, None
        for i, ch in enumerate(body):
            if ch in "({":
                depth += 1
            elif ch in ")}":
                if depth == 0:
                    end = i
                    break
                depth -= 1
        body = body[:end]
        if "navigator.credentials" in body:
            out.append(body)
    return out


def test_webauthn_runs_inside_the_tap():
    """Safari needs navigator.credentials.create/get inside the tap: no await (no network request) before it."""
    js = AUTH_JS.read_text()
    handlers = _click_handlers(js)
    calls = [re.search(r"navigator\.credentials\.(create|get)\(", h).group(1) for h in handlers]
    assert sorted(calls) == ["create", "create", "get", "get"]  # owner add, invite, sign-in, owner confirmation
    for h in handlers:
        before = h[: h.index("navigator.credentials.")]
        assert "await" not in before and "fetch(" not in before and "post(" not in before and ".then(" not in before, h
        assert not h.lstrip().startswith("async")
    # the options are prepared ahead and refreshed before the 5-minute challenge expires
    assert "Preparing… tap again in a moment." in js
    assert re.search(r"const FRESH = 240e3", js)
    for name in ("NotAllowedError", "InvalidStateError", "SecurityError", "SiteError",
                 "This device already has a passkey for this site"):  # fmt: skip
        assert name in js
