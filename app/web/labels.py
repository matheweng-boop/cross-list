"""One set of display words for every page: automotive grade, units and dates (lifecycle classes are in
app/services/lifecycle.py, vendor names in app/services/vendors.py). Source data keeps its own wording; these only
change how it is shown."""

from datetime import date, datetime
from functools import lru_cache

from app.config import PROJECT_ROOT, get_settings
from app.services import text as text_service

# grade of a part: automotive (AEC-Q100 stated), not automotive (industrial / commercial stated), or not stated
GRADE_LABELS = {"automotive": "Automotive (AEC-Q100)", "not_automotive": "Not automotive", "unknown": "Not stated"}
GRADE_BADGES = {
    "automotive": ("AEC-Q100", "auto"),
    "industrial": ("Industrial", "ind"),
    "commercial": ("Commercial", "ind"),
}


def unit(text) -> str:
    """Units written one way (app/services/text.py): kV/us -> kV/µs, kVRMS -> kVrms, 2.4GHz -> 2.4 GHz."""
    return text_service.units(text)


_DATE_FORMATS = {
    "day": "%d %b %Y",  # 20 Oct 2026
    "stamp": "%d %b %Y %H:%M",  # 20 Oct 2026 14:05
    "short": "%d %b",  # 20 Oct
    "weekday": "%a %d %b",  # Tue 20 Oct
    "long": "%A %d %B %Y",  # Tuesday 20 October 2026
    "time": "%H:%M",
}


def fmt_date(value, kind: str = "day") -> str:
    """Dates in one of a few forms (see _DATE_FORMATS); empty for no date."""
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if kind in ("stamp", "time") and type(value) is date:
        kind = "day"
    return value.strftime(_DATE_FORMATS[kind])


@lru_cache
def data_as_of() -> date | None:
    """When the cross lists were last loaded (the load marker), else the newest data/real file; fixed per process."""
    marker = get_settings().data_dir / "real_data.sha256"
    files = [marker] if marker.exists() else list((PROJECT_ROOT / "data" / "real").glob("*.yaml"))
    return datetime.fromtimestamp(max(f.stat().st_mtime for f in files)).date() if files else None


def register(env) -> None:
    from app.services import lifecycle, vendors
    from app.services.seed import UNOFFICIAL_TITLE, unofficial_keys

    # values from unofficial datasheet copies are marked † (macro unofficial_mark) with this title and a footnote
    env.globals["unofficial_keys"] = lambda part: unofficial_keys(part) if part is not None else set()
    env.globals["unofficial_title"] = UNOFFICIAL_TITLE
    env.filters["unit"] = unit
    env.filters["vendor"] = vendors.display
    env.filters["desc"] = text_service.clean_description
    env.filters["date"] = fmt_date
    env.globals["grade_label"] = GRADE_LABELS
    env.globals["data_as_of"] = data_as_of
    # lifecycle text as a source states it ("Standard", "Contact sales (ND)") in the five classes' words
    env.globals["life_text"] = lambda status: lifecycle.CLASS_LABELS[lifecycle.status_class(status)]
