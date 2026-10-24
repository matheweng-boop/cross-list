"""Shareable > Technology overview: a short brief on the Skyworks + Qorvo portfolio for readers outside the company.

The words come from data/business/tech_overview.yaml; everything countable is built here from the site's data, so the
page follows the catalogue: part and family counts (the same grouping as Products > Skyworks + Qorvo), who holds each
technology platform (data/business/capabilities.yaml) and the "up to" figures (catalogue specifications).
"""

import re
from collections import Counter
from datetime import date
from functools import lru_cache
from itertools import islice

from app import yamlio
from app.config import PROJECT_ROOT
from app.services import blocks, lifecycle, vocab
from app.services import opportunity as op
from app.services import portfolio as pf

FILE = PROJECT_ROOT / "data" / "business" / "tech_overview.yaml"
LINES = pf.LINES
_NOT_HELD = ("divested", "not held", "closing", "closed")
_DATE = re.compile(r"\b(20\d\d-\d\d-\d\d)\b")
_NUM = re.compile(r"\d+(?:\.\d+)?")


@lru_cache
def curated() -> dict:
    return (yamlio.load(FILE.read_text()) if FILE.exists() else None) or {}


@lru_cache
def active_rows() -> tuple[dict, ...]:
    """Active Skyworks and Qorvo catalogue parts, each with its product family as on the portfolio page."""
    out = []
    for r in blocks.catalog_rows():
        if r["manufacturer"] not in LINES or lifecycle.is_risk(r["status"]):
            continue
        fam = pf.category_of(r["category"], r["sub"])
        if fam == pf.OTHER_CATEGORY and r["function"]:  # as portfolio.product_categories()
            fam = pf.category_of(vocab.fn_label(r["function"]))
        out.append({**r, "family": fam})
    return tuple(out)


def catalogue_date() -> date | None:
    """The newest collection date named in the catalogue files' header comments."""
    found = []
    for path in blocks._catalog_files():
        with path.open() as f:
            head = "".join(line for line in islice(f, 12) if line.startswith("#"))
        found += _DATE.findall(head)
    return date.fromisoformat(max(found)) if found else None


def owner_of(caps: list[str]) -> str:
    """'Skyworks', 'Qorvo' or 'Both', from the current owners of the capability entries."""
    plats = op.capabilities()
    who = {o for k in caps if (p := plats.get(k)) and p.get("status", "current") not in _NOT_HELD
           for o in p.get("owner") or []}  # fmt: skip
    return "Both" if who >= set(LINES) else next(iter(who), "")


def series_prefix(series: str) -> str:
    return series.rstrip("x")


def series_parts(series: str) -> list[str]:
    pre = series_prefix(series).upper()
    return [r["mpn"] for r in active_rows() if r["mpn"].upper().startswith(pre)]


def _fmt(v: float) -> str:
    return f"{v:,.0f}" if v >= 100 or v == int(v) else f"{v:g}"


def figure(family: str, fig: dict) -> dict | None:
    """One "up to" value of a family: the extreme of a catalogue specification over its active parts, with the part
    that holds it."""
    pick = max if fig.get("agg", "max") == "max" else min
    skip = re.compile(fig["skip"], re.I) if fig.get("skip") else None
    vals = []
    for r in active_rows():
        if r["family"] != family or fig["spec"] not in r["key_specs"]:
            continue
        if skip and skip.search(r["description"]):
            continue
        nums = [float(x) for x in _NUM.findall(str(r["key_specs"][fig["spec"]]))]
        if nums:
            vals.append((pick(nums) * float(fig.get("scale", 1)), r["mpn"]))
    if not vals:
        return None
    v = pick(x for x, _ in vals)
    mpn = min(m for x, m in vals if x == v)
    return {"text": fig["text"].format(v=_fmt(round(v, 3))), "mpn": mpn}


@lru_cache
def build() -> dict:
    cur = curated()
    rows = active_rows()
    per_line = Counter(r["manufacturer"] for r in rows)
    fam_count: dict[str, Counter] = {}
    for r in rows:
        fam_count.setdefault(r["family"], Counter())[r["manufacturer"]] += 1
    fam_cur = cur.get("families") or {}
    families = []
    for label, _ in pf.CATEGORY_RULES:
        if label not in fam_count:
            continue
        c, info = fam_count[label], fam_cur.get(label) or {}
        figs = [f for f in (figure(label, x) for x in info.get("figures") or []) if f]
        families.append({"label": label, "Skyworks": c["Skyworks"], "Qorvo": c["Qorvo"], "total": sum(c.values()),
                         "headline": info.get("headline", ""), "figures": figs})  # fmt: skip
    families.sort(key=lambda f: -f["total"])
    platforms = [{**p, "owner": owner_of(p.get("caps") or [])} for p in cur.get("platforms") or []]
    by_key = {p["key"]: p for p in platforms}
    markets = [{**m, "platform_labels": [by_key[k]["label"] for k in m.get("platforms") or [] if k in by_key]}
               for m in cur.get("markets") or []]  # fmt: skip
    matrix = [{"label": p["label"], "owner": p["owner"], "cells": [p["key"] in (m.get("platforms") or [])
               for m in markets]} for p in platforms]  # fmt: skip
    rf_top = next((f for fam in families if fam["label"].startswith("Amplifiers") for f in fam["figures"]
                   if "GHz" in f["text"]), None)  # fmt: skip
    auto = sum(1 for r in rows if r["automotive"])
    facts = [
        {"num": f"{len(rows):,}", "label": "active parts in the public catalogue",
         "note": f"Skyworks {per_line['Skyworks']:,} · Qorvo {per_line['Qorvo']:,}"},
        {"num": str(len(families)), "label": "product families", "note": "from RF front ends to isolation and timing"},
        {"num": str(len(platforms)), "label": "technology platforms",
         "note": "compound semiconductor, silicon, acoustic"},
        {"num": str(len(markets)), "label": "end markets", "note": "mobile to industrial and energy"},
        {"num": f"{auto:,}", "label": "parts marked automotive grade", "note": "as stated in the catalogue"},
    ]  # fmt: skip
    if rf_top:
        facts.append({"num": rf_top["text"].replace("to ", "up to ", 1), "label": "RF and microwave coverage",
                      "note": f"highest catalogue amplifier frequency ({rf_top['mpn']})"})  # fmt: skip
    return {"cur": cur, "facts": facts, "platforms": platforms, "markets": markets, "matrix": matrix,
            "families": families, "catalogue_date": catalogue_date(),
            "unclassified": fam_count.get(pf.OTHER_CATEGORY, Counter()).total()}  # fmt: skip
