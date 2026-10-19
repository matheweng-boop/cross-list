"""Check data/schematic/*.yaml (typical-application data per datasheet) against the parts and the datasheet text.

    python tools/check_typical.py [data/schematic/<file>.yaml ...]

For every file: each entry's datasheet must be one the parts reference; every quote must appear in that datasheet's
text (whitespace-insensitive); every pin regex must match a pin of a part using that datasheet; every `to` must be a
pin name of such a part or a known net. Then coverage: datasheets referenced by parts with a pinout in the real-data
files the schematic file names under `covers:` that have no entry.
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TEXT_DIRS = [ROOT / "var" / "datasheets", ROOT / "var" / "gate_drivers", ROOT / "var" / "text"]
NETS = {"GND", "VDD", "VCC", "VIO", "RF", "OUT", "SIGNAL", "LOAD", "ANTENNA", "SUPPLY"}
KINDS = {"capacitor", "resistor", "ferrite", "inductor", "diode", "crystal", "tvs", "zener"}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace(" ", " ")).strip().lower()


def text_for(datasheet: str) -> str | None:
    stem = Path(datasheet).stem
    for d in TEXT_DIRS:
        for p in d.rglob(stem + ".txt") if d.exists() else []:
            return p.read_text(errors="ignore")
    return None


def parts_by_datasheet(real_files: list[str]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for f in real_files:
        doc = yaml.load((ROOT / f).read_text(), Loader=yaml.CSafeLoader)
        named = doc.get("pinouts") or {}
        for p in doc["parts"]:
            pins = p.get("pinout")
            if isinstance(pins, str):  # a named pin list from the file's `pinouts:` presets
                pins = named.get(pins)
            if pins and p.get("datasheet"):
                out.setdefault(p["datasheet"], []).append({**p, "pinout": pins})
    return out


def check(path: Path) -> list[str]:
    doc = yaml.safe_load(path.read_text())
    errs = []
    parts = parts_by_datasheet(doc.get("covers") or [])
    seen = set()
    for e in doc.get("datasheets") or []:
        ds = e.get("datasheet", "?")
        where = f"{path.name}:{ds}"
        seen.add(ds)
        if ds not in parts:
            errs.append(f"{where}: no part with a pinout uses this datasheet")
            continue
        pins = {n for p in parts[ds] for n in p["pinout"]}
        txt = text_for(ds)
        if txt is None:
            errs.append(f"{where}: datasheet text not found (looked for {Path(ds).stem}.txt under var/)")
        body = norm(txt or "")
        items = [("supplies", s) for s in e.get("supplies") or []]
        items += [("components", c) for c in e.get("components") or []]
        items += [("pin_rules", r) for r in e.get("pin_rules") or []]
        for kind, it in items:
            q = it.get("quote")
            if not q:
                errs.append(f"{where}: {kind} item without quote: {it}")
            elif txt is not None and norm(q) not in body:
                errs.append(f"{where}: quote not found in datasheet text: {q!r}")
            pat = it.get("pins") or (f"^{re.escape(it['pin'])}$" if it.get("pin") else None)
            if pat:
                try:
                    rx = re.compile(pat)
                except re.error as ex:
                    errs.append(f"{where}: bad regex {pat!r}: {ex}")
                    continue
                if not any(rx.search(n) for n in pins):
                    errs.append(f"{where}: {kind} pins {pat!r} match no pin of these parts ({sorted(pins)})")
            if kind == "supplies" and it.get("ground") not in pins | NETS:
                errs.append(f"{where}: supply ground {it.get('ground')!r} is not a pin name or known net")
            if kind == "components":
                if it.get("kind") not in KINDS:
                    errs.append(f"{where}: component kind {it.get('kind')!r} not in {sorted(KINDS)}")
                if it.get("to") not in pins | NETS:
                    errs.append(f"{where}: component 'to' {it.get('to')!r} is not a pin name or known net")
    for ds in sorted(set(parts) - seen):
        errs.append(f"{path.name}: no entry for datasheet {ds} ({len(parts[ds])} parts)")
    return errs


def main(argv: list[str]) -> int:
    files = [Path(a) for a in argv] or sorted((ROOT / "data" / "schematic").glob("*.yaml"))
    bad = 0
    for f in files:
        errs = check(f)
        bad += len(errs)
        print(f"{f.name}: {'ok' if not errs else f'{len(errs)} problem(s)'}")
        for e in errs:
            print("  " + e)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
