"""Run the full data scan (app/services/validation.py) and write docs/data_scan.md. Read-only.

uv run python tools/data_scan.py
"""

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from app.db import get_session
    from app.services import validation

    session = next(get_session())
    r = validation.scan(session)
    t = r["totals"]
    out = [f"# Data scan – {date.today()}", "",
           f"{r['passed']:,} of {r['checked']:,} automatic checks passed. Items for a person: "
           f"{t.get('high', 0)} high, {t.get('medium', 0)} medium, {t.get('low', 0)} low.", "",
           "## Confirmed automatically", ""]  # fmt: skip
    for area, a in r["areas"].items():
        out += [f"### {area} ({a['records']:,} records)", "", "| Check | Passed | Rule |", "|---|---|---|"]
        out += [f"| {c['name']} | {c['passed']:,} / {c['total']:,} | {c['rule']} |" for c in a["checks"]]
        out.append("")
    out += [
        "## Needs a person",
        "",
        "| Priority | Area | What to check | Why a person | Impact if wrong |",
        "|---|---|---|---|---|",
    ]
    for i in r["items"]:
        ex = f" (e.g. {', '.join(map(str, i['examples'][:4]))})" if i["examples"] else ""
        out.append(f"| {i['priority']} | {i['area']} | {i['title']}{ex} | {i['why']} | {i['impact']} |")
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "data_scan.md").write_text("\n".join(out) + "\n")
    print(f"wrote docs/data_scan.md: {len(r['items'])} items for a person")


if __name__ == "__main__":
    main()
