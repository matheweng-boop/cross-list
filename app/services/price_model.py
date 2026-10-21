"""Rough price band per part at 10k / 100k / 1M a year (assumptions: data/business/price_model.yaml).

1. Curve: the part's DigiKey price breaks (cached quote) give a price-vs-quantity slope (least squares on log-log),
   extended past the reel quantity.
2. Band: past the last break the price follows P(V) = P_last * (V / q_last) ** s, with s checked against real prices
   (see validation in the YAML); a Monte Carlo over s, the distributor-to-direct factor and the cost inputs gives the
   10th / 50th / 90th percentile at each volume as low / target / high.
3. Floor: a bottom-up cost (dies on a wafer with a simple yield model + lead frame, mold compound, wire, assembly +
   test) divided by (1 - minimum margin); the band never goes below it.
4. Calls: the owner says whether real prices sit at the low end, in the band or at the high end; every call moves the
   band of the part's family, and a part's own call places its target.

Everything is an estimate; the page shows every input so a wrong one can be spotted and changed in the YAML.
"""

import math
import random
import zlib
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import DataReview, Part, PriceQuote

FILE = PROJECT_ROOT / "data" / "business" / "price_model.yaml"
LIST_FILE = PROJECT_ROOT / "data" / "business" / "list_prices.yaml"  # public list prices from makers' own pages
DATASET = "price"  # DataReview rows: key = part number, verdict = low | ok | high
CALLS = {"low": "Our real price is at or below the low end", "ok": "Within the band",
         "high": "Our real price is at or above the high end"}  # fmt: skip
SIGN = {"low": -1, "ok": 0, "high": 1}


@lru_cache
def config() -> dict:
    return yamlio.load(FILE.read_text())


@lru_cache
def list_prices() -> dict[str, dict]:
    return (yamlio.load(LIST_FILE.read_text()) or {}).get("prices") or {} if LIST_FILE.exists() else {}


def has_list_price(mpn: str) -> bool:
    return mpn in list_prices()


def breaks(pq: PriceQuote | None) -> list[tuple[int, float]]:
    """Lowest price at each break quantity over all the quote's offers (cut tape, reel …)."""
    best: dict[int, float] = {}
    for offer in (pq.offers or []) if pq is not None and pq.found else []:
        for q, p in offer.get("breaks") or []:
            if p and p > 0 and (q not in best or p < best[q]):
                best[int(q)] = float(p)
    return sorted(best.items())


def fit(points: list[tuple[int, float]]) -> dict | None:
    """Slope of log price vs log quantity on the breaks from min_qty up, clamped; anchored at the largest break."""
    if not points:
        return None
    c = config()["curve"]
    use = [(q, p) for q, p in points if q >= c["min_qty"]] or points
    lo, hi = c["slope_range"]
    if len(use) >= 2:
        xs, ys = [math.log(q) for q, _ in use], [math.log(p) for _, p in use]
        mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
        sxx = sum((x - mx) ** 2 for x in xs)
        slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx if sxx else c["default_slope"]
        fitted = True
    else:
        slope, fitted = c["default_slope"], False
    q_end, p_end = use[-1]
    return {"slope": min(hi, max(lo, slope)), "raw_slope": slope, "fitted": fitted, "q_end": q_end, "p_end": p_end,
            "points": use}  # fmt: skip


def package_class(code: str) -> str | None:
    code = (code or "").upper().strip()
    pairs = [(p, k) for k, v in config()["packages"].items() for p in v["prefixes"]]
    prefixes = sorted(pairs, key=lambda x: -len(x[0]))  # longest first: SSOP before SSO, SOIC before SO
    return next((k for p, k in prefixes if code.startswith(p)), None)


def _die_cost(area_mm2: float, wafer_mm: float, wafer_usd: float, d0: float) -> float:
    """Wafer cost / good dies: gross dies with the edge-loss term, Poisson yield exp(-A * D0)."""
    gross = math.pi * (wafer_mm / 2) ** 2 / area_mm2 - math.pi * wafer_mm / math.sqrt(2 * area_mm2)
    good = max(gross, 1) * math.exp(-(area_mm2 / 100) * d0)
    return wafer_usd / good


def cost(part: Part) -> dict | None:
    """Cost build-up (low / mid / high) for the part's family and package; None for an unknown family."""
    cfg = config()
    fam = cfg["families"].get(part.family)
    if fam is None:
        return None
    pins = (part.package.pin_count if part.package else None) or 8
    pk_key = package_class(part.package.code if part.package else "") or "soic"
    if pk_key == "soic" and part.package and (part.package.span_mm or 0) >= 9:  # e.g. SOIC-16W, SOIC-16 (DW)
        pk_key = "soic_wide"
    pk = cfg["packages"][pk_key]
    pkg = {"lead_frame": pk["lead_frame"], "mold": pk["mold"], "wire": pk["wire_per_pin"] * pins,
           "assembly": pk["assembly"]}  # fmt: skip
    out = {}
    for i, level in enumerate(("low", "mid", "high")):
        die = fam["dies"] * _die_cost(fam["die_mm2"][i], fam["wafer_mm"], fam["wafer_usd"][i], fam["defects_per_cm2"])
        test = fam["test_s"][i] * fam["test_usd_per_s"]
        out[level] = {"die": die, "test": test, "total": die + sum(pkg.values()) + test}
    return {"family": fam, "package": pk, "package_key": pk_key, "pins": pins, "pkg": pkg, "levels": out,
            "floor": out["mid"]["total"] / (1 - cfg["margin"]["floor"])}  # fmt: skip


def calls(session: Session) -> dict[str, dict]:
    """Latest call per part number: {"verdict", "comment", "author", "date"}."""
    out: dict[str, dict] = {}
    for r in session.scalars(select(DataReview).where(DataReview.dataset == DATASET).order_by(DataReview.id)):
        out[r.key] = {"verdict": r.verdict, "comment": r.comment, "author": r.author, "date": r.created_at}
    return {k: v for k, v in out.items() if v["verdict"] in SIGN}


def family_factor(session: Session, family: str) -> tuple[float, int]:
    """(multiplier, number of calls) from the owner's calls on parts of the family."""
    c = config()["calls"]
    mpns = calls(session)
    if not mpns:
        return 1.0, 0
    fam = {p.mpn: p.family for p in session.scalars(select(Part).where(Part.mpn.in_(list(mpns))))}
    signs = [SIGN[v["verdict"]] for k, v in mpns.items() if fam.get(k) == family]
    m = math.prod((1 + c["step"] * s) for s in signs) if signs else 1.0
    return min(c["limits"][1], max(c["limits"][0], m)), len(signs)


def model(session: Session, part: Part, pq: PriceQuote | None) -> dict:
    """The band per volume, the cost floor and everything they rest on; `missing` says what is not there."""
    cfg = config()
    pts, source = breaks(pq), "DigiKey"
    if not pts and part.mpn in list_prices():  # no DigiKey breaks cached: the maker's own public list price tiers
        lp = list_prices()[part.mpn]
        pts, source = [(int(q), float(p)) for q, p in lp["breaks"]], f"{lp['maker']} list price ({lp['retrieved']})"
    f = fit(pts)
    cb = cost(part)
    factor, n_calls = family_factor(session, part.family)
    mine = calls(session).get(part.mpn)
    out = {"points": pts, "source": source, "fit": f, "cost": cb, "factor": factor, "n_calls": n_calls,
           "call": mine, "rows": [], "missing": []}  # fmt: skip
    if f is None:
        out["missing"].append("no DigiKey price breaks cached and no public list price for this part yet")
    if cb is None:
        out["missing"].append(f"no cost assumptions for the family '{part.family}'")
    if f is None:
        return out
    floor = cb["floor"] if cb else 0.0
    mean, sd, rule = extension(f)
    out["extension"] = {"mean": mean, "sd": sd, "rule": rule}
    for vol, (k_lo, k_hi) in cfg["volumes"].items():
        draws = simulate(part, f, cb, vol, k_lo, k_hi, factor)
        lo, mid, hi = _percentiles(draws, cfg["monte_carlo"]["percentiles"])
        hi = max(hi, lo * cfg["margin"]["min_band"])  # at the floor the band keeps a minimum width
        sign = SIGN.get((mine or {}).get("verdict"), 0)
        target = lo if sign < 0 else hi if sign > 0 else mid
        dist = f["p_end"] * (vol / f["q_end"]) ** mean if vol > f["q_end"] else f["p_end"]
        out["rows"].append({"volume": int(vol), "distributor": dist, "low": lo, "target": target, "high": hi,
                            "at_floor": lo <= floor * 1.02})  # fmt: skip
    return out


def extension(f: dict) -> tuple[float, float, str]:
    """(mean, sd, rule) of the slope past the last break: the pooled scaling equation, or for a part whose own curve
    is flat (complex mixed-signal / RF parts) a share of its own slope."""
    c = config()["curve"]
    flat = c["flat_curve"]
    if f["fitted"] and f["raw_slope"] > flat["flat_above"]:
        return flat["ratio"] * f["raw_slope"], flat["sd"], "flat"
    return c["extend"]["mean"], c["extend"]["sd"], "pooled"


def _tri(rng: random.Random, values: list) -> float:
    lo, mid, hi = values
    return rng.triangular(lo, hi, mid)


def _percentiles(xs: list[float], ps: list[int]) -> list[float]:
    s = sorted(xs)
    return [s[min(len(s) - 1, int(p / 100 * len(s)))] for p in ps]


def simulate(part: Part, f: dict, cb: dict | None, vol: int, k_lo: float, k_hi: float, factor: float) -> list[float]:
    """Monte Carlo draws of the direct price at a yearly volume: the slope past the last break (normal, from the
    scaling-equation check), the distributor-to-direct factor (uniform) and the cost inputs (triangular), the price
    never below the drawn cost floor. Seeded by the part number, so a page shows the same band every time."""
    cfg = config()
    ext, n = cfg["curve"]["extend"], cfg["monte_carlo"]["draws"]
    mean, sd, _ = extension(f)
    rng = random.Random(zlib.crc32(f"{part.mpn}:{vol}".encode()))
    fam = (cb or {}).get("family")
    pkg = sum((cb or {}).get("pkg", {}).values())
    out = []
    for _ in range(n):
        s = min(ext["limits"][1], max(ext["limits"][0], rng.gauss(mean, sd)))
        dist = f["p_end"] * (vol / f["q_end"]) ** s if vol > f["q_end"] else f["p_end"]
        price = dist * rng.uniform(k_lo, k_hi) * factor
        if fam:
            die = fam["dies"] * _die_cost(_tri(rng, fam["die_mm2"]), fam["wafer_mm"], _tri(rng, fam["wafer_usd"]),
                                          fam["defects_per_cm2"])  # fmt: skip
            unit_cost = die + pkg + _tri(rng, fam["test_s"]) * fam["test_usd_per_s"]
            price = max(price, unit_cost / (1 - cfg["margin"]["floor"]))
        out.append(price)
    return out


def record(session: Session, mpn: str, verdict: str, comment: str = "", author: str = "") -> None:
    if verdict not in SIGN:
        raise ValueError("unknown call")
    session.add(DataReview(dataset=DATASET, key=mpn[:120], verdict=verdict, comment=comment.strip()[:2000] or None,
                           author=author.strip()[:100] or None))  # fmt: skip
    session.commit()
