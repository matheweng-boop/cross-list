"""Import research files (data/blocks/research/*_more_block_diagrams.yaml) as block-diagram templates and split them:
applications that fit the Skyworks / Qorvo portfolio go to the library (data/blocks/templates.yaml); the others go
to data/blocks/background_templates.yaml, used only for occurrence and attach statistics.

  uv run python tools/import_diagrams.py data/blocks/research/ti_more_block_diagrams.yaml TI [more files + vendors]

Fit = at least MIN_FUNCTIONS distinct functions with a Skyworks or Qorvo part, and at least MIN_SHARE of the
in-scope positions covered. New function ids proposed by a research file are added to functions.yaml (synonyms of
existing ids are mapped instead); a new id is a customer part (source: external) when its technology proximity is 0.
Re-running skips applications already present by name.
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

MIN_FUNCTIONS, MIN_SHARE = 3, 0.3
SYNONYMS = {"application_processor": "soc", "dram": "ddr_flash", "nor_flash": "flash", "nand_flash": "flash",
            "ufs_storage": "flash", "haptic_driver": "haptics_driver", "mems_sensor": "env_sensor"}  # fmt: skip
FUNCTIONS = ROOT / "data/blocks/functions.yaml"
LIBRARY = ROOT / "data/blocks/templates.yaml"
BACKGROUND = ROOT / "data/blocks/background_templates.yaml"


def add_functions(new: dict) -> list[str]:
    """Append proposed function ids that are not in functions.yaml yet (as flow-style lines, like the file)."""
    fns = yaml.safe_load(FUNCTIONS.read_text())["functions"]
    tech = yaml.safe_load((ROOT / "data/business/technology.yaml").read_text()) or {}
    cats = yaml.safe_load(FUNCTIONS.read_text())["categories"]
    lines, added = [], []
    for fid, f in (new or {}).items():
        if fid in fns or fid in SYNONYMS:
            continue
        cat = f.get("category") if f.get("category") in cats else "sensors"
        entry = {"label": str(f.get("label") or fid), "category": cat}
        if (tech.get(fid) or {}).get("proximity", 0) == 0:
            entry["source"] = "external"
        if f.get("note"):
            entry["note"] = str(f["note"])[:160]
        lines.append(f"  {fid}: " + yaml.safe_dump(entry, default_flow_style=True, width=1000).strip())
        added.append(fid)
    if lines:
        with FUNCTIONS.open("a") as fh:
            fh.write("  # added by tools/import_diagrams.py from research files\n" + "\n".join(lines) + "\n")
    return added


def remap(app: dict) -> dict:
    for g in app.get("groups") or []:
        g["fn_hint"] = [SYNONYMS.get(str(h).split(" (")[0], h) for h in g.get("fn_hint") or []]
    return app


def fits(t: dict, mk: dict, mine: frozenset) -> tuple[bool, int, float]:
    from app.services import opportunity as op

    fns = [b["fn"] if isinstance(b, dict) else str(b).split(" x")[0].strip() for g in t["groups"] for b in g["blocks"]]
    st = [op.status_of(f, mk, mine) for f in fns]
    scope = [s for s in st if s in op.IN_SCOPE]
    ours = {f for f, s in zip(fns, st, strict=True) if s == "supported"}
    share = sum(s == "supported" for s in scope) / len(scope) if scope else 0.0
    return len(ours) >= MIN_FUNCTIONS and share >= MIN_SHARE, len(ours), share


def main(pairs: list[tuple[str, str]]) -> None:
    research = [(yaml.safe_load(Path(p).read_text()), vendor) for p, vendor in pairs]
    for r, _ in research:
        print("new functions:", add_functions(r.get("new_functions") or {}))
    import research_to_templates as rt  # reads functions.yaml at import: after add_functions

    from app import db
    from app.services import blocks
    from app.services import opportunity as op

    blocks.catalogue.cache_clear()
    session = next(db.get_session())
    mk, mine = op.makers(session), op.COMPANIES["combined"][1]
    existing = {t["name"] for t in (yaml.safe_load(LIBRARY.read_text()) or [])}
    existing |= {t["name"] for t in (yaml.safe_load(BACKGROUND.read_text()) or [])} if BACKGROUND.exists() else set()
    lib, bg = [], []
    for r, vendor in research:
        for app in r["applications"]:
            t = rt.convert(remap(app), r.get("docs") or {}, app.get("vendor") or vendor, app.get("category") or "Other")
            if t["name"] in existing:
                continue
            ok, n, share = fits(t, mk, mine)
            (lib if ok else bg).append(t)
            print(f"{'LIBRARY   ' if ok else 'background'} {n:2d} fns {share:4.0%}  {t['name']}")
    for path, out in ((LIBRARY, lib), (BACKGROUND, bg)):
        if out:
            text = yaml.safe_dump(out, sort_keys=False, allow_unicode=True, width=200, default_flow_style=None)
            head = "" if path.exists() else (
                "# Diagrams that do not fit the Skyworks / Qorvo portfolio (tools/import_diagrams.py): not shown in\n"
                "# the library, used only for occurrence and attach statistics on the Business opportunity pages.\n"
            )  # fmt: skip
            with path.open("a") as fh:
                fh.write(f"{head}\n# ---- imported by tools/import_diagrams.py\n{text}")
    print(f"{len(lib)} to the library, {len(bg)} to the background")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(list(zip(args[::2], args[1::2], strict=True)))
