"""TAM estimates (Data management): market size per product or technology, each with its source, a source-quality
note and the owner's review (agree / disagree with a comment).

Researched examples come from data/business/tam.yaml (copied from the case research notes, never estimated here);
estimates added on the page are TamEstimate rows. Reviews are DataReview rows (dataset "tam"): the latest one counts.
"""

from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import DataReview, TamEstimate

DATASET = "tam"
_FILE = PROJECT_ROOT / "data" / "business" / "tam.yaml"
VERDICT = {"correct": "agree", "wrong": "disagree", "unsure": "unsure"}


@lru_cache
def researched() -> tuple[dict, ...]:
    data = (yamlio.load(_FILE.read_text()) if _FILE.exists() else None) or {}
    out = []
    for e in data.get("estimates") or []:
        src = e.get("source") or {}
        out.append({
            "key": str(e["id"]), "product": e.get("product") or "", "fn": e.get("fn") or "",
            "value": str(e.get("value") or ""), "usd": e.get("usd"), "year": e.get("year"),
            "region": e.get("region") or "", "scope": e.get("scope") or "", "quality": e.get("quality") or "",
            "coverage": e.get("coverage") or "", "coverage_note": e.get("coverage_note") or "",
            "source": {"title": src.get("title") or "", "publisher": src.get("publisher") or "",
                       "url": src.get("url") or "", "date": str(src.get("date") or "")},
            "origin": e.get("origin") or "", "example": True, "author": None,
        })  # fmt: skip
    return tuple(out)


def _row(r: TamEstimate) -> dict:
    return {"key": f"u{r.id}", "product": r.product, "fn": r.fn or "", "value": r.value, "usd": r.usd,
            "year": r.year, "region": r.region or "", "scope": r.scope or "", "quality": r.quality or "",
            "coverage": "", "coverage_note": "",
            "source": {"title": r.source_title or "", "publisher": r.source_publisher or "",
                       "url": r.source_url or "", "date": r.source_date or ""},
            "origin": "Added on this page", "example": False, "author": r.author}  # fmt: skip


def reviews(session: Session) -> dict[str, DataReview]:
    """The latest review per estimate key."""
    q = select(DataReview).where(DataReview.dataset == DATASET).order_by(DataReview.created_at, DataReview.id)
    return {r.key: r for r in session.scalars(q)}


def estimates(session: Session) -> list[dict]:
    """Every estimate with its review, grouped by product (largest first within a product)."""
    rows = [dict(e) for e in researched()]
    rows += [_row(r) for r in session.scalars(select(TamEstimate).order_by(TamEstimate.id))]
    rev = reviews(session)
    for e in rows:
        r = rev.get(e["key"])
        e["review"] = {"verdict": VERDICT.get(r.verdict, r.verdict), "comment": r.comment or "", "author": r.author,
                       "date": r.created_at} if r else None  # fmt: skip
        e["question"] = question(e)
    rows.sort(key=lambda e: (e["product"].lower(), -(e["usd"] or 0)))
    return rows


def _lower_first(text: str) -> str:
    first = text.split(" ")[0]
    return text if any(c.isupper() for c in first[1:]) else text[:1].lower() + text[1:]


def question(e: dict) -> str:
    """One yes / no question for the owner: does the named source give this figure?"""
    src = e["source"]
    who = src["publisher"] or src["title"] or "the source"
    year = f"{e['year']} " if e.get("year") else ""
    region = f" ({e['region']})" if e.get("region") else ""
    return f"Does {who} put the {year}market for {_lower_first(e['product'])}{region} at {e['value']}?"


def check_hint(e: dict) -> str:
    """Exactly what to check for the question."""
    src = e["source"]
    year = f" for {e['year']}" if e.get("year") else ""
    what = f" Answer No if it counts a different market than: {e['scope']}." if e.get("scope") else ""
    if src["url"]:
        return f"Open the source and look for {e['value']}{year}.{what}"
    title, who = src["title"] or e["product"], src["publisher"] or "the publisher"
    return f"No link was recorded. Search for “{title}” by {who}; answer No if you cannot find {e['value']}{year}."


def counts(session: Session) -> dict:
    rows = estimates(session)
    agree = sum(1 for e in rows if e["review"] and e["review"]["verdict"] == "agree")
    disagree = sum(1 for e in rows if e["review"] and e["review"]["verdict"] == "disagree")
    return {"n": len(rows), "agree": agree, "disagree": disagree, "open": len(rows) - agree - disagree,
            "no_link": sum(1 for e in rows if not e["source"]["url"])}  # fmt: skip


def known_key(session: Session, key: str) -> bool:
    if any(e["key"] == key for e in researched()):
        return True
    return key.startswith("u") and key[1:].isdigit() and session.get(TamEstimate, int(key[1:])) is not None


def parse_usd(text: str) -> float | None:
    """'$1.4 B', '400 M', '2,310,000,000' -> US dollars; None when it cannot be read (then it stays unknown)."""
    t = (text or "").strip().lower().replace(",", "").replace("$", "").replace("usd", "").strip()
    mult = 1.0
    for suffix, m in (("billion", 1e9), ("bn", 1e9), ("b", 1e9), ("million", 1e6), ("m", 1e6), ("k", 1e3)):
        if t.endswith(suffix):
            t, mult = t[: -len(suffix)].strip(), m
            break
    t = t.split("–")[0].split("-")[0].strip()
    try:
        return float(t) * mult if t else None
    except ValueError:
        return None


def by_function(session: Session) -> dict[str, dict]:
    """Public market size per function, for the Opportunity explorer and the demand score: the estimates linked to a
    function, without the ones the owner disagreed with. Where some figures cover the whole market (coverage full),
    only those count (owner, 22 Oct 2026: for tuners, the total radio market). Agreed figures are used when there are
    any; otherwise every open one. usd = the median, with the low, high, latest year and how many sources (owner,
    21 Oct 2026: market size comes from public data only, never from commercial inputs)."""
    out: dict[str, dict] = {}
    groups: dict[str, list[dict]] = {}
    for e in estimates(session):
        verdict = (e["review"] or {}).get("verdict")
        if e["fn"] and e["usd"] and verdict != "disagree":
            groups.setdefault(e["fn"], []).append({**e, "agreed": verdict == "agree"})
    for fn, rows in groups.items():
        rows = [e for e in rows if e["coverage"] == "full"] or rows
        use = [e for e in rows if e["agreed"]] or rows
        vals = sorted(float(e["usd"]) for e in use)
        mid = len(vals) // 2
        median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
        out[fn] = {"usd": median, "low": vals[0], "high": vals[-1], "n": len(vals),
                   "agreed": any(e["agreed"] for e in use),
                   "year": max((e["year"] or 0) for e in use) or None}  # fmt: skip
    return out
