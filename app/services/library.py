"""Technical library: deep dives per topic (data/library/topics/<key>.yaml) with references, a block diagram drawn
by us, design rules, research trends and where our parts sit; and the background list of every source assessed
(data/library/sources.yaml). Only our own summaries and short quotes with citations are stored."""

import re
from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT

FOLDER = PROJECT_ROOT / "data" / "library"
FEASIBILITY = {"high": "High", "medium": "Medium", "low": "Low", "blocked": "Blocked"}
HORIZON = {"now": "Now", "2-3y": "2–3 years", "5y+": "5+ years"}
_KEY = re.compile(r"^[a-z0-9_]+$")


@lru_cache
def sources() -> tuple[dict, ...]:
    return tuple((yamlio.load((FOLDER / "sources.yaml").read_text()) or {}).get("sources") or [])


@lru_cache
def topic(key: str) -> dict | None:
    path = FOLDER / "topics" / f"{key}.yaml"
    if not _KEY.match(key) or not path.exists():
        return None
    return yamlio.load(path.read_text()) or {}


def topics() -> list[dict]:
    """Every topic, by its optional `order:` field, then by key."""
    out = [t | {"key": p.stem} for p in sorted((FOLDER / "topics").glob("*.yaml")) if (t := topic(p.stem))]
    return sorted(out, key=lambda t: (t.get("order", 99), t["key"]))


def refs_by_id(t: dict) -> dict[str, dict]:
    return {r["id"]: r for r in t.get("references") or []}


# ---- use across the site -------------------------------------------------------------------------------------------
def fns(t: dict) -> tuple[set[str], set[str]]:
    """(functions where we name parts, every function in the topic's block diagram), canonical ids."""
    from app.services import vocab

    fit = {vocab.canonical(s["fn"]) for s in t.get("skyworks_fit") or []}
    drawn = {vocab.canonical(b["fn"] if isinstance(b, dict) else b)
             for g in (t.get("block_diagram") or {}).get("groups") or [] for b in g.get("blocks") or []}  # fmt: skip
    return fit, drawn


def for_function(fn: str) -> list[dict]:
    """Topics that cover a function: first those that name our parts for it, then those that only draw it."""
    out = []
    for t in topics():
        fit, drawn = fns(t)
        if fn in fit or fn in drawn:
            note = next((s.get("note") for s in t.get("skyworks_fit") or [] if s["fn"] == fn), "")
            out.append({"key": t["key"], "title": t["title"], "ours": fn in fit, "note": note,
                        "trends": t.get("trends") or [], "n_rules": len(t.get("design_rules") or [])})  # fmt: skip
    return sorted(out, key=lambda x: not x["ours"])


def items(keys: list[str]) -> list[dict]:
    """Named topics in the shape for_function returns (for a case's `library:` list)."""
    out = []
    for k in keys or []:
        t = topic(k)
        if t:
            out.append({"key": k, "title": t["title"], "ours": False, "note": "", "trends": t.get("trends") or [],
                        "n_rules": len(t.get("design_rules") or [])})  # fmt: skip
    return out


def cases_using(key: str) -> list[dict]:
    """Preliminary cases that name the topic in their `library:` list."""
    from app.services import prelim
    from app.services import reports as rp

    return [{"slug": r["slug"], "title": r["title"]} for r in rp.reports()
            if key in ((prelim.raw(r["slug"]) or {}).get("library") or [])]  # fmt: skip


def notes(key: str) -> str:
    path = FOLDER / "notes" / f"{key}.md"
    return path.read_text() if _KEY.match(key) and path.exists() else ""


# ---- reviewers' assessment of rules and trends (DataReview rows, dataset "library:<key>", latest verdict counts) -----
VERDICTS = {"agree": "correct", "disagree": "wrong", "reset": "unsure"}
_LOWER = {"high": "med", "med": "low", "medium": "low", "low": "low"}


def dataset(key: str) -> str:
    return f"library:{key}"[:40]


def item_ids(key: str) -> set[str]:
    t = topic(key) or {}
    return {str(x["id"]) for x in [*(t.get("design_rules") or []), *(t.get("trends") or [])] if x.get("id")}


def reviewed(session, key: str) -> dict:
    """The topic with each rule and trend carrying its feedback; a disputed item's confidence drops one step."""
    from sqlalchemy import select

    from app.models import DataReview

    fb: dict[str, dict] = {}
    q = select(DataReview).where(DataReview.dataset == dataset(key)).order_by(DataReview.id)
    for r in session.scalars(q):
        f = fb.setdefault(r.key, {"verdict": None, "comments": []})
        f["verdict"] = None if r.verdict == "unsure" else r.verdict
        if r.comment:
            f["comments"].append({"text": r.comment, "author": r.author, "date": r.created_at})

    def attach(rows):
        out = []
        for x in rows or []:
            f = fb.get(str(x.get("id")), {})
            if f.get("verdict") == "wrong" and x.get("conf"):
                x = {**x, "conf_was": x["conf"], "conf": _LOWER.get(x["conf"], "low")}
            out.append({**x, "fb": f})
        return out

    t = topic(key) or {}
    n = sum(1 for f in fb.values() if f["verdict"] or f["comments"])
    return {**t, "design_rules": attach(t.get("design_rules")), "trends": attach(t.get("trends")), "n_feedback": n}


def react(session, key: str, item: str, verdict: str, comment: str = "", author: str = "") -> None:
    from app.models import DataReview

    if item not in item_ids(key) or verdict not in VERDICTS:
        raise ValueError("unknown item or verdict")
    session.add(DataReview(dataset=dataset(key), key=item[:120], verdict=VERDICTS[verdict],
                           comment=comment.strip()[:2000] or None, author=author.strip()[:100] or None))  # fmt: skip
    session.commit()
