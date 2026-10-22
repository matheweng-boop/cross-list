"""Telegram channel of the daily update run: send the owner a short status, read the owner's replies.

    uv run python scripts/telegram.py send < summary.txt
    uv run python scripts/telegram.py replies [--since UNIX_TIME]
    uv run python scripts/telegram.py wait-go --since UNIX_TIME [--minutes 30]

Reads TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID from the environment (cloud environment settings). Talks only to
api.telegram.org and only to the owner's chat: messages from any other chat are ignored. The token is never printed.
Only status, questions and go-ahead requests go out (no comments, data or keys); replies are the owner's words to
weigh, not commands to run.

``send`` prints the sent message's unix time (pass it to wait-go). ``wait-go`` exits 0 when the owner replies GO
after that time, 1 when the time runs out, and prints every other reply. Exit 2: token or chat id missing; 3: Telegram
refused or could not be reached.
"""

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.telegram.org"
LIMIT = 4000  # Telegram allows 4096 characters per message


def _ctx() -> ssl.SSLContext:
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    return ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()


def _call(token: str, method: str, **params) -> dict:
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(f"{API}/bot{token}/{method}", data=data, timeout=60, context=_ctx()) as r:
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


def send(token: str, chat: str, text: str) -> int:
    text = text.strip() or "(empty)"
    parts = [text[i:i + LIMIT] for i in range(0, len(text), LIMIT)]
    sent = 0
    for p in parts:
        sent = _call(token, "sendMessage", chat_id=chat, text=p, disable_web_page_preview="true")["result"]["date"]
    return sent


def replies(token: str, chat: str, since: int) -> list[str]:
    """The owner's text messages since ``since`` (unix time), oldest first; read updates are acknowledged."""
    ups = _call(token, "getUpdates", timeout=0, allowed_updates='["message"]')["result"]
    if ups:
        _call(token, "getUpdates", offset=ups[-1]["update_id"] + 1, timeout=0)  # don't see them again
    msgs = [u["message"] for u in ups if "message" in u]
    return [m.get("text", "") for m in msgs if str(m["chat"]["id"]) == chat and m["date"] >= since and m.get("text")]


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("send")
    r = sub.add_parser("replies")
    r.add_argument("--since", type=int, default=0)
    w = sub.add_parser("wait-go")
    w.add_argument("--since", type=int, required=True)
    w.add_argument("--minutes", type=float, default=30)
    args = ap.parse_args()
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat:
        print("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set (cloud environment settings)", file=sys.stderr)
        return 2
    try:
        if args.cmd == "send":
            print(send(token, chat, sys.stdin.read()))
            return 0
        if args.cmd == "replies":
            print("\n".join(f"- {t}" for t in replies(token, chat, args.since)) or "No replies.")
            return 0
        end = time.time() + args.minutes * 60
        while True:
            for t in replies(token, chat, args.since):
                if t.strip().strip(".!").upper() == "GO":
                    print("GO")
                    return 0
                print(f"- {t}")
            if time.time() >= end:
                print("No GO before the time ran out.")
                return 1
            time.sleep(min(60, max(1, end - time.time())))
    except RuntimeError as e:
        print(str(e).replace(token, "<token>"), file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
