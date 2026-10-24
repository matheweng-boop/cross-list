"""Who is signed in: the session cookie, the accounts behind it, login throttling and the proof of work.

The cookie holds the account id, its role and its session_version, signed with the site key. Every request checks the
account in the database too, so removing a guest (or bumping session_version) signs them out at once.
"""

import hashlib
import hmac
import logging
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Account, PowSpent

COOKIE = "crosslist_auth"
MAX_AGE = 30 * 24 * 3600
OWNER, GUEST = "owner", "guest"
REPLAY = "crosslist.replay"  # ASGI scope key set only by the owner's approval of a guest item (never from HTTP)

log = logging.getLogger("crosslist.auth")
_PROCESS_KEY = secrets.token_bytes(32)


@dataclass(frozen=True)
class Principal:
    id: int
    name: str
    role: str

    @property
    def is_owner(self) -> bool:
        return self.role == OWNER

    @property
    def is_guest(self) -> bool:
        return self.role == GUEST


def now() -> datetime:
    return datetime.now(UTC)


def aware(dt: datetime | None) -> datetime | None:
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


def site_key() -> bytes | None:
    """The signing key; changing the password signs everyone out. None when the site has neither key nor password."""
    s = get_settings()
    base = s.secret_key or s.site_password
    if not base:
        return None
    return hmac.new(base.encode(), b"crosslist:" + s.site_password.encode(), hashlib.sha256).digest()


def _sign(text: str, key: bytes) -> str:
    return hmac.new(key, text.encode(), hashlib.sha256).hexdigest()


def make_cookie(account: Account) -> str:
    key = site_key()
    if key is None:
        raise RuntimeError("no site key")
    body = f"v2.{account.id}.{account.role}.{account.session_version}.{int(time.time())}"
    return f"{body}.{_sign(body, key)}"


def read_cookie(value: str) -> tuple[int, str, int] | None:
    """(account id, role, session_version) from a well-signed, unexpired cookie, else None."""
    key = site_key()
    if key is None or not value:
        return None
    body, _, sig = value.rpartition(".")
    if not body or not hmac.compare_digest(sig, _sign(body, key)):
        return None
    parts = body.split(".")
    if len(parts) != 5 or parts[0] != "v2" or parts[2] not in (OWNER, GUEST):
        return None
    try:
        aid, sv, issued = int(parts[1]), int(parts[3]), int(parts[4])
    except ValueError:
        return None
    if not 0 <= time.time() - issued <= MAX_AGE:
        return None
    return aid, parts[2], sv


def account_from_cookie(session: Session, value: str) -> Account | None:
    got = read_cookie(value)
    if got is None:
        return None
    aid, role, sv = got
    acct = session.get(Account, aid)
    if acct is None or acct.disabled or acct.role != role or acct.session_version != sv:
        return None
    return acct


def set_login_cookie(resp, request: Request, account: Account) -> None:
    resp.set_cookie(COOKIE, make_cookie(account), max_age=MAX_AGE, httponly=True, samesite="lax",
                    secure=request.url.scheme == "https", path="/")  # fmt: skip


def ensure_owner(session: Session) -> Account:
    acct = session.scalar(select(Account).where(Account.role == OWNER).order_by(Account.id).limit(1))
    if acct is None:
        acct = Account(name="Owner", role=OWNER, handle=new_handle())
        session.add(acct)
        session.flush()
    return acct


def new_handle() -> str:
    from webauthn.helpers import bytes_to_base64url

    return bytes_to_base64url(secrets.token_bytes(32))


def principal(request: Request) -> Principal | None:
    return getattr(request.state, "principal", None)


def client_ip(request: Request) -> str:
    """The visitor's address. On Render every request comes through Render's proxy, and uvicorn runs with
    --proxy-headers, so request.client is already the first X-Forwarded-For address; locally it is the socket."""
    return request.client.host if request.client else "unknown"


# --- login throttling (in memory: the site runs as one process) -------------------------------------------------------
class LoginGuard:
    WINDOW = 300  # attempts per IP: at most ATTEMPTS in WINDOW seconds
    ATTEMPTS = 30
    FAIL_WINDOW = 900  # FAILURES failures in FAIL_WINDOW seconds lock the IP for LOCK seconds
    FAILURES = 10
    LOCK = 900
    SPIKE_WINDOW = 300  # more than SPIKE failures site-wide in SPIKE_WINDOW seconds: every attempt waits SLOWDOWN s
    SPIKE = 50
    SLOWDOWN = 3.0

    def __init__(self):
        self.reset()

    def reset(self) -> None:
        self.attempts: dict[str, deque] = defaultdict(deque)
        self.failures: dict[str, deque] = defaultdict(deque)
        self.locked: dict[str, float] = {}
        self.all_failures: deque = deque()

    @staticmethod
    def _trim(q: deque, window: float, t: float) -> deque:
        while q and q[0] <= t - window:
            q.popleft()
        return q

    def refuse(self, ip: str) -> str | None:
        """Record an attempt; a plain-English reason when this IP must wait, else None."""
        t = time.monotonic()
        if self.locked.get(ip, 0) > t:
            return "Too many failed sign-ins from this network. Try again in 15 minutes."
        self.locked.pop(ip, None)
        q = self._trim(self.attempts[ip], self.WINDOW, t)
        if len(q) >= self.ATTEMPTS:
            return "Too many sign-in attempts. Wait a few minutes and try again."
        q.append(t)
        return None

    def failed(self, ip: str, how: str) -> bool:
        """Record a failure; True when it locked the address just now."""
        t = time.monotonic()
        q = self._trim(self.failures[ip], self.FAIL_WINDOW, t)
        q.append(t)
        self._trim(self.all_failures, self.SPIKE_WINDOW, t).append(t)
        log.warning("sign-in failed: ip=%s method=%s recent_failures=%d", ip, how, len(q))  # never the password
        if len(q) >= self.FAILURES:
            self.locked[ip] = t + self.LOCK
            q.clear()
            log.warning("sign-in locked for 15 minutes: ip=%s", ip)
            return True
        return False

    def slowdown(self) -> float:
        t = time.monotonic()
        return self.SLOWDOWN if len(self._trim(self.all_failures, self.SPIKE_WINDOW, t)) > self.SPIKE else 0.0


guard = LoginGuard()


# --- proof of work ---------------------------------------------------------------------------------------------------
POW_TTL = 300


def _pow_key() -> bytes:
    return hmac.new(site_key() or _PROCESS_KEY, b"crosslist:pow", hashlib.sha256).digest()


def pow_issue() -> dict:
    bits = max(0, min(get_settings().pow_bits, 28))
    body = f"{secrets.token_hex(16)}.{int(time.time()) + POW_TTL}.{bits}"
    return {"challenge": f"{body}.{_sign(body, _pow_key())[:32]}", "bits": bits}


def _zero_bits(digest: bytes) -> int:
    n = 0
    for b in digest:
        if b == 0:
            n += 8
            continue
        return n + 8 - b.bit_length()
    return n


def pow_check(session: Session, challenge: str, nonce: str) -> bool:
    """True once per challenge: well signed, not expired, and SHA-256(challenge:nonce) starts with enough zero bits."""
    if not challenge or not nonce or len(nonce) > 32 or len(challenge) > 200:
        return False
    body, _, sig = challenge.rpartition(".")
    if not body or not hmac.compare_digest(sig, _sign(body, _pow_key())[:32]):
        return False
    try:
        rand, exp, bits = body.split(".")
        exp_i, bits_i = int(exp), int(bits)
    except ValueError:
        return False
    if exp_i < time.time() or bits_i < min(get_settings().pow_bits, 28):
        return False
    if _zero_bits(hashlib.sha256(f"{challenge}:{nonce}".encode()).digest()) < bits_i:
        return False
    session.execute(delete(PowSpent).where(PowSpent.expires_at < now()))
    try:
        with session.begin_nested():
            session.add(PowSpent(key=rand, expires_at=now() + timedelta(seconds=POW_TTL + 60)))
    except IntegrityError:
        return False
    session.commit()
    return True
