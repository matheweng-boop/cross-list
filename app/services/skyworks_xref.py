"""Skyworks' own public cross reference (www.skyworksinc.com/cross-reference), as read into
data/manage/skyworks_cross_reference.yaml (owner, 10 Nov 2026: "If the cross exists in the Skyworks cross reference then
just put a little check mark behind it").

``mark(their, ours)`` says whether the official table pairs a competitor part with one of our parts. A competitor part
is found by its own ordering code (else by the longest official number it starts with: the table also lists base
numbers such as ADUM1400 or ISO7720F) and by a TI device name such as ISO7730-Q1 for its …Q1 ordering codes."""

from functools import lru_cache
from urllib.parse import quote

from app import yamlio
from app.config import PROJECT_ROOT
from app.partnumbers import normalize_pn, reel_q1_variants

FILE = PROJECT_ROOT / "data" / "manage" / "skyworks_cross_reference.yaml"
SITE = "https://www.skyworksinc.com/cross-reference?PartNumber="


@lru_cache(maxsize=1)
def table() -> dict[str, list[dict]]:
    """{normalised competitor part: [rows]}; rows without a Skyworks part ("No Cross") are left out."""
    try:
        rows = yamlio.load(FILE.read_text()).get("rows") or []
    except (OSError, ValueError, AttributeError):
        return {}
    out: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("ours"):
            out.setdefault(normalize_pn(r["part"]), []).append(r)
    return out


def _keys(their: str) -> list[str]:
    """The table's numbers for this part: its own ordering code (or its reel twin) and the TI device name it belongs
    to (ISO7730-Q1 for ISO7730QDWRQ1); without its own code, the longest base number it starts with."""
    t, k = table(), normalize_pn(their)
    own = [alt for alt in (k, *reel_q1_variants(k)) if alt in t]
    device = [
        key
        for key, rows in t.items()
        if rows[0]["part"].upper().endswith("-Q1") and key not in own and k.endswith("Q1") and k.startswith(key[:-2])
    ]
    if own:
        return own + device
    base = [key for key in t if len(key) >= 5 and k.startswith(key)]
    return ([max(base, key=len)] if base else []) + device


def _same(ours: str, official: str) -> bool:
    a, b = normalize_pn(ours), normalize_pn(official)
    return a == b or a == b + "R"


def rows_for(their: str) -> list[dict]:
    return [r for key in _keys(their) for r in table()[key]]


def mark(their: str | None, ours: str | None) -> dict | None:
    """{"match": their match type, "part": the competitor number as listed, "url": the official page} when the
    official table pairs ``their`` with ``ours``; else None."""
    if not their or not ours:
        return None
    for r in rows_for(their):
        if _same(ours, r["ours"]):
            return {"match": r["match"], "part": r["part"], "url": SITE + quote(r["part"])}
    return None
