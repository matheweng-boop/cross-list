"""Skyworks + Qorvo: the two product lines of the combined company side by side (Products > Skyworks + Qorvo).

Counts come from the catalogues and the cross lists; the reasoning (core competence, which line to pick per
segment, advantages against each competitor, cross-sell bundles) is curated in data/business/portfolio_compare.yaml.
"""

from collections import Counter, defaultdict
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import Manufacturer, ManufacturerRole, Part
from app.services import blocks
from app.services import rf_coverage as rf

FILE = PROJECT_ROOT / "data" / "business" / "portfolio_compare.yaml"
LINES = ("Skyworks", "Qorvo")


@lru_cache
def curated() -> dict:
    return (yamlio.load(FILE.read_text()) if FILE.exists() else None) or {}


def function_label(fn: str) -> str:
    f = blocks.catalogue()["functions"].get(fn)
    return f["label"] if f else fn.replace("_", " ")


@lru_cache
def overlap() -> dict:
    """Active catalogue parts per function for each line: functions both sell, and those only one sells."""
    rows = []
    for fn, parts in blocks.catalog_parts().items():
        act = Counter(p["manufacturer"] for p in parts if not p.get("risk"))
        if not (act["Skyworks"] or act["Qorvo"]):
            continue
        rows.append({"fn": fn, "label": function_label(fn), "Skyworks": act["Skyworks"], "Qorvo": act["Qorvo"]})
    rows.sort(key=lambda r: -(r["Skyworks"] + r["Qorvo"]))
    return {
        "both": [r for r in rows if r["Skyworks"] and r["Qorvo"]],
        "Skyworks": [r for r in rows if r["Skyworks"] and not r["Qorvo"]],
        "Qorvo": [r for r in rows if r["Qorvo"] and not r["Skyworks"]],
        "totals": {m: sum(r[m] for r in rows) for m in LINES},
    }


@lru_cache
def rf_bands() -> dict:
    """RF functions by band: active parts of each line and of all competitors together, and who has more."""
    bands = rf.config()["bands"]
    ours: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for p in rf.parts():
        if p.get("risk"):
            continue
        for fn in p["functions"]:
            for b in p["bands"]:
                ours[(fn, b)][p["manufacturer"]] += 1
    theirs: Counter = Counter()
    for p in rf.competitor_parts():
        for fn in p["functions"]:
            for b in p["bands"]:
                theirs[(fn, b)] += 1
    rows = []
    for fn in rf.config()["functions"]:
        cells = []
        for b in bands:
            c = ours.get((fn, b["id"]), Counter())
            s, q, comp = c["Skyworks"], c["Qorvo"], theirs[(fn, b["id"])]
            lead = "" if not (s or q) else "both" if s and q and 0.5 <= s / q <= 2 else "Skyworks" if s > q else "Qorvo"
            cells.append({"band": b["id"], "Skyworks": s, "Qorvo": q, "competitors": comp, "lead": lead})
        if any(c["Skyworks"] or c["Qorvo"] for c in cells):
            rows.append({"fn": fn, "label": function_label(fn), "cells": cells})
    return {"bands": bands, "rows": rows}


def competitors(session: Session) -> list[dict]:
    """Each competitor: its RF catalogue parts (catalogue rows) and its parts in the cross lists, by function."""
    notes = {c.get("vendor"): c for c in curated().get("competitors") or []}
    # data names (TI, pSemi, Trans-Tech …) land on the curated vendor that lists them as aliases
    alias = {a: v for v, c in notes.items() for a in c.get("aliases") or []}
    rf_by: dict[str, Counter] = defaultdict(Counter)
    for p in rf.competitor_parts():
        for fn in p["functions"]:
            rf_by[alias.get(p["manufacturer"], p["manufacturer"])][fn] += 1
    cross_by: dict[str, Counter] = defaultdict(Counter)
    q = (
        select(Manufacturer.name, Part.family, func.count(Part.id))
        .join(Part.manufacturer)
        .where(Manufacturer.role == ManufacturerRole.competitor)
        .group_by(Manufacturer.name, Part.family)
    )
    for name, fam, n in session.execute(q):
        if name not in LINES:
            cross_by[alias.get(name, name)][fam] += n
    names = sorted(
        set(rf_by) | set(cross_by) | set(notes), key=lambda n: -(sum(rf_by[n].values()) + sum(cross_by[n].values()))
    )
    out = []
    for n in names:
        out.append({
            "vendor": n, "rf": rf_by[n].most_common(), "cross": cross_by[n].most_common(),
            "rf_total": sum(rf_by[n].values()), "cross_total": sum(cross_by[n].values()), "notes": notes.get(n),
        })  # fmt: skip
    return out


@lru_cache
def bundles(limit: int = 30) -> list[dict]:
    """Block diagrams where both lines fill blocks: per application, the functions each line can supply."""
    cp = blocks.catalog_parts()
    has = {fn: Counter(p["manufacturer"] for p in parts if not p.get("risk")) for fn, parts in cp.items()}
    out = []
    for i, t in enumerate(blocks.templates()):
        fns = blocks.template_functions(t)
        sky = [fn for fn in fns if has.get(fn, {}).get("Skyworks")]
        qor = [fn for fn in fns if has.get(fn, {}).get("Qorvo")]
        if not sky or not qor:
            continue
        only_s, only_q = [f for f in sky if f not in qor], [f for f in qor if f not in sky]
        out.append({
            "i": i, "name": blocks.display_name(t), "category": t.get("category") or "Other", "blocks": len(fns),
            "skyworks": sky, "qorvo": qor, "only_skyworks": only_s, "only_qorvo": only_q,
            "covered": len(set(sky) | set(qor)),
        })  # fmt: skip
    # most complementary first: both lines bring something the other doesn't, then by blocks covered
    out.sort(key=lambda r: (-(min(len(r["only_skyworks"]), len(r["only_qorvo"])) > 0), -r["covered"], r["name"]))
    return out[:limit]
