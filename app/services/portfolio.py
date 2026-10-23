"""Skyworks + Qorvo: the two product lines of the combined company side by side (Products > Skyworks + Qorvo).

Counts come from the catalogues and the cross lists; the reasoning (core competence, which line to pick per
segment, advantages against each competitor, cross-sell bundles) is curated in data/business/portfolio_compare.yaml.
"""

import re
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
    ("Power management", ("power management", "dc-dc", "pmic", "battery management", "power loss", "over ethernet")),
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


# --- Which line to offer: does a Skyworks pick match a Qorvo pick? (owner, 23 Oct 2026) ------------------------------
# Functions that do the same job in a diagram under different catalogue names.
SAME_JOB = ({"rf_frontend", "wifi_fem"}, {"rf_switch", "antenna_switch"}, {"lna", "gnss_lna"},
            {"filter_saw_baw", "rf_passive"})  # fmt: skip
MATCH_RULE = ("est: similar when both parts do the same job (same function), their stated frequency ranges overlap, "
              "their supply voltages agree within 20 % and their output power class is the same; otherwise Further "
              "design effort required (extra parts, another band, power stage or supply rail around the other line's "
              "part).")  # fmt: skip
_SUPPLY_KEY = re.compile(r"supply|\bvcc\b|\bvdd\b|\bvd\b|voltage", re.I)
_SKIP_SUPPLY = re.compile(r"control|logic|isolation|withstand|breakdown|surge|cmti|current|\(m?A\)", re.I)


def _same_job(a: str, b: str) -> bool:
    return a == b or any(a in g and b in g for g in SAME_JOB)


def _ghz(specs: dict, description: str) -> tuple[float, float] | None:
    """Stated frequency span in GHz; a 'MHz' column holding GHz-sized numbers (2.4-2.5 for a Wi-Fi part) is read as
    GHz (est: no RF front end works below 10 MHz)."""
    ranges = rf.frequency_ranges(specs, description)
    if not ranges:
        return None
    lo, hi = min(r[0] for r in ranges), max(r[1] for r in ranges)
    return (lo * 1000, hi * 1000) if hi < 0.01 else (lo, hi)


def _supply(specs: dict) -> tuple[float, float] | None:
    vals = []
    for k, v in (specs or {}).items():
        if _SUPPLY_KEY.search(str(k)) and not _SKIP_SUPPLY.search(str(k)):
            vals += [float(n) for n in re.findall(r"\d+(?:\.\d+)?", str(v)) if 0.5 <= float(n) <= 100]
    return (min(vals), max(vals)) if vals else None


def _pick_part(mpn: str, rows: dict) -> dict:
    r = rows.get(mpn.upper()) or {}
    specs = r.get("key_specs") or {}
    return {"mpn": mpn, "function": r.get("function") or "", "label": vocab.fn_label(r["function"]) if r.get(
        "function") else "", "ghz": _ghz(specs, r.get("description") or ""), "supply": _supply(specs),
            "power": rf.power_class(rf.output_power_dbm(specs))}  # fmt: skip


def _compare(s: dict, q: dict) -> dict:
    reasons, notes, checked = [], [], 0
    if not (s["function"] and q["function"]):
        reasons.append("function not in the catalogue")
    elif not _same_job(s["function"], q["function"]):
        reasons.append(f"different function ({s['label']} vs {q['label']})")
    if s["ghz"] and q["ghz"]:
        checked += 1
        if s["ghz"][0] > q["ghz"][1] or q["ghz"][0] > s["ghz"][1]:
            reasons.append(f"different band ({s['ghz'][0]:g}–{s['ghz'][1]:g} vs {q['ghz'][0]:g}–{q['ghz'][1]:g} GHz)")
    else:
        notes.append("frequency")
    if s["supply"] and q["supply"]:
        checked += 1
        if s["supply"][0] > q["supply"][1] * 1.2 or q["supply"][0] > s["supply"][1] * 1.2:
            reasons.append(f"different supply ({s['supply'][1]:g} V vs {q['supply'][1]:g} V)")
    else:
        notes.append("supply")
    if s["power"] and q["power"]:
        checked += 1
        if s["power"] != q["power"]:
            reasons.append(f"different output power class ({_power_label(s['power'])} vs {_power_label(q['power'])})")
    notes = [f"not stated on both sides, not checked: {', '.join(notes)}"] if notes and not reasons else []
    if reasons and s["function"] and q["function"] and not _same_job(s["function"], q["function"]):
        n = _same_block(s["function"], q["function"])
        if n:
            notes.append(f"used side by side in the same block of {n} library diagram{'s' if n != 1 else ''}")
    return {"skyworks": s, "qorvo": q, "similar": not reasons, "reasons": reasons, "notes": notes,
            "score": (0 if reasons else 10) - 2 * len(reasons) + checked
            + (3 if _same_job(s["function"], q["function"]) else 0)}  # fmt: skip


def _power_label(cls: str) -> str:
    return next((c["label"] for c in rf.config()["power_classes"] if c["id"] == cls), cls)


@lru_cache
def _same_block(a: str, b: str) -> int:
    """Library diagrams with both functions in one block (they work together there, they do not replace each other)."""
    n = 0
    for t in blocks.templates():
        for g in t["groups"]:
            fns = {x["fn"] if isinstance(x, dict) else str(x).split(" x")[0].strip() for x in g["blocks"]}
            if a in fns and b in fns:
                n += 1
                break
    return n


@lru_cache
def pick_matches() -> dict[str, dict]:
    """Per curated segment with picks on both sides: each Skyworks pick against its closest Qorvo pick, marked similar
    or "Further design effort required" by MATCH_RULE, with the reasons. Read from the catalogue's functions,
    frequencies and supplies (est)."""
    rows = {r["mpn"].upper(): r for r in blocks.catalog_rows()}
    out = {}
    for seg in curated().get("segments") or []:
        sky = [(_pick_part(m, rows)) for m in (seg.get("pick_skyworks") or {}).get("parts") or []]
        qor = [(_pick_part(m, rows)) for m in (seg.get("pick_qorvo") or {}).get("parts") or []]
        if not (sky and qor):
            continue
        pairs = [max((_compare(s, q) for q in qor), key=lambda c: c["score"]) for s in sky]
        n = sum(p["similar"] for p in pairs)
        out[seg["id"]] = {"pairs": pairs, "similar": n, "total": len(pairs),
                          "verdict": "similar" if n == len(pairs) else "mixed" if n else "effort"}  # fmt: skip
    return out
