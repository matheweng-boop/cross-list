"""Pre-lim product ideas and reports: a list (data/business/reports.yaml), each with a body template."""

from functools import lru_cache

import yaml

from app.config import PROJECT_ROOT

FILE = PROJECT_ROOT / "data" / "business" / "reports.yaml"
BODIES = PROJECT_ROOT / "app" / "web" / "templates" / "business" / "reports"
KINDS = {"report": "Report", "idea": "Product idea"}
STATUSES = {"draft": "Draft, not reviewed", "reviewed": "Reviewed", "archived": "Archived"}


@lru_cache
def reports() -> tuple[dict, ...]:
    rows = (yaml.safe_load(FILE.read_text()) or {}).get("reports") or [] if FILE.exists() else []
    rows = [r for r in rows if (BODIES / f"{r['slug']}.html").exists()]
    return tuple(sorted(rows, key=lambda r: str(r.get("date") or ""), reverse=True))


def report(slug: str) -> dict | None:
    return next((r for r in reports() if r["slug"] == slug), None)
