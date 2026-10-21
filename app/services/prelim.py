"""Preliminary business cases: one structured file per case (data/business/cases/<slug>.yaml, layout in _template.yaml)
shown on the case's report page. Reviewers react to each item (DataReview rows, dataset "case:<slug>", latest verdict
counts) and enter real ASPs (business inputs, key "case:<slug>:<item>") that replace the estimates.

Each case also carries the Opportunity score of its main function (`fn:`) at the distance of its headline feature
(`headline:`, default the first feature), the feasibility 1–3 derived from that distance, and a confidence: the
score's, one step lower when a reviewer disagreed with any item; a disagreed item's own confidence drops one step."""

import re
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import DataReview
from app.services import opportunity as op
from app.services import scoring

FOLDER = PROJECT_ROOT / "data" / "business" / "cases"
DISTANCE = {  # how far a feature is from what we ship today
    0: ("Today", "Available now: sell, document or support it"),
    1: ("Firmware", "Firmware, licence or documentation on existing chips"),
    2: ("Package", "New package, module or reference design from existing chips"),
    3: ("New chip", "New chip built from technology we already have"),
    4: ("New technology", "Needs a process, IP or capability we don't have"),
}
VERDICTS = {"agree": "correct", "disagree": "wrong", "closer": "closer", "further": "further", "answer": "answered",
            "reset": "unsure"}  # fmt: skip
VERDICT_LABEL = {"correct": "agreed", "wrong": "disputed", "closer": "move closer", "further": "move further",
                 "answered": "answered"}  # fmt: skip
QUESTION_GROUPS = (("bu", "Business unit (internal)"), ("customer", "OEM / Tier-1"))
BENEFIT_KINDS = {  # what kind of architectural gain the customer gets; fixed so cases compare side by side
    "parts": "Fewer parts", "cabling": "Cabling", "placement": "Placement", "scaling": "Scaling",
    "performance": "Performance", "safety": "Safety", "software": "Software", "sourcing": "Sourcing",
    "compliance": "Compliance",
}  # fmt: skip
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
    """Every id a reviewer can react to or price (the business-unit opener of the report too, case or not)."""
    from app.services import reports as rp

    c = raw(slug) or {}
    extra = {rp.OPENER_ID} if (rp.report(slug) or {}).get("bu_opener") else set()
    pos = c.get("position") or {}
    rows = [x for k in LISTS for x in pos.get(k) or []]
    rows += [*(c.get("outlook") or []), *(c.get("features") or []), *(c.get("attach") or []),
             *((c.get("prices") or {}).get("items") or [])]  # fmt: skip
    rows += (c.get("customer_benefit") or {}).get("gains") or []
    rows += [x for k, _ in QUESTION_GROUPS for x in (c.get("questions") or {}).get(k) or []]
    return {str(x["id"]) for x in rows if x.get("id")} | extra


def opener(session: Session, slug: str, fb: dict | None = None) -> dict | None:
    """The report's first question to the business unit (bu_opener in reports.yaml) with its recorded answers."""
    from app.services import reports as rp

    o = (rp.report(slug) or {}).get("bu_opener")
    if not o:
        return None
    fb = _feedback(session, slug) if fb is None else fb
    return {**o, "id": rp.OPENER_ID, "text": o.get("question", ""), "fb": fb.get(rp.OPENER_ID, {})}


def headline(c: dict) -> dict | None:
    """The feature the case is about (`headline:` id, else the first feature)."""
    feats = c.get("features") or []
    return next((f for f in feats if f.get("id") == c.get("headline")), feats[0] if feats else None)


def derived_feasibility(slug: str) -> int | None:
    h = headline(raw(slug) or {})
    return scoring.feasibility(h.get("distance")) if h else None


def opportunity(session: Session, slug: str, fb: dict | None = None) -> dict:
    """Opportunity score of the case's function at its headline distance, feasibility (derived, and the curated one
    from reports.yaml when it differs) and the case confidence."""
    from app.services import reports as rp

    c = raw(slug) or {}
    fb = _feedback(session, slug) if fb is None else fb
    h = headline(c) or {}
    d = h.get("distance")
    disputed = sorted(k for k, f in fb.items() if f["verdict"] == "wrong")
    dc = scoring.lower("medium") if h.get("id") in disputed else "medium"
    fn = c.get("fn")
    why = f"headline feature: {h.get('feature', '')}"
    s = scoring.rescore(scoring.combined(session), fn, d, why, dc) if fn else None
    confidence = (s or {}).get("confidence") or "low"
    curated = int((rp.report(slug) or {}).get("feasibility") or 0) or None
    derived = scoring.feasibility(d)
    return {"fn": fn, "headline": h, "score": s, "feasibility": curated or derived, "derived": derived,
            "curated": curated, "mismatch": bool(curated and derived and curated != derived),
            "confidence": scoring.lower(confidence) if disputed else confidence, "disputed": disputed}  # fmt: skip


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
    """The case with feedback attached to its items, and the revenue illustration from the estimated target prices
    (no real prices are entered: commercial inputs are retired, owner 21 Oct 2026)."""
    c = raw(slug)
    if c is None:
        return None
    fb = _feedback(session, slug)
    asp, _ = op.inputs(session)

    def attach(rows):
        return [_reviewed({**x, "fb": fb.get(str(x.get("id")), {})}) for x in rows or []]

    pos = c.get("position") or {}
    benefit = c.get("customer_benefit") or {}
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
            "customer_benefit": {**benefit, "gains": attach(benefit.get("gains"))} if benefit else None,
            "features": attach(c.get("features")), "attach": attach(c.get("attach")),
            "questions": {k: attach((c.get("questions") or {}).get(k)) for k, _ in QUESTION_GROUPS},
            "prices": {**prices, "items": items}, "revenue": revenue, "n_feedback": n_fb,
            "opener": opener(session, slug, fb),
            "opportunity": opportunity(session, slug, fb)}  # fmt: skip


def _reviewed(x: dict) -> dict:
    """A disagreed item's confidence drops one step (high -> med -> low); the original is kept as conf_was."""
    if x.get("conf") and (x.get("fb") or {}).get("verdict") == "wrong":
        low = scoring.lower(x["conf"])
        x = {**x, "conf_was": x["conf"], "conf": "med" if low == "medium" else low}
    return x


def react(session: Session, slug: str, key: str, verdict: str, comment: str = "", author: str = "") -> None:
    if key not in item_ids(slug) or verdict not in VERDICTS:
        raise ValueError("unknown item or verdict")
    session.add(DataReview(dataset=dataset(slug), key=key[:120], verdict=VERDICTS[verdict],
                           comment=comment.strip()[:2000] or None, author=author.strip()[:100] or None))  # fmt: skip
    session.commit()

