"""Lifetime demand seen (owner, 26 Oct 2026): "when we run the command to update the cross-list especially for gap
technologies we should enter a rough lifetime volume estimate every time to get to total volume over multiple
requests ... in steps of 100k". Approved with the safeguard "store volume data based on this no other addition of
information is allowed".

Where volumes come from: Products › Cross a list › "Update cross-lists" (owner only). Each row "Not in our data" and
each gap row (a known part with no Skyworks/Qorvo cross) gets a step select; one DemandEntry per row with a volume.

Safeguards (tests/test_demand.py checks each):
- Stored per entry: part number (as resolved), function, lifetime volume (one of STEPS), date, lookup id. Nothing else:
  the form has no free-text field for volumes and the server refuses any other field or value.
- Owner only: guests cannot send (403) and never see volumes or totals; every view goes through seen(request), which
  is None for a guest, for nobody signed in and for any /shareable page (PDF pack, PowerPoint).
- Never in the Cross a list Excel or Copy table, never as values in the inbox or /api/inbox: the run gets counts only.
- Never in repo files: the entries live in the database only (no YAML).
- Retention: entries older than 12 months are deleted at start-up and on every read (purge), so totals drop them.

Totals per part and per function: total lifetime volume, number of requests (lookups), first and last date. A part's
first entry also asks for a Part review (a TechReviewRequest with a fixed, value-free question); the Research & ideas
page shows one owner-only idea card per function with demand (computed from the entries, so nothing goes to YAML).

Scoring: the shared Opportunity score never changes. With the owner-only switch "Use demand seen in scoring" (default
off, a SiteSetting), owner pages add a second number, "with demand seen": the demand factor becomes the higher of
its own value and a log scale of the lifetime volume (SEEN_LOW = 0, SEEN_HIGH = 100).
"""

import math
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import DemandEntry, SiteSetting, TechReviewRequest
from app.partnumbers import normalize_pn

# lifetime volume steps (pieces): 100k to 1M in 100k steps, then 1.5M, 2M, 3M, 5M, 10M, 20M
STEPS = (*range(100_000, 1_000_001, 100_000), 1_500_000, 2_000_000, 3_000_000, 5_000_000, 10_000_000, 20_000_000)
RETENTION_MONTHS = 12
SCORING_KEY = "demand_in_scoring"
SEEN_LOW, SEEN_HIGH = 100_000, 10_000_000  # log scale of the scoring switch: 100k = 0, 10M or more = 100
REVIEW_QUESTION = ("Requested from Cross a list: what the part does, where it is used and what a Skyworks/Qorvo part "
                   "would need to replace it.")  # fmt: skip


def fmt(v: int) -> str:
    """100000 -> 100k, 1200000 -> 1.2M."""
    if v >= 1_000_000:
        return f"{v / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    return f"{v // 1000}k"


CHOICES = [(v, fmt(v)) for v in STEPS]


def parse_step(raw: str) -> int | None:
    """"" (no volume) -> None; a step -> its int; anything else raises ValueError."""
    raw = (raw or "").strip()
    if raw in ("", "-", "—"):
        return None
    if not raw.isdigit() or int(raw) not in STEPS:
        raise ValueError(f"not a volume step: {raw[:20]!r}")
    return int(raw)


def cutoff(today: date | None = None) -> date:
    """The oldest day kept: the same day 12 months ago (28 Feb for 29 Feb)."""
    t = today or date.today()
    try:
        return t.replace(year=t.year - 1)
    except ValueError:
        return t.replace(year=t.year - 1, day=28)


def purge(session: Session, today: date | None = None) -> int:
    old = DemandEntry.day < cutoff(today)
    n = session.scalar(select(func.count(DemandEntry.id)).where(old)) or 0
    if n:  # a write only when there is something to delete (a read must not hold the database's write lock)
        session.execute(delete(DemandEntry).where(old))
        session.commit()
    return n


@dataclass
class Total:
    volume: int = 0
    lookups: set = field(default_factory=set)
    first: date | None = None
    last: date | None = None
    parts: dict = field(default_factory=dict)  # part -> volume (per-function totals)

    @property
    def n(self) -> int:
        return len(self.lookups)

    @property
    def text(self) -> str:
        return f"{fmt(self.volume)} lifetime over {self.n} request{'' if self.n == 1 else 's'}"

    def add(self, e: DemandEntry) -> None:
        self.volume += e.volume
        self.lookups.add(e.lookup_id)
        self.first = min(self.first or e.day, e.day)
        self.last = max(self.last or e.day, e.day)
        self.parts[e.part] = self.parts.get(e.part, 0) + e.volume


@dataclass
class Totals:
    parts: dict[str, Total]  # by normalised part number
    fns: dict[str, Total]
    by_lookup: dict[int, list[DemandEntry]]
    no_fn: dict[str, Total] = field(default_factory=dict)  # parts without a known function (sent for lookup)
    scoring: bool = False
    scores: dict = field(default_factory=dict)  # fn -> {"score", "with_seen"} (switch on only)

    def part(self, mpn: str | None) -> Total | None:
        return self.parts.get(normalize_pn(mpn or "")) if mpn else None

    def fn(self, fn: str | None) -> Total | None:
        return self.fns.get(fn) if fn else None

    def lookup(self, lookup_id: int) -> list[DemandEntry]:
        return self.by_lookup.get(lookup_id, [])


def entries(session: Session) -> list[DemandEntry]:
    purge(session)
    return list(session.scalars(select(DemandEntry).order_by(DemandEntry.day, DemandEntry.id)))


def totals(session: Session) -> Totals:
    parts: dict[str, Total] = {}
    fns: dict[str, Total] = {}
    by_lookup: dict[int, list] = {}
    no_fn: dict[str, Total] = {}
    for e in entries(session):
        parts.setdefault(normalize_pn(e.part), Total()).add(e)
        if e.fn:
            fns.setdefault(e.fn, Total()).add(e)
        else:
            no_fn.setdefault(e.part, Total()).add(e)
        by_lookup.setdefault(e.lookup_id, []).append(e)
    t = Totals(parts, fns, by_lookup, no_fn, scoring_on(session))
    if t.scoring and fns:
        t.scores = scores_with_seen(session, fns)
    return t


def new_count(session: Session, since: date) -> int:
    """How many entries were added since a day: all the daily run gets (never the values)."""
    purge(session)
    return session.scalar(select(func.count(DemandEntry.id)).where(DemandEntry.day >= since)) or 0


def record(session: Session, lookup_id: int, items: list[tuple[str, str | None, int]],
           today: date | None = None) -> int:  # fmt: skip
    """Store one entry per (part as resolved, function, volume); a part's first entry asks for a Part review."""
    from app.services import vocab

    day = today or date.today()
    purge(session, day)
    known = {normalize_pn(p) for p in session.scalars(select(DemandEntry.part))}
    asked = {normalize_pn(m) for m in session.scalars(select(TechReviewRequest.mpn).where(
        TechReviewRequest.status.in_(("new", "in_progress"))))}  # fmt: skip
    n = 0
    for part, fn, volume in items:
        if volume not in STEPS or not part:
            raise ValueError("volume must be one of the steps")
        part = part.strip()[:100]
        session.add(DemandEntry(part=part, fn=(fn or None) and fn[:80], volume=volume, day=day, lookup_id=lookup_id))
        n += 1
        key = normalize_pn(part)
        if key not in known and key not in asked:  # first volume for this part: a Part review request
            session.add(TechReviewRequest(mpn=part, question=REVIEW_QUESTION,
                                          application=vocab.fn_label(fn)[:200] if fn else None))  # fmt: skip
            asked.add(key)
        known.add(key)
    session.commit()
    return n


def delete_for_lookup(session: Session, lookup_id: int) -> None:
    session.execute(delete(DemandEntry).where(DemandEntry.lookup_id == lookup_id))


# ---- the owner-only scoring switch -----------------------------------------------------------------------------------
def scoring_on(session: Session) -> bool:
    row = session.get(SiteSetting, SCORING_KEY)
    return bool(row and row.value == "on")


def set_scoring(session: Session, on: bool) -> None:
    row = session.get(SiteSetting, SCORING_KEY)
    if row is None:
        session.add(SiteSetting(key=SCORING_KEY, value="on" if on else "off"))
    else:
        row.value = "on" if on else "off"
    session.commit()


def seen_factor(volume: int) -> float:
    lo, hi = math.log10(SEEN_LOW), math.log10(SEEN_HIGH)
    return min(100.0, max(0.0, 100 * (math.log10(max(volume, 1)) - lo) / (hi - lo)))


def with_seen(score: dict | None, volume: int) -> int | None:
    """The score with the demand factor raised to the demand seen (never lowered); the shared score is not changed."""
    if not score or not score.get("factors"):
        return None
    v = seen_factor(volume)
    total = sum((max(f["value"], v) if f["key"] == "demand" else f["value"]) * f["weight"] for f in score["factors"])
    return round(total / 100)


def scores_with_seen(session: Session, fns: dict[str, Total]) -> dict:
    from app.services import scoring

    rows = scoring.combined(session)["rows"]
    out = {}
    for fn, t in fns.items():
        s = rows.get(fn)
        if s and s.get("score") is not None:
            out[fn] = {"score": s["score"], "with_seen": with_seen(s, t.volume)}
    return out


# ---- the one way a page sees volumes ---------------------------------------------------------------------------------
def seen(request) -> Totals | None:
    """The totals for the owner's own pages; None for a guest, nobody signed in, or a Shareable output."""
    from app.auth.session import signed_in_owner

    if signed_in_owner(request) is None or request.url.path.startswith(("/shareable", "/api/")):
        return None
    cached = getattr(request.state, "demand_totals", None)
    if cached is not None:
        return cached
    from app.db import get_engine

    with Session(get_engine()) as s:
        t = totals(s)
        s.expunge_all()
    request.state.demand_totals = t
    return t
