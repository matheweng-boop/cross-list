"""The last few answers to one reviewed item (DataReview rows are append-only: every answer is kept, the newest one is
the current verdict). Used by the "History (n)" line under every review box and by the inbox's "earlier:" note.
Nothing here changes which answer counts."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DataReview

N = 5
_DEFAULT = {"correct": "agree", "wrong": "disagree", "unsure": "unsure", "answered": "answered"}
_LABELS = {
    "price": {"low": "low end", "ok": "in the band", "high": "high end"},
    "auto_reach": {"correct": "accepted", "wrong": "rejected", "unsure": "back to proposed"},
    "application": {"correct": "verified", "unsure": "back to entered", "wrong": "not verified"},
    "case:": {"closer": "move closer", "further": "move further"},
}
# datasets whose boxes only the owner sees: a guest never gets their comments (and no guest gets author names)
OWNER_ONLY = ("tam", "price", "application")


def label(dataset: str, verdict: str) -> str:
    """The dataset's own word for a stored verdict (agree / disagree / unsure by default)."""
    own = _LABELS.get(dataset) or next((v for k, v in _LABELS.items() if k.endswith(":") and dataset.startswith(k)), {})
    return own.get(verdict) or _DEFAULT.get(verdict, verdict)


def owner_only(dataset: str) -> bool:
    return dataset in OWNER_ONLY


def _entry(r: DataReview) -> dict:
    return {"id": r.id, "verdict": r.verdict, "label": label(r.dataset, r.verdict), "comment": r.comment or "",
            "author": r.author or "", "date": r.created_at}  # fmt: skip


def _order(q):
    return q.order_by(DataReview.created_at.desc(), DataReview.id.desc())


def history(session: Session, dataset: str, key: str, n: int = N) -> list[dict]:
    """The last ``n`` answers to one item, newest first: verdict, label, comment, author, date."""
    q = _order(select(DataReview).where(DataReview.dataset == dataset, DataReview.key == key[:120])).limit(n)
    return [_entry(r) for r in session.scalars(q)]


def by_dataset(session: Session, dataset: str, n: int = N + 1) -> dict[str, list[dict]]:
    """``history`` for every key of a dataset in one query (for pages with many boxes)."""
    out: dict[str, list[dict]] = {}
    for r in session.scalars(_order(select(DataReview).where(DataReview.dataset == dataset))):
        rows = out.setdefault(r.key, [])
        if len(rows) < n:
            rows.append(_entry(r))
    return out


def for_viewer(rows: list[dict], dataset: str, guest: bool) -> list[dict]:
    """A guest sees no author names, and no comments from owner-only datasets."""
    if not guest:
        return rows
    hide = owner_only(dataset)
    return [{**r, "author": "", "comment": "" if hide else r["comment"]} for r in rows]


def short_date(d: datetime | None) -> str:
    return f"{d.day} {d:%b}" if d else ""


def earlier_note(rows: list[dict], before_id: int | None = None, limit: int = 2) -> str:
    """Inbox note on a change of mind: "earlier: 22 Oct agree · 'consensus on CAGR'; 20 Oct unsure". ``rows`` newest
    first; only answers given before the row ``before_id`` count."""
    old = [r for r in rows if before_id is None or r["id"] < before_id][:limit]
    if not old:
        return ""
    parts = []
    for r in old:
        c = " ".join(r["comment"].split())
        c = c if len(c) <= 60 else c[:57] + "..."
        parts.append(f"{short_date(r['date'])} {r['label']}" + (f" · '{c}'" if c else ""))
    return "earlier: " + "; ".join(parts)
