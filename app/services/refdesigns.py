"""Reference designs collected from manufacturers' public sites (data/reference_designs/*.yaml, see its README)."""

from collections import Counter
from functools import lru_cache
from pathlib import Path

import yaml

from app.services import blocks

DIR = Path(__file__).resolve().parents[2] / "data" / "reference_designs"
DOC_LABELS = {
    "design_guide": "Design guide",
    "schematic": "Schematic",
    "bom": "BOM",
    "layout": "Layout",
    "block_diagram": "Block diagram",
}


@lru_cache
def sources() -> tuple[dict, ...]:
    """The `source` block of every design file (vendor, pages, collected, method)."""
    out = []
    for path in sorted(DIR.glob("*.yaml")):
        if path.stem.endswith("_applications"):
            continue
        data = yaml.safe_load(path.read_text()) or {}
        out.append({**(data.get("source") or {}), "file": path.name, "n": len(data.get("designs") or [])})
    return tuple(out)


@lru_cache
def designs() -> tuple[dict, ...]:
    out = []
    for path in sorted(DIR.glob("*.yaml")):
        if path.stem.endswith("_applications"):
            continue
        for d in (yaml.safe_load(path.read_text()) or {}).get("designs") or []:
            if d.get("id") and d.get("url"):
                d["_text"] = " ".join(
                    str(x)
                    for x in [d["id"], d.get("title"), d.get("summary"), *(d.get("parts") or []),
                              *(d.get("applications") or [])]
                    if x
                ).lower()  # fmt: skip
                out.append(d)
    return tuple(out)


def function_label(fn: str) -> str:
    f = blocks.catalogue()["functions"].get(fn)
    return f["label"] if f else fn.replace("_", " ")


def search(q: str = "", vendor: str = "", market: str = "", fn: str = "", isolation: bool = False,
           docs: bool = False) -> list[dict]:  # fmt: skip
    words = q.lower().split()
    return [
        d
        for d in designs()
        if all(w in d["_text"] for w in words)
        and (not vendor or d.get("vendor") == vendor)
        and (not market or market in (d.get("markets") or []))
        and (not fn or fn in (d.get("functions") or []))
        and (not isolation or d.get("isolation"))
        and (not docs or d.get("documents"))
    ]


def facets(rows: list[dict]) -> dict[str, list[tuple[str, int]]]:
    def count(key):
        c = Counter(v for d in rows for v in (d.get(key) or []))
        return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))

    return {
        "vendor": sorted(Counter(d.get("vendor") for d in rows).items(), key=lambda kv: -kv[1]),
        "market": count("markets"),
        "function": count("functions"),
    }
