"""Radio frequency bands (data/engineering_rf_bands.yaml) and the Skyworks / Qorvo RF parts whose published frequency
range covers each band."""

from collections import defaultdict
from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT
from app.services import blocks
from app.services.rf_coverage import frequency_ranges

FILE = PROJECT_ROOT / "data" / "engineering_rf_bands.yaml"

# what each group is and which front-end parts it calls for (shown above the parts of a band)
GROUP_NOTES = {
    "cellular_low": "Long range, building penetration. FDD bands need a duplexer per band; antennas are large, so "
    "antenna tuners matter. Parts: PA modules (PAMiD), LNAs / diversity modules, antenna switches and tuners, filters.",
    "cellular_mid": "The capacity layer of 4G and 5G, often carrier-aggregated. Parts: mid / high-band PA modules, "
    "diversity receive modules, multiplexers and BAW filters, antenna switches.",
    "cellular_c": "5G mid-band TDD: wide channels (100 MHz), massive MIMO in base stations. Parts: n77/n78/n79 PA "
    "modules with integrated LNA and switch (TDD), BAW filters; GaN or LDMOS PAs and LNAs in radios.",
    "cellular_mmw": "Short range, very wide channels, beam steering. Parts: beamformer ICs, mmWave PAs and LNAs "
    "(often in antenna modules), up / down-converters, LO synthesizers.",
    "gnss": "Receive-only signals about -130 dBm at the antenna: a low-noise LNA with pre- / post-filters that reject "
    "cellular and Wi-Fi blockers (B13 / B14 and 1.7 GHz are the usual threats). Dual-frequency (L1 + L5) for "
    "lane-level accuracy.",
    "wlan": "Licence-free bands shared by Wi-Fi, Bluetooth and IoT: coexistence filters and front-end modules (PA + "
    "LNA + switch) per band; sub-GHz IoT uses small PAs / LNAs and SAW filters.",
    "short": "Short-range links and sensing: UWB front ends (switch, LNA, filter), V2X front ends at 5.9 GHz, NFC "
    "and UHF RFID readers.",
    "broadcast": "Receive-only: tuners and their LNAs / filters; AM and FM need high linearity against strong "
    "stations.",
    "satcom": "Uplink and downlink are far apart: BUC (up-converter + PA) and LNB / LNA (receive) chains with "
    "multiplied LOs; GaN PAs at Ku / Ka.",
    "radar": "Pulsed or FMCW: high peak power (GaN), limiters to protect LNAs, phase shifters for electronic "
    "steering; automotive radar is single-chip at 76-81 GHz.",
    "ieee": "Letter bands name frequency ranges, not uses (IEEE Std 521); BizDev's RF coverage page uses them.",
}


@lru_cache
def data() -> dict:
    return yamlio.load(FILE.read_text()) or {"groups": {}, "bands": []}


def band(band_id: str) -> dict | None:
    return next((b for b in data()["bands"] if b["id"] == band_id), None)


@lru_cache
def rf_parts() -> tuple[dict, ...]:
    """Our catalogue parts in RF functions, with their stated frequency ranges (GHz)."""
    rf_fns = {k for k, f in blocks.catalogue()["functions"].items() if f.get("category") == "rf"}
    out = []
    for path, doc in blocks._catalog_docs():
        for p in doc.get("parts") or []:
            fns = [blocks.FUNCTION_ALIAS.get(x, x) for x in [p.get("function"), *(p.get("also") or [])] if x]
            fns = [f for f in dict.fromkeys(fns) if f in rf_fns]
            if not fns:
                continue
            ranges = frequency_ranges(p.get("key_specs") or {}, p.get("description") or "")
            if ranges:
                maker = p.get("manufacturer") or ("Qorvo" if "qorvo" in path.name else "Skyworks")
                out.append({"mpn": p["mpn"], "manufacturer": maker,
                            "function": fns[0], "ranges": ranges, "url": p.get("product_url") or "",
                            "description": (p.get("description") or "")[:150],
                            "risk": bool(blocks._RISK.search(str(p.get("status") or "")))})  # fmt: skip
    return tuple(out)


def _covers(lo: float, hi: float, a: float, b: float) -> bool:
    """A part range [lo, hi] serves a band range [a, b] (GHz) when it contains the band centre or half the band."""
    c = (a + b) / 2
    overlap = min(hi, b) - max(lo, a)
    return lo <= c <= hi or (b > a and overlap >= (b - a) / 2)


def competitor_rf_parts() -> tuple[dict, ...]:
    from app.services.rf_coverage import competitor_parts

    return tuple({**p, "function": p["functions"][0]} for p in competitor_parts() if p["ranges"])


def parts_for(band_id: str, competitors: bool = False) -> list[dict]:
    """Active parts covering a band, grouped by function. A part is band-specific when its stated range is at most
    four times the band's width (or under 300 MHz); functions with the most band-specific parts come first, and
    within a function the narrowest ranges first."""
    bd = band(band_id)
    if not bd:
        return []
    spans = [(r[0] / 1000, r[1] / 1000) for r in bd["ranges"]]
    limit = max(4 * max(b - a for a, b in spans), 0.3)
    by_fn: dict[str, list[dict]] = defaultdict(list)
    for p in competitor_rf_parts() if competitors else rf_parts():
        if p["risk"]:
            continue
        if any(_covers(lo, hi, a, b) for lo, hi in p["ranges"] for a, b in spans):
            width = max(hi - lo for lo, hi in p["ranges"])  # spot test frequencies do not make a part band-specific
            shown = [r for r in p["ranges"] if r[1] > r[0]] or p["ranges"][:1]  # ranges, not spot test frequencies
            by_fn[p["function"]].append({**p, "width": width, "specific": width <= limit, "shown": shown[:3]})
    cat = blocks.catalogue()["functions"]
    out = []
    for f, ps in by_fn.items():
        ps.sort(key=lambda p: (p["width"], p["mpn"]))
        out.append({"fn": f, "label": (cat.get(f) or {}).get("label", f), "specific": [p for p in ps if p["specific"]],
                    "wide": [p for p in ps if not p["specific"]]})  # fmt: skip
    return sorted(out, key=lambda g: (-len(g["specific"]), -len(g["wide"]), g["label"]))
