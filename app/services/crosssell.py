"""Cross-sell from a part number, optionally narrowed by a loosely described application ("dcdc", "broadcast").

The part gives the function (and, where the catalogue states them, the automotive grade and RF bands); the application
words choose which reference architectures count. Suggestions are the other functions in those architectures, ordered
by a visible score: how often they appear with the part, whether they sit in the same block or a connected one, and
how well the architectures fit the part's grade.
"""

import re
from difflib import SequenceMatcher, get_close_matches

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Part
from app.partnumbers import normalize_pn
from app.services import blocks
from app.services import opportunity as op
from app.services import rf_coverage as rf
from app.services.pipeline import fn_for_family

# words people type -> words architectures use; a concept matches when any of its words is in the architecture
SYNONYMS = {
    "dcdc": ["dc/dc", "dc-dc", "dcdc", "buck", "boost", "converter", "power supply", "point-of-load", "regulator"],
    "acdc": ["ac/dc", "ac-dc", "acdc", "pfc", "flyback", "llc", "adapter", "power supply", "psu"],
    "power": ["power supply", "psu", "dc/dc", "ac/dc", "converter", "pfc", "ups"],
    "broadcast": ["broadcast", "radio", "tuner", "fm", "am/fm", "dab", "hd radio", "head unit", "infotainment"],
    "radio": ["radio", "tuner", "transceiver", "lmr", "sdr"],
    "ev": ["ev", "hev", "electric vehicle", "traction", "on-board charger", "onboard charger", "obc", "xev"],
    "charger": ["charger", "charging", "wallbox", "evse", "obc"],
    "battery": ["battery", "bms", "cell", "energy storage", "ess"],
    "bms": ["bms", "battery management", "battery"],
    "motor": ["motor", "drive", "servo", "bldc", "stepper", "inverter", "compressor"],
    "inverter": ["inverter", "traction", "solar", "drive"],
    "solar": ["solar", "pv", "photovoltaic", "mppt", "optimizer", "rapid shutdown"],
    "5g": ["5g", "nr", "cellular", "base station", "radio unit", "small cell", "massive mimo", "o-ran", "fwa"],
    "cellular": ["cellular", "lte", "5g", "modem", "smartphone", "base station"],
    "wifi": ["wi-fi", "wifi", "wlan", "access point", "router", "gateway"],
    "bluetooth": ["bluetooth", "ble", "802.15.4"],
    "gnss": ["gnss", "gps", "navigation", "tracker"],
    "satellite": ["satellite", "satcom", "ntn", "terminal"],
    "radar": ["radar", "lidar"],
    "automotive": ["automotive", "vehicle", "car", "ev", "hev", "adas", "telematics", "body"],
    "industrial": ["industrial", "plc", "factory", "automation", "din-rail", "field"],
    "medical": ["medical", "patient", "pump", "ecg", "ultrasound", "cpap", "x-ray", "ct"],
    "iot": ["iot", "smart meter", "sensor", "asset tracker", "wearable"],
    "datacenter": ["server", "data center", "data-center", "datacenter", "rack", "enterprise"],
    "telecom": ["telecom", "-48 v", "base station", "backhaul", "router"],
    "audio": ["audio", "speaker", "amplifier", "soundbar"],
    "isolation": ["isolated", "isolation", "gate driver"],
}
_ALIASES = {"dc/dc": "dcdc", "dc-dc": "dcdc", "ac/dc": "acdc", "ac-dc": "acdc", "wi-fi": "wifi", "wlan": "wifi",
            "gps": "gnss", "hev": "ev", "xev": "ev", "bldc": "motor", "pv": "solar", "lte": "cellular",
            "ble": "bluetooth", "satcom": "satellite", "car": "automotive", "server": "datacenter"}  # fmt: skip


def resolve_part(session: Session, q: str) -> dict | None:
    """A part number (exact first, then the closest one that starts with it) -> maker, ours or not, functions,
    automotive grade and RF bands where stated."""
    key = normalize_pn(q)
    if len(key) < 3:
        return None
    hits = []
    for fn, ps in blocks.catalog_parts().items():  # our catalogue (Skyworks, Qorvo)
        for p in ps:
            k = normalize_pn(p["mpn"])
            if k == key or k.startswith(key):
                hits.append((k != key, len(k), p["mpn"], p["manufacturer"], True, fn, p["values"].get("qualification")))
    for p in session.scalars(select(Part).where(func.upper(Part.mpn).like(f"{q.strip().upper()}%")).limit(20)):
        fn = fn_for_family(p.family)
        if fn:
            hits.append((normalize_pn(p.mpn) != key, len(p.mpn), p.mpn, p.manufacturer.name, p.is_reference, fn, None))
    for p in rf.competitor_parts():
        k = normalize_pn(p["mpn"])
        if k == key or k.startswith(key):
            hits.append((k != key, len(k), p["mpn"], p["manufacturer"], False, p["functions"][0], None))
    if not hits:
        return None
    hits.sort()
    best = hits[0]
    same = [h for h in hits if h[2] == best[2]]
    fns = list(dict.fromkeys(h[5] for h in same))
    from app.services import rf_bands

    ranges = next((p["ranges"] for p in rf_bands.rf_parts() if p["mpn"] == best[2]), None) or next(
        (p["ranges"] for p in rf.competitor_parts() if p["mpn"] == best[2] and p["ranges"]), []
    )
    ranges = [r for r in ranges if r[1] > r[0]] or ranges
    grade = next((h[6] for h in same if h[6]), None)
    others = sorted({h[2] for h in hits if h[2] != best[2]})[:8]
    return {"mpn": best[2], "manufacturer": best[3], "ours": best[4], "fns": fns, "automotive": grade == "automotive",
            "grade": grade, "ranges": ranges, "exact": not best[0], "others": others}  # fmt: skip


def _concepts(q: str) -> list[tuple[str, list[str]]]:
    """Each typed word -> (word, words to look for)."""
    out, known = [], [*SYNONYMS, *_ALIASES]
    for w in re.findall(r"[a-z0-9][a-z0-9/.\-]*", q.lower()):
        c = _ALIASES.get(w, w)
        if c not in SYNONYMS and len(w) >= 4:  # a misspelt known word: "broadcst" -> broadcast
            close = get_close_matches(w, known, n=1, cutoff=0.8)
            c = _ALIASES.get(close[0], close[0]) if close else c
        out.append((w, SYNONYMS.get(c, [w])))
    return out


def _app_text(t: dict, a: op.Application) -> str:
    return " ".join([a.name, a.category, a.market, *(g.get("label", "") for g in t.get("groups") or [])]).lower()


def match_applications(apps: list[op.Application], q: str) -> list[tuple[op.Application, float, list[str]]]:
    """Architectures matching loosely described words: synonyms, substrings, and close spellings ("broadcst").
    Score = share of the typed words matched (name hits count double against block-label hits)."""
    concepts = _concepts(q)
    if not concepts:
        return [(a, 1.0, []) for a in apps]
    tpls = [*blocks.templates(), *blocks.background_templates()]
    out = []
    for a in apps:
        name, text = a.name.lower(), _app_text(tpls[a.i], a)
        words = set(re.findall(r"[a-z0-9][a-z0-9/.\-]*", text))
        score, hit = 0.0, []
        for w, syn in concepts:
            if any(re.search(rf"(?<![a-z0-9]){re.escape(s)}(?![a-z0-9])", name) for s in syn):
                score, _ = score + 1.0, hit.append(w)
            elif any(re.search(rf"(?<![a-z0-9]){re.escape(s)}(?![a-z0-9])", text) for s in syn):
                score, _ = score + 0.5, hit.append(w)
            elif len(w) >= 5 and any(SequenceMatcher(None, w, x).ratio() >= 0.85 for x in words):
                score, _ = score + 0.75, hit.append(w)
        if hit:
            out.append((a, score / len(concepts), hit))
    return sorted(out, key=lambda r: -r[1])


def suggest(session: Session, part: dict, app_q: str = "", co: str = "combined") -> dict:
    """Functions to offer next to the part in the (matching) architectures that contain its function, ordered by
    score = together share x (1 + 0.6 same-block share + 0.3 connected share) x grade fit."""
    _, _, mine = op.company(co)
    apps = op.with_status(op.applications(), op.makers(session), mine)
    anchor = part["fns"][0]  # the part's own function; the others it also fills only when no design has that one
    with_part = [a for a in apps if any(p.fn == anchor for p in a.positions)]
    if not with_part:
        with_part = [a for a in apps if any(p.fn in part["fns"] for p in a.positions)]
    matched = match_applications(with_part, app_q) if app_q.strip() else [(a, 1.0, []) for a in with_part]
    used = [a for a, _, _ in matched]
    rows: dict[str, dict] = {}
    for a in used:
        for p in a.positions:
            if p.fn in part["fns"] or p.status not in op.IN_SCOPE:
                continue
            rows.setdefault(p.fn, {"fn": p.fn, "label": p.label, "status": p.status, "apps": set()})["apps"].add(a.i)
    n = len(used) or 1
    auto_share = sum(a.market == "Automotive" for a in used) / n
    out = []
    for e in rows.values():
        sub = [a for a in used if a.i in e["apps"]]
        why = op.pair_reasons(sub, anchor, e["fn"])
        share = len(sub) / n
        same, linked = why["same"] / max(why["n"], 1), why["linked"] / max(why["n"], 1)
        fit = 1.0
        if part["automotive"]:
            fit = 0.7 + 0.3 * (sum(a.market == "Automotive" for a in sub) / len(sub))
        score = share * (1 + 0.6 * same + 0.3 * linked) * fit
        out.append({**e, "apps": len(sub), "share": share, "same": same, "linked": linked, "fit": fit,
                    "score": score, "why": why})  # fmt: skip
    out.sort(key=lambda e: (-e["score"], e["label"]))
    for e in out:
        e["offer"] = offer(session, e["fn"], part, mine) if e["status"] == "supported" else []
    ours = [e for e in out if e["status"] == "supported"]
    new = [e for e in out if e["status"] != "supported"]
    return {"apps": matched, "n": len(used), "n_with_part": len(with_part), "auto_share": auto_share,
            "ours": ours, "new": new}  # fmt: skip


def offer(session: Session, fn: str, part: dict, mine: frozenset, limit: int = 4) -> list[dict]:
    """Our best parts for a function, preferring automotive-grade ones for an automotive part and, for RF functions,
    parts that share a band with it."""
    cands = []
    for m in blocks.parts_for(session, fn, top=8)["manufacturers"]:
        if m["manufacturer"] in mine:
            for p in m["best"]:
                auto = (p.get("implies") or {}).get("qualification") == "automotive"
                cands.append({"mpn": p["mpn"], "url": p["url"], "manufacturer": m["manufacturer"], "auto": auto})
    if part["ranges"]:  # RF: our parts of the function whose stated range overlaps the part's, narrowest first
        from app.services import rf_bands

        known = {p["mpn"]: [r for r in p["ranges"] if r[1] > r[0]] or p["ranges"] for p in rf_bands.rf_parts()}
        rows = []
        for c in blocks.catalog_parts().get(fn, []):
            rs = known.get(c["mpn"], [])
            if c["manufacturer"] in mine and any(lo <= b and hi >= a for lo, hi in rs for a, b in part["ranges"]):
                auto = c["values"].get("qualification") == "automotive"
                width = max(hi - lo for lo, hi in rs)
                rows.append(
                    (width, {"mpn": c["mpn"], "url": c["url"], "manufacturer": c["manufacturer"], "auto": auto})
                )
        if rows:
            cands = [c for _, c in sorted(rows, key=lambda r: r[0])]
    if part["automotive"]:
        cands.sort(key=lambda c: not c["auto"])
    return cands[:limit]
