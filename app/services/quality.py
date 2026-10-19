"""Accuracy loop for the business data: reviewer verdicts per item, automated consistency checks, a review queue
ordered by impact on the rankings, catalogue parts that may already fill a gap, and the open items as a to-do."""

import re
from collections import Counter, defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DataReview, PartMapping, TechFeedback
from app.services import blocks
from app.services import opportunity as op

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
def possible_existing(session: Session, fn: str, limit: int = 12) -> list[dict]:
    """Skyworks / Qorvo catalogue parts whose description matches the function's keywords but that are not mapped
    to it, plus the parts the path evidence names. Parts a reviewer rejected are left out."""
    path = op.evidence("path").get(fn) or {}
    words = [str(w) for w in path.get("catalog_keywords") or [] if len(str(w)) > 2]
    named = {str(m).upper() for m in path.get("existing_parts") or []}
    if not words and not named:
        return []
    rx = re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.I) if words else None
    have = {c["mpn"].upper() for c in blocks._candidates(session, fn) or []}
    decided = {m.mpn.upper(): m.verdict for m in session.scalars(select(PartMapping).where(PartMapping.fn == fn))}
    out, seen = [], set()
    for r in blocks.catalog_rows():
        mpn = str(r.get("mpn") or "").upper()
        if not mpn or mpn in have or mpn in seen or decided.get(mpn) == "no":
            continue
        text = f"{r.get('description', '')} {r.get('category', '')} {r.get('sub', '')}"
        hit = mpn in named or any(mpn.startswith(n) for n in named if len(n) >= 5) or (rx and rx.search(text))
        if hit:
            seen.add(mpn)
            out.append({**r, "named": mpn in named, "confirmed": decided.get(mpn) == "yes"})
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
        "Technology fit falls back to a weight of 0.05.")  # fmt: skip
    add("warn", "Gap functions without a competition entry", sorted(in_scope - set(op.competition())),
        "Competition weight falls back to 0.85.")  # fmt: skip
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
def queue(session: Session, apps: list[op.Application], limit: int = 30) -> list[dict]:
    rev = summary(session)
    ds = datasets()
    out = []
    for rank, e in enumerate(op.technology_fit(apps)[:25], 1):
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
