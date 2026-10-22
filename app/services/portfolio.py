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
from app.services import blocks, vendors, vocab
from app.services import rf_coverage as rf

FILE = PROJECT_ROOT / "data" / "business" / "portfolio_compare.yaml"
LINES = ("Skyworks", "Qorvo")


@lru_cache
def curated() -> dict:
    return (yamlio.load(FILE.read_text()) if FILE.exists() else None) or {}


@lru_cache
def overlap() -> dict:
    """Active catalogue parts per function for each line: functions both sell, and those only one sells."""
    rows = []
    for fn, parts in blocks.catalog_parts().items():
        act = Counter(p["manufacturer"] for p in parts if not p.get("risk"))
        if not (act["Skyworks"] or act["Qorvo"]):
            continue
        rows.append({"fn": fn, "label": vocab.fn_label(fn), "Skyworks": act["Skyworks"], "Qorvo": act["Qorvo"]})
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
            rows.append({"fn": fn, "label": vocab.fn_label(fn), "cells": cells})
    return {"bands": bands, "rows": rows}


def competitors(session: Session) -> list[dict]:
    """Each competitor: its RF catalogue parts (catalogue rows) and its parts in the cross lists, by function."""
    notes = {c.get("vendor"): c for c in curated().get("competitors") or []}
    # data names (TI, pSemi, Lark …) land on the curated vendor that names them or their owner (data/vendors.yaml)
    alias = {vendors.group(a): v for v, c in notes.items() for a in [v, *(c.get("aliases") or [])]}

    def who(name: str) -> str:
        return alias.get(vendors.group(name), vendors.display(name))

    rf_by: dict[str, Counter] = defaultdict(Counter)
    for p in rf.competitor_parts():
        for fn in p["functions"]:
            rf_by[who(p["manufacturer"])][fn] += 1
    cross_by: dict[str, Counter] = defaultdict(Counter)
    q = (
        select(Manufacturer.name, Part.family, func.count(Part.id))
        .join(Part.manufacturer)
        .where(Manufacturer.role == ManufacturerRole.competitor)
        .group_by(Manufacturer.name, Part.family)
    )
    for name, fam, n in session.execute(q):
        if name not in LINES:
            cross_by[who(name)][fam] += n
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


# ---- product categories (owner, 22 Oct 2026: "the same table for all Skyworks / Qorvo parts") ------------------
# The two catalogues name their categories differently; each part's "category > sub-category" is matched in order
# against these words (lower case) to one shared category. The first match wins.
CATEGORY_RULES = (
    ("Isolated gate drivers", ("isolated gate driver", "isolated fet driver")),
    ("Digital isolators and isolated interfaces", ("digital isolator", "isolated transceiver", "industrial io")),
    ("Isolated amplifiers, ADCs and current sensors", ("isolated analog", "isolated current")),
    ("Optocouplers", ("optocoupler",)),
    ("Broadcast radio, TV and audio", ("audio and radio", "tv and video", "audio")),
    ("Front-end modules", ("front-end module", "diversity receive", "beamformer")),
    ("Filters, duplexers and multiplexers", ("filter", "duplexer", "diplexer", "multiplexer")),
    ("RF switches and antenna tuning", ("switch", "digitally tunable")),
    ("Attenuators, phase shifters and limiters", ("attenuator", "phase shifter", "limiter", "gain equalizer")),
    ("Mixers, modulators and converters", ("mixer", "modulator", "rf converter", "frequency multiplier")),
    ("Oscillators, VCOs and synthesizers", ("timing > oscillator", "vco", "pll", "synthesizer")),
    ("Clocks and network timing", ("clock", "jitter", "synchronizer")),
    ("RF power transistors", ("power transistor",)),
    ("Amplifiers (PA, LNA, gain, CATV)", ("amplifier",)),
    ("Wireless transceivers and UWB", ("uwb", "transceiver ic", "communications controller")),
    ("Power management", ("power management", "dc-dc", "pmic", "battery management", "power loss", "power over ethernet")),
    ("Motor controllers", ("motor controller",)),
    ("Diodes", ("diode",)),
    ("RF passives", ("passive", "coupler", "divider", "delay line")),
    ("Voice and modems", ("voice", "modem")),
)
OTHER_CATEGORY = "Other or not classified"


def category_of(category: str, sub: str = "") -> str:
    text = f"{category} > {sub}".lower()
    return next((label for label, words in CATEGORY_RULES if any(w in text for w in words)), OTHER_CATEGORY)


def _lead(s: int, q: int) -> str:
    """Which line has more parts: both when within 2x of each other (as in the band table)."""
    return "" if not (s or q) else "both" if s and q and 0.5 <= s / q <= 2 else "Skyworks" if s > q else "Qorvo"


@lru_cache
def product_categories() -> dict:
    """Active Skyworks and Qorvo catalogue parts per shared product category (discontinued, last-time-buy and
    not-for-new-design parts are left out, as in the other tables on the page)."""
    from app.services import lifecycle

    count: dict[str, Counter] = defaultdict(Counter)
    for r in blocks.catalog_rows():
        if r["manufacturer"] in LINES and not lifecycle.is_risk(r["status"]):
            cat = category_of(r["category"], r["sub"])
            if cat == OTHER_CATEGORY and r["function"]:  # e.g. Qorvo parts named only by an evaluation kit
                cat = category_of(vocab.fn_label(r["function"]))
            count[cat][r["manufacturer"]] += 1
    order = [label for label, _ in CATEGORY_RULES] + [OTHER_CATEGORY]
    rows = [{"label": k, "Skyworks": count[k]["Skyworks"], "Qorvo": count[k]["Qorvo"],
             "lead": _lead(count[k]["Skyworks"], count[k]["Qorvo"])} for k in order if k in count]  # fmt: skip
    rows.sort(key=lambda r: (r["label"] == OTHER_CATEGORY, -(r["Skyworks"] + r["Qorvo"])))
    totals = {m: sum(r[m] for r in rows) for m in LINES}
    return {"rows": rows, "totals": totals, "lead": _lead(totals["Skyworks"], totals["Qorvo"])}


# ---- synergies: Skyworks and Qorvo functions that sit next to each other in the library diagrams -----------------
@lru_cache
def synergies(limit: int = 12, min_diagrams: int = 2) -> list[dict]:
    """Pairs of functions where Skyworks has the stronger line in one and Qorvo in the other, and the library diagrams
    put them together: the cross-sell pairing (same block, connected blocks, Bundle strength) limited to the two
    lines, without gaps or competitors. Example parts are active catalogue parts of each line."""
    from app.services import opportunity as op
    from app.services import scoring

    cp = blocks.catalog_parts()
    has = {fn: Counter(p["manufacturer"] for p in parts if not p.get("risk")) for fn, parts in cp.items()}
    led = {m: {fn for fn, c in has.items() if c[m] > c[[x for x in LINES if x != m][0]]} for m in LINES}
    apps = [a for a in op.applications() if not a.background]
    pairs: dict[tuple[str, str], list] = defaultdict(list)
    for a in apps:
        fns = {p.fn for p in a.positions}
        for s in fns & led["Skyworks"]:
            for q in fns & led["Qorvo"]:
                pairs[(s, q)].append(a)
    out = []
    for (s, q), sub in pairs.items():
        if len(sub) < min_diagrams:
            continue
        why = op.pair_reasons(sub, s, q, limit=3)
        if not (why["same"] or why["linked"] or why["companion"]):
            continue  # only in the same diagrams, never next to each other: not a synergy
        n_s = sum(1 for a in apps if any(p.fn == s for p in a.positions)) or 1
        share = len(sub) / n_s
        same, linked = why["same"] / max(why["n"], 1), why["linked"] / max(why["n"], 1)

        def examples(fn, m):
            rows = [p for p in cp.get(fn, []) if p["manufacturer"] == m and not p.get("risk")]
            return sorted(rows, key=lambda p: p.get("preview", False))[:3]

        out.append({"skyworks": s, "qorvo": q, "skyworks_label": vocab.fn_label(s), "qorvo_label": vocab.fn_label(q),
                    "n": len(sub), "same": why["same"], "linked": why["linked"], "summary": why["summary"],
                    "score": scoring.bundle(share, same, linked), "diagrams": why["rows"],
                    "skyworks_parts": examples(s, "Skyworks"), "qorvo_parts": examples(q, "Qorvo"),
                    "n_skyworks": has[s]["Skyworks"], "n_qorvo": has[q]["Qorvo"]})  # fmt: skip
    out.sort(key=lambda r: (-r["score"], -r["n"], r["skyworks_label"]))
    # one row per function pair; keep the list varied: at most two rows per Skyworks or Qorvo function
    seen: Counter = Counter()
    picked = []
    for r in out:
        if seen[("s", r["skyworks"])] < 2 and seen[("q", r["qorvo"])] < 2:
            picked.append(r)
            seen[("s", r["skyworks"])] += 1
            seen[("q", r["qorvo"])] += 1
        if len(picked) >= limit:
            break
    return picked
