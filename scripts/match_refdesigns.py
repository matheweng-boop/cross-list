"""Match the public reference designs to the library block diagrams and write data/blocks/refdesign_matches.yaml.

    uv run python scripts/match_refdesigns.py            # matches + anchors (crosses from data/real, ~2 minutes)
    uv run python scripts/match_refdesigns.py --add      # also add clearly missing, common blocks to the templates
                                                          # (and remove earlier additions that no longer qualify)
    uv run python scripts/match_refdesigns.py --no-crosses --out /tmp/x.yaml   # quick run without anchors

Run it in the daily update when data/reference_designs/, data/real/ or data/blocks/templates.yaml changed. The output
depends only on those files (no dates, sorted), so two runs give the same file. Anchors use the site's own crosses: the
real part data is loaded into a throw-away in-memory database and crossed as on the part pages.
"""

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

HEADER = """# Public reference designs behind the library block diagrams (owner, 25 Oct 2026: one representative
# diagram per application, informed by all matching designs). Written by scripts/match_refdesigns.py; do not edit
# by hand.
# anchors: design part (as the design names it) -> our crossed part (the site's crosses; type as on the part pages)
# design_anchors: design (vendor:id) -> its anchor parts
# diagrams: per library diagram its matched designs (best first), how many of them contain each function,
#   the diagram's functions they confirm, the common functions it lacks (suggested, >= 40 %, n >= 4) and anchors.
"""


def _session(crosses: bool):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from sqlalchemy.pool import StaticPool

    import app.models  # noqa: F401  (registers the tables)
    from app.db import Base

    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(eng)
    s = Session(eng)
    if crosses:
        from app.services.seed import load_file

        for f in sorted((ROOT / "data" / "real").glob("*.yaml")):
            load_file(s, f)
        s.flush()
    return s


def run(out: Path, crosses: bool = True) -> dict:
    from app import yamlio  # noqa: F401  (C loader)
    from app.services import refmatch

    data = refmatch.build(_session(crosses))
    import yaml

    out.write_text(HEADER + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120))
    return data


def refmatch_rule() -> str:
    from app.services import refmatch

    return f">= {refmatch.ADD_SHARE:.0%} and >= {refmatch.ADD_MIN} matched designs"


def _group_for(t: dict, fn: str) -> str | None:
    """The frame a new block goes in: the one holding most blocks of the same category; None when no frame holds
    one (then the block stays a suggestion: there is no natural place for it)."""
    from app.services import blocks

    cat = blocks.catalogue()["functions"]
    want = (cat.get(fn) or {}).get("category")
    score = [(sum(1 for b in g.get("blocks") or []
                  if (cat.get(b["fn"] if isinstance(b, dict) else str(b).split()[0]) or {}).get("category") == want),
              -i, g["id"]) for i, g in enumerate(t.get("groups") or [])]  # fmt: skip
    best = max(score, default=(0, 0, None))
    return best[2] if best[0] else None


def add_blocks(data: dict, path: Path) -> list[tuple[str, str, int, int]]:
    """Add each clearly missing, common function (>= 60 % and >= 8 matched designs) to its template, in place in the
    YAML text: a block {fn: <id>, src: refdesigns} in the best frame and a refdesigns_added note on the template."""
    from app.services import blocks, refmatch

    text = path.read_text()
    tpls = {t.get("name"): t for t in blocks.templates()}
    done = []
    for e in data["diagrams"]:
        t = tpls.get(e["name"])
        add = refmatch.to_add(e, blocks.template_functions(t)) if t else []
        if not t or not add:
            continue
        start = text.index(f"- name: {e['name']}\n") if f"- name: {e['name']}\n" in text else -1
        if start < 0:
            continue
        end = text.find("\n- name:", start + 1)
        end = len(text) if end < 0 else end
        chunk = text[start:end]
        notes = []
        for s in add:
            gid = _group_for(t, s["fn"])
            # the frame in either layout ({id: x, ..., blocks: [...]} or "- id: x" with "blocks: [...]" below)
            m = gid and re.search(r"(?:\{id: |- id: )" + re.escape(gid) + r"[,\n]", chunk)
            b = chunk.find("blocks: [", m.end()) if m else -1
            if b < 0:
                continue
            depth, j = 0, b + len("blocks: ")
            while j < len(chunk):  # the list's closing bracket
                depth += {"[": 1, "]": -1}.get(chunk[j], 0)
                if depth == 0:
                    break
                j += 1
            chunk = chunk[:j] + f", {{fn: {s['fn']}, src: refdesigns}}" + chunk[j:]
            notes.append(f"{s['fn']} ({s['n']} of {e['n']} designs)")
            done.append((e["name"], s["fn"], s["n"], e["n"]))
        if notes:
            line = ("  refdesigns_added: \"Added from the matched public reference designs "
                    f"(scripts/match_refdesigns.py, in at least 60 % of them): {'; '.join(notes)}\"\n")  # fmt: skip
            head_end = chunk.index("\n") + 1
            chunk = chunk[:head_end] + line + chunk[head_end:]
        text = text[:start] + chunk + text[end:]
    path.write_text(text)
    return done


_ADDED = re.compile(r", \{fn: ([a-z0-9_]+), src: refdesigns\}")


def prune_blocks(data: dict, path: Path) -> list[tuple[str, str]]:
    """Remove earlier automatic additions ({fn: x, src: refdesigns}) that no longer qualify under the current
    thresholds (the function in at least ADD_SHARE and ADD_MIN of the matched designs). Only blocks still exactly as
    the script wrote them (marker and note unchanged) are removed: a block the owner touched stays."""
    from app.services import refmatch

    text = path.read_text()
    by_name = {e["name"]: e for e in data["diagrams"]}
    done = []
    for name, e in by_name.items():
        start = text.find(f"- name: {name}\n")
        if start < 0:
            continue
        end = text.find("\n- name:", start + 1)
        end = len(text) if end < 0 else end
        chunk = text[start:end]
        note = re.search(r'  refdesigns_added: "[^"]*"\n', chunk)
        if not note:
            continue  # no note from the script: the owner changed it, leave the blocks alone
        n, fns = e.get("n") or 0, e.get("functions") or {}
        drop = [fn for fn in _ADDED.findall(chunk) if f"{fn} (" in note.group(0)
                and not (fns.get(fn, 0) >= refmatch.ADD_MIN and n and fns.get(fn, 0) / n >= refmatch.ADD_SHARE)]
        if not drop:
            continue
        for fn in drop:
            chunk = chunk.replace(f", {{fn: {fn}, src: refdesigns}}", "", 1)
            done.append((name, fn))
        kept = [x for x in re.findall(r"([a-z0-9_]+ \(\d+ of \d+ designs\))", note.group(0))
                if x.split()[0] not in drop]
        new = note.group(0).split("): ")[0] + "): " + "; ".join(kept) + '"\n' if kept else ""
        chunk = chunk.replace(note.group(0), new, 1)
        text = text[:start] + chunk + text[end:]
    path.write_text(text)
    return done


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "blocks" / "refdesign_matches.yaml")
    ap.add_argument("--no-crosses", action="store_true", help="skip the anchors (no part data loaded)")
    ap.add_argument("--add", action="store_true", help="add clearly missing, common blocks to templates.yaml")
    a = ap.parse_args(argv)
    data = run(a.out, not a.no_crosses)
    if a.add:
        tfile = ROOT / "data" / "blocks" / "templates.yaml"
        removed = prune_blocks(data, tfile)
        for name, fn in removed:
            print(f"removed {fn} from {name} (no longer in {refmatch_rule()})")
        if removed:
            from app.services import blocks

            blocks.templates.cache_clear()
            data = run(a.out, not a.no_crosses)
        added = add_blocks(data, tfile)
        for name, fn, n, of in added:
            print(f"added {fn} to {name} ({n} of {of} designs)")
        if added:  # the templates changed: match again so the file reflects them
            from app.services import blocks

            blocks.templates.cache_clear()
            data = run(a.out, not a.no_crosses)
    ds = data["diagrams"]
    ns = sorted(e["n"] for e in ds if e["n"])
    print(f"{len(ns)} of {len(ds)} diagrams matched; median {ns[len(ns) // 2] if ns else 0} designs; "
          f"{len(data['anchors'])} anchor parts; "
          f"{sum(len(e['suggested']) for e in ds)} suggestions")  # fmt: skip
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
