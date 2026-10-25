"""Automotive grade of a Skyworks / Qorvo part: automotive, industrial/commercial or not stated, and how we know.

Order: the grade the cross lists or the catalogue state, then "AEC-Q" in the part's text, then part-number
conventions. A convention is used only where every part with a stated grade that follows it is automotive
(checked 2026-10-20 on 2,625 parts with a stated grade):
  -AM / -AU suffix (Skyworks isolation, automotive ordering codes)   41/41 and 51/51 automotive
  Q after a Qorvo QP../QM../TQ.. number (QPQ1035Q, QPC1220Q)          6/6 automotive
Dropped: the SKYA prefix (17/19: SKYA21002 and SKYA21024 are stated industrial).
"""

import re
from functools import lru_cache

AUTOMOTIVE, NOT_AUTO, NOT_STATED = "automotive", "industrial/commercial", "not stated"

_NOT_AUTO = {"not_automotive", "industrial", "commercial", "consumer"}
_CONVENTIONS = (
    (re.compile(r"-A[MU]\d?R?$"), "part-number convention: -AM / -AU suffix"),
    (re.compile(r"^(?:QP[A-Z]\d{4}|QM\d{5}|TQ[A-Z]\d+)Q$"), "part-number convention: Q suffix (Qorvo)"),
)


def grade(part: dict) -> tuple[str, str]:
    """(grade, how) for a part entry as blocks._candidates gives it (mpn, values, description, detail)."""
    q = (part.get("values") or {}).get("qualification")
    if q == "automotive":
        return AUTOMOTIVE, "stated (cross list or catalogue)"
    if q in _NOT_AUTO:
        return NOT_AUTO, "stated (cross list or catalogue)"
    if "AEC-Q" in f"{part.get('description') or ''} {part.get('detail') or ''}".upper():
        return AUTOMOTIVE, "description says AEC-Q"
    mpn = str(part.get("mpn") or "").upper()
    for rx, how in _CONVENTIONS:
        if rx.search(mpn):
            return AUTOMOTIVE, how
    return NOT_STATED, ""


# ---- the AEC-Q mark on part chips and the "Automotive-qualified only" filter (owner, 24 Oct 2026) ------------------
# One test everywhere (Cross-sell, portfolio, Technology overview): a part counts as AEC-Q qualified only when grade()
# says automotive; everything else (stated industrial or not stated) is marked "not automotive".
@lru_cache
def _catalogue_index() -> dict[str, dict]:
    from app.services import blocks

    out: dict[str, dict] = {}
    for parts in blocks.catalog_parts().values():
        for p in parts:
            out.setdefault(str(p["mpn"]).upper(), p)
    return out


def is_aec(part: dict | str) -> bool:
    """AEC-Q qualified (automotive grade): from the part's own values when it has them ("implies" as parts_for gives
    them), else from its catalogue entry; a part number alone is looked up in the catalogue."""
    p = {"mpn": part} if isinstance(part, str) else part
    if not p.get("values") and p.get("implies"):
        p = {**p, "values": p["implies"]}
    g = grade(p)[0]
    if g == NOT_STATED:
        known = _catalogue_index().get(str(p.get("mpn") or "").upper())
        if known is not None and known is not p:
            g = grade(known)[0]
    return g == AUTOMOTIVE


def of_row(row: dict) -> dict:
    """A catalogue browse row (blocks.catalog_rows) in the form grade() reads."""
    a = row.get("automotive")
    q = "automotive" if a else "not_automotive" if a is False else None
    return {"mpn": row["mpn"], "values": {"qualification": q}, "description": row.get("description") or "",
            "detail": " ".join(map(str, (row.get("key_specs") or {}).values()))}  # fmt: skip


def marked(parts: list, aec_only: bool = False) -> tuple[list[dict], int]:
    """Part chips with their mark (`aec`: True / False) and, under the filter, only the AEC-Q ones: (shown, hidden).
    Nothing is dropped silently: the page says how many non-automotive parts the filter hides."""
    out = [{**({"mpn": p} if isinstance(p, str) else p), "aec": is_aec(p)} for p in parts]
    shown = [p for p in out if p["aec"]] if aec_only else out
    return shown, len(out) - len(shown)
