"""RF fundamentals: engineering notes written from public Mini-Circuits and RF Essentials material
(data/engineering_rf_notes.yaml explains the sources)."""

from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT

FILE = PROJECT_ROOT / "data" / "engineering_rf_notes.yaml"
CATEGORIES = {"rf_specs": "RF specifications", "components": "Components", "architecture": "Architectures",
              "technology": "Technology"}  # fmt: skip


@lru_cache
def topics() -> tuple[dict, ...]:
    return tuple((yamlio.load(FILE.read_text()) or {}).get("topics") or []) if FILE.exists() else ()


def by_category() -> list[tuple[str, str, list[dict]]]:
    return [(k, label, sorted((t for t in topics() if t["category"] == k), key=lambda t: t["title"].lower()))
            for k, label in CATEGORIES.items()]  # fmt: skip
