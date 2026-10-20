"""Preliminary business cases: one structured file per case (data/business/cases/<slug>.yaml, layout in _template.yaml)
shown on the case's report page. Reviewers react to each item (DataReview rows, dataset "case:<slug>", latest verdict
counts) and enter real ASPs (business inputs, key "case:<slug>:<item>") that replace the estimates."""

import re
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import DataReview
from app.services import opportunity as op

FOLDER = PROJECT_ROOT / "data" / "business" / "cases"
DISTANCE = {  # how far a feature is from what we ship today
    0: ("Today", "Available now: sell, document or support it"),
    1: ("Firmware", "Firmware, licence or documentation on existing chips"),
    2: ("Package", "New package, module or reference design from existing chips"),
    3: ("New chip", "New chip built from technology we already have"),
    4: ("New technology", "Needs a process, IP or capability we don't have"),
}
VERDICTS = {"agree": "correct", "disagree": "wrong", "closer": "closer", "further": "further", "reset": "unsure"}
VERDICT_LABEL = {"correct": "agreed", "wrong": "disputed", "closer": "move closer", "further": "move further"}
LISTS = ("advantages", "disadvantages", "diff_good", "diff_bad")
_SLUG = re.compile(r"^[a-z0-9-]+$")


def dataset(slug: str) -> str:
    return f"case:{slug}"[:40]


@lru_cache
def raw(slug: str) -> dict | None:
    path = FOLDER / f"{slug}.yaml"
    if not _SLUG.match(slug) or not path.exists():
        return None
    return yamlio.load(path.read_text()) or {}


def item_ids(slug: str) -> set[str]:
    """Every id a reviewer can react to or price."""
    c = raw(slug) or {}
    pos = c.get("position") or {}
    rows = [x for k in LISTS for x in pos.get(k) or []]
    rows += [*(c.get("outlook") or []), *(c.get("features") or []), *(c.get("attach") or []),
             *((c.get("prices") or {}).get("items") or [])]  # fmt: skip
    return {str(x["id"]) for x in rows if x.get("id")}


def _feedback(session: Session, slug: str) -> dict[str, dict]:
    """Per item: the latest verdict and every comment, oldest first."""
    out: dict[str, dict] = {}
    q = select(DataReview).where(DataReview.dataset == dataset(slug)).order_by(DataReview.id)
    for r in session.scalars(q):
        f = out.setdefault(r.key, {"verdict": None, "comments": []})
        f["verdict"] = None if r.verdict == "unsure" else r.verdict
        if r.comment:
            f["comments"].append({"text": r.comment, "author": r.author, "date": r.created_at})
    return out


def case(session: Session, slug: str) -> dict | None:
    """The case with feedback and real prices attached to its items, and the revenue illustration."""
    c = raw(slug)
    if c is None:
        return None
    fb = _feedback(session, slug)
    asp, _ = op.inputs(session)

    def attach(rows):
        return [{**x, "fb": fb.get(str(x.get("id")), {})} for x in rows or []]

    pos = c.get("position") or {}
    prices = c.get("prices") or {}
    items = [{**x, "real": asp.get(f"case:{slug}:{x['id']}"), "fb": fb.get(str(x["id"]), {})}
             for x in prices.get("items") or []]  # fmt: skip
    by_id = {x["id"]: x for x in items}
    revenue = []
    for v in c.get("volumes") or []:
        p = by_id.get(v.get("price"))
        if p:
            price = p["real"] if p["real"] is not None else p.get("target")
            revenue.append({**v, "unit": price, "real": p["real"] is not None,
                            "revenue": (v.get("units") or 0) * (price or 0)})  # fmt: skip
    n_fb = sum(1 for f in fb.values() if f["verdict"] or f["comments"])
    return {**c, "position": {k: attach(pos.get(k)) for k in LISTS}, "outlook": attach(c.get("outlook")),
            "features": attach(c.get("features")), "attach": attach(c.get("attach")),
            "prices": {**prices, "items": items}, "revenue": revenue, "n_feedback": n_fb}  # fmt: skip


def react(session: Session, slug: str, key: str, verdict: str, comment: str = "", author: str = "") -> None:
    if key not in item_ids(slug) or verdict not in VERDICTS:
        raise ValueError("unknown item or verdict")
    session.add(DataReview(dataset=dataset(slug), key=key[:120], verdict=VERDICTS[verdict],
                           comment=comment.strip()[:2000] or None, author=author.strip()[:100] or None))  # fmt: skip
    session.commit()


def set_price(session: Session, slug: str, key: str, value: float | None, note: str = "") -> None:
    prices = {str(x["id"]) for x in ((raw(slug) or {}).get("prices") or {}).get("items") or []}
    if key not in prices:
        raise ValueError("unknown price item")
    op.set_input(session, "asp", f"case:{slug}:{key}", value, note)
    session.commit()
