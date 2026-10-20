"""Reference designs collected from manufacturers' public sites (data/reference_designs/*.yaml, see its README)."""

import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from app import yamlio

DIR = Path(__file__).resolve().parents[2] / "data" / "reference_designs"
DOC_LABELS = {
    "design_guide": "Design guide",
    "schematic": "Schematic",
    "bom": "BOM",
    "layout": "Layout",
    "block_diagram": "Block diagram",
}


@lru_cache
def _files() -> tuple[tuple[Path, dict], ...]:
    """Every design file, parsed once per process."""
    paths = sorted(DIR.glob("*.yaml"))
    return tuple((path, yamlio.load(path.read_text()) or {}) for path in paths)


@lru_cache
def sources() -> tuple[dict, ...]:
    """The `source` block of every design file (vendor, pages, collected, method)."""
    return tuple({**(data.get("source") or {}), "file": path.name, "n": len(data.get("designs") or [])}
                 for path, data in _files())  # fmt: skip


@lru_cache
def designs() -> tuple[dict, ...]:
    out = []
    for _path, data in _files():
        for d in data.get("designs") or []:
            if d.get("id") and d.get("url"):
                d["_text"] = " ".join(
                    str(x)
                    for x in [d["id"], d.get("title"), d.get("summary"), *(d.get("parts") or []),
                              *(d.get("applications") or [])]
                    if x
                ).lower()  # fmt: skip
                out.append(d)
    return tuple(out)


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


_SUFFIX = re.compile(r"(?:[-\s].*)$")  # ordering / grade suffixes: -Q1, -1, " G", -2C, -M ...
_RUN = re.compile(r"\d{4,}")


def family_of(mpn: str) -> str:
    """Product family of a part number: the last two digits of its first 4+ digit series become "xx" and a suffix of
    two or more letters right after it is kept (1EDI3025AS and 1EDI3035AS -> 1EDI30xxAS; UCC21540 -> UCC215xx).
    A part number without such a series is its own family: nothing is merged by guesswork."""
    stem = _SUFFIX.sub("", mpn.strip()).upper() or mpn.strip().upper()
    m = _RUN.search(stem)
    if not m:
        return stem
    letters = re.match(r"[A-Z]*", stem[m.end() :]).group(0)
    # TI's 4-digit LM numbers are a running catalogue (LM5113 driver, LM5180 flyback): only the last digit varies
    keep = 1 if stem[: m.start()] == "LM" and len(m.group(0)) == 4 else 2
    return stem[: m.end() - keep] + "x" * keep + (letters if len(letters) >= 2 else "")


def families(rows: list[dict], q: str = "") -> list[dict]:
    """Families of the parts used in the given designs, most used first: members (with the number of designs each
    is in) and the designs. ``q`` keeps families whose name or member matches, when it names a part."""
    fam: dict[tuple[str, str], dict] = {}
    for d in rows:
        for p in d.get("parts") or []:
            key = (d["vendor"], family_of(p))
            f = fam.setdefault(key, {"family": key[1], "vendor": key[0], "members": Counter(), "designs": {}})
            f["members"][p] += 1
            f["designs"][d["id"]] = d
    out = list(fam.values())
    words = q.upper().split()
    if words:
        hit = [f for f in out if all(any(w in s for s in [f["family"], *f["members"]]) for w in words)]
        out = hit or out
    for f in out:
        f["designs"] = sorted(f["designs"].values(), key=lambda d: d.get("title") or "")
        f["markets"] = Counter(m for d in f["designs"] for m in d.get("markets") or []).most_common(3)
        f["functions"] = Counter(x for d in f["designs"] for x in d.get("functions") or []).most_common(4)
    return sorted(out, key=lambda f: (-len(f["designs"]), f["family"]))


def grouped_parts(parts: list[str]) -> list[tuple[str, list[str]]]:
    """A design's parts grouped by family, in first-seen order."""
    out: dict[str, list[str]] = {}
    for p in parts:
        out.setdefault(family_of(p), []).append(p)
    return list(out.items())
