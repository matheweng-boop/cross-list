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
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import notify  # noqa: E402  (shared with the site's alerts)


def send(token: str, chat: str, text: str) -> int:
    return notify.send(token, chat, text)


def replies(token: str, chat: str, since: int) -> list[str]:
    return notify.replies(token, chat, since)


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
    cfg = notify.settings()
    if cfg is None:
        print("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set (cloud environment settings)", file=sys.stderr)
        return 2
    token, chat = cfg
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
