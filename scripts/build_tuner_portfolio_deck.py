"""Skyworks tuner portfolio deck (owner, 10 Nov 2026): build the animated .pptx (app/services/tuner_deck.py), run the
checks and write it to a local file for a look. The site builds it on request for the owner only (Shareable >
Private · only for you), so the file is never committed or served from static/.

    uv run python scripts/build_tuner_portfolio_deck.py                 # writes var/skyworks-tuner-portfolio.pptx
    uv run python scripts/build_tuner_portfolio_deck.py path/to/out.pptx
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.services import tuner_deck as td  # noqa: E402
from app.services.pptx_anim import check  # noqa: E402


def main(argv: list[str]) -> int:
    out = Path(argv[0]) if argv else ROOT / "var" / td.FILENAME
    blob = td.build()
    problems = check(blob)
    for p in problems:
        print(p)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    print(f"wrote {out} ({len(blob) // 1024} KB, {len(problems)} problems)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
