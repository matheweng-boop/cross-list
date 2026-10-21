"""Technical library: deep dives per topic (data/library/topics/<key>.yaml) with references, a block diagram drawn
by us, design rules, research trends and where our parts sit; and the background list of every source assessed
(data/library/sources.yaml). Only our own summaries and short quotes with citations are stored."""

import re
from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT

FOLDER = PROJECT_ROOT / "data" / "library"
FEASIBILITY = {"high": "High", "medium": "Medium", "low": "Low", "blocked": "Blocked"}
HORIZON = {"now": "Now", "2-3y": "2–3 years", "5y+": "5+ years"}
_KEY = re.compile(r"^[a-z0-9_]+$")


@lru_cache
def sources() -> tuple[dict, ...]:
    return tuple((yamlio.load((FOLDER / "sources.yaml").read_text()) or {}).get("sources") or [])


@lru_cache
def topic(key: str) -> dict | None:
    path = FOLDER / "topics" / f"{key}.yaml"
    if not _KEY.match(key) or not path.exists():
        return None
    return yamlio.load(path.read_text()) or {}


def topics() -> list[dict]:
    """Every topic, by its optional `order:` field, then by key."""
    out = [t | {"key": p.stem} for p in sorted((FOLDER / "topics").glob("*.yaml")) if (t := topic(p.stem))]
    return sorted(out, key=lambda t: (t.get("order", 99), t["key"]))


def refs_by_id(t: dict) -> dict[str, dict]:
    return {r["id"]: r for r in t.get("references") or []}
