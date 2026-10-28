"""AI services we may deploy later (owner, 27 Oct 2026): a read-only list in data/manage/ai_services.yaml, shown to the
owner on Data management › AI services (later). Nothing here runs; the site sends no data to an AI service."""

from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT

FILE = PROJECT_ROOT / "data" / "manage" / "ai_services.yaml"
STATUS = {"idea": "Idea", "parked": "Parked"}
FIELDS = ("id", "name", "does", "where", "data_out", "status", "needs", "added", "quote")


@lru_cache
def data() -> list[dict]:
    return list(((yamlio.load(FILE.read_text()) if FILE.exists() else None) or {}).get("services") or [])
