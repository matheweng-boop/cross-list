"""TAM estimates (Data management): market size per product or technology, each with its source, a source-quality
note and the owner's review (agree / disagree with a comment).

Researched examples come from data/business/tam.yaml (copied from the case research notes, never estimated here);
estimates added on the page are TamEstimate rows. Reviews are DataReview rows (dataset "tam"): the latest one counts.

Biweekly check (scripts/check_tam.py, results in data/business/tam_checks.yaml): each source is fetched politely and
marked verified, changed, unverifiable or disqualified. Nothing is ever deleted: a disqualified estimate is left out of
``by_function`` the same way an owner "disagree" is. Owner answers always win: an estimate the owner agreed with stays
in, and a disqualifying check only raises a flag for the owner (``e["flag"]``).

Combined topics (data/business/tam_topics.yaml, owner 25 Oct 2026): estimates for the same function and scope become
one entry stated as a band (low – high, year, CAGR band) once at least two of its sources are reviewed (owner agree)
or verified by the check. Disagreed or disqualified members are left out of the band and noted. ``by_function`` uses
the band of a combined topic where one exists (usd = its midpoint, for scoring).
"""

import re
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import DataReview, TamEstimate

DATASET = "tam"
_FILE = PROJECT_ROOT / "data" / "business" / "tam.yaml"
CHECKS_FILE = PROJECT_ROOT / "data" / "business" / "tam_checks.yaml"
TOPICS_FILE = PROJECT_ROOT / "data" / "business" / "tam_topics.yaml"
CHECK_LABELS = {"verified": "verified", "changed": "changed", "unverifiable": "unverifiable",
                "disqualified": "disqualified"}  # fmt: skip
_YAML_CACHE: dict = {}
VERDICT = {"correct": "agree", "wrong": "disagree", "unsure": "unsure"}
_APPLIED = PROJECT_ROOT / "data" / "business" / "tam_applied.yaml"


@lru_cache
def applied() -> dict[str, dict]:
    """Answers already worked into a report or the market size (data/business/tam_applied.yaml): key -> entry with
    verdict, date, applied_in (list of {label, href}) and note. These items take no new verdict until the entry is
    removed (owner, 25 Oct 2026)."""
    data = (yamlio.load(_APPLIED.read_text()) if _APPLIED.exists() else None) or {}
    out = {}
    for e in data.get("applied") or []:
        where = [str(w) for w in e.get("applied_in") or []]
        out[str(e["key"])] = {
            "verdict": e.get("verdict") or "", "date": e.get("date"), "note": e.get("note") or "",
            "applied_in": [{"label": "TAM page" if w == "TAM page" else w,
                            "href": "/business/tam" if w == "TAM page" else f"/business/reports/{w}"} for w in where],
        }  # fmt: skip
    return out


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
    """The latest review per estimate key (Data quality comments are not a verdict and are left out)."""
    from app.services.review_history import COMMENT_VERDICTS

    q = select(DataReview).where(DataReview.dataset == DATASET, DataReview.verdict.notin_(COMMENT_VERDICTS))
    q = q.order_by(DataReview.created_at, DataReview.id)
    return {r.key: r for r in session.scalars(q)}


def _load(path) -> dict:
    """A committed YAML file, re-read when it changes ({} when it is missing)."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    hit = _YAML_CACHE.get(str(path))
    if hit and hit[0] == mtime:
        return hit[1]
    data = yamlio.load(path.read_text()) or {}
    _YAML_CACHE[str(path)] = (mtime, data)
    return data


def checks() -> dict[str, dict]:
    """The latest biweekly check per estimate key: {status, date, evidence, url, why, new_value, new_year}."""
    return {str(k): v for k, v in (_load(CHECKS_FILE).get("checks") or {}).items() if isinstance(v, dict)}


def check_summary() -> dict | None:
    """The last check run: {date, verified, changed, unverifiable, disqualified}; None before the first run."""
    data = _load(CHECKS_FILE)
    if not data.get("checked"):
        return None
    st = [c.get("status") for c in checks().values()]
    return {"date": str(data["checked"]), **{s: st.count(s) for s in CHECK_LABELS}}


def history(session: Session) -> dict[str, list[DataReview]]:
    """Every review per estimate key, oldest first (the review history shown inside a combined topic)."""
    q = select(DataReview).where(DataReview.dataset == DATASET).order_by(DataReview.created_at, DataReview.id)
    out: dict[str, list[DataReview]] = {}
    for r in session.scalars(q):
        out.setdefault(r.key, []).append(r)
    return out


def exclusion(e: dict) -> str | None:
    """Why an estimate is left out of the market size, or None. The owner's answer wins over the check."""
    verdict = (e.get("review") or {}).get("verdict")
    if verdict == "disagree":
        c = (e["review"] or {}).get("comment")
        return "owner disagreed" + (f": {c}" if c else "")
    chk = e.get("check") or {}
    if chk.get("status") == "disqualified" and verdict != "agree":
        return f"check of {chk.get('date', '')} disqualified it: {chk.get('why') or chk.get('evidence') or ''}".strip()
    return None


def estimates(session: Session) -> list[dict]:
    """Every estimate with its review and check, grouped by product (largest first within a product)."""
    rows = [dict(e) for e in researched()]
    rows += [_row(r) for r in session.scalars(select(TamEstimate).order_by(TamEstimate.id))]
    rev, chk = reviews(session), checks()
    for e in rows:
        r = rev.get(e["key"])
        e["review"] = {"verdict": VERDICT.get(r.verdict, r.verdict), "comment": r.comment or "", "author": r.author,
                       "date": r.created_at} if r else None  # fmt: skip
        e["question"] = question(e)
        e["applied"] = applied().get(e["key"])
        e["check"] = chk.get(e["key"])
        e["usd_high"] = parse_range(e["value"])[1] or e["usd"]
        e["cagr"] = parse_cagr(e.get("scope") or "")
        e["flag"] = None
        e["excluded"] = exclusion(e)
        _flag(e)
    rows.sort(key=lambda e: (e["product"].lower(), -(e["usd"] or 0)))
    return rows


def _flag(e: dict) -> None:
    """The owner agreed, the check disqualifies: the owner's answer wins, and the owner is asked to look again."""
    chk = e.get("check") or {}
    if chk.get("status") == "disqualified" and (e.get("review") or {}).get("verdict") == "agree":
        e["flag"] = f"You agreed, but the check of {chk.get('date', '')} found: {chk.get('why') or 'disqualified'}"


def flags(session: Session) -> list[dict]:
    """Estimates the owner agreed with that the check disqualifies: shown to the owner, never excluded."""
    return [e for e in estimates(session) if e["flag"]]


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




_RANGE = re.compile(r"\$?\s?(\d+(?:\.\d+)?)\s*(?:[–-]\s*\$?(\d+(?:\.\d+)?))?\s*(B|bn|billion|M|million)\b", re.I)


def parse_range(text: str) -> tuple[float | None, float | None]:
    """The first money figure of a text as (low, high) in US dollars: '$3.7–3.9 B' -> (3.7e9, 3.9e9),
    '$1.5 B, rising to $3.0 B in 2030' -> (1.5e9, 1.5e9); (None, None) when there is none."""
    m = _RANGE.search(text or "")
    if not m:
        return None, None
    mult = 1e9 if m.group(3).lower() in ("b", "bn", "billion") else 1e6
    lo = float(m.group(1)) * mult
    return lo, float(m.group(2)) * mult if m.group(2) else lo


def parse_cagr(text: str) -> float | None:
    """'... (5.2 % a year)' or '12.25 % CAGR' -> 5.2; None when no growth rate is given."""
    m = re.search(r"(\d+(?:\.\d+)?)\s?%\s?(?:a year|CAGR|per year)", text or "", re.I)
    return float(m.group(1)) if m else None


def money(v: float | None) -> str:
    """$0.89 B, $450 M."""
    if not v:
        return "–"
    return f"${v / 1e9:,.2f} B" if v >= 1e9 else f"${v / 1e6:,.0f} M"


def band_text(low: float | None, high: float | None, year=None) -> str:
    """'$0.89–2.31 B (2024)'; one figure when low and high are the same."""
    if not low:
        return "–"
    yr = f" ({year})" if year else ""
    if not high or abs(high - low) < 1:
        return money(low) + yr
    if high >= 1e9:
        return f"${low / 1e9:,.2f}–{high / 1e9:,.2f} B{yr}"
    return f"${low / 1e6:,.0f}–{high / 1e6:,.0f} M{yr}"


def topic_defs() -> list[dict]:
    return [t for t in (_load(TOPICS_FILE).get("topics") or []) if isinstance(t, dict) and t.get("id")]


def combine(defn: dict, rows: list[dict]) -> dict:
    """One topic's band from its member estimates (each with review, check and exclusion as in ``estimates``).
    A verdict recorded in the topic file counts where this database has no review for that member (the owner's
    answers come from the live site through the daily run). Combined = at least 2 used members reviewed or verified.
    The band is set by the full-coverage members where there are any (owner, 22 Oct 2026)."""
    by_key = {e["key"]: e for e in rows}
    members, used, out_ex = [], [], []
    for m in defn.get("members") or []:
        key = str(m.get("key") if isinstance(m, dict) else m)
        if key not in by_key:
            continue
        e = dict(by_key[key])
        if e["review"] is None and isinstance(m, dict) and m.get("verdict"):
            e["review"] = {"verdict": m["verdict"], "comment": m.get("note") or "", "author": None,
                           "date": m.get("date"), "recorded": True}  # fmt: skip
            e["excluded"] = exclusion(e)
            _flag(e)
        members.append(e)
        if e["excluded"]:
            out_ex.append({"key": key, "why": e["excluded"]})
        else:
            used.append(e)
    reviewed = [e for e in used if (e["review"] or {}).get("verdict") == "agree"
                or (e.get("check") or {}).get("status") == "verified"]  # fmt: skip
    setters = [e for e in ([e for e in used if e.get("coverage") == "full"] or used) if e.get("usd")]
    low = min((e["usd"] for e in setters), default=None)
    high = max((e["usd_high"] or e["usd"] for e in setters), default=None)
    year = max((e.get("year") or 0 for e in setters), default=0) or None
    cagrs = [e["cagr"] for e in used if e.get("cagr") is not None]
    reported = [{"who": e["source"]["publisher"] or e["source"]["title"], "cagr": e["cagr"]}
                for e in used if e.get("cagr") is not None]  # growth rates only as each source reports them
    disc = {str(d.get("key")): d.get("why") or "" for d in defn.get("discrepancies") or [] if isinstance(d, dict)}
    return {**{k: defn.get(k) for k in ("id", "title", "fn", "scope", "coverage", "combined", "note", "layer",
                                        "bottom_up")},
            "reported": reported, "discrepancies": disc,
            "members": members, "used": used, "excluded": out_ex, "n": len(used), "n_reviewed": len(reviewed),
            "setters": [e["key"] for e in setters], "is_combined": len(reviewed) >= 2 and low is not None,
            "low": low, "high": high, "year": year, "band": band_text(low, high, year),
            "cagr_low": min(cagrs) if cagrs else None, "cagr_high": max(cagrs) if cagrs else None,
            "agreed": any((e["review"] or {}).get("verdict") == "agree" for e in used)}  # fmt: skip


def topics(session: Session, rows: list[dict] | None = None) -> list[dict]:
    """Every topic of data/business/tam_topics.yaml, computed from the current reviews and checks."""
    rows = estimates(session) if rows is None else rows
    return [combine(d, rows) for d in topic_defs()]


def by_function(session: Session) -> dict[str, dict]:
    """Public market size per function, for the Opportunity explorer and the demand score: the estimates linked to a
    function, without the ones the owner disagreed with or the biweekly check disqualified (unless the owner agreed:
    then it stays, with a flag). Where a combined topic exists for the function (data/business/tam_topics.yaml), its
    band is the market size: low, high, year, CAGR band, usd = the midpoint (for scoring). Otherwise, where some
    figures cover the whole market (coverage full), only those count (owner, 22 Oct 2026: for tuners, the total radio
    market); agreed figures are used when there are any, else every open one; usd = the median, with the low, high,
    latest year and how many sources (owner, 21 Oct 2026: market size comes from public data only, never from
    commercial inputs). Every entry carries "band", the text to show ("$0.89–2.31 B (2024)")."""
    out: dict[str, dict] = {}
    groups: dict[str, list[dict]] = {}
    rows = estimates(session)
    for e in rows:
        if e["fn"] and e["usd"] and not e["excluded"]:
            groups.setdefault(e["fn"], []).append({**e, "agreed": (e["review"] or {}).get("verdict") == "agree"})
    for fn, grp in groups.items():
        grp = [e for e in grp if e["coverage"] == "full"] or grp
        use = [e for e in grp if e["agreed"]] or grp
        vals = sorted(float(e["usd"]) for e in use)
        mid = len(vals) // 2
        median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
        high = max(float(e["usd_high"] or e["usd"]) for e in use)  # the top of a stated range ("$400–500 M")
        year = max((e["year"] or 0) for e in use) or None
        out[fn] = {"usd": median, "low": vals[0], "high": high, "n": len(vals),
                   "agreed": any(e["agreed"] for e in use), "year": year,
                   "band": band_text(vals[0], high, year), "topic": None}  # fmt: skip
    for t in topics(session, rows):
        if t["is_combined"] and t["fn"]:
            out[t["fn"]] = {"usd": (t["low"] + t["high"]) / 2, "low": t["low"], "high": t["high"], "n": t["n"],
                            "agreed": t["agreed"], "year": t["year"], "band": t["band"], "topic": t["id"],
                            "cagr_low": t["cagr_low"], "cagr_high": t["cagr_high"],
                            "layer": t.get("layer") or ""}  # fmt: skip
    return out
