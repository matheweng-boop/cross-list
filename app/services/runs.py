"""Data management > Schedule: what runs continuously, at each deploy, daily (the evening run), weekly or every two
weeks (data/manage/schedule.yaml), and the live counts of what tonight's run will pick up."""

import re
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import AreaRequest

FILE = PROJECT_ROOT / "data" / "manage" / "schedule.yaml"
FREQUENCIES = {
    "continuous": "Continuously (as you use the site)",
    "deploy": "At every redeploy",
    "daily": "Every evening, 18:42 Berlin",
    "weekly": "Weekly",
    "biweekly": "Every two weeks",
}


@lru_cache(maxsize=1)
def jobs() -> tuple[dict, ...]:
    rows = (yamlio.load(FILE.read_text()) or {}).get("jobs") or []
    bad = [r.get("name") for r in rows if r.get("frequency") not in FREQUENCIES]
    if bad:
        raise ValueError(f"unknown frequency in {FILE.name}: {bad}")
    return tuple(rows)


def by_frequency() -> list[tuple[str, str, list[dict]]]:
    return [(k, label, [j for j in jobs() if j["frequency"] == k]) for k, label in FREQUENCIES.items()]


def tonight() -> list[dict]:
    return sorted((j for j in jobs() if j.get("tonight")), key=lambda j: j["tonight"])


def _doc(name: str) -> str:
    p = PROJECT_ROOT / "docs" / name
    return p.read_text() if p.exists() else ""


def open_questions() -> list[str]:
    """The numbered open questions (bold title of each) in docs/open_questions.md, before the settled list."""
    text = _doc("open_questions.md").split("\n## ", 1)[0]
    return re.findall(r"^\d+\. \*\*(.+?)\*\*", text, flags=re.M)


def queue(session: Session) -> dict[str, int]:
    """Live counts of what is waiting for tonight's run."""
    from app.services import reviews as rv

    backlog = _doc("pinout_backlog.md")
    return {
        "reviews": sum(e["status"] in ("new", "in_progress") for e in rv.requests(session)),
        "areas": session.scalar(select(func.count()).select_from(AreaRequest).where(AreaRequest.status == "new")) or 0,
        "pinouts_left": len(re.findall(r"^- \[ \]", backlog, flags=re.M)),
        "pinouts_done": len(re.findall(r"^- \[x\]", backlog, flags=re.M | re.I)),
        "questions": len(open_questions()),
    }
