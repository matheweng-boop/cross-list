"""Daily accuracy check of the cross engine (owner, 26 Oct 2026; docs/daily_update.md).

    uv run python scripts/check_cross_accuracy.py [--write]

Re-crosses every known-answer pair (data/manage/cross_known_pairs.yaml: pairs the owner marked Right or Wrong on
Products › Cross a list, and the engineer notes in data/cross_notes.yaml) with the same two result columns as the
Cross a list page, against the database the site settings point to (var/crosslist.db locally). Prints the hit rate
and the misses; --write saves them to data/manage/cross_accuracy.yaml, which the page shows as "Drop-ins correct:
X % of N known pairs (checked <date>)". Exit code 0 always (a miss is work for the run, not a failure).
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import PROJECT_ROOT  # noqa: E402
from app.db import init_engine  # noqa: E402
from app.services import crosslist  # noqa: E402

OUT = PROJECT_ROOT / "data" / "manage" / crosslist.ACCURACY_FILE


def to_yaml(res: dict) -> str:
    data = {k: res[k] for k in ("checked", "n", "hits", "rate", "misses")} | {"not_in_data": len(res["not_in_data"])}
    head = "# Written by scripts/check_cross_accuracy.py (daily run). Shown on Products › Cross a list.\n"
    return head + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=200)


def main(argv=None, session: Session | None = None, out: Path = OUT) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args(argv)
    if session is None:
        session = Session(init_engine())
    res = crosslist.check_accuracy(session, crosslist.known_pairs())
    print(f"Drop-ins correct: {res['rate']} % of {res['n']} known pairs ({len(res['not_in_data'])} not in the data)")
    for m in res["misses"]:
        print("  miss:", m)
    if args.write:
        out.write_text(to_yaml(res))
        print("written:", out)
    return res


if __name__ == "__main__":
    main()
