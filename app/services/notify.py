"""Telegram messages to the owner: the daily run's status (scripts/telegram.py) and the site's security alerts.

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from the environment. Talks only to api.telegram.org and only to the
owner's chat. The token is never printed or logged.

``alert`` is for the site: when the two variables are not set it logs and skips; otherwise it sends in a background
thread with a 3-second timeout, so a request never waits for Telegram and never fails because of it. Alerts carry no
secrets, tokens or links (``clean`` removes any that slip in).
"""

import json
import logging
import os
import re
import ssl
import threading
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.telegram.org"
LIMIT = 4000  # Telegram allows 4096 characters per message
ALERT_TIMEOUT = 3.0

log = logging.getLogger("crosslist.notify")


def _ctx() -> ssl.SSLContext:
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    return ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()


def _call(token: str, method: str, _timeout: float = 60, **params) -> dict:
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(f"{API}/bot{token}/{method}", data=data, timeout=_timeout, context=_ctx()) as r:
            out = json.load(r)
    except urllib.error.HTTPError as e:
        try:
            desc = json.load(e).get("description", "")
        except ValueError:
            desc = ""
        raise RuntimeError(f"Telegram refused {method}: HTTP {e.code} {desc}".strip()) from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Telegram not reachable ({e.reason}); is api.telegram.org allowed?") from None
    if not out.get("ok"):
        raise RuntimeError(f"Telegram refused {method}: {out.get('description', '')}")
    return out


def send(token: str, chat: str, text: str, timeout: float | None = None) -> int:
    """Send ``text`` (split into parts Telegram accepts); the unix time of the last part sent."""
    text = text.strip() or "(empty)"
    parts = [text[i:i + LIMIT] for i in range(0, len(text), LIMIT)]
    extra = {"_timeout": timeout} if timeout else {}
    sent = 0
    for p in parts:
        sent = _call(token, "sendMessage", chat_id=chat, text=p, disable_web_page_preview="true",
                     **extra)["result"]["date"]  # fmt: skip
    return sent


def replies(token: str, chat: str, since: int) -> list[str]:
    """The owner's text messages since ``since`` (unix time), oldest first; read updates are acknowledged."""
    ups = _call(token, "getUpdates", timeout=0, allowed_updates='["message"]')["result"]
    if ups:
        _call(token, "getUpdates", offset=ups[-1]["update_id"] + 1, timeout=0)  # don't see them again
    msgs = [u["message"] for u in ups if "message" in u]
    return [m.get("text", "") for m in msgs if str(m["chat"]["id"]) == chat and m["date"] >= since and m.get("text")]


def settings() -> tuple[str, str] | None:
    """(bot token, chat id) from the environment, or None when either is missing."""
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip(), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    return (token, chat) if token and chat else None


# --- the site's security alerts --------------------------------------------------------------------------------------
_LINK = re.compile(r"https?://\S+|/invite/[A-Za-z0-9_-]+|\b[A-Za-z0-9_-]{32,}\b")


def clean(text: str) -> str:
    """The alert text without links or anything that looks like a token (long random strings)."""
    return _LINK.sub("[removed]", text).strip()[:LIMIT]


def _deliver(token: str, chat: str, text: str) -> None:
    try:
        send(token, chat, text, timeout=ALERT_TIMEOUT)
    except Exception as e:  # never let an alert break anything
        log.warning("Telegram alert not sent: %s", str(e).replace(token, "<token>"))


def _start(target, *args) -> None:
    threading.Thread(target=target, args=args, daemon=True, name="telegram-alert").start()


def alert(text: str) -> bool:
    """Tell the owner about a security event. True when a message was started, False when alerts are off."""
    text = "BizDev: " + clean(text)
    cfg = settings()
    if cfg is None:
        log.info("alert not sent (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set): %s", text)
        return False
    log.info("alert: %s", text)
    _start(_deliver, cfg[0], cfg[1], text)
    return True
