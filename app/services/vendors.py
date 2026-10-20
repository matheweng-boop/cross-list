"""One display name per company (data/vendors.yaml): "Texas Instruments" in one file and "TI" in another are shown
the same way, and a subsidiary can be grouped under its owner. Names not in the file are shown as they are."""

from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT

FILE = PROJECT_ROOT / "data" / "vendors.yaml"


@lru_cache
def _table() -> dict[str, dict]:
    """Every known spelling (display, legal, aliases; lower case) -> its vendor entry."""
    out = {}
    for v in (yamlio.load(FILE.read_text()) or {}).get("vendors") or []:
        for name in (v["display"], v.get("legal"), *(v.get("aliases") or [])):
            if name:
                out[str(name).strip().lower()] = v
    return out


def entry(name: str | None) -> dict | None:
    return _table().get(str(name or "").strip().lower())


def display(name: str | None) -> str:
    """'Texas Instruments' -> 'TI', 'Rohm' -> 'ROHM'; unknown names unchanged."""
    v = entry(name)
    return v["display"] if v else str(name or "")


def group(name: str | None) -> str:
    """Display name of the owner for a subsidiary brand (pSemi -> Murata, Lark -> Trans-Tech), else of the company."""
    v = entry(name)
    return display(v.get("parent") or v["display"]) if v else str(name or "")
