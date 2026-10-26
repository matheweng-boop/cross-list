"""Anti-bot and browser security: no indexing, security headers, same-site writes, size limits."""

from fastapi.testclient import TestClient

from app.config import get_settings
from app.security import CSP
from tests.conftest import sign_in_owner


def test_robots_and_noindex_everywhere(locked):
    r = locked.get("/robots.txt")
    assert r.status_code == 200 and r.text == "User-agent: *\nDisallow: /\n"
    for path in ("/login", "/robots.txt", "/static/app.css", "/parts"):
        assert locked.get(path, follow_redirects=False).headers["x-robots-tag"] == "noindex, nofollow"
    assert '<meta name="robots" content="noindex,nofollow">' in locked.get("/login").text
    sign_in_owner(locked)
    assert '<meta name="robots" content="noindex,nofollow">' in locked.get("/parts").text


def test_security_headers_on_every_response(client):
    for path in ("/", "/parts", "/static/app.css", "/no-such-page", "/healthz"):
        h = client.get(path).headers
        assert h["content-security-policy"] == CSP, path
        assert h["x-content-type-options"] == "nosniff"
        assert h["referrer-policy"] == "same-origin"
        assert h["x-frame-options"] == "DENY"
        pp = h["permissions-policy"]
        assert "camera=()" in pp and "geolocation=()" in pp and "microphone=(self)" in pp
        assert "strict-transport-security" not in h  # plain http (local)
    assert "frame-ancestors 'none'" in CSP and "default-src 'self'" in CSP and "https:" not in CSP


def test_hsts_and_secure_cookie_on_https(locked):
    c = TestClient(locked.app, base_url="https://testserver")
    assert "max-age=" in c.get("/login").headers["strict-transport-security"]
    r = sign_in_owner(c)
    assert r.status_code == 303 and "secure" in r.headers["set-cookie"].lower()


def test_writes_from_other_sites_are_refused(client):
    r = client.post("/requests", data={"mpns": "SR8641"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/requests", data={"mpns": "SR8641"}, headers={"sec-fetch-site": "cross-site"})
    assert r.status_code == 403
    r = client.post("/login", data={"password": "x"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403
    ok = client.post("/requests", data={"mpns": "SR8641"}, headers={"origin": "http://testserver",
                                                                   "sec-fetch-site": "same-origin"})  # fmt: skip
    assert ok.status_code == 200
    s = get_settings()
    assert client.post("/requests", data={"mpns": "SR8641"}, headers={"origin": s.origin}).status_code == 200


def test_request_size_limits(client):
    big = "x" * (4 * 1024 * 1024 + 10)
    assert client.post("/site-feedback", content=big, headers={"content-type": "application/json"}).status_code == 413
    # uploads keep their 10 MB: a 5 MB body reaches the upload route (which then judges the file itself)
    r = client.post("/manage/uploads", data={"title": "x"}, files={"file": ("a.bin", b"\0" * (5 * 1024 * 1024))})
    assert r.status_code != 413
    huge = b"\0" * (11 * 1024 * 1024 + 10)
    assert client.post("/manage/uploads", files={"file": ("a.bin", huge)}).status_code == 413

    def chunks():
        yield b'{"text": "hi"}'

    assert client.post("/site-feedback", content=chunks(), headers={"content-type": "application/json"}).status_code \
        == 411  # fmt: skip


def test_inbox_bearer_still_works(locked, monkeypatch):
    monkeypatch.setattr(get_settings(), "inbox_token", "k" * 40)
    r = locked.get("/api/inbox", headers={"Authorization": "Bearer " + "k" * 40})
    assert r.status_code == 200 and r.headers["x-robots-tag"] == "noindex, nofollow"


def test_guest_note_and_auth_script_have_no_outside_sources(locked):
    page = locked.get("/login").text
    assert "/static/auth.js" in page and "http" not in page.split("<body>")[1].split("</main>")[0]


def test_only_shareable_previews_may_be_framed_and_only_by_this_site(client):
    """Owner, 25 Oct 2026: Shareable previews open in a lightbox (an iframe on the same site); every other page stays
    unframeable."""
    for path in ("/shareable/technology-overview", "/shareable/synergies", "/shareable/presentation/preview?s=title"):
        r = client.get(path)
        csp = r.headers["content-security-policy"]
        assert r.headers["x-frame-options"] == "SAMEORIGIN" and "frame-ancestors 'self'" in csp, path
    for path in ("/", "/shareable", "/shareable/presentation", "/manage/overview"):
        r = client.get(path, follow_redirects=False)
        csp = r.headers["content-security-policy"]
        assert r.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in csp, path
