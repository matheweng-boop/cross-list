"""Part numbers compare without case and without separators: "Si8641BD-IS", "SI8641BD IS" and "si8641bd–is" are the
same part. The database search strips the same characters in SQL (app/services/queries.py), so a part number matches
the same way on every page. ``*`` stays (a wildcard in searches)."""

import re

SEPARATORS = (" ", "-", "–", "_", "/", ".", ",", "#")
_SEP = re.compile("[" + re.escape("".join(SEPARATORS)) + r"\s]")


def normalize_pn(text: str | None) -> str:
    return _SEP.sub("", text or "").upper()


def reel_q1_variants(key: str) -> list[str]:
    """The same automotive ordering code with and without its reel letter: TI puts the reel "R" before the "Q1"
    suffix (ISOW7841AQDWERQ1 is the reel of ISOW7841AQDWEQ1). Takes and returns normalised part numbers."""
    if not key.endswith("Q1") or len(key) < 7:
        return []
    if key.endswith("RQ1"):
        return [key[:-3] + "Q1"]
    return [key[:-2] + "RQ1"]
