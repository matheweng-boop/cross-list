import hashlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.main import create_app
from app.models import Part


@pytest.fixture
def client(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'test.db'}", seed_synthetic=True)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def session(client):
    with Session(get_engine()) as s:
        yield s


@pytest.fixture
def part(session):
    def get(mpn: str) -> Part:
        return session.scalars(select(Part).where(Part.mpn == mpn)).unique().one()

    return get


# --- signing in (passkeys and guests, 23 Oct 2026) --------------------------------------------------------------------
def solve_pow(client) -> dict:
    """Solve the sign-in page's proof of work the way the browser does."""
    from app.auth.session import _zero_bits

    c = client.get("/login/pow").json()
    n = 0
    while _zero_bits(hashlib.sha256(f"{c['challenge']}:{n}".encode()).digest()) < c["bits"]:
        n += 1
    return {"pow_challenge": c["challenge"], "pow_nonce": str(n)}


@pytest.fixture
def locked(client, monkeypatch):
    """The site with a password, as on Render; the client is not signed in."""
    from app.auth import gate
    from app.config import get_settings

    s = get_settings()
    monkeypatch.setattr(s, "site_password", "s3cret")
    monkeypatch.setattr(s, "secret_key", "k")
    monkeypatch.setattr(s, "pow_bits", 6)
    monkeypatch.setattr(s, "rp_id", "localhost")
    monkeypatch.setattr(s, "origin", "http://localhost")
    monkeypatch.setattr(gate, "FAIL_DELAY", 0)
    return client


def sign_in_owner(c, password="s3cret"):
    return c.post("/login", data={"password": password, "next": "/", **solve_pow(c)}, follow_redirects=False)


@pytest.fixture
def owner(locked):
    """The test client signed in as the owner with the password."""
    assert sign_in_owner(locked).status_code == 303
    return locked


@pytest.fixture
def make_guest(locked):
    """make_guest(name) -> (TestClient signed in as a new guest, Account id)."""
    from app.auth.session import COOKIE, make_cookie, new_handle
    from app.models import Account

    def make(name="Anna Guest"):
        with Session(get_engine()) as s:
            acct = Account(name=name, role="guest", handle=new_handle())
            s.add(acct)
            s.commit()
            cookie, aid = make_cookie(acct), acct.id
        g = TestClient(locked.app)
        g.cookies.set(COOKIE, cookie)
        return g, aid

    return make
