"""Car radio market, bottom-up from the site's own price estimates (data/business/radio_market.yaml).

Owner, 25 Oct 2026: the market that counts is the total radio market, adjacent technologies included; content per
vehicle comes from the price estimates, and missing prices must be asked for, never guessed. So:

- Each part of the reference systems is priced with the price model at the automotive volume (1M a year): from its
  own prices (prices the owner entered, a public list price, a cached DigiKey quote) or, for a part without any, from a
  priced sibling only once the owner has made a low / in band / high call on the part. Without that the part is
  "needed": the figure that rests on it is Not Enough Data and the part is listed as a required to-do.
- Market at current BOM content = BOM per vehicle x 90-92 M vehicles x today's system mix (no growth).
- Vehicles are flat, so growth is content growth: the mix moving to digital systems at today's prices. One CAGR per
  layer, used for every projection. Analyst growth rates are shown only as reported by their source.
"""

from __future__ import annotations

from functools import lru_cache

from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.services import price_builder as pb
from app.services import price_model as pm

FILE = PROJECT_ROOT / "data" / "business" / "radio_market.yaml"
NED = "Not Enough Data"
LAYERS = {"tuner": "Tuner content (tuner ICs only)",
          "radio": "Radio content (tuners + digital radio demodulators)",
          "adjacent": "Adjacent radio content (antenna amplifier, antenna switch, audio amplifier)",
          "total": "Total radio market (radio + adjacent content)"}  # fmt: skip
CASE = "radio-tuner-next"
CHOICE = "radio_bom_part"  # DataReview rows: key = block, verdict "chosen", comment = the part number the owner picked


@lru_cache
def config() -> dict:
    return yamlio.load(FILE.read_text()) or {}


def _direct(vol: int) -> tuple[float, float]:
    """The distributor-to-direct factor range at a volume (price_model.yaml volumes)."""
    k = pm.config()["volumes"].get(vol) or list(pm.config()["volumes"].values())[-1]
    return k[0], k[-1]


def price(session: Session, mpn: str | None, block: str, vol: int) -> dict:
    """One part at `vol` a year: {ok, low, target, high, basis, source, why}. ok False = Not Enough Data, with why."""
    if not mpn:
        return {"ok": False, "why": "no part chosen for this block yet"}
    calls = pm.calls(session)
    call = calls.get(mpn) or calls.get(mpn.upper())
    row = pb.Row(mpn=mpn)
    info = pb.site_info(session, mpn)
    fam = info["family"] or pm.config()["function_family"].get(block, "")
    if fam not in pm.config()["families"]:  # no cost model for the block: entered prices x the direct factor
        own = pb.own_prices(session, row, info)
        if own is None:
            return {"ok": False, "why": "no prices entered (no price model family for this block)"}
        pts, cur, source = own
        last = pts[-1][1] * pm.usd_rate(cur)
        lo, hi = (last * k for k in _direct(vol))
        return {"ok": True, "low": lo, "target": (lo + hi) / 2, "high": hi, "source": source,
                "basis": "own prices × direct factor (no cost model for this block)"}  # fmt: skip
    row.family = fam
    out = pb.price_row(session, row, vol, pm.margin(None), 1.0, pm.config()["oem"]["default_sop"])
    if not out["scenarios"]:
        return {"ok": False, "why": out["error"] or "no prices"}
    if out["anchor"] and not call:  # sibling parity is a model guess until the owner places the part
        return {"ok": False, "why": f"no prices of its own (only a sibling, {out['anchor']['mpn']}); enter prices "
                                    "or make a low / in band / high call"}  # fmt: skip
    at = out["scenarios"][0][1]["at"]
    lo, mid, hi = at["low"], at["target"], at["high"]
    if out["anchor"] and call:
        mid = {"low": lo, "high": hi}.get(call["verdict"], mid)
    basis = out["basis"] + (f"; owner call: {pm.CALLS[call['verdict']].lower()}" if call else "")
    return {"ok": True, "low": lo, "target": mid, "high": hi, "basis": basis, "source": out["source"]}


def _sum(rows: list[dict], layers: set[str]) -> dict:
    use = [r for r in rows if r["layer"] in layers]
    if not use:
        return {"ok": True, "low": 0.0, "target": 0.0, "high": 0.0}
    if not all(r["price"]["ok"] for r in use):
        return {"ok": False}
    q = {"low": lambda r: r["qty"][0], "target": lambda r: sum(r["qty"]) / 2, "high": lambda r: r["qty"][1]}
    return {"ok": True, **{k: sum(f(r) * r["price"][k] for r in use) for k, f in q.items()}}


LAYER_SETS = {"tuner": {"tuner"}, "radio": {"tuner", "demod"}, "adjacent": {"adjacent"},
              "total": {"tuner", "demod", "adjacent"}}  # fmt: skip


def choices(session: Session) -> dict[str, str]:
    """The part the owner picked for a block that has none in the YAML (newest per block)."""
    from sqlalchemy import select

    from app.models import DataReview

    q = select(DataReview).where(DataReview.dataset == CHOICE).order_by(DataReview.id)
    return {r.key: r.comment for r in session.scalars(q) if r.comment}


def choose(session: Session, block: str, mpn: str, author: str = "") -> None:
    from app.models import DataReview

    blocks = {r["block"] for s in config().get("systems") or [] for r in s.get("rows") or []}
    if block not in blocks or not mpn.strip():
        raise ValueError("unknown block or no part number")
    session.add(DataReview(dataset=CHOICE, key=block, verdict="chosen", comment=mpn.strip()[:120],
                           author=author.strip()[:100] or None))  # fmt: skip
    session.commit()


def systems(session: Session) -> list[dict]:
    """The reference systems with every row priced and the content per vehicle per layer."""
    cfg, vol = config(), config().get("volume", 1000000)
    picked = choices(session)
    out = []
    for s in cfg.get("systems") or []:
        rows = []
        for r in s.get("rows") or []:
            qty = list(r.get("qty") or [1, 1])
            if not r.get("part") and picked.get(r["block"]):
                r = {**r, "part": picked[r["block"]], "chosen": True}
            alt = price(session, r["alt"], r["block"], vol) if r.get("alt") else None
            rows.append({**r, "qty": qty, "price": price(session, r.get("part"), r["block"], vol),
                         "alt_price": alt if alt and alt["ok"] else None})  # fmt: skip
        out.append({**s, "rows": rows, "content": {k: _sum(rows, v) for k, v in LAYER_SETS.items()}})
    return out


def mix() -> dict:
    """Today's digital share of new-car radios: known regions weighted by vehicles; unknown regions counted as all
    AM/FM (low) and as all digital (high). {low, high, known, unknown, regions, target}."""
    m = config().get("mix") or {}
    regs = m.get("regions") or []
    world = m.get("world_m") or sum(r["vehicles_m"] for r in regs) or 1
    known = sum(r["vehicles_m"] * r["share"] for r in regs if r.get("share") is not None)
    unknown = sum(r["vehicles_m"] for r in regs if r.get("share") is None)
    return {"low": known / world, "high": min(1.0, (known + unknown) / world), "regions": regs,
            "unknown": [r["region"] for r in regs if r.get("share") is None], "target": m.get("target")}  # fmt: skip


def _cagr(a: float, b: float, years: int) -> float | None:
    return ((b / a) ** (1 / years) - 1) * 100 if a > 0 and b > 0 and years > 0 else None


def layer_market(sysmap: dict, layer: str, mx: dict, veh: dict) -> dict:
    """Market at current BOM content for one layer: low = fewest vehicles, low prices, lowest digital share; high =
    most vehicles, high prices, highest share. Not Enough Data when either system's content is."""
    a, d = sysmap["analog"]["content"][layer], sysmap["digital"]["content"][layer]
    if not (a["ok"] and d["ok"]):
        return {"ok": False}

    def at(k: str, share: float) -> float:
        return a[k] * (1 - share) + d[k] * share

    lo = veh["low"] * min(at("low", mx["low"]), at("low", mx["high"]))
    hi = veh["high"] * max(at("high", mx["low"]), at("high", mx["high"]))
    per = {"low": min(at("low", mx["low"]), at("low", mx["high"])),
           "high": max(at("high", mx["low"]), at("high", mx["high"]))}  # fmt: skip
    # one content-driven CAGR: today's mix -> every new radio digital by the target year, today's target prices
    years = config()["target_year"] - config()["base_year"]
    t_low, t_high = at("target", mx["low"]), at("target", mx["high"])
    end = at("target", mx["target"]) if mx.get("target") is not None else d["target"]
    cg = [c for c in (_cagr(t_low, end, years), _cagr(t_high, end, years)) if c is not None]
    return {"ok": True, "low": lo, "high": hi, "per_vehicle": per, "cagr_max": max(cg) if cg else None,
            "cagr_min": min(cg) if cg else None, "y_low": veh["low"] * end, "y_high": veh["high"] * end,
            "end_per_vehicle": end}  # fmt: skip


def needed(sys_rows: list[dict]) -> list[dict]:
    """Parts without a usable price basis, once each: {part, label, block, why, href}."""
    seen, out = set(), []
    for s in sys_rows:
        for r in s["rows"]:
            key = r.get("part") or f"block:{r['block']}"
            if r["price"]["ok"] or key in seen:
                continue
            seen.add(key)
            fam = pm.config()["function_family"].get(r["block"], "")
            href = "/pricing/estimate?" + (f"name={r['part']}" if r.get("part") else f"family={fam}" if fam else "")
            out.append({"part": r.get("part") or "", "label": r["label"], "block": r["block"],
                        "why": r["price"]["why"], "href": href.rstrip("?"), "layer": r["layer"]})  # fmt: skip
    return out


def summary(session: Session) -> dict:
    """Everything the TAM page, the case and the Price estimate page show."""
    cfg = config()
    veh = cfg["vehicles"]
    sys_rows = systems(session)
    sysmap = {s["id"]: s for s in sys_rows}
    mx = mix()
    layers = {k: {"label": LAYERS[k], **layer_market(sysmap, k, mx, veh)} for k in LAYERS}
    for v in layers.values():
        ok = v["ok"]
        v["band"] = band(v["low"], v["high"]) if ok else NED
        v["per_vehicle_text"] = band(v["per_vehicle"]["low"], v["per_vehicle"]["high"]) if ok else NED
        v["y_text"] = band(v["y_low"], v["y_high"]) if ok else NED
        v["cagr_text"] = (f"{v['cagr_min']:.1f}–{v['cagr_max']:.1f} % a year" if ok and v["cagr_max"] is not None
                          else NED)  # fmt: skip
    oc = cfg.get("owner_check") or {}
    years = cfg["target_year"] - cfg["base_year"]
    check = {"analog": oc.get("analog"), "digital": oc.get("digital_2030"), "source": oc.get("source"),
             "low": veh["low"] * oc.get("analog", 0), "high": veh["high"] * oc.get("digital_2030", 0),
             "cagr_max": _cagr(oc.get("analog", 0), oc.get("digital_2030", 0), years)}  # fmt: skip
    return {"systems": sys_rows, "mix": mx, "layers": layers, "needed": needed(sys_rows), "vehicles": veh,
            "check": check, "base_year": cfg["base_year"], "target_year": cfg["target_year"],
            "volume": cfg.get("volume"), "mandates": cfg.get("mandates") or [], "ned": NED,
            "assumption": f"vehicles flat at {veh['low'] / 1e6:.0f}–{veh['high'] / 1e6:.0f} M a year (owner)",
            }  # fmt: skip


def money(v: float | None) -> str:
    if v is None:
        return NED
    return f"${v / 1e9:,.2f} B" if v >= 1e9 else f"${v / 1e6:,.0f} M" if v >= 1e6 else f"${v:,.2f}"


def band(lo: float | None, hi: float | None) -> str:
    if lo is None or hi is None:
        return NED
    if hi >= 1e9 and lo >= 1e8:
        return f"${lo / 1e9:,.2f}–{hi / 1e9:,.2f} B"
    if hi >= 1e6:
        return f"${lo / 1e6:,.0f}–{hi / 1e6:,.0f} M"
    return f"${lo:,.2f}–{hi:,.2f}"


def inbox_lines(session: Session) -> list[str]:
    """The daily inbox section: prices the owner must enter before the radio market figures can be computed."""
    s = summary(session)
    lines = ["\n## Prices needed for market estimates\n",
             "Ask the owner to enter these on Price estimate (public distributor or list prices, or a low / in band / "
             "high call; never internal or customer prices). Until then the radio market at current BOM content is "
             "Not Enough Data.\n"]  # fmt: skip
    lines += [f"- {n['part'] or n['label'] + ' (no part chosen)'} · {n['label']} · {n['why']} · {n['href']}"
              for n in s["needed"]] or ["None."]  # fmt: skip
    return lines
