"""Pull the owner's comments from the live site for the daily update run.

    uv run python scripts/pull_inbox.py [--since YYYY-MM-DD]

Reads CROSSLIST_SITE_URL (e.g. https://<service>.onrender.com) from the environment. The read-only inbox key (the
same value as CROSSLIST_INBOX_TOKEN on Render) comes either from a network secret of the cloud environment, which
adds "Authorization: Bearer <key>" to requests for the site's host (the key never enters the session), or from the
environment variable CROSSLIST_INBOX_TOKEN. Calls GET /api/inbox and saves the text to
var/inbox/<today>.md (var/ is never committed). Without --since it continues from the last pull (var/inbox/.last),
else from yesterday. Prints the saved path; exits 2 when the site address is missing, 1 when the site refuses
(no key reached it, or a wrong one).
"""

import argparse
import os
import ssl
import sys
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "var" / "inbox"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", help="first day to include, YYYY-MM-DD")
    args = ap.parse_args()
    url, token = os.environ.get("CROSSLIST_SITE_URL", "").rstrip("/"), os.environ.get("CROSSLIST_INBOX_TOKEN", "")
    if not url:
        print("CROSSLIST_SITE_URL must be set (cloud environment settings)", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    last = OUT / ".last"
    today = datetime.now(UTC).date()
    since = args.since or (last.read_text().strip() if last.exists() else str(today - timedelta(days=1)))
    date.fromisoformat(since)  # fail early on a bad date
    headers = {"Authorization": f"Bearer {token}"} if token else {}  # else a network secret adds it on the way
    req = urllib.request.Request(f"{url}/api/inbox?since={since}", headers=headers)
    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    ctx = ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=120, context=ctx) as r:
            text = r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"The site refused: HTTP {e.code} (check the key on Render and the network secret for the site's host)",
              file=sys.stderr)
        return 1
    path = OUT / f"{today}.md"
    path.write_text(text)
    last.write_text(str(today))  # the next pull starts from today, so nothing falls between two runs
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
