"""Security headers on every response, no indexing by search engines, request size limits and a same-site check on
everything that changes data. Plain ASGI, outermost, so it also covers errors and static files.

Content-Security-Policy: only this site. 'unsafe-inline' is allowed for scripts because the pages have small inline
scripts and onclick handlers (the menu, the suggestions list, the feedback button, the visuals' page scripts), and for
styles because the templates use style="" attributes and htmx adds its indicator style. No other site is allowed.
"""

import re

from app.config import get_settings

CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data: blob:; font-src 'self'; connect-src 'self'; media-src 'self' blob:; "
       "worker-src 'self' blob:; "
       "object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'")  # fmt: skip
# the microphone stays allowed for this site (the dictation button in the feedback window)
PERMISSIONS = ("camera=(), geolocation=(), microphone=(self), payment=(), usb=(), display-capture=(), "
               "magnetometer=(), gyroscope=(), accelerometer=()")
HEADERS = [
    (b"content-security-policy", CSP.encode()),
    (b"x-content-type-options", b"nosniff"),
    (b"referrer-policy", b"same-origin"),
    (b"x-frame-options", b"DENY"),
    (b"permissions-policy", PERMISSIONS.encode()),
    (b"x-robots-tag", b"noindex, nofollow"),
]
HSTS = (b"strict-transport-security", b"max-age=31536000")
# Shareable previews open in a lightbox on the same site (owner, 25 Oct 2026): these pages may be framed by this site
# only (frame-ancestors 'self', SAMEORIGIN); every other page stays unframeable.
_FRAMEABLE = re.compile(r"^/shareable/(pack|presentation/preview|technology-overview|synergies|automotive)$")
HEADERS_SAMEORIGIN = [
    (k, CSP.replace("frame-ancestors 'none'", "frame-ancestors 'self'").encode() if k == b"content-security-policy"
     else b"SAMEORIGIN" if k == b"x-frame-options" else v)
    for k, v in HEADERS
]

MAX_BODY = 4 * 1024 * 1024  # forms and JSON (saved diagrams are the largest)
MAX_UPLOAD = 11 * 1024 * 1024  # the 10 MB upload limit plus the form around the file
_UPLOADS = re.compile(r"^/(manage/uploads|site-feedback/[^/]+/file)$")
UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}

ROBOTS = "User-agent: *\nDisallow: /\n"


def _limit(path: str) -> int:
    return MAX_UPLOAD if _UPLOADS.match(path) else MAX_BODY


class SecurityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        https = scope.get("scheme") == "https"

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                names = {k.lower() for k, _ in message.get("headers", [])}
                base = HEADERS_SAMEORIGIN if _FRAMEABLE.match(scope.get("path", "")) else HEADERS
                extra = [h for h in base if h[0] not in names] + ([HSTS] if https else [])
                message = {**message, "headers": list(message.get("headers", [])) + extra}
            await send(message)

        if scope["method"] in UNSAFE:
            why = self._refuse(scope)
            if why:
                status, text = why
                await send_with_headers({"type": "http.response.start", "status": status,
                                         "headers": [(b"content-type", b"text/plain; charset=utf-8")]})  # fmt: skip
                return await send_with_headers({"type": "http.response.body", "body": text.encode()})
        await self.app(scope, receive, send_with_headers)

    @staticmethod
    def _refuse(scope) -> tuple[int, str] | None:
        h = {k.decode().lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        # a browser on another site may not send data here (logins and forms are same-site only)
        if h.get("sec-fetch-site") == "cross-site":
            return 403, "Refused: sent from another site."
        origin = h.get("origin")
        if origin and origin != "null":
            host = h.get("host", "")
            if origin.split("://", 1)[-1] != host and origin != get_settings().origin:
                return 403, "Refused: sent from another site."
        length = h.get("content-length")
        if length is None:
            if "chunked" in h.get("transfer-encoding", ""):
                return 411, "Send the length of the data."
            return None
        try:
            n = int(length)
        except ValueError:
            return 400, "Bad length."
        if n > _limit(scope.get("path", "")):
            return 413, "Too large: files up to 10 MB, other input up to 4 MB."
        return None
