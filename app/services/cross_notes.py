"""Engineer notes on specific crosses (data/cross_notes.yaml): the use-case reasoning behind a
recommendation, e.g. why a 13-pin LGA part is accepted against a 14-pin one.

Part numbers match by prefix after removing dashes and spaces, so a note on "UCC20225A-Q1" covers
every orderable code that starts with UCC20225AQ1... as well as the exact code."""

import re
from functools import lru_cache

import yaml

from app.config import PROJECT_ROOT
from app.matching.engine import pin_positions

NOTES_FILE = PROJECT_ROOT / "data" / "cross_notes.yaml"
VERDICTS = {
    "best": "Best option",
    "next_best": "Next best option",
    "acceptable": "Acceptable",
    "not_recommended": "Not recommended",
}


def _key(mpn: str) -> str:
    return re.sub(r"[\s\-–]", "", mpn or "").upper()


@lru_cache
def _notes() -> list[dict]:
    return yaml.safe_load(NOTES_FILE.read_text()) or [] if NOTES_FILE.exists() else []


def notes_for(reference: str, candidate: str) -> list[dict]:
    ref, cand = _key(reference), _key(candidate)
    out = []
    for n in _notes():
        if ref.startswith(_key(n["reference"])) and cand.startswith(_key(n["candidate"])):
            out.append({**n, "verdict_label": VERDICTS.get(n.get("verdict"), n.get("verdict") or "")})
    return out


def position_note(result) -> str | None:
    """Explain a pin-to-pin fit between packages with different pin counts: which positions are
    empty on one side and what the other part has there."""
    ref, cand, fit = result.reference, result.candidate, result.fit
    if not (fit.same_package and fit.same_pinout) or ref.package.pin_count == cand.package.pin_count:
        return None
    rp, cp = pin_positions(ref), pin_positions(cand)
    if rp is None or cp is None:
        return None

    def empty(part):
        pkg = part.package
        if not pkg.pin_positions:
            return set()
        return set(range(1, (pkg.positions_total or pkg.pin_count) + 1)) - set(pkg.pin_positions)

    parts = []
    for pos in sorted(empty(ref)):
        parts.append(f"position {pos} is empty on {ref.mpn} and {cp[pos - 1]} on {cand.mpn}")
    for pos in sorted(empty(cand)):
        parts.append(f"position {pos} is empty on {cand.mpn} and {rp[pos - 1]} on {ref.mpn}")
    if not parts:
        return None
    return (f"{ref.package.pin_count}-pin vs {cand.package.pin_count}-pin package on the same footprint: "
            + "; ".join(parts) + ". All other pins match by position.")  # fmt: skip
