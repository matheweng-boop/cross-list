"""Re-file RF catalogue parts whose BizDev function is too general, by rules on the published description.

  uv run python tools/rf_remap.py            # dry run: print what would change
  uv run python tools/rf_remap.py --write    # edit data/catalog/*_parts.yaml in place

A rule sets a more specific `function` and keeps the old one in `also`, so the part still fills both blocks
(see blocks.catalog_parts). Re-running is safe: parts already carrying the target function are skipped.
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FILES = [ROOT / "data/catalog/skyworks_parts.yaml", ROOT / "data/catalog/qorvo_parts.yaml"]
GNSS = re.compile(r"GNSS|GPS|GLONASS|Galileo|\bBDS\b|Compass")

# (name, test(part, function) -> bool, new function, also); the first matching rule wins
RULES = [
    ("GNSS LNA / front end", lambda p, f: f in ("lna", "rf_frontend", "power_amplifier", "rf_gain_block")
     and GNSS.search(p["description"]) and re.search(r"low-noise|\bLNA\b|front-end", p["description"], re.I),
     "gnss_lna", "lna"),
    ("Diversity receive module", lambda p, f: f == "rf_frontend"
     and re.search(r"diversity (receive|LNA|FEM|LFEM)|RX diversity", p["description"], re.I),
     "diversity_rx_module", "rf_frontend"),
    ("Driver amplifier", lambda p, f: f in ("rf_gain_block", "power_amplifier")
     and re.search(r"driver amp|pre-?driver", p["description"], re.I),
     None, "rf_predriver"),
]  # fmt: skip


def plan(path: Path) -> list[tuple[str, str, str | None, str, str]]:
    out = []
    for p in yaml.safe_load(path.read_text()).get("parts") or []:
        f = p.get("function")
        if f in ("gnss_lna", "diversity_rx_module") or "rf_predriver" in (p.get("also") or []):
            continue
        for name, test, new, also in RULES:
            if test({**p, "description": p.get("description") or ""}, f):
                out.append((p["mpn"], f, new, also if also != (new or f) else f, name))
                break
    return out


def apply(path: Path, changes: list) -> None:
    lines = path.read_text().splitlines(keepends=True)
    starts = {ln[len("- mpn: ") :].strip().strip("'\""): i for i, ln in enumerate(lines) if ln.startswith("- mpn: ")}
    edits = []
    for mpn, old, new, also, name in changes:
        i = starts[mpn]
        j = i + 1
        while j < len(lines) and not lines[j].startswith("- "):
            if lines[j].startswith("  function: "):
                break
            j += 1
        assert lines[j].startswith("  function: "), mpn
        func = f"  function: {new}\n" if new else lines[j]
        old_also = [x for x in [old if new else None] if x]
        keep = [a for a in dict.fromkeys([*old_also, also]) if a and a != (new or old)]
        edits.append((j, [func, f"  also: [{', '.join(keep)}]  # {name.lower()} (tools/rf_remap.py)\n"]))
    for j, repl in sorted(edits, reverse=True):
        lines[j : j + 1] = repl
    path.write_text("".join(lines))


def main(write: bool) -> None:
    for path in FILES:
        changes = plan(path)
        for mpn, old, new, also, name in changes:
            print(f"{path.name:20} {mpn:22} {old:16} -> {new or old:20} also {also:14} {name}")
        print(f"{path.name}: {len(changes)} parts")
        if write and changes:
            apply(path, changes)


if __name__ == "__main__":
    main("--write" in sys.argv)
