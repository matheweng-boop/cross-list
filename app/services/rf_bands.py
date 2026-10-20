"""Radio frequency bands (data/engineering_rf_bands.yaml) and the Skyworks / Qorvo RF parts whose published frequency
range covers each band."""

import re
from collections import defaultdict
from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT
from app.services import blocks, broadcast, lifecycle, vocab
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
    """Our catalogue parts in RF functions and our broadcast tuners / receivers, with their stated frequency ranges
    (GHz)."""
    rf_fns = {k for k, f in blocks.catalogue()["functions"].items() if f.get("category") == "rf"}
    out = []
    for path, doc in blocks._catalog_docs():
        for p in doc.get("parts") or []:
            fns = [f for f in vocab.fills(p.get("function"), p.get("also") or []) if f in rf_fns]
            if not fns:
                continue
            ranges = frequency_ranges(p.get("key_specs") or {}, p.get("description") or "")
            if ranges:
                maker = p.get("manufacturer") or ("Qorvo" if "qorvo" in path.name else "Skyworks")
                out.append({"mpn": p["mpn"], "manufacturer": maker,
                            "function": fns[0], "ranges": ranges, "url": p.get("product_url") or "",
                            "description": (p.get("description") or "")[:150],
                            "risk": lifecycle.is_risk(p.get("status"))})  # fmt: skip
    return tuple(out + _broadcast_parts())


# broadcast bands of our tuners and receivers: (code, stated range in the data short, unit to GHz, default MHz range)
_BCAST = (
    ("FM", r"FM[^\n]*?\((\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*MHz", 1e-3, (76, 108)),
    ("AM", r"\bAM[^\n]*?\((\d+)\s*(?:-|to)\s*(\d+)\s*kHz", 1e-6, (520, 1710)),
    ("LW", r"\bLW[^\n]*?\((\d+)\s*(?:-|to)\s*(\d+)\s*kHz", 1e-6, (144, 288)),
    ("SW", r"\bSW[^\n]*?\((\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*MHz", 1e-3, (2.3, 30)),
    ("WB", None, 1e-3, (162.4, 162.55)),  # NOAA weather band; the data shorts name it without a range
    ("DAB", r"DAB[^\n]*?\((\d{3})\s*(?:-|to)\s*(\d{3})\s*MHz", 1e-3, (174, 240)),
)


def _broadcast_parts() -> list[dict]:
    """Our broadcast tuners and single-chip receivers (data/broadcast), with the bands their data shorts state.
    Coprocessors take I/Q, not RF, so they cover no band."""
    cat = {p["mpn"].upper(): p for path, doc in blocks._catalog_docs() for p in doc.get("parts") or []}
    docs = {x["doc"]: x for x in broadcast.documents()}
    out = []
    for d in broadcast.catalog():
        if d["role"] not in ("tuner", "receiver"):
            continue
        text = [str(f) for f in (docs.get(d["doc"]) or {}).get("features") or []]
        codes = {"DAB" if c == "DMB" else c for c in d["analog"] + d["digital_iq"] + d["digital_decode"]}
        ranges = []
        for code, pat, unit, default in _BCAST:
            if code not in codes:
                continue
            m = next((m for f in text if pat and (m := re.search(pat, f))), None)
            lo, hi = (float(m.group(1)), float(m.group(2))) if m else default
            ranges.append((lo * unit, hi * unit))
        if "DAB" in codes and any("1452" in f for f in [*text, str(d.get("note") or "")]):
            ranges.append((1.452, 1.492))  # L-band
        c = cat.get(d["mpn"].upper()) or cat.get(d["mpn"].split("-")[0].upper()) or {}
        if ranges:
            out.append({"mpn": d["mpn"], "manufacturer": "Skyworks",
                        "function": "am_fm_tuner" if d["role"] == "tuner" else "single_chip_radio",
                        "ranges": sorted(ranges), "url": c.get("product_url") or "",
                        "description": (c.get("description") or d.get("description") or "")[:150],
                        "risk": lifecycle.is_risk(c.get("status"))})  # fmt: skip
    return out


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
            shown.sort(key=lambda r: not any(_covers(r[0], r[1], a, b) for a, b in spans))  # the covering one first
            by_fn[p["function"]].append({**p, "width": width, "specific": width <= limit, "shown": shown[:3]})
    out = []
    for f, ps in by_fn.items():
        ps.sort(key=lambda p: (p["width"], p["mpn"]))
        out.append({"fn": f, "label": vocab.fn_label(f), "specific": [p for p in ps if p["specific"]],
                    "wide": [p for p in ps if not p["specific"]]})  # fmt: skip
    return sorted(out, key=lambda g: (-len(g["specific"]), -len(g["wide"]), g["label"]))


@lru_cache
def band_counts() -> dict[str, dict[str, int]]:
    """Per band: our active band-specific parts by line, and all covering parts (for the table view)."""
    out = {}
    for b in data()["bands"]:
        groups = parts_for(b["id"])
        spec = [p for g in groups for p in g["specific"]]
        out[b["id"]] = {
            "Skyworks": sum(p["manufacturer"] == "Skyworks" for p in spec),
            "Qorvo": sum(p["manufacturer"] == "Qorvo" for p in spec),
            "all": sum(len(g["specific"]) + len(g["wide"]) for g in groups),
        }
    return out
