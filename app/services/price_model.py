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
import re
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
ENTERED = "price_breaks"  # DataReview rows: key = part number (upper case), verdict "entered", comment = JSON breaks
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


def usd_rate(currency: str | None) -> float:
    """USD per unit of the currency (ECB reference rate in the YAML); unknown currencies count as USD."""
    return config()["fx"]["usd_per"].get((currency or "USD").upper(), 1.0)


def breaks(pq: PriceQuote | None) -> list[tuple[int, float]]:
    """Lowest price at each break quantity over all the quote's offers (cut tape, reel …), in USD."""
    rate = usd_rate(getattr(pq, "currency", None))
    best: dict[int, float] = {}
    for offer in (pq.offers or []) if pq is not None and pq.found else []:
        for q, p in offer.get("breaks") or []:
            if p and p > 0 and (q not in best or p * rate < best[q]):
                best[int(q)] = float(p) * rate
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
    """Wafer cost / good dies: gross dies with the edge-loss term and the negative-binomial yield
    (1 + A * D0 / alpha) ** -alpha for clustered defects (Systems library: semiconductor_cost)."""
    gross = math.pi * (wafer_mm / 2) ** 2 / area_mm2 - math.pi * wafer_mm / math.sqrt(2 * area_mm2)
    alpha = config()["yield_model"]["alpha"]
    good = max(gross, 1) * (1 + (area_mm2 / 100) * d0 / alpha) ** -alpha
    return wafer_usd / good


def complexity(family: str) -> str:
    return (config()["families"].get(family) or {}).get("class", "standard")


def is_automotive(part: Part) -> bool:
    return any(pv.key == "qualification" and pv.value == "automotive" for pv in getattr(part, "params", None) or [])


def margin(gm: float | None = None) -> float:
    """The gross margin in use: the slider's value (clamped to the YAML range), else the default (owner, 9 Nov 2026:
    typically 55-70 %, so the middle)."""
    lo, hi = config()["margin"]["slider"]
    return min(hi, max(lo, gm)) if gm else config()["margin"]["default"]


def fab_scenarios() -> list[str]:
    """The wafer-source what-ifs, reference (foundry prices) first. Never stored per part or family: the page works out
    every scenario and the reader flips between them in the browser, so no choice is sent, logged or saved."""
    return list(config()["fab"]["wafer_factor"])


WIDE = re.compile(r"\d+W\b|\((DW\w*|DF[MP])\)|\bW(IDE|B)\b", re.I)  # SOIC-16W, SOIC-16 (DW), SOIC-20 (DFM), SOIC-8 WB


def is_wide(code: str, span_mm: float | None = None) -> bool:
    """Wide-body package: from its body width when known, else from the package code."""
    return (span_mm or 0) >= 9 or bool(WIDE.search(code or ""))


def units_of(part) -> int | None:
    """What scales the part within its family: channels (an isolator's channel split, e.g. 3/1 = 4), I/Q channels or
    tuners; None when unknown."""
    if getattr(part, "units", None):
        return int(part.units)
    for pv in getattr(part, "params", None) or []:
        if pv.key == "channel_config" and pv.value:
            nums = [int(x) for x in re.findall(r"\d+", str(pv.value))]
            return sum(nums) or None
    return None


def scale(family: str, units: int | None) -> tuple[float, float]:
    """(die area factor, test time factor) for `units` against the family's base; (1, 1) when unknown."""
    sc = config().get("scaling", {}).get(family)
    if not sc or not units:
        return 1.0, 1.0
    d = units - sc["base"]
    return max(sc["min"], 1 + sc["die_per_unit"] * d), max(sc["min"], 1 + sc["test_per_unit"] * d)


def part_ns(family: str, package: str = "", pins: int = 0, automotive: bool = False, name: str = "estimate",
            units: int | None = None, maker: str = ""):  # fmt: skip
    """A part that is not in the database, with what the cost model reads."""
    from types import SimpleNamespace

    pkg = SimpleNamespace(code=package, pin_count=pins or None, span_mm=None)
    params = [SimpleNamespace(key="qualification", value="automotive")] if automotive else []
    return SimpleNamespace(mpn=name, family=family, package=pkg, params=params, units=units, maker=maker)


def cost(part: Part, gm: float | None = None, fab: str | None = None, maker_k: float = 1.0) -> dict | None:
    """Cost build-up (low / mid / high) for the part's family and package, with wafers priced for the `fab` scenario
    (default: the reference foundry prices) and every line times the maker's scale factor `maker_k` (scale_for);
    None for an unknown family."""
    cfg = config()
    fam = cfg["families"].get(part.family)
    if fam is None:
        return None
    pins = (part.package.pin_count if part.package else None) or 8
    pk_key = package_class(part.package.code if part.package else "") or "soic"
    if pk_key == "soic" and part.package and is_wide(part.package.code, part.package.span_mm):
        pk_key = "soic_wide"
    pk = cfg["packages"][pk_key]
    units = units_of(part)
    k_die, k_test = scale(part.family, units)
    big = max(1.0, fam["die_mm2"][1] * k_die / cfg["large_die_mm2"])  # larger body for a larger die
    pkg = {"lead_frame": (pk["lead_frame"] + pk.get("lead_frame_per_pin", 0) * pins) * big,
           "mold": pk["mold"] * big, "wire": pk["wire_per_pin"] * pins,
           "assembly": pk["assembly"] + pk.get("assembly_per_pin", 0) * pins}  # fmt: skip
    cls = cfg["classes"][fam.get("class", "standard")]
    auto = is_automotive(part)
    out = {}
    src = fab if fab in cfg["fab"]["wafer_factor"] else fab_scenarios()[0]
    wf, adj = cfg["fab"]["wafer_factor"][src], cfg["cost_adjust"]
    adj_k = adj * maker_k
    pkg = {k: v * adj_k for k, v in pkg.items()}  # the owner's cost adjustment and the maker's scale: every line
    for i, level in enumerate(("low", "mid", "high")):
        wafer = fam["wafer_usd"][i] * wf[i]
        die = fam["dies"] * _die_cost(fam["die_mm2"][i] * k_die, fam["wafer_mm"], wafer, fam["defects_per_cm2"]) * adj_k
        test = fam["test_s"][i] * k_test * cls["test_usd_per_s"] * (cfg["automotive_test"][i] if auto else 1) * adj_k
        out[level] = {"die": die, "test": test, "total": die + sum(pkg.values()) + test}
    return {"family": fam, "class": cls, "automotive": auto, "fab": src, "wafer_factor": wf, "cost_adjust": adj,
            "package": pk, "package_key": pk_key, "pins": pins, "units": units, "scale": (k_die, k_test),
            "scaling": cfg.get("scaling", {}).get(part.family),
            "pkg": pkg, "levels": out, "margin": margin(gm), "maker_k": maker_k, "floor_margin": floor_margin(gm),
            "cost_price": out["mid"]["total"] / (1 - margin(gm)),
            "floor": out["mid"]["total"] / (1 - floor_margin(gm))}  # fmt: skip


def floor_margin(gm: float | None = None) -> float:
    """The margin of the hard floor: the slider's value, else the low end of the typical range (55 %)."""
    return margin(gm) if gm else config()["margin"]["draw"][0]


def market_weight(vol: int, f: dict | None) -> float:
    """How much the band leans on the market curve (the rest on the cost-based price) at a yearly volume: the YAML
    weight, less when the curve rests on few breaks, none without a curve."""
    if f is None:
        return 0.0
    b = config()["blend"]
    w = float(b["market_weight"].get(vol, b["market_weight"].get(int(vol), 0.5)))
    return w * b["few_breaks_factor"] if len(f["points"]) < b["few_breaks"] else w


def maker_of(part) -> str:
    """The part's maker: the parts database, else the `maker` the caller set, else the public list price's."""
    m = getattr(part, "manufacturer", None)
    name = getattr(m, "name", None) if m is not None else None
    return name or getattr(part, "maker", "") or (list_prices().get(getattr(part, "mpn", "")) or {}).get("maker", "")


def tech_class(family: str) -> str:
    return config()["scale"]["tech_class"].get(family, family or "")


def breadth(session: Session, maker: str, family: str) -> int:
    """How many of the maker's parts the site holds in families sharing the part's technology class."""
    if not maker:
        return 0
    from sqlalchemy import func

    from app.models import Manufacturer

    cls = tech_class(family)
    fams = [f for f in {*config()["families"], *config()["scale"]["tech_class"]} if tech_class(f) == cls] or [family]
    q = (select(func.count(Part.id)).join(Manufacturer, Part.manufacturer_id == Manufacturer.id)
         .where(func.lower(Manufacturer.name) == maker.lower(), Part.family.in_(fams)))  # fmt: skip
    return session.scalar(q) or 0


def scale_for(session: Session | None, maker: str, family: str) -> dict:
    """The maker's scale tier (owner, 9 Nov 2026: "how much of a technology the company sells at volume"): a tier
    named in the YAML with its public reason, else one from the count of its parts in the technology class; unknown
    makers take the neutral tier. {maker, tier, factor, label, why, count, cls, own}."""
    sc = config()["scale"]
    named = {k.lower(): v for k, v in sc["makers"].items()}.get((maker or "").lower())
    n = breadth(session, maker, family) if session is not None else 0
    if named:
        tier, why = named["tier"], named["why"]
    elif maker and n:
        tier = next((t for t, at_least in sc["breadth_tiers"] if n >= at_least), sc["default_tier"])
        why = f"{n} parts in this technology class on the site"
    else:
        tier, why = sc["default_tier"], "maker unknown: neutral tier"
    t = sc["tiers"][tier]
    return {"maker": maker, "tier": tier, "factor": t["factor"], "label": t["label"], "why": why, "count": n,
            "cls": tech_class(family), "own": (maker or "").lower() in {m.lower() for m in sc["own_makers"]}}


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


def model(session: Session, part: Part, pq: PriceQuote | None, gm: float | None = None,
          fab: str | None = None, owner: bool = False) -> dict:  # fmt: skip
    """The band per volume, the cost floor and everything they rest on; `missing` says what is not there. With
    `owner` (the owner is looking: never for guests, Shareables or exports) the owner's price levels apply too: the
    family factor rests on them when there are any, and a part's own level re-centres its band."""
    cfg = config()
    pts, source, list_cur = breaks(pq), "DigiKey", None
    if not pts and part.mpn in list_prices():  # no DigiKey breaks cached: the maker's own public list price tiers
        lp = list_prices()[part.mpn]
        list_cur = (lp.get("currency") or "USD").upper()
        rate = usd_rate(list_cur)
        pts = [(int(q), float(p) * rate) for q, p in lp["breaks"]]
        source = f"{lp.get('source') or lp['maker'] + ' list price'} ({lp['retrieved']})"
    f = fit(pts)
    sc = scale_for(session, maker_of(part), part.family)
    cb = cost(part, gm, fab, sc["factor"])
    factor, n_calls = family_factor(session, part.family)
    levels = points(session) if owner else []
    lv_factor, n_levels = level_factor(levels, part.family)
    if n_levels:  # owner, 9 Nov 2026: numeric levels say more than low / ok / high calls
        factor = lv_factor
    own_levels = [p for p in levels if p["key"] == part.mpn.strip().upper()]
    mine = calls(session).get(part.mpn)
    cur = list_cur or ((getattr(pq, "currency", None) or "USD").upper() if pts else "USD")
    out = {"points": pts, "source": source, "fit": f, "cost": cb, "factor": factor, "n_calls": n_calls,
           "n_levels": n_levels, "levels": own_levels, "call": mine, "rows": [], "missing": [],
           "converted_from": cur if cur != "USD" else None, "scale": sc,
           "gm": margin(gm)}  # fmt: skip
    if f is None and cb is None:
        out["missing"].append("no DigiKey price breaks cached and no public list price for this part yet")
    if cb is None:
        out["missing"].append(f"no cost assumptions for the family '{part.family}'")
    if cb is None and f is None:
        return out
    if f is None:  # no public curve: the band is the cost-based price alone (owner, 9 Nov 2026)
        out["cost_only"] = True
    floor = cb["floor"] if cb else 0.0
    if f is not None:
        mean, sd, rule = extension(f, part.family)
        out["extension"] = {"mean": mean, "sd": sd, "rule": rule}
    for vol, k in cfg["volumes"].items():
        w = market_weight(int(vol), f) if cb else 1.0
        draws = simulate(part, f, cb, vol, k, factor, gm, w)
        lo, mid, hi = _percentiles(draws, cfg["monte_carlo"]["percentiles"])
        hi = max(hi, lo * cfg["margin"]["min_band"])  # at the floor the band keeps a minimum width
        sign = SIGN.get((mine or {}).get("verdict"), 0)
        target = lo if sign < 0 else hi if sign > 0 else mid
        dist = (f["p_end"] * (vol / f["q_end"]) ** mean if vol > f["q_end"] else f["p_end"]) if f else None
        base = mid if factor == 1 else _percentiles(simulate(part, f, cb, vol, k, 1.0, gm, w), [50])[0]
        out["rows"].append({"volume": int(vol), "distributor": dist, "low": lo, "target": target, "high": hi,
                            "at_floor": lo <= floor * 1.02, "base": base, "weight": w,
                            "allowed_cost": target * (1 - margin(gm))})  # fmt: skip
    if own_levels:
        recentre(out["rows"], own_levels, gm)
    out["single"] = single(out)
    return out


def single(m: dict) -> dict | None:
    """One price per part at 1M a year (owner, 9 Nov 2026: "a single price estimate at 1 million pieces, the floor for
    example"): the band's target at 1M, never below the cost floor at the lowest typical margin; the owner's own
    level at 1M (or the band it re-centred) wins. {price, floor, by_level}."""
    row = next((r for r in m.get("rows") or [] if r["volume"] == 1000000), None)
    if row is None:
        return None
    floor = (m.get("cost") or {}).get("floor")
    if row.get("set_by"):
        return {"price": row["target"], "floor": floor, "by_level": True}
    return {"price": max(row["target"], floor or 0.0), "floor": floor, "by_level": False}


def recentre(rows: list[dict], own: list[dict], gm: float | None = None) -> None:
    """The part's own price levels set its band: at a volume with a level the target is the level (the middle of a
    range), elsewhere the target moves by the same ratio (geometric mean over its levels); low and high keep their
    distance from the target in percent."""
    at = {p["volume"]: p for p in own}
    ratios = {r["volume"]: at[r["volume"]]["mid"] / r["target"] for r in rows if r["volume"] in at and r["target"]}
    if not ratios:
        return
    other = math.exp(sum(math.log(x) for x in ratios.values()) / len(ratios))
    latest = max(own, key=lambda p: p["id"])
    for r in rows:
        k = ratios.get(r["volume"], other)
        r.update(low=r["low"] * k, target=r["target"] * k, high=r["high"] * k, at_floor=False,
                 allowed_cost=r["target"] * k * (1 - margin(gm)),
                 set_by=at.get(r["volume"], latest))  # fmt: skip


def extension(f: dict, family: str = "") -> tuple[float, float, str]:
    """(mean, sd, rule) of the slope past the last break: the pooled scaling equation; for a part whose own curve is
    flat, or any complex part, a share of its own slope (a complex part with too few breaks: its class slope)."""
    cfg = config()
    c, flat = cfg["curve"], cfg["curve"]["flat_curve"]
    complex_ = complexity(family) == "complex"
    if f["fitted"] and (f["raw_slope"] > flat["flat_above"] or complex_):
        return flat["ratio"] * f["raw_slope"], flat["sd"], "flat"
    if complex_:
        mean, sd = cfg["classes"]["complex"]["slope"]
        return mean, sd, "complex"
    return c["extend"]["mean"], c["extend"]["sd"], "pooled"


def _tri(rng: random.Random, values: list) -> float:
    lo, mid, hi = values
    return rng.triangular(lo, hi, mid)


def _percentiles(xs: list[float], ps: list[int]) -> list[float]:
    s = sorted(xs)
    return [s[min(len(s) - 1, int(p / 100 * len(s)))] for p in ps]


def simulate(part: Part, f: dict | None, cb: dict | None, vol: int, k: list[float], factor: float,
             gm: float | None = None, w: float = 1.0) -> list[float]:  # fmt: skip
    """Monte Carlo draws of the direct price at a yearly volume: the slope past the last break (normal, from the
    scaling-equation check), the distributor-to-direct factor `k` (uniform over [low, high], or triangular over
    [low, most likely, high]) and the cost inputs (triangular), the price never below the drawn cost floor: the drawn
    unit cost at the slider's margin, or without one at a margin drawn from the YAML triangle (55 / 62.5 / 70 %).
    The market price and the cost-based price (unit cost at that margin) are blended with the market weight `w`
    (owner, 9 Nov 2026: the price scales with die, lead frame and packaging), and the result never goes below the unit
    cost at the floor margin (the slider's, else 55 %). Without a curve (`f` None) the cost-based price alone.
    Seeded by the part number, so a page shows the same band every time."""
    cfg = config()
    ext, n = cfg["curve"]["extend"], cfg["monte_carlo"]["draws"]
    mean, sd, _ = extension(f, part.family) if f else (0.0, 0.0, "")
    auto = (cb or {}).get("automotive", False)
    rng = random.Random(zlib.crc32(f"{part.mpn}:{vol}".encode()))
    fam = (cb or {}).get("family")
    pkg = sum((cb or {}).get("pkg", {}).values())
    out = []
    mk = (cb or {}).get("maker_k", 1.0)
    for _ in range(n):
        price = 0.0
        if f is not None:
            s = min(ext["limits"][1], max(ext["limits"][0], rng.gauss(mean, sd)))
            dist = f["p_end"] * (vol / f["q_end"]) ** s if vol > f["q_end"] else f["p_end"]
            price = dist * (rng.uniform(*k) if len(k) == 2 else _tri(rng, k))
        if fam:
            adj = (cb or {}).get("cost_adjust", 1.0) * mk
            wafer = _tri(rng, fam["wafer_usd"]) * _tri(rng, (cb or {}).get("wafer_factor", [1.0, 1.0, 1.0]))
            k_die, k_test = (cb or {}).get("scale", (1.0, 1.0))
            die = fam["dies"] * adj * _die_cost(_tri(rng, fam["die_mm2"]) * k_die, fam["wafer_mm"], wafer,
                                                fam["defects_per_cm2"])  # fmt: skip
            rate = (cb or {}).get("class", {}).get("test_usd_per_s", 0.01)
            test = _tri(rng, fam["test_s"]) * k_test * rate * (_tri(rng, cfg["automotive_test"]) if auto else 1)
            unit_cost = die + pkg + test * adj
            gm_draw = margin(gm) if gm else _tri(rng, cfg["margin"]["draw"])  # no slider: 55-70 %, owner 9 Nov 2026
            cost_price = unit_cost / (1 - gm_draw)
            blend = cost_price if f is None else w * price + (1 - w) * cost_price
            price = max(blend * factor, unit_cost / (1 - floor_margin(gm)))
        else:
            price *= factor
        out.append(price)
    return out


def record(session: Session, mpn: str, verdict: str, comment: str = "", author: str = "") -> None:
    if verdict not in SIGN:
        raise ValueError("unknown call")
    session.add(DataReview(dataset=DATASET, key=mpn[:120], verdict=verdict, comment=comment.strip()[:2000] or None,
                           author=author.strip()[:100] or None))  # fmt: skip
    session.commit()


def record_breaks(session: Session, mpn: str, breaks_: list[tuple[int, float]], currency: str = "USD",
                  note: str = "", author: str = "") -> None:
    """Price breaks the owner entered for a part (public distributor or list prices only), kept so the market
    estimates can use them (owner, 25 Oct 2026). The newest entry per part counts."""
    import json

    if not mpn.strip() or not breaks_:
        raise ValueError("a part number and at least one price break are needed")
    cur = currency.upper() if currency.upper() in config()["fx"]["usd_per"] else "USD"
    data = {"breaks": [[int(q), float(p)] for q, p in breaks_], "currency": cur, "note": note.strip()[:300]}
    session.add(DataReview(dataset=ENTERED, key=mpn.strip().upper()[:120], verdict="entered",
                           comment=json.dumps(data), author=author.strip()[:100] or None))  # fmt: skip
    session.commit()


def entered(session: Session) -> dict[str, dict]:
    """The newest owner-entered price breaks per part number (upper case): {breaks, currency, note, author, date}."""
    import json

    out: dict[str, dict] = {}
    q = select(DataReview).where(DataReview.dataset == ENTERED).order_by(DataReview.id)
    for r in session.scalars(q):
        try:
            d = json.loads(r.comment or "{}")
        except ValueError:
            continue
        if d.get("breaks"):
            out[r.key] = {**d, "author": r.author, "date": r.created_at}
    return out


def _num(tok: str) -> float:
    if "," in tok and "." in tok:  # 1.429,28 or 1,429.28
        tok = tok.replace(".", "").replace(",", ".") if tok.rfind(",") > tok.rfind(".") else tok.replace(",", "")
    elif "," in tok:
        tok = tok.replace(",", ".")
    return float(tok)


def _is_qty(tok: str) -> bool:
    """A whole number, with or without thousands separators (1000, 1,000, 1.000); 18,66000 is a price."""
    return bool(re.fullmatch(r"\d+|\d{1,3}(?:[.,]\d{3})+", tok))


def parse_breaks(text: str) -> list[tuple[int, float]]:
    """Price breaks as pasted: "quantity price" per line, or DigiKey's layout with the quantity on its own line above
    the price line. Any currency sign, either decimal mark; extended prices after the unit price are ignored."""
    out: dict[int, float] = {}
    pending = None
    for line in (text or "").splitlines():
        toks = re.findall(r"\d[\d.,]*\d|\d", line)
        if not toks:
            continue
        if len(toks) == 1 and _is_qty(toks[0]) and pending is None:
            pending = int(re.sub(r"[.,]", "", toks[0]))
            continue
        if pending is not None and not _is_qty(toks[0]):
            q, price = pending, _num(toks[0])
        elif len(toks) >= 2 and _is_qty(toks[0]):
            q, price = int(re.sub(r"[.,]", "", toks[0])), _num(toks[1])
        else:
            pending = None
            continue
        pending = None
        if q > 0 and price > 0:
            out[q] = price
    return sorted(out.items())


def estimate(session: Session, family: str, breaks_: list[tuple[int, float]], package: str = "", pins: int = 0,
             automotive: bool = False, name: str = "estimate", currency: str = "USD", gm: float | None = None,
             fab: str | None = None, units: int | None = None, owner: bool = False, maker: str = "") -> dict:
    """The model for a part that is not in the database: pasted price breaks (in `currency`, converted to USD), a
    family, a package (wide body read from its code) and what scales the part (channels, I/Q channels, tuners)."""
    from types import SimpleNamespace

    part = part_ns(family, package, pins, automotive, name, units, maker)
    pq = SimpleNamespace(found=True, currency=currency, offers=[{"breaks": [list(b) for b in breaks_]}])
    m = model(session, part, pq, gm, fab, owner)  # type: ignore[arg-type]
    m["source"] = "pasted"
    m["converted_from"] = currency.upper() if currency.upper() != "USD" else None
    return m


def oem_path(m: dict, sop: int | None = None, volume: int | None = None, released: int | None = None) -> dict | None:
    """OEM target prices per year: the band's target at `volume` today, falling by the yearly productivity (5-7 %)
    until SOP and through the production years, but only while the part is in its first 5-6 years on the market
    (from the `released` year; unknown = new); after that the price is flat. Rows: {year, low, high, phase, flat}."""
    c = config()["oem"]
    volume = volume or c["volume"]
    row = next((r for r in m.get("rows") or [] if r["volume"] == volume), None)
    if row is None:
        return None
    sop = sop or c["default_sop"]
    base = c["base_year"]
    rel = released if released and released <= base else base
    (p_lo, p_hi), (n_lo, n_hi), mr = c["productivity"], c["price_down_years"], c["mature_rate"]

    def price(y: int, p: float, n_years: int) -> float:
        down = max(0, min(y, rel + n_years) - base)  # years from today to y that are still in the price-down window
        return row["target"] * (1 - p) ** down * (1 - mr) ** (y - base - down)

    rows = []
    for y in range(base, max(sop, base) + c["lifetime_years"]):
        phase = "today" if y == base else "before SOP" if y < sop else "SOP" if y == sop else "production"
        rows.append({"year": y, "high": price(y, p_lo, n_lo), "low": price(y, p_hi, n_hi), "flat": y > rel + n_hi,
                     "phase": phase})
    return {"volume": volume, "sop": sop, "start": row["target"], "rows": rows, "productivity": c["productivity"],
            "released": released, "assumed_new": released is None, "years": c["price_down_years"],
            "flat_from": rel + n_hi + 1, "mature_rate": mr}  # fmt: skip


def scaled(m: dict, lo: float, hi: float) -> list[dict]:
    """Another part's band from this one's: every price times a parity range (our part vs the anchor part)."""
    return [{"volume": r["volume"], "low": r["low"] * lo, "target": r["target"] * (lo + hi) / 2, "high": r["high"] * hi}
            for r in m.get("rows") or []]


# --- The owner's price levels (owner, 9 Nov 2026) ----------------------------------------------------------------
# Numbers the owner gives for real price levels: a part at a yearly volume, our part or a competitor's cross. They are
# confidential: kept only in the site's database (DataReview "price_point", key = the priced part number in upper case,
# comment = JSON), entered and seen by the owner only, never in a Shareable, an export or the inbox text (a count only),
# and never in any file of the repository. Every entry is kept; the newest per part and volume counts, and a "deleted"
# row takes a level out.
LEVELS = "price_point"
WHOSE = {"ours": "Our part", "theirs": "Competitor's cross"}
_LEVEL_NUM = re.compile(r"(\d+(?:[.,]\d*)?|[.,]\d+)(x*)", re.I)


def parse_level(text: str) -> tuple[float, float]:
    """A price level as typed: "3.5", "$0.71-0.76", "0.71 to 0.76", "0,84" or "0.7x" (0.70-0.79). (low, high) with
    low <= high; ValueError when there is no price."""
    t = re.sub(r"(?i)usd|\$", "", text or "").strip()
    nums = _LEVEL_NUM.findall(t)
    rest = _LEVEL_NUM.sub("", t)
    if not nums or len(nums) > 2 or re.sub(r"(?i)\s|-|–|—|~|to|about|approx\.?|ca\.?", "", rest):
        raise ValueError("enter a price such as 3.5, 0.71-0.76 or 0.7x")
    vals: list[float] = []
    for num, xs in nums:
        num = num.replace(",", ".")
        vals += [float(num + "0" * len(xs)), float(num + "9" * len(xs))] if xs else [float(num)]
    lo, hi = min(vals), max(vals)
    if not (0 < lo <= hi < 100000):
        raise ValueError("enter a price above zero")
    return lo, hi


def record_level(session: Session, key: str, volume: int, text: str, whose: str, ours: str = "", cross: str = "",
                 family: str = "", base: float | None = None, author: str = "") -> dict:
    """Store one price level; `base` is the model's own target for the part at that volume (no calls, no levels), so
    the family factor can compare the level with it later. Returns what was stored."""
    import json

    key = (key or "").strip().upper()[:120]
    if not key:
        raise ValueError("a part number is needed")
    if int(volume) not in {int(v) for v in config()["volumes"]}:
        raise ValueError("pick 10k, 100k or 1M a year")
    if whose not in WHOSE:
        raise ValueError("say whose part it is")
    lo, hi = parse_level(text)
    data = {"volume": int(volume), "low": lo, "high": hi, "whose": whose, "ours": ours.strip().upper()[:120],
            "cross": cross.strip().upper()[:120], "family": family if family in config()["families"] else "",
            "base": base if base and base > 0 else None}  # fmt: skip
    session.add(DataReview(dataset=LEVELS, key=key, verdict="entered", comment=json.dumps(data),
                           author=author.strip()[:100] or None))  # fmt: skip
    session.commit()
    return data


def delete_level(session: Session, key: str, volume: int, author: str = "") -> None:
    import json

    session.add(DataReview(dataset=LEVELS, key=(key or "").strip().upper()[:120], verdict="deleted",
                           comment=json.dumps({"volume": int(volume)}), author=author.strip()[:100] or None))
    session.commit()


def points(session: Session) -> list[dict]:
    """The owner's current price levels, newest per part and volume: {key, volume, low, high, mid, whose, ours, cross,
    family, base, author, date, id}. Owner only: never pass these to a guest's page or any shared output."""
    import json

    cur: dict[tuple[str, int], dict | None] = {}
    for r in session.scalars(select(DataReview).where(DataReview.dataset == LEVELS).order_by(DataReview.id)):
        try:
            d = json.loads(r.comment or "{}")
            vol = int(d["volume"])
        except (ValueError, KeyError, TypeError):
            continue
        if r.verdict == "deleted":
            cur[(r.key, vol)] = None
        elif d.get("low"):
            cur[(r.key, vol)] = {**d, "key": r.key, "volume": vol, "mid": (d["low"] + d["high"]) / 2,
                                 "author": r.author, "date": r.created_at, "id": r.id}  # fmt: skip
    return sorted((p for p in cur.values() if p), key=lambda p: (p["key"], p["volume"]))


def _geomean(xs: list[float]) -> float:
    return math.exp(sum(math.log(x) for x in xs) / len(xs))


def level_factor(levels: list[dict], family: str) -> tuple[float, int]:
    """(multiplier, number of levels) for a family: the geometric mean of level / the model's own target over the
    family's levels that have one, within the calls' limits; (1.0, 0) without any."""
    ratios = [p["mid"] / p["base"] for p in levels if p.get("family") == family and p.get("base")]
    if not ratios:
        return 1.0, 0
    lo, hi = config()["calls"]["limits"]
    return min(hi, max(lo, _geomean(ratios))), len(ratios)


def pairs(levels: list[dict]) -> list[dict]:
    """Our part and its competitor cross priced at the same volume: {ours, cross, volume, family, ratio}."""
    at = {(p["key"], p["volume"]): p for p in levels}
    out: dict[tuple, dict] = {}
    for p in levels:
        if p["whose"] == "ours" and p.get("cross"):
            ours, theirs = p, at.get((p["cross"], p["volume"]))
        elif p["whose"] == "theirs" and p.get("ours"):
            ours, theirs = at.get((p["ours"], p["volume"])), p
        else:
            continue
        if not ours or not theirs or ours["whose"] != "ours" or theirs["whose"] != "theirs":
            continue
        out[(ours["key"], theirs["key"], p["volume"])] = {
            "ours": ours["key"], "cross": theirs["key"], "volume": p["volume"],
            "family": ours.get("family") or theirs.get("family") or "", "ratio": ours["mid"] / theirs["mid"]}
    return list(out.values())


def parity(levels: list[dict], family: str) -> dict:
    """Our part vs a competitor's cross: learned from the owner's pairs in the family (geometric mean, +/- the YAML
    spread), else the YAML default. {lo, hi, ratio, n, learned}."""
    cfg = config()
    rs = [p["ratio"] for p in pairs(levels) if p["family"] == family]
    if not rs:
        lo, hi = cfg["parity"]
        return {"lo": lo, "hi": hi, "ratio": (lo + hi) / 2, "n": 0, "learned": False}
    g, sp = _geomean(rs), cfg.get("parity_spread", 0.05)
    return {"lo": min(min(rs), g * (1 - sp)), "hi": max(max(rs), g * (1 + sp)), "ratio": g, "n": len(rs),
            "learned": True}  # fmt: skip


def level_count(session: Session, since=None) -> int:
    """How many price levels were entered (since a time): the only thing the inbox may say about them."""
    from sqlalchemy import func

    q = select(func.count(DataReview.id)).where(DataReview.dataset == LEVELS, DataReview.verdict == "entered")
    if since is not None:
        q = q.where(DataReview.created_at >= since)
    return session.scalar(q) or 0

