"""Site feedback: one digest per day, with near-duplicates grouped so each point is answered once.

Grouping is plain word overlap (no external service): two items are the same point when they share most of their
words, or somewhat fewer when they were sent from the same page. An item that repeats an earlier, still-open point
is attached to that point instead of starting a new one.
"""

import re
from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SiteFeedback, aware

KINDS = {"problem": "Something is wrong", "idea": "Idea / request", "data": "Data is missing or wrong",
         "question": "Question"}  # fmt: skip
STATUSES = {"new": "New", "planned": "Planned", "done": "Done", "wont": "Won't do", "duplicate": "Duplicate"}
OPEN = ("new", "planned")
_STOP = set("a an the and or of to in on for is are be it this that with at as by from i we you not no can should "
            "would could please there here page".split())  # fmt: skip


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+(?:[-.][a-z0-9]+)*", text.lower()) if w not in _STOP and len(w) > 1}


def similar_text(a: str, b: str, threshold: float) -> bool:
    """True when the shorter text shares at least `threshold` of its words with the other."""
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return a.strip().lower() == b.strip().lower()
    return len(wa & wb) / min(len(wa), len(wb)) >= threshold


def similar(a: SiteFeedback, b: SiteFeedback) -> bool:
    same_page = a.path.split("?")[0] == b.path.split("?")[0]
    return similar_text(a.text, b.text, 0.5 if same_page else 0.7)


def _day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime(day.year, day.month, day.day, tzinfo=UTC)
    return start, start + timedelta(days=1)


def digest(session: Session, day: date) -> dict:
    """The day's feedback as groups of the same point, each with the earlier open point it repeats (if any)."""
    start, end = _day_bounds(day)
    items = list(session.scalars(select(SiteFeedback).where(SiteFeedback.created_at >= start,
                                                             SiteFeedback.created_at < end)
                                 .order_by(SiteFeedback.created_at)))  # fmt: skip
    earlier = list(session.scalars(select(SiteFeedback).where(SiteFeedback.created_at < start,
                                                               SiteFeedback.status.in_(OPEN))))  # fmt: skip
    groups: list[list[SiteFeedback]] = []
    for it in items:
        g = next((g for g in groups if any(similar(it, x) for x in g)), None)
        if g is None:
            groups.append([it])
        else:
            g.append(it)
    out = []
    for g in groups:
        repeats = next((e for e in earlier if any(similar(e, x) for x in g)), None)
        statuses = Counter(x.status for x in g)
        out.append({
            "ids": [x.id for x in g], "members": g, "lead": max(g, key=lambda x: len(x.text)),
            "pages": sorted({x.page or x.path for x in g}), "kinds": sorted({x.kind for x in g}),
            "status": statuses.most_common(1)[0][0], "response": next((x.response for x in g if x.response), ""),
            "repeats": repeats,
        })  # fmt: skip
    out.sort(key=lambda r: (r["status"] not in OPEN, -len(r["ids"])))
    sections = Counter((x.page or "").split(" › ")[0] or "Other" for x in items)
    return {"day": day, "n": len(items), "groups": out, "sections": sections.most_common(),
            "kinds": Counter(x.kind for x in items), "open": sum(1 for r in out if r["status"] in OPEN)}  # fmt: skip


def open_points(session: Session) -> dict:
    """Every point not yet worked into the site (status New or Planned), from all days, as one list: similar items
    grouped, newest point first (owner, 22 Oct 2026: one list instead of a button per day)."""
    items = list(session.scalars(select(SiteFeedback).where(SiteFeedback.status.in_(OPEN))
                                 .order_by(SiteFeedback.created_at.desc())))  # fmt: skip
    groups: list[list[SiteFeedback]] = []
    for it in items:
        g = next((g for g in groups if any(similar(it, x) for x in g)), None)
        if g is None:
            groups.append([it])
        else:
            g.append(it)
    out = []
    for g in groups:
        statuses = Counter(x.status for x in g)
        out.append({
            "ids": [x.id for x in g], "members": g, "lead": max(g, key=lambda x: len(x.text)),
            "pages": sorted({x.page or x.path for x in g}), "kinds": sorted({x.kind for x in g}),
            "status": statuses.most_common(1)[0][0], "response": next((x.response for x in g if x.response), ""),
            "repeats": None, "newest": max(aware(x.created_at) for x in g),
            "first": min(aware(x.created_at) for x in g),
        })  # fmt: skip
    out.sort(key=lambda r: r["newest"], reverse=True)
    return {"n": len(items), "groups": out}


def days(session: Session, limit: int = 30) -> list[tuple[date, int, int]]:
    """Days with feedback, newest first: (day, items, still open)."""
    per: dict[date, list[int]] = {}
    for created, status in session.execute(select(SiteFeedback.created_at, SiteFeedback.status)):
        d = aware(created).date()
        per.setdefault(d, [0, 0])
        per[d][0] += 1
        per[d][1] += status in OPEN
    return [(d, n, o) for d, (n, o) in sorted(per.items(), reverse=True)][:limit]


def respond(session: Session, ids: list[int], status: str, response: str) -> int:
    """One answer for a whole group: every item gets the status and the response."""
    if status not in STATUSES:
        raise ValueError(status)
    rows = list(session.scalars(select(SiteFeedback).where(SiteFeedback.id.in_(ids))))
    now = datetime.now(UTC)
    for r in rows:
        r.status, r.response = status, (response.strip() or None)
        r.responded_at = now if r.response else r.responded_at
    return len(rows)


def digest_text(d: dict) -> str:
    lines = [f"BizDev feedback {d['day']:%Y-%m-%d}: {d['n']} items, {len(d['groups'])} points, {d['open']} open"]
    for g in d["groups"]:
        lead = g["lead"]
        lines.append(f"\n- [{STATUSES[g['status']]}] {lead.text.strip()}")
        lines.append(f"  x{len(g['ids'])} · {', '.join(KINDS.get(k, k) for k in g['kinds'])} · {'; '.join(g['pages'])}")
        if g["repeats"]:
            lines.append(f"  repeats #{g['repeats'].id} from {aware(g['repeats'].created_at):%Y-%m-%d}")
        if g["response"]:
            lines.append(f"  response: {g['response']}")
    return "\n".join(lines) + "\n"
