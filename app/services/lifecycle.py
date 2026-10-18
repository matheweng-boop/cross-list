"""Lifecycle helpers: badges, 'new part' detection."""

from datetime import date

from app.models import LifecycleStatus, Part

BADGES = {
    LifecycleStatus.preview: ("Preview", "info"),
    LifecycleStatus.active: ("Active", "ok"),
    LifecycleStatus.nrnd: ("NRND", "warn"),
    LifecycleStatus.last_time_buy: ("Last time buy", "bad"),
    LifecycleStatus.obsolete: ("Obsolete / EOL", "bad"),
    LifecycleStatus.unknown: ("Unknown", "muted"),
}


def is_new(part: Part, days: int, today: date | None = None) -> bool:
    if part.release_date is None:
        return False
    today = today or date.today()
    return 0 <= (today - part.release_date).days <= days or part.lifecycle_status == LifecycleStatus.preview


def badge(part: Part) -> tuple[str, str]:
    return BADGES[part.lifecycle_status]
