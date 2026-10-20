"""Opportunities > Automotive map: per automotive application and function, how far Skyworks + Qorvo are from an
automotive product (A automotive today, B qualify it, C variant, D adjacent technology, gap).

A and B come from the parts (blocks._candidates, grade from autograde); C, D and notes from
data/business/auto_reach.yaml. Reviews (accept / reject) are DataReview rows with dataset "auto_reach" and key
"<app>:<fn>"; the latest verdict counts. The whole map is built once per data version and review state.
"""

import re
from collections import defaultdict
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import DataReview
from app.services import autograde, blocks, vocab
from app.services import opportunity as op

FILE = PROJECT_ROOT / "data" / "business" / "auto_reach.yaml"
DATASET = "auto_reach"
OURS = ("Skyworks", "Qorvo")
LEVELS = ("A", "B", "C", "D", "gap")
LEVEL_LABEL = {"A": "Automotive today", "B": "Qualify it", "C": "Variant", "D": "Adjacent technology", "gap": "Gap"}
LEVEL_HELP = {
    "A": "We sell an automotive-grade part of this function",
    "B": "We sell parts of this function, none automotive: mostly qualification work",
    "C": "We have the technology and a close product: a new design on the same process",
    "D": "Related technology we own, further away: new process steps, packaging or partners",
    "gap": "Neither company has it",
}
_DEMAND = {"high": 0, "medium": 1, "low": 2}
_URL = re.compile(r"https?://\S+")
_CACHE: dict[tuple, dict] = {}


@lru_cache
def config() -> dict:
    return yamlio.load(FILE.read_text()) or {}


@lru_cache
def applications() -> tuple[dict, ...]:
    """Configured applications with the library diagrams they cover and the functions those diagrams use."""
    tpls = [(blocks.display_name(t), t) for t in blocks.templates()]
    taken: set[str] = set()
    out = []
    for a in config().get("applications") or []:
        keys = [k.lower() for k in a.get("templates") or []]
        mine = [(n, t) for n, t in tpls if n not in taken and any(k in t.get("name", "").lower() for k in keys)]
        taken.update(n for n, _ in mine)
        fns = {f for _, t in mine for f in blocks.template_functions(t)}
        out.append({"id": a["id"], "label": a["label"], "diagrams": [n for n, _ in mine], "fns": fns})
    return tuple(out)


def _rows() -> dict[tuple[str, str], dict]:
    return {(r["app"], r["fn"]): r for r in config().get("rows") or []}


def _review_version(session: Session) -> tuple:
    return session.execute(
        select(func.count(DataReview.id), func.max(DataReview.id)).where(DataReview.dataset == DATASET)
    ).one()


def _verdicts(session: Session) -> dict[str, str]:
    """Latest verdict per cell key: correct (accepted) or wrong (rejected)."""
    q = select(DataReview.key, DataReview.verdict).where(DataReview.dataset == DATASET).order_by(DataReview.id)
    return {k: v for k, v in session.execute(q)}


def _function_level(session: Session, fn: str) -> dict | None:
    """Computed A / B for a function from our parts; None for customer parts, level None when we have no part."""
    cands = blocks._candidates(session, fn)
    if cands is None:
        return None
    graded = [(p, *autograde.grade(p)) for p in cands if p["manufacturer"] in OURS]
    ours = [p for p, _, _ in graded]
    auto = [p for p, g, _ in graded if g == autograde.AUTOMOTIVE]
    how: dict[str, int] = defaultdict(int)
    for _, g, h in graded:
        if g == autograde.AUTOMOTIVE:
            how[h] += 1
    stated = sum(1 for _, g, _ in graded if g != autograde.NOT_STATED)
    if auto:
        show, level = auto, "A"
        why = f"{len(auto)} of {len(ours)} Skyworks / Qorvo parts are automotive grade."
        missing = ""
    elif ours:
        show, level = ours, "B"
        why = f"{len(ours)} Skyworks / Qorvo parts, none stated automotive ({len(ours) - stated} with no grade stated)."
        missing = "Automotive qualification (AEC-Q100) of an existing part, or a check whether one already has it."
    else:
        return {"level": None}
    show = sorted(show, key=lambda p: (p.get("risk", False), p.get("preview", False), p["mpn"]))[:6]
    return {"level": level, "why": why, "missing": missing, "n_ours": len(ours), "n_auto": len(auto),
            "how": dict(how), "parts": [{"mpn": p["mpn"], "manufacturer": p["manufacturer"], "url": p.get("url") or ""}
                                        for p in show]}  # fmt: skip


def _platforms(ids) -> list[str]:
    caps = op.capabilities()
    return [caps[i]["name"] if i in caps else str(i) for i in ids or []]


def _source(text) -> dict:
    """'Title, publisher, year, URL (note)' -> text and link."""
    m = _URL.search(str(text))
    return {"text": str(text)[: m.start()].rstrip(" ,") + str(text)[m.end() :] if m else str(text),
            "url": m.group(0) if m else ""}  # fmt: skip


def _curated(row: dict) -> dict:
    """A row of auto_reach.yaml as shown on the page."""
    return {"level": str(row.get("level") or ""), "title": row.get("title") or "",
            "why": " ".join(str(row.get("why") or "").split()), "missing": row.get("missing") or "",
            "driver": row.get("driver") or "", "demand": row.get("demand") or "",
            "confidence": row.get("confidence") or "", "sources": [_source(x) for x in row.get("sources") or []],
            "platforms": _platforms(row.get("platforms")),
            "parts": [{"mpn": m, "manufacturer": "", "url": f"/find?q={m}"} for m in row.get("parts") or []],
            }  # fmt: skip


def _cell(row: dict | None, comp: dict | None) -> dict | None:
    """One cell: a curated level where we have no part (or override), else the computed A/B with the row as the
    next step (or a note), else a gap; None for the customer's own parts."""
    if row and row.get("level") and (row.get("override") or not comp or not comp["level"]):
        return {**_curated(row), "curated": True}
    if comp and comp["level"]:
        return {**comp, "curated": False, "next": _curated(row) if row else None}
    if comp is None:
        return None
    return {"level": "gap", "why": "Neither Skyworks nor Qorvo sells a part of this function.", "curated": False}


def build(session: Session) -> dict:
    """The map: applications (rows), functions (columns), cells by (app, fn), moves and rejected calls."""
    key = (blocks._data_version(session), _review_version(session))
    if key in _CACHE:
        return _CACHE[key]
    rows, verdicts, cat = _rows(), _verdicts(session), blocks.catalogue()["functions"]
    apps = applications()
    computed = {fn: _function_level(session, fn) for fn in {f for a in apps for f in a["fns"]} | {f for _, f in rows}}
    cells: dict[tuple[str, str], dict] = {}
    for a in apps:
        for fn in a["fns"] | {f for app, f in rows if app == a["id"]}:
            c = _cell(rows.get((a["id"], fn)) or rows.get(("*", fn)), computed.get(fn))
            if c is None:
                continue
            k = f"{a['id']}:{fn}"
            reviewable = c["level"] != "A" or bool(c.get("next"))
            status = {"correct": "accepted", "wrong": "rejected"}.get(verdicts.get(k), "proposed") if reviewable else ""
            c.update(key=k, app=a["id"], app_label=a["label"], fn=fn, label=vocab.fn_label(fn), status=status,
                     category=(cat.get(fn) or {}).get("category", ""))  # fmt: skip
            cells[(a["id"], fn)] = c
    # RF first, then the radio SoCs and timing, then the catalogue's category order
    lead = ["rf", "radio", "networking", "timing", *blocks.catalogue()["categories"]]
    order = {c: i for i, c in enumerate(dict.fromkeys(lead))}
    fn_cat = {fn: (cat.get(fn) or {}).get("category", "") for _, fn in cells}
    columns = sorted(fn_cat, key=lambda f: (order.get(fn_cat[f], 99), vocab.fn_label(f).lower()))
    rv = config().get("rf_view") or {}
    rf = {f for f in columns if fn_cat[f] in (rv.get("categories") or []) or f in (rv.get("functions") or [])}
    live = [c for c in cells.values() if c["status"] != "rejected"]
    out = {"apps": apps, "columns": columns, "rf": rf, "cells": cells, "moves": _moves(live),
           "rejected": [c for c in cells.values() if c["status"] == "rejected"],
           "counts": {lv: sum(1 for c in live if c["level"] == lv) for lv in LEVELS}}  # fmt: skip
    _CACHE.clear()
    _CACHE[key] = out
    return out


def _moves(cells: list[dict]) -> list[dict]:
    """The B, C and D steps (a cell's own level, or the next step on a cell we already fill), one per function and
    step: research demand first, then B and C before D, then how many applications need it."""
    by: dict[tuple, dict] = {}
    for c in cells:
        step = c.get("next") if (c.get("next") or {}).get("level") else c
        if step["level"] not in ("B", "C", "D"):
            continue
        m = by.setdefault((c["fn"], step["level"], step.get("title") or ""), {
            "fn": c["fn"], "label": step.get("title") or c["label"], "level": step["level"], "apps": [],
            "demand": "", "driver": "", "key": c["key"], "category": c["category"], "now": c["level"]})  # fmt: skip
        m["apps"].append(c["app_label"])
        if step.get("demand") and _DEMAND.get(step["demand"], 9) < _DEMAND.get(m["demand"], 9):
            m["demand"], m["driver"], m["key"] = step["demand"], step.get("driver") or "", c["key"]
    return sorted(by.values(), key=lambda m: (_DEMAND.get(m["demand"], 3), m["level"] == "D", -len(m["apps"]),
                                              m["level"], m["label"]))  # fmt: skip


def review(session: Session, key: str, verdict: str, author: str | None = None) -> None:
    """accept -> correct, reject -> wrong, reset -> unsure (back to proposed)."""
    v = {"accept": "correct", "reject": "wrong", "reset": "unsure"}[verdict]
    session.add(DataReview(dataset=DATASET, key=key[:120], verdict=v, author=author))
    session.commit()
