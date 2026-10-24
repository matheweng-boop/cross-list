"""Which paths are open without signing in, and which are the owner's alone (Data management)."""

import re

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")

# Reachable without signing in. Everything else needs the owner or a guest.
OPEN_EXACT = frozenset({
    "/login", "/login/pow", "/healthz", "/robots.txt",
    "/api/inbox",  # checks its own read-only Bearer key
    "/passkey/login/options", "/passkey/login/verify",
})  # fmt: skip
OPEN_PREFIXES = ("/static/",)
_INVITE = re.compile(r"^/invite/[A-Za-z0-9_-]{20,100}(/options|/verify)?$")

# Data management (owner only): pages a guest may not open, and actions a guest may not send. Methodology
# (/business/method) and the cross rules (/rules) stay readable.
OWNER_PAGES = ("/manage", "/owner", "/business/tam", "/business/quality", "/business/validation", "/business/data",
               "/requests", "/blocks/feedback", "/blocks/area-requests", "/api/blocks/feedback",
               "/business/capabilities/feedback.txt",
               "/shareable/technology-overview/edit")  # fmt: skip
OWNER_ACTIONS = ("/manage", "/owner", "/business/tam", "/business/quality", "/business/validation", "/business/data",
                 "/requests/", "/blocks/feedback/", "/blocks/area-requests/",
                 "/shareable/technology-overview/edit")  # fmt: skip


def is_open(path: str) -> bool:
    return path in OPEN_EXACT or path.startswith(OPEN_PREFIXES) or bool(_INVITE.match(path))


def _under(path: str, prefix: str) -> bool:
    if prefix.endswith("/"):
        return path.startswith(prefix)
    return path == prefix or path.startswith((prefix + "/", prefix + "."))


def owner_only(path: str, method: str) -> bool:
    prefixes = OWNER_PAGES if method in SAFE_METHODS else OWNER_ACTIONS
    return any(_under(path, p) for p in prefixes)
