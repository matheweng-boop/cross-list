import pytest

from app.config import get_settings


@pytest.fixture
def locked(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "site_password", "s3cret")
    monkeypatch.setattr(get_settings(), "secret_key", "k")
    return client


def test_open_without_password(client):
    assert client.get("/parts").status_code == 200


def test_pages_ask_for_the_password(locked):
    r = locked.get("/parts?q=SR", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login?next=/parts%3Fq%3DSR"
    assert locked.get("/api/parts").status_code == 401
    assert locked.get("/suggest?q=SR", headers={"HX-Request": "true"}).status_code == 401
    assert locked.get("/healthz").status_code == 200
    assert locked.get("/static/app.css").status_code == 200


def test_wrong_password_is_refused(locked):
    r = locked.post("/login", data={"password": "nope", "next": "/parts"}, follow_redirects=False)
    assert r.status_code == 401
    assert locked.get("/parts", follow_redirects=False).status_code == 303


def test_sign_in_and_out(locked):
    r = locked.post("/login", data={"password": "s3cret", "next": "/parts"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/parts"
    assert locked.get("/parts").status_code == 200
    assert "Sign out" in locked.get("/parts").text
    locked.get("/logout")
    assert locked.get("/parts", follow_redirects=False).status_code == 303


def test_next_cannot_leave_the_site(locked):
    r = locked.post("/login", data={"password": "s3cret", "next": "//evil.example"}, follow_redirects=False)
    assert r.headers["location"] == "/"
