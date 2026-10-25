"""Accuracy loop for the business data: reviewer verdicts per item, automated consistency checks, a review queue
ordered by impact on the rankings, catalogue parts that may already fill a gap, and the open items as a to-do."""

import re
from collections import Counter, defaultdict
from datetime import date, datetime
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import DataReview, PartMapping, TechFeedback, aware
from app.services import blocks
from app.services import opportunity as op
from app.services.review_history import COMMENT2, COMMENT_VERDICTS

COMMENT_LABELS = {"comment": "Comment", "comment2": "Comment (2nd round)"}
CHECKED_FILE = PROJECT_ROOT / "data" / "business" / "quality_checked.yaml"

VERDICTS = {"correct": "Correct", "wrong": "Wrong", "unsure": "Unsure"}


def datasets() -> dict[str, tuple[str, dict]]:
    """Every reviewable business dataset: name -> (label, {key: entry})."""
    out = {
        "technology": ("Technology rating", op.technology()),
        "competition": ("Competition", op.competition()),
        "customers": ("Customer segment", op.customers()),
        "capabilities": ("Technology platform", op.capabilities()),
    }
    for topic, label in op.EVIDENCE_TOPICS.items():
        out[topic] = (label, op.evidence(topic))
    out["new_markets"] = ("New-market idea", op.evidence("new_markets"))
    return out


def summary(session: Session) -> dict[tuple[str, str], dict]:
    """Verdict counts and the latest comments per (dataset, key)."""
    out: dict[tuple[str, str], dict] = defaultdict(lambda: {"correct": 0, "wrong": 0, "unsure": 0, "comments": []})
    for r in session.scalars(select(DataReview).order_by(DataReview.created_at)):
        e = out[(r.dataset, r.key)]
        e[r.verdict] = e.get(r.verdict, 0) + 1
        if r.comment:
            e["comments"].append((r.verdict, r.comment, r.author, r.created_at))
    return out


def state(s: dict | None) -> str:
    """verified (only correct verdicts), disputed (at least as many wrong as correct), or unverified."""
    if not s or not (s["correct"] or s["wrong"]):
        return "unverified"
    return "disputed" if s["wrong"] >= s["correct"] else "verified"


# ---- catalogue parts that may already fill a function ---------------------------------------------------------
@lru_cache(maxsize=512)
def _keyword_hits(fn: str) -> tuple[tuple[str, dict, bool], ...]:
    """Catalogue rows matching the function's path keywords or named parts: (MPN, row, named). Depends only on the
    data files, so it is worked out once per function and process."""
    path = op.evidence("path").get(fn) or {}
    words = [str(w) for w in path.get("catalog_keywords") or [] if len(str(w)) > 2]
    named = {str(m).upper() for m in path.get("existing_parts") or []}
    if not words and not named:
        return ()
    rx = re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.I) if words else None
    out, seen = [], set()
    for r in blocks.catalog_rows():
        mpn = str(r.get("mpn") or "").upper()
        if not mpn or mpn in seen:
            continue
        text = f"{r.get('description', '')} {r.get('category', '')} {r.get('sub', '')}"
        if mpn in named or any(mpn.startswith(n) for n in named if len(n) >= 5) or (rx and rx.search(text)):
            seen.add(mpn)
            out.append((mpn, r, mpn in named))
    return tuple(out)


def possible_existing(session: Session, fn: str, limit: int = 12) -> list[dict]:
    """Skyworks / Qorvo catalogue parts whose description matches the function's keywords but that are not mapped
    to it, plus the parts the path evidence names. Parts a reviewer rejected are left out."""
    hits = _keyword_hits(fn)
    if not hits:
        return []
    have = {c["mpn"].upper() for c in blocks._candidates(session, fn) or []}
    decided = {m.mpn.upper(): m.verdict for m in session.scalars(select(PartMapping).where(PartMapping.fn == fn))}
    out = [{**r, "named": named, "confirmed": decided.get(mpn) == "yes"}
           for mpn, r, named in hits if mpn not in have and decided.get(mpn) != "no"]  # fmt: skip
    out.sort(key=lambda r: (not r["confirmed"], not r["named"], r.get("status") != "Active", r["mpn"]))
    return out[:limit]


# ---- automated checks -------------------------------------------------------------------------------------------
def checks(apps: list[op.Application]) -> list[dict]:
    """Consistency checks across the data files. level: error (wrong data), warn (missing / suspicious), ok."""
    fns = blocks.catalogue()["functions"]
    in_scope = {p.fn for a in apps for p in a.positions if p.status in ("gap", "competitor")}
    out = []

    def add(level, title, items, hint):
        out.append(
            {"level": level if items else "ok", "title": title, "n": len(items), "examples": items[:12], "hint": hint}
        )

    add("warn", "Gap functions without a technology rating", sorted(in_scope - set(op.technology())),
        "Without a path either, distance scores the neutral 50 with low confidence.")  # fmt: skip
    add("warn", "Gap functions without a competition entry", sorted(in_scope - set(op.competition())),
        "Competition scores the neutral 50 with low confidence.")  # fmt: skip
    add("warn", "Gap functions without a path to product", sorted(in_scope - set(op.evidence("path"))),
        "The technology rating is used instead of the path.")  # fmt: skip
    bands = {"low": (0, 3), "medium": (4, 7), "high": (8, 999)}
    bad = []
    for k, e in op.competition().items():
        n, band = len(e.get("vendors") or []), bands.get(e.get("crowding"))
        if band and not band[0] <= n <= band[1]:
            bad.append(f"{k}: {e.get('crowding')} but {n} suppliers")
    add(
        "error",
        "Competition level does not match the supplier count",
        bad,
        "Few = up to 3, Several = 4-7, Crowded = 8+.",
    )
    unknown = [f"{ds}: {k}" for ds in ("technology", "competition", *op.EVIDENCE_TOPICS) for k in datasets()[ds][1]
               if k not in fns]  # fmt: skip
    add("error", "Entries for function ids that do not exist", unknown, "Renamed or misspelled function ids.")
    plat_bad = [f"{k}: {f}" for k, p in op.capabilities().items() for f in p.get("functions") or [] if f not in fns]
    add("error", "Technology platforms pointing at unknown functions", plat_bad, "Fix the id in capabilities.yaml.")
    exists = [k for k, e in op.evidence("path").items() if e.get("path") == "exists" and k in in_scope]
    add("warn", "Path says 'already in portfolio' but the function is still a gap", exists,
        "Confirm the catalogue parts on the evidence page so they count as portfolio.")  # fmt: skip
    tech3 = [k for k in in_scope if (op.technology().get(k) or {}).get("proximity") == 3]
    add("warn", "Rated 'same technology' but still a gap", sorted(tech3), "Often a missing catalogue mapping.")
    nosrc = []
    for ds in ("customers", "capabilities", *op.EVIDENCE_TOPICS):
        nosrc += [f"{ds}: {k}" for k, e in datasets()[ds][1].items()
                  if isinstance(e, dict) and not (e.get("source") or e.get("sources"))]  # fmt: skip
    add("warn", "Entries without a source", nosrc, "Unsourced entries cannot be checked.")
    low = [f"{ds}: {k}" for ds in op.EVIDENCE_TOPICS for k, e in datasets()[ds][1].items()
           if isinstance(e, dict) and e.get("confidence") == "low"]  # fmt: skip
    add("warn", "Low-confidence evidence", low, "Review these first if they feed a top-ranked function.")
    nomatch = [a.name for a in apps if not a.background and not op.segments_of(a.name)]
    add(
        "warn", "Library applications without a customer segment", nomatch, "Where to hunt shows no companies for them."
    )
    return out


# ---- review queue: unreviewed items that move the rankings most -----------------------------------------------
def queue(session: Session, apps: list[op.Application], scores: dict | None = None, limit: int = 30) -> list[dict]:
    rev = summary(session)
    ds = datasets()
    out = []
    for rank, e in enumerate(op.technology_fit(apps, scores)[:25], 1):
        for name in ("path", "technology", "competition", "trends"):
            if e["fn"] in ds[name][1] and state(rev.get((name, e["fn"]))) == "unverified":
                ent = ds[name][1][e["fn"]]
                conf = ent.get("confidence") if isinstance(ent, dict) else None
                chk = (ent.get("check") or {}) if isinstance(ent, dict) else {}
                in_score = name in ("path", "technology", "competition", "trends")
                out.append({"fn": e["fn"], "label": e["label"], "rank": rank, "dataset": name, "ds_label": ds[name][0],
                            "confidence": conf, "in_score": in_score, "check": chk or None})  # fmt: skip
    order = {"low": 0, None: 1, "medium": 2, "high": 3}
    out.sort(key=lambda q: (q["rank"], order.get(q["confidence"], 1)))
    return out[:limit]


def research(apps: list[op.Application], scores: dict | None = None) -> list[dict]:
    """Low-confidence factors of the scored gap functions, highest score first: research to do."""
    out = []
    for e in op.technology_fit(apps, scores):
        if e["score"] is None:
            continue
        for f in e["factors"]:
            if f["confidence"] == "low":
                out.append({"fn": e["fn"], "label": e["label"], "score": e["score"],
                            "suggestion_label": e["suggestion_label"], "factor": f["label"],
                            "basis": f["basis"]})  # fmt: skip
    return out


def stats(session: Session) -> list[dict]:
    rev = summary(session)
    out = []
    for name, (label, items) in datasets().items():
        st = Counter(state(rev.get((name, k))) for k in items)
        dicts = [e for e in items.values() if isinstance(e, dict)]
        conf = Counter(e.get("confidence") for e in dicts)
        chk = Counter((e.get("check") or {}).get("status") for e in dicts)
        row = {"name": name, "label": label, "n_items": len(items), "low": conf.get("low", 0)}
        row.update({k: st.get(k, 0) for k in ("verified", "disputed", "unverified")})
        row.update(src_ok=chk["confirmed"] + chk["corrected"], src_corr=chk["corrected"], src_no=chk["unconfirmed"])
        out.append(row)
    return out


def todo(session: Session) -> str:
    """Disputed and unsure items with comments, and open technology feedback, for the next data update."""
    lines = ["# Business data to-do (disputed / unsure items and open feedback)", ""]
    ds = datasets()
    for (name, key), s in sorted(summary(session).items()):
        if state(s) == "disputed" or s["unsure"]:
            label = ds.get(name, (name,))[0]
            lines.append(f"- [{label}] {key}: {s['correct']} correct, {s['wrong']} wrong, {s['unsure']} unsure")
            lines += [f"    - {v}: {c} ({a or 'anonymous'}, {t:%Y-%m-%d})" for v, c, a, t in s["comments"]]
    for f in session.scalars(select(TechFeedback).where(TechFeedback.status == "open")):
        lines.append(f"- [Technology feedback / {f.kind}] {f.topic or '-'}: {f.text} ({f.author or 'anonymous'})")
    for m in session.scalars(select(PartMapping).order_by(PartMapping.created_at)):
        lines.append(f"- [Part mapping] {m.fn}: {m.mpn} ({m.manufacturer}) -> {m.verdict} ({m.author or 'anonymous'})")
    return "\n".join(lines) + "\n"


# ---- the review queue as yes / no questions (Data management > Data quality) ------------------------------------
_PROX_WORDS = {3: "the same technology we already make", 2: "close to what we make (new design blocks needed)",
               1: "far from what we make", 0: "unrelated to what we make"}  # fmt: skip
_OUTLOOK_WORDS = {"growing": "grow", "stable": "stay about the same", "declining": "fall"}
_PATH_WORDS = {"variant": "a new variant of a product line we already sell",
               "new_design": "a new chip on technology we already have",
               "new_capability": "new technology for us (partner, licence or buy a company)",
               "not_pursue": "not ours to build (the customer's own chip or an unrelated technology)"}  # fmt: skip


def _links(e: dict, n: int = 3) -> list[tuple[str, str]]:
    """(site, URL) of the sources that were opened for the entry, else of the sources named in it."""
    out: list[tuple[str, str]] = []
    for x in ((e.get("check") or {}).get("evidence") or []) + list(e.get("sources") or []):
        x = str(x)
        i = x.find("http")
        if i >= 0:
            url = x[i:].split(" ")[0].rstrip(",;")
            if url not in [u for _, u in out]:
                out.append((url.split("/")[2] if url.count("/") >= 2 else url, url))
    return out[:n]


def _names(xs, n: int = 6) -> str:
    xs = [str(x) for x in xs or []]
    return ", ".join(xs[:n]) + (f" and {len(xs) - n} more" if len(xs) > n else "")


def ask(dataset: str, fn: str, label: str, e: dict) -> dict | None:
    """One specific yes / no question about a data item, what exactly to check, and where."""
    first = label.split(" ")[0]
    lab = label if any(c.isupper() for c in first[1:]) else label[:1].lower() + label[1:]  # "PoL LDO", "gate driver"
    links = _links(e)
    if dataset == "competition":
        vendors = e.get("vendors") or []
        if not vendors:
            q = f"Is it right that no established company (other than us) sells a {lab} today?"
            check = "Search for the product type. If you find one, name it in the comment."
        else:
            q = f"Do these companies sell a {lab} today: {_names(vendors)}?"
            check = ("Look at each company's product pages. Comment if one does not sell it, or if a big supplier "
                     "is missing (name it in the comment).")  # fmt: skip
    elif dataset == "technology":
        p = e.get("proximity")
        if p not in _PROX_WORDS:
            return None
        q = f"Is a {lab} {_PROX_WORDS[p]} at Skyworks / Qorvo?"
        check = f"The reason given: “{str(e.get('reasoning') or '').strip()}” Comment if this is not right."
    elif dataset == "path":
        if e.get("path") == "exists":
            parts = e.get("existing_parts") or []
            q = f"Can these parts of ours be sold as a {lab}: {_names(parts, 5)}?" if parts else f"Do we sell a {lab}?"
            check = "Open the parts on our product pages. Comment if none of them does the job."
        elif e.get("path") in _PATH_WORDS:
            q = f"Would a {lab} be {_PATH_WORDS[e['path']]}?"
            check = (f"What it builds on: {str(e.get('base') or 'not stated').strip()} Comment if we already sell "
                     f"it, or if it needs much more (or less) than that.")  # fmt: skip
        else:
            return None
    elif dataset == "trends":
        o = e.get("outlook")
        if o not in _OUTLOOK_WORDS:
            return None
        q = f"Will demand for {lab} parts {_OUTLOOK_WORDS[o]} over the next 3–5 years?"
        why = str(e.get("note") or "").strip()
        check = (f"The reason given: “{why}” " if why else "") + (
            "Open the source and check that it says this." if links
            else "No source could be opened for this; answer from what you know, or write “not sure” in the comment."
        )  # fmt: skip
    else:
        return None
    return {"dataset": dataset, "key": fn, "question": q, "check": check, "links": links,
            "page": f"/business/evidence/{fn}"}  # fmt: skip


def questions(session: Session, apps: list[op.Application], scores: dict | None = None, limit: int = 30) -> list[dict]:
    """The review queue as yes / no questions: the TAM estimates nobody has answered yet, then the unchecked items
    behind the top-ranked functions (most influential first)."""
    from app.services import tam

    out = []
    for e in tam.estimates(session):
        if e["review"] is None:
            url = e["source"]["url"]
            out.append({"dataset": tam.DATASET, "key": e["key"], "question": e["question"], "check": tam.check_hint(e),
                        "links": [(url.split("/")[2], url)] if url.count("/") >= 2 else [],
                        "page": f"/business/tam#t-{e['key']}"})  # fmt: skip
    ds = datasets()
    for q in queue(session, apps, scores, limit=limit):
        item = ask(q["dataset"], q["fn"], q["label"], ds[q["dataset"]][1][q["fn"]])
        if item:
            out.append(item)
    # commented items stay on the page until the owner closes them: the second round first, then the open
    # questions, then the comments being checked
    th = {k: t for k, t in threads(session).items() if t["status"] != "closed"}
    seen = {(q["dataset"], q["key"]) for q in out}
    out += [q for k in th if k not in seen and (q := item_question(session, *k))]
    for q in out:
        q["thread"] = th.get((q["dataset"], q["key"]))
    rank = {"round2": 0, None: 1, "checking": 2}
    out = [q for q in out if q["thread"]] + [q for q in out if not q["thread"]][: max(limit - len(th), 0)]
    return sorted(out, key=lambda q: rank[(q["thread"] or {}).get("status")])


# ---- comments on the questions, checked by the daily run, then a second round (owner, 25 Oct 2026) ----------------
# A comment is a DataReview row with verdict "comment" (first round) or "comment2" (second round). The daily run checks
# it and records the item in data/business/quality_checked.yaml (it cannot write the live database); the item then
# comes back as "Checked: <note> – OK now?" with the comment box again and one "Looks right now" (verdict "correct").
_CHECKED_CACHE: dict = {}


def _minute(x) -> datetime | None:
    """A time from the YAML or the database as a UTC-aware datetime to the minute (the inbox prints minutes)."""
    if isinstance(x, str):
        try:
            x = datetime.fromisoformat(x.strip())
        except ValueError:
            return None
    if isinstance(x, datetime):
        return aware(x).replace(second=0, microsecond=0)
    return None


def checked() -> dict[tuple[str, str], dict]:
    """The daily run's checks of commented items: (dataset, key) -> {date, comment_at, note}."""
    try:
        stamp = (str(CHECKED_FILE), CHECKED_FILE.stat().st_mtime_ns)
    except OSError:
        return {}
    if _CHECKED_CACHE.get("stamp") != stamp:
        data = yamlio.load(CHECKED_FILE.read_text()) or {}
        out = {}
        for e in data.get("checked") or []:
            if isinstance(e, dict) and e.get("dataset") and e.get("key"):
                out[(str(e["dataset"]), str(e["key"]))] = {"date": e.get("date"), "comment_at": e.get("comment_at"),
                                                           "note": str(e.get("note") or "").strip()}  # fmt: skip
        _CHECKED_CACHE.update(stamp=stamp, data=out)
    return _CHECKED_CACHE["data"]


def _covers(chk: dict | None, r: DataReview) -> bool:
    """Whether the run's check covers comment ``r`` (by comment_at to the minute, else by the check's date)."""
    if not chk:
        return False
    at, when = _minute(chk.get("comment_at")), _minute(r.created_at)
    if at is not None:
        return when <= at
    d = chk.get("date")
    try:
        d = d if isinstance(d, date) else date.fromisoformat(str(d))
    except ValueError:
        return False
    return when.date() <= d


def threads(session: Session) -> dict[tuple[str, str], dict]:
    """Comment threads per (dataset, key): status "checking" (comment received, being checked), "round2" (checked,
    back to the owner) or "closed" (the owner said it looks right now), with the last comment and the check."""
    rows: dict[tuple[str, str], list[DataReview]] = defaultdict(list)
    q = select(DataReview).order_by(DataReview.created_at, DataReview.id)
    for r in session.scalars(q.where(DataReview.key.in_(
            select(DataReview.key).where(DataReview.verdict.in_(COMMENT_VERDICTS))))):  # fmt: skip
        rows[(r.dataset, r.key)].append(r)
    chk = checked()
    out = {}
    for item, rs in rows.items():
        last = max((i for i, r in enumerate(rs) if r.verdict in COMMENT_VERDICTS), default=None)
        if last is None:
            continue
        c = rs[last]
        if any(r.verdict == "correct" for r in rs[last + 1 :]):
            status = "closed"
        elif _covers(chk.get(item), c):
            status = "round2"
        else:
            status = "checking"
        out[item] = {"status": status, "round": 2 if c.verdict == COMMENT2 else 1, "comment": c.comment or "",
                     "author": c.author, "date": c.created_at, "check": chk.get(item)}  # fmt: skip
    return out


def item_question(session: Session, dataset: str, key: str) -> dict | None:
    """The question for one item as on the Data quality page (it states the current value), or None."""
    from app.services import tam, vocab

    if dataset == tam.DATASET:
        e = next((e for e in tam.estimates(session) if e["key"] == key), None)
        if e is None:
            return None
        url = e["source"]["url"]
        return {"dataset": dataset, "key": key, "question": e["question"], "check": tam.check_hint(e),
                "links": [(url.split("/")[2], url)] if url.count("/") >= 2 else [],
                "page": f"/business/tam#t-{key}"}  # fmt: skip
    entry = (datasets().get(dataset) or ("", {}))[1].get(key)
    return ask(dataset, key, vocab.fn_label(key), entry) if isinstance(entry, dict) else None


def inbox_lines(session: Session) -> list[str]:
    """The inbox section: every comment still being checked, with the item, its current value and the comment."""
    out = ["\n## Data quality comments (being checked)\n",
           "Check each comment: apply it (fix the data) or find out why the value stands. Then add the item to "
           "data/business/quality_checked.yaml (dataset, key, date, comment_at, note: what was done or found); the "
           "site then asks the owner again (second round).\n"]  # fmt: skip
    ds = datasets()
    lines = []
    for (dataset, key), t in sorted(threads(session).items(), key=lambda kv: kv[1]["date"]):
        if t["status"] != "checking":
            continue
        q = item_question(session, dataset, key)
        label = "TAM estimate" if dataset == "tam" else ds.get(dataset, (dataset,))[0]
        lines.append(f"- {aware(t['date']):%Y-%m-%d %H:%M} [round {t['round']}] {label} / {key} · now: "
                     f"{q['question'] if q else '(item no longer on the page)'} · comment: "
                     f"{' '.join(t['comment'].split())}")  # fmt: skip
    return out + (lines or ["None."])
