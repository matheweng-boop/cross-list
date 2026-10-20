"""Lifecycle helpers: badges, 'new part' detection, and the one classifier for lifecycle text."""

import re
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


# Lifecycle text as catalogues and data files state it ("Active", "Standard", "Featured", "In Production",
# "No new designs", "Last Time Buy", "Discontinued", "Pre Release", "last_time_buy", ...) in five classes.
# Every page uses this one rule, so a part is active or at risk the same way everywhere.
_OBSOLETE = re.compile(r"obsolete|discontinu|end of life|\beol\b", re.I)
_NRND = re.compile(r"nrnd|not recommended|not for new|no new design|last[ _]time", re.I)
_PREVIEW = re.compile(r"preview|sampl|pre[- _]?release|pre[- ]production", re.I)
_ACTIVE = {"active", "standard", "production", "in production", "released", "new", "featured", "non standard",
           "non-catalog model"}  # fmt: skip


def status_class(status) -> str:
    """'active', 'preview', 'nrnd' (incl. last time buy), 'obsolete' or 'unknown' (not stated, contact sales)."""
    s = str(status or "").strip().lower()
    if _OBSOLETE.search(s):
        return "obsolete"
    if _NRND.search(s):
        return "nrnd"
    if _PREVIEW.search(s):
        return "preview"
    return "active" if s in _ACTIVE else "unknown"


def is_risk(status) -> bool:
    """Not for new designs: NRND, last time buy or obsolete. An unknown status is not a risk by itself."""
    return status_class(status) in ("nrnd", "obsolete")
