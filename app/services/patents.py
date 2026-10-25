"""US patent landscape of Skyworks and the Qorvo group per technology platform (data/business/evidence/
patents_platforms.yaml), and the patent depth per function that the priority score's likeliness uses (owner, 25 Oct
2026: background only, no page of its own; a small bonus in the priority score; a compact summary for the synergies
report). Public data, indicative, not legal advice."""

from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT

FILE = PROJECT_ROOT / "data" / "business" / "evidence" / "patents_platforms.yaml"
PER_FUNCTION = PROJECT_ROOT / "data" / "business" / "evidence" / "patents.yaml"
DEPTHS = ("strong", "some", "little", "none_found")
COMPANIES = ("skyworks", "qorvo")
USPTO_HOSTS = ("ppubs.uspto.gov", "image-ppubs.uspto.gov")


@lru_cache
def load() -> dict:
    return (yamlio.load(FILE.read_text()) if FILE.exists() else None) or {}


@lru_cache
def per_function() -> dict[str, dict]:
    return (yamlio.load(PER_FUNCTION.read_text()) if PER_FUNCTION.exists() else None) or {}


def platforms() -> dict[str, dict]:
    return load().get("platforms") or {}


def automotive() -> dict[str, dict]:
    return load().get("automotive") or {}


@lru_cache
def _by_function() -> dict[str, str]:
    """Function -> the platform entry that covers it (the first platform listing it)."""
    out: dict[str, str] = {}
    for key, p in platforms().items():
        for fn in p.get("functions") or []:
            out.setdefault(fn, key)
    return out


def platform_for(fn: str) -> tuple[str, dict] | None:
    """(platform key, entry with its automotive cut as "auto" or None) for a function, or None."""
    key = _by_function().get(fn)
    if not key:
        return None
    auto = next((a for a in automotive().values() if a.get("platform") == key), None)
    return key, {**platforms()[key], "auto": auto}


def depth(fn: str) -> dict | None:
    """Patent depth of a function: its own entry in patents.yaml, else the platform entry that covers it.
    {depth, source: 'function' | 'platform', label} or None when neither exists."""
    own = per_function().get(fn)
    if own and own.get("depth") in DEPTHS:
        return {"depth": own["depth"], "source": "function", "label": ""}
    plat = platform_for(fn)
    if plat and plat[1].get("depth") in DEPTHS:
        return {"depth": plat[1]["depth"], "source": "platform", "label": plat[1].get("label", plat[0])}
    return None


def _round(n: int) -> int:
    """Counts rounded for sharing: below 20 as is, below 100 to 5, then to 10."""
    n = int(n or 0)
    return n if n < 20 else 5 * round(n / 5) if n < 100 else 10 * round(n / 10)


def patent_summary() -> dict:
    """Compact, public summary for the synergies report: per platform the leader (Skyworks | Qorvo | both), rounded US
    family counts and whether the platform has an automotive cut; plus overlap and complement lists."""
    d = load()
    auto = {a.get("platform") for a in automotive().values()}
    rows = {}
    for key, p in platforms().items():
        rows[key] = {"label": p.get("label", key), "leader": p.get("leader", "both"),
                     "skyworks": _round(p.get("skyworks")), "qorvo": _round(p.get("qorvo")),
                     "automotive": key in auto}  # fmt: skip
    ov = d.get("overlap") or {}
    return {"source": d.get("source", ""), "date": str(d.get("searched", "")), "note": d.get("disclaimer", ""),
            "platforms": rows, "overlap": list(ov.get("overlap") or []), "complement": dict(ov.get("complement") or {}),
            "automotive": {k: {"label": a.get("label", k), "skyworks": _round(a.get("skyworks")),
                               "qorvo": _round(a.get("qorvo"))} for k, a in automotive().items()}}  # fmt: skip
