"""Automotive grade of a Skyworks / Qorvo part: automotive, industrial/commercial or not stated, and how we know.

Order: the grade the cross lists or the catalogue state, then "AEC-Q" in the part's text, then part-number
conventions. A convention is used only where every part with a stated grade that follows it is automotive
(checked 2026-10-20 on 2,625 parts with a stated grade):
  -AM / -AU suffix (Skyworks isolation, automotive ordering codes)   41/41 and 51/51 automotive
  Q after a Qorvo QP../QM../TQ.. number (QPQ1035Q, QPC1220Q)          6/6 automotive
Dropped: the SKYA prefix (17/19: SKYA21002 and SKYA21024 are stated industrial).
"""

import re

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
