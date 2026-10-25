"""List research items whose gist is still an "auto summary", for the daily run to rewrite (docs/daily_update.md).

    uv run python scripts/auto_gists.py [-n 15] [--type evidence]

Prints, oldest-written-first by type order, the next N items: key, where to write the gist, the page, and the current
auto gist. Write the new `gist:` (one plain sentence, at most 25 words) and `abstract:` (at most 3 short bullets:
what it says, why it matters to us, what decision it asks for) into the item's own YAML entry; items that are HTML or
Markdown only (background notes, idea expansions, open questions) go to data/business/gists.yaml under their key.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import digest  # noqa: E402

WHERE = {
    "evidence": "data/business/evidence/<topic>.yaml, entry <fn> (patent platforms: patents_platforms.yaml)",
    "note": "data/engineering_rf_notes.yaml, topic <id>",
    "question": "data/business/gists.yaml, key question:<id>",
    "expansion": "data/business/gists.yaml, key expansion:<slug>",
    "background": "data/business/gists.yaml, key background:<slug>",
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=15)
    ap.add_argument("--type", choices=list(digest.TYPES), default="")
    args = ap.parse_args()
    rows = [r for r in digest.items() if r["auto"] and (not args.type or r["type"] == args.type)]
    print(f"{len(rows)} auto summaries left; the next {min(args.n, len(rows))}:")
    for r in rows[: args.n]:
        print(f"- {r['key']} · write in: {WHERE.get(r['type'], 'its own YAML entry')} · page {r['href']}\n"
              f"  now: {r['gist']}")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
