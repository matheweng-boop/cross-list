"""Lifecycle / revision refresh job.

Runs on demand or on a schedule (cron/launchd locally, a worker container later).
Each *source* reports what it knows about a part; changes are written to the part
and recorded as ChangeEvents so the Lifecycle page can show what changed.

Sources implemented now:
  * CsvSource – lifecycle lists placed in var/lifecycle/*.csv (manual updates or
    exports from manufacturer/distributor PCN notices).
Website sources per manufacturer are added once those sites are reachable and
their terms of use permit automated access.
"""

import csv
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ChangeEvent, LifecycleStatus, Part


@dataclass
class LifecycleInfo:
    status: LifecycleStatus | None = None
    release_date: date | None = None
    revision: str | None = None
    revision_date: date | None = None
    source: str = ""


class Source(Protocol):
    name: str

    def lookup(self, part: Part) -> LifecycleInfo | None: ...


class CsvSource:
    """CSV columns: manufacturer, mpn, status, release_date, revision, revision_date, source"""

    name = "csv"

    def __init__(self, paths: list[Path]):
        self.rows: dict[tuple[str, str], LifecycleInfo] = {}
        for path in paths:
            with open(path, newline="") as f:
                for row in csv.DictReader(f):
                    key = (row["manufacturer"].strip().lower(), row["mpn"].strip().upper())
                    self.rows[key] = LifecycleInfo(
                        status=LifecycleStatus(row["status"].strip()) if row.get("status") else None,
                        release_date=date.fromisoformat(row["release_date"]) if row.get("release_date") else None,
                        revision=row.get("revision") or None,
                        revision_date=date.fromisoformat(row["revision_date"]) if row.get("revision_date") else None,
                        source=row.get("source") or f"csv:{Path(path).name}",
                    )

    def lookup(self, part: Part) -> LifecycleInfo | None:
        return self.rows.get((part.manufacturer.name.lower(), part.mpn.upper()))


def apply_update(session: Session, part: Part, info: LifecycleInfo) -> list[ChangeEvent]:
    events = []

    def record(kind, old, new):
        events.append(ChangeEvent(part_id=part.id, kind=kind, old_value=old, new_value=new, source=info.source))

    if info.status and info.status != part.lifecycle_status:
        record("lifecycle", part.lifecycle_status.value, info.status.value)
        part.lifecycle_status = info.status
    if info.revision and info.revision != part.datasheet_revision:
        new = info.revision + (f" ({info.revision_date.isoformat()})" if info.revision_date else "")
        record("revision", part.datasheet_revision, new)
        part.datasheet_revision = info.revision
        part.datasheet_date = info.revision_date or part.datasheet_date
    if info.release_date and info.release_date != part.release_date:
        record("release", part.release_date.isoformat() if part.release_date else None, info.release_date.isoformat())
        part.release_date = info.release_date
    part.lifecycle_checked_at = datetime.now(UTC)
    if info.source:
        part.lifecycle_source = info.source
    session.add_all(events)
    return events


def run(session: Session, sources: list[Source]) -> dict:
    parts = session.scalars(select(Part)).all()
    checked = changed = 0
    events: list[ChangeEvent] = []
    for part in parts:
        for src in sources:
            info = src.lookup(part)
            if info is None:
                continue
            checked += 1
            new = apply_update(session, part, info)
            if new:
                changed += 1
                events.extend(new)
    session.commit()
    return {"parts": len(parts), "checked": checked, "changed": changed, "events": len(events)}
