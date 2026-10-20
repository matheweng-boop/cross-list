"""RF coverage by frequency band and output power (data/business/rf_bands.yaml explains the method).

Frequencies come from the catalogue's published key specs (or, when none is stated, from the description); the
parsing is deliberately simple and conservative: a part without a readable frequency is counted as "not stated",
never placed in a band by guesswork.
"""

import math
import re
from collections import Counter, defaultdict
from functools import lru_cache
from pathlib import Path

from app import yamlio
from app.services import blocks, lifecycle, vocab

CONFIG = Path(__file__).resolve().parents[2] / "data" / "business" / "rf_bands.yaml"
_NUM = re.compile(r"\d+(?:\.\d+)?")
_FREQ_KEY = re.compile(r"freq", re.I)
_SKIP_KEY = re.compile(r"\bIF\b|\bLO\b|bandwidth|offset|step|resolution|spacing|switching|toggle|rise|clock", re.I)
_DESC_RANGE = re.compile(r"(\d+(?:\.\d+)?)\s*(GHz|MHz)?\s*(?:to|-|–)\s*(\d+(?:\.\d+)?)\s*(GHz|MHz)", re.I)
_DESC_POINT = re.compile(r"(\d+(?:\.\d+)?)\s*(GHz|MHz)\b", re.I)
_POWER_KEY = re.compile(r"P1 ?dB|Psat|saturated|output power|power rating|linear .*power", re.I)


@lru_cache
def config() -> dict:
    return yamlio.load(CONFIG.read_text())


def _unit(key: str, value: str) -> float | None:
    """GHz multiplier from the key's or the value's unit; None when neither states one."""
    for text in (value, key):
        if re.search(r"GHz", text, re.I):
            return 1.0
        if re.search(r"MHz", text, re.I):
            return 1e-3
        if re.search(r"kHz", text, re.I):
            return 1e-6
    return None


def frequency_ranges(specs: dict, description: str = "") -> list[tuple[float, float]]:
    """Frequency ranges in GHz stated by a part: Min / Max key pairs, "887-925" style values, single test or centre
    frequencies, and as a fallback ranges written in the description."""
    lows, highs, out = [], [], []
    for k, v in (specs or {}).items():
        k, v = str(k), str(v)
        if not _FREQ_KEY.search(k) or _SKIP_KEY.search(k) or not _NUM.search(v):
            continue
        mult = _unit(k, v)
        if mult is None:  # no unit anywhere: catalogue values above 100 are MHz, small ones GHz
            mult = 1e-3 if max(float(n) for n in _NUM.findall(v)) > 100 else 1.0
        segs = [[float(n) * mult for n in _NUM.findall(s)] for s in re.split(r"/|,|;", v) if _NUM.search(s)]
        if re.search(r"\bmin", k, re.I):
            lows += [s[0] for s in segs]
        elif re.search(r"\bmax", k, re.I):
            highs += [s[-1] for s in segs]
        else:
            out += [(min(s), max(s)) for s in segs]
    out += [(lo, hi) for lo, hi in zip(lows, highs, strict=False) if lo <= hi]
    if lows and not highs:
        out += [(lo, lo) for lo in lows]
    if highs and not lows:
        out += [(hi, hi) for hi in highs]
    if not out and description:
        for a, ua, b, ub in _DESC_RANGE.findall(description):
            mult = 1.0 if ub.lower() == "ghz" else 1e-3
            ma = mult if not ua else (1.0 if ua.lower() == "ghz" else 1e-3)
            out.append((float(a) * ma, float(b) * mult))
        if not out:
            out = [(float(a) * (1.0 if u.lower() == "ghz" else 1e-3),) * 2 for a, u in _DESC_POINT.findall(description)]
    return [(lo, hi) for lo, hi in out if 0.001 <= lo <= hi <= 120]


def output_power_dbm(specs: dict) -> float | None:
    best = None
    for k, v in (specs or {}).items():
        k, v = str(k), str(v)
        if not _POWER_KEY.search(k) or not _NUM.search(v):
            continue
        n = float(_NUM.findall(v)[0])
        dbm = 10 * math.log10(n * 1000) if re.search(r"\(W\)|\bW\b", k + " " + v) and n > 0 else n
        best = dbm if best is None else max(best, dbm)
    return best


def power_class(dbm: float | None) -> str | None:
    if dbm is None:
        return None
    return next(c["id"] for c in config()["power_classes"] if dbm <= c["max_dbm"])


@lru_cache
def parts() -> tuple[dict, ...]:
    """Our RF catalogue parts in the measured functions, with their bands and (for PAs) power class."""
    fset, bands = set(config()["functions"]), config()["bands"]
    out = []
    for path, data in blocks._catalog_docs():
        for p in data.get("parts") or []:
            fns = [f for f in vocab.fills(p.get("function"), p.get("also") or []) if f in fset]
            if not fns:
                continue
            ranges = frequency_ranges(p.get("key_specs") or {}, p.get("description") or "")
            status = str(p.get("status") or "")
            maker = p.get("manufacturer") or ("Qorvo" if "qorvo" in path.name else "Skyworks")
            out.append({
                "mpn": p["mpn"], "manufacturer": maker,
                "functions": fns, "url": p.get("product_url") or "", "description": (p.get("description") or "")[:160],
                "risk": lifecycle.is_risk(status), "status": status,
                "bands": [b["id"] for b in bands if any(lo < b["hi"] and hi >= b["lo"] for lo, hi in ranges)],
                "ghz": (min(lo for lo, _ in ranges), max(hi for _, hi in ranges)) if ranges else None,
                "power": power_class(output_power_dbm(p.get("key_specs") or {})),
            })  # fmt: skip
    return tuple(out)


COMPETITOR_DIR = Path(__file__).resolve().parents[2] / "data" / "catalog" / "rf_competitors"


@lru_cache
def competitor_parts() -> tuple[dict, ...]:
    """Competitors' RF parts (data/catalog/rf_competitors/*.yaml): counted to show who else serves a slot, never offered
    as our parts. Same fields as parts(). Every part of a known function is kept (circulators, diplexers ...); the band
    views pick their own functions."""
    known, bands = vocab.functions(), config()["bands"]
    out = []
    for path in sorted(COMPETITOR_DIR.glob("*.yaml")) if COMPETITOR_DIR.exists() else []:
        for p in (yamlio.load(path.read_text()) or {}).get("parts") or []:
            fns = [f for f in vocab.fills(p.get("function")) if f in known]
            if not fns:
                continue
            lo, hi = p.get("freq_min_ghz"), p.get("freq_max_ghz")
            ranges = (
                [(float(lo), float(hi))] if lo is not None and hi is not None and 0 <= float(lo) <= float(hi) else []
            )
            status = str(p.get("status") or "")
            out.append({
                "mpn": str(p["mpn"]), "manufacturer": p.get("manufacturer") or path.stem, "functions": fns,
                "url": p.get("url") or "", "description": str(p.get("description") or "")[:160], "status": status,
                "risk": lifecycle.is_risk(status), "ranges": ranges,
                "bands": [b["id"] for b in bands if any(a < b["hi"] and z >= b["lo"] for a, z in ranges)],
                "ghz": ranges[0] if ranges else None,
                "power": power_class(float(p["pout_dbm"])) if p.get("pout_dbm") is not None else None,
            })  # fmt: skip
    return tuple(out)


def application_bands(name: str) -> list[str]:
    found = []
    for rule in config()["applications"]:
        if re.search(rule["match"], name, re.I):
            found += [b for b in rule["bands"] if b not in found]
    return found


def _fns_of(t: dict) -> set[str]:
    return {b["fn"] if isinstance(b, dict) else str(b).split(" x")[0].strip() for g in t["groups"] for b in g["blocks"]}


BLOCK_BANDS = Path(__file__).resolve().parents[2] / "data" / "business" / "rf_block_bands.yaml"


@lru_cache
def block_bands() -> dict:
    """Per-block bands (and PA power class) stated for each template: data/business/rf_block_bands.yaml."""
    return ((yamlio.load(BLOCK_BANDS.read_text()) or {}).get("templates") or {}) if BLOCK_BANDS.exists() else {}


def _block_needs(t: dict, fset: set) -> list[tuple[str, str, str | None, str]] | None:
    """(function, band, power class, basis) for each RF block of a template with stated bands; None when the
    template has no entry (the name rules are used instead)."""
    entry = block_bands().get(t["name"])
    if not entry:
        return None
    out = []
    for g in t.get("groups") or []:
        for fn, spec in (entry.get(g["id"]) or {}).items():
            if fn in fset and isinstance(spec, dict):
                out += [(fn, b, spec.get("power"), spec.get("basis") or "") for b in spec.get("bands") or []]
    return out


def demand() -> tuple[dict[str, Counter], dict[str, list[str]], int, int]:
    """Applications needing each (function, band), from the bands stated per block where the template has them
    (power amplifiers also per power class, key "power_amplifier:<class>"), else from rules on the application name;
    the names behind each band; RF applications with no band at all, out of all applications using a measured
    function."""
    fset, limits = set(config()["functions"]), config().get("function_bands") or {}
    need: dict[str, Counter] = defaultdict(Counter)
    apps: dict[str, list[str]] = defaultdict(list)
    unknown = rf = 0
    for t in [*blocks.templates(), *blocks.background_templates()]:
        fns = _fns_of(t) & fset
        if not fns:
            continue
        rf += 1
        name = blocks.display_name(t)
        stated = _block_needs(t, fset)
        if stated is not None:
            seen: set = set()
            for fn, b, power, _ in stated:
                if (fn, b) not in seen:
                    seen.add((fn, b))
                    need[fn][b] += 1
                if fn == "power_amplifier" and (fn, b, power) not in seen:
                    seen.add((fn, b, power))
                    need[f"{fn}:{power or ''}"][b] += 1
            bands = sorted({b for _, b, _, _ in stated})
        else:
            bands = application_bands(t["name"])
            for b in bands:
                for f in fns:
                    if f not in limits or b in limits[f]:
                        need[f][b] += 1
                        if f == "power_amplifier":  # power not stated
                            need[f"{f}:"][b] += 1
        if not bands:
            unknown += 1
        for b in bands:
            apps[b].append(name)
    return need, apps, unknown, rf


def basis(fn: str, band: str) -> list[tuple[str, str]]:
    """(application, reason) for the blocks of a function stated in a band."""
    fset = set(config()["functions"])
    out = []
    for t in [*blocks.templates(), *blocks.background_templates()]:
        for f, b, _, why in _block_needs(t, fset) or []:
            if f == fn and b == band and (blocks.display_name(t), why) not in out:
                out.append((blocks.display_name(t), why))
    return out


def rows() -> list[dict]:
    """One row per measured function (power amplifiers once per power class), with a cell per band."""
    cfg, ps, cs = config(), parts(), competitor_parts()
    need, _, _, _ = demand()
    out = []
    for fn in cfg["functions"]:
        classes = [(c["id"], c["label"]) for c in cfg["power_classes"]] if fn == "power_amplifier" else [(None, "")]
        mine = [p for p in ps if fn in p["functions"]]
        theirs = [p for p in cs if fn in p["functions"] and not p["risk"]]
        for cid, clabel in classes:
            sub = [p for p in mine if cid is None or p["power"] == cid]
            comp = [p for p in theirs if cid is None or p["power"] == cid]
            cells = {}
            for b in cfg["bands"]:
                inb = [p for p in sub if b["id"] in p["bands"]]
                active = [p for p in inb if not p["risk"]]
                # power amplifiers: blocks of this power class plus blocks whose power is not stated
                n_need = need[f"{fn}:{cid}"][b["id"]] + need[f"{fn}:"][b["id"]] if cid else need[fn][b["id"]]
                rivals = Counter(p["manufacturer"] for p in comp if b["id"] in p["bands"])
                cells[b["id"]] = {"n": len(active), "risk": len(inb) - len(active), "need": n_need,
                                  "by": Counter(p["manufacturer"] for p in active),
                                  "comp": sum(rivals.values()), "rivals": rivals}  # fmt: skip
            out.append({"fn": fn, "label": vocab.fn_label(fn),
                        "power": cid, "power_label": clabel, "cells": cells, "total": len(sub),
                        "no_freq": sum(1 for p in sub if not p["bands"]),
                        "no_power": sum(1 for p in mine if p["power"] is None) if cid else 0})  # fmt: skip
    return out


THIN_NEED = 5  # a slot with one or two parts is "thin" when at least this many applications need it
CROWDED = 4  # makers: a slot this many competitors serve is crowded


def market(c: dict) -> str:
    """Who else serves a slot: nobody (open, or little real need), competitors only, or crowded."""
    if not c["comp"]:
        return "nobody"
    return "crowded" if len(c["rivals"]) >= CROWDED else "competitors"


def gaps(rs: list[dict]) -> list[dict]:
    """Slots that applications need where we have no active part (or only ageing ones), then thin slots (one or two
    active parts for five or more applications), most needed first. For power amplifiers a band counts as a gap only
    when no power class has a part; a missing class is listed as such."""
    bands = {b["id"]: b for b in config()["bands"]}
    out = []
    pa = [r for r in rs if r["fn"] == "power_amplifier"]
    for r in rs:
        for bid, c in r["cells"].items():
            if not c["need"] or c["n"] > 2 or (c["n"] and c["need"] < THIN_NEED):
                continue
            if c["n"]:
                kind = "thin"
            elif r["fn"] == "power_amplifier" and any(x["cells"][bid]["n"] for x in pa):
                kind = "power"  # other power classes exist in this band
            else:
                kind = "risk" if c["risk"] else "none"
            out.append({"fn": r["fn"], "label": r["label"], "power_label": r["power_label"], "band": bands[bid],
                        "need": c["need"], "kind": kind, "risk": c["risk"], "n": c["n"], "comp": c["comp"],
                        "rivals": c["rivals"].most_common(), "market": market(c)})  # fmt: skip
    order = {"none": 0, "risk": 1, "thin": 2, "power": 3}
    seen = {"competitors": 0, "crowded": 1, "nobody": 2}  # competitors only = proven demand, the strongest signal
    return sorted(out, key=lambda g: (order[g["kind"]], seen[g["market"]], -g["need"], g["label"]))


def slot_parts(fn: str, band: str, power: str | None = None, competitors: bool = False) -> list[dict]:
    src = competitor_parts() if competitors else parts()
    return sorted(
        (p for p in src if fn in p["functions"] and band in p["bands"] and (not power or p["power"] == power)),
        key=lambda p: (p["risk"], p["manufacturer"], p["mpn"]),
    )
