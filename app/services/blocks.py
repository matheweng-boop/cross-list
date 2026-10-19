"""Block-diagram generator: system functions, templates, and the Skyworks parts in Cross List that fill them.

data/blocks/functions.yaml maps each function to a source (a Cross List family, a broadcast role, an external
customer part, or nothing yet = opportunity); data/blocks/templates.yaml holds starting diagrams.
"""

import re
import time
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT
from app.models import Manufacturer, ManufacturerRole, Part
from app.services import broadcast

BLOCKS_DIR = PROJECT_ROOT / "data" / "blocks"


def _yaml(name: str):
    path: Path = BLOCKS_DIR / name
    return yaml.safe_load(path.read_text()) if path.exists() else None


@lru_cache
def catalogue() -> dict:
    return _yaml("functions.yaml") or {"categories": {}, "functions": {}}


@lru_cache
def templates() -> list[dict]:
    return _yaml("templates.yaml") or []


@lru_cache
def background_templates() -> list[dict]:
    """Diagrams that do not fit the Skyworks / Qorvo portfolio: not shown in the library, used only for occurrence
    and attach statistics on the Business opportunity pages."""
    return _yaml("background_templates.yaml") or []


@lru_cache
def question_help() -> dict[str, str]:
    """One or two sentences per design-question id: what the decision implies."""
    return _yaml("question_help.yaml") or {}


# vendor / source in a template name ("(TI)", "(NXP)", "(Microchip AN5324)", "(TI reference)") is kept in the data
# (sources) but not shown
_SOURCE_PAREN = re.compile(
    r"\s*\((?:[^()]*\b(?:TI|NXP|MediaTek|Qualcomm|Microchip|Skyworks|Infineon|RF|TIDM|TIDA|AN\d+|reference|Airfast|Dimensity|Filogic|Genio|MT\d+|T930|FastConnect|Dragonwing|QTM\d*|QCC\d*|QCS\d*|WCN\d*|Snapdragon|SAF\w*|TEF\w*)\b[^()]*)\)",
    re.I,
)


_VENDOR_WORDS = re.compile(r"\s*/\s*Digital Airfast\b|\bAirfast\b\s*", re.I)


def display_name(t: dict) -> str:
    name = _VENDOR_WORDS.sub(" ", _SOURCE_PAREN.sub("", t.get("name") or ""))
    return re.sub(r"\s{2,}", " ", name).strip()


# hand-shortened titles where the split by punctuation does not read well
_T = (
    ("Automotive telematics control unit (TCU) / V2X module", "Telematics control unit / V2X", ""),
    ("Automotive infotainment head unit with radio tuner (AM/FM/HD/DAB)", "Infotainment head unit",
     "radio tuner AM / FM / HD / DAB"),
    ("Automotive phone-as-a-key (PaaK) module with BLE satellite modules", "Phone-as-a-key", "BLE satellite modules"),
    ("IoT edge-AI board with companion PMIC, DCXO and Wi-Fi/BT combo", "IoT edge-AI board",
     "companion PMIC, DCXO, Wi-Fi / BT combo"),
    ("IoT Bluetooth LE SoC reference design and IoT processor Wi-Fi companion", "IoT Bluetooth LE and Wi-Fi",
     "BLE SoC reference design, processor Wi-Fi companion"),
    ("HEV/EV HV-to-LV DC/DC converter (phase-shifted full bridge, HV battery to 12 V)", "HEV/EV DC/DC converter",
     "HV battery to 12 V, phase-shifted full bridge"),
    ("Energy storage system battery (multimodule, daisy chain) - rack BMS", "Energy storage battery",
     "rack BMS, multimodule daisy chain"),
    ("Server / telecom AC/DC power supply unit (54 V output, with 12 V standby)", "Server / telecom PSU",
     "54 V output, 12 V standby"),
    ("Automotive telematics & infotainment RF", "Telematics & infotainment RF", ""),
)  # fmt: skip
TITLE_OVERRIDE = {name: (title, sub) for name, title, sub in _T}
_COMBO = re.compile(r"^Wi-Fi 6/6E \+ Bluetooth")


def title_parts(t: dict) -> tuple[str, str]:
    """Short title and subtitle: 'HEV/EV on-board charger (two-stage PFC + isolated DC/DC)' ->
    ('HEV/EV on-board charger', 'two-stage PFC + isolated DC/DC'); the first '(', ' - ' or ', ' splits."""
    name = display_name(t)
    if name in TITLE_OVERRIDE:
        return TITLE_OVERRIDE[name]
    if _COMBO.match(name):
        return "Wi-Fi 6/6E + Bluetooth combo", "client / IoT / automotive module, + 802.15.4"
    m = re.match(r"^(.*?)\s*\((.*)\)\s*(?:-\s*(.*))?$", name)
    if m:
        return m.group(1).strip(), " · ".join(x.strip() for x in (m.group(2), m.group(3)) if x)
    for sep in (" - ", ", "):
        if sep in name:
            a, b = name.split(sep, 1)
            return a.strip(), b.strip()
    return name, ""


def template_functions(t: dict) -> list[str]:
    out = []
    for g in t.get("groups") or []:
        for b in g.get("blocks") or []:
            out.append(b["fn"] if isinstance(b, dict) else str(b).split()[0])
    return list(dict.fromkeys(out))


_SOURCE_VENDOR = re.compile(r"\b(TI|NXP|Qualcomm|MediaTek|Skyworks|Microchip|Infineon)\b")
# Applications that several reference architectures describe: a title containing one of these keys puts the
# architecture in a "possible variant" group. Groups are flags for review; architectures are never merged.
VARIANT_KEYS = (
    "traction inverter", "on-board charger", "adas domain controller", "telematics", "v2x", "infotainment", "radar",
    "car radio", "connected radio", "smart car access", "phone-as-a-key", "battery", "bms", "ev charging", "wallbox",
    "dc fast charg", "smart meter", "electricity meter", "plc", "servo", "bldc", "motor drive", "smartwatch",
    "earbuds", "smart speaker", "patient monitor", "pulse oximeter", "glucose", "wi-fi access point", "router",
    "gateway", "small cell", "massive mimo", "radio unit", "fixed-wireless", "fwa", "smartphone", "tracker",
    "ip camera", "security camera", "video doorbell", "thermostat", "smart home", "robot", "drone", "laptop",
    "notebook", "tablet", "xr", "glasses", "headset", "zone control", "zonal", "body control", "power steering",
    "eps", "lighting", "headlamp", "headlight", "usb-c", "power bank", "gate driver", "isolated bias", "ups",
    "solar", "server", "psu", "power supply", "optical", "ethernet switch", "refrigerator", "washer", "cooktop",
)  # fmt: skip


def source_of(t: dict) -> str:
    """Who published the reference architecture (from the name or the note), or Cross List when drawn here."""
    m = _SOURCE_VENDOR.search(f"{t.get('name', '')} {t.get('note', '')}")
    return m.group(1) if m else "Cross List"


def variant_key(t: dict) -> str | None:
    name = re.sub(r"\([^()]*\)", "", t.get("name", "")).lower()
    return next((k for k in VARIANT_KEYS if re.search(r"(?<![a-z])" + re.escape(k), name)), None)


@lru_cache
def variant_groups() -> dict[str, list[int]]:
    """Possible variant groups among the library architectures (two or more sharing a key)."""
    groups: dict[str, list[int]] = {}
    for i, t in enumerate(templates()):
        k = variant_key(t)
        if k:
            groups.setdefault(k, []).append(i)
    return {k: v for k, v in groups.items() if len(v) > 1}


def template_cards(session: Session) -> list[tuple[str, list[dict]]]:
    """Applications by category for the generator page: display name, block count and the Skyworks / Qorvo
    categories involved (have = parts in Cross List, else opportunity)."""
    cat, n = catalogue(), counts(session)
    out: dict[str, list] = {}
    for i, t in enumerate(templates()):
        chips: dict[str, bool] = {}
        for fn in template_functions(t):
            f = cat["functions"].get(fn) or {}
            if n.get(fn) is None:
                continue  # customer / external part
            label = cat["categories"].get(f.get("category"), f.get("category"))
            chips[label] = chips.get(label, False) or bool(n[fn])
        blocks_n = sum(len(g.get("blocks") or []) for g in t.get("groups") or [])
        title, sub = title_parts(t)
        from app.services.opportunity import market_of

        key = variant_key(t)
        peers = [display_name(templates()[j]) for j in variant_groups().get(key, []) if j != i]
        card = {"i": i, "name": title, "sub": sub, "blocks": blocks_n, "questions": len(t.get("questions") or []),
                "chips": sorted(chips.items(), key=lambda c: (not c[1], c[0])), "source": source_of(t),
                "market": market_of(t.get("name", ""), t.get("category") or "Other"), "variant": key if peers else None,
                "peers": peers}  # fmt: skip
        out.setdefault(t.get("category") or "Other", []).append(card)
    return list(out.items())


def function_uses() -> dict[str, list[dict]]:
    """Which applications use each function (for the coverage page)."""
    uses: dict[str, list] = {}
    for i, t in enumerate(templates()):
        for fn in template_functions(t):
            uses.setdefault(fn, []).append({"i": i, "name": display_name(t), "category": t.get("category") or "Other"})
    return uses


def template_groups() -> list[tuple[str, list[tuple[int, dict]]]]:
    """Templates by category, in file order: [(category, [(index, template)])]."""
    out: dict[str, list] = {}
    for i, t in enumerate(templates()):
        out.setdefault(t.get("category") or "Other", []).append((i, t))
    return list(out.items())


# Catalogue parts (data/catalog/<manufacturer>_parts.yaml, collected from the public product pages): every
# Skyworks and Qorvo part with its category, package, a few key specs and lifecycle, mapped to a function. They
# carry no Cross List parameters except the automotive grade, so an answered requirement other than automotive
# leaves them out (unknown is not assumed). Parts already in Cross List with full parameters win over the
# catalogue entry; tuners and demods come from the broadcast data.
CATALOG_DIR = BLOCKS_DIR.parent / "catalog"
QORVO_FALLBACK = "research/qorvo_parts.yaml"  # the first 82 verified Qorvo parts, until the full catalogue exists
FUNCTION_ALIAS = {
    "rf_pa": "power_amplifier", "rf_filter": "filter_saw_baw", "buck": "wide_vin_buck", "rf_vga": "rf_gain_block",
    "catv_amplifier": "rf_gain_block", "rf_beamformer": "beamformer_ic", "rf_vco": "rf_synthesizer",
    "rf_power_divider": "rf_passive", "rf_duplexer": "diplexer", "uwb_transceiver": "uwb_soc",
    "rf_tunable_capacitor": "antenna_tuner", "rf_power_transistor": "power_amplifier", "rf_equalizer": "rf_passive",
    "rf_modulator": "rf_mixer",
}  # fmt: skip
_RISK = re.compile(r"obsolete|last time buy|nrnd|not recommended|discontinued|no new designs", re.I)
_SPEC_PREF = re.compile(r"config|channel|frequency|isolation|output current|gain|noise figure|insertion|input voltage|"
                        r"interface|rating|power|converters|regulators", re.I)  # fmt: skip


def _norm_mpn(mpn: str) -> str:
    """SI8641BD-B-IS and SI8641BD-IS are one part (die revision letter dropped)."""
    return re.sub(r"-[A-Z]-", "-", (mpn or "").upper())


def _catalog_files() -> list[Path]:
    files = sorted(CATALOG_DIR.glob("*_parts.yaml")) if CATALOG_DIR.exists() else []
    if not any(f.name.startswith("qorvo") for f in files) and (BLOCKS_DIR / QORVO_FALLBACK).exists():
        files.append(BLOCKS_DIR / QORVO_FALLBACK)
    return files


_Loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)  # libyaml when available: the catalogues are several MB


@lru_cache
def _catalog_docs() -> tuple[tuple[Path, dict], ...]:
    """Each catalogue file parsed once per process."""
    return tuple((path, yaml.load(path.read_text(), Loader=_Loader) or {}) for path in _catalog_files())


@lru_cache
def catalog_parts() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for path, data in _catalog_docs():
        for p in data.get("parts") or []:
            fn = FUNCTION_ALIAS.get(p.get("function"), p.get("function"))
            if not fn:
                continue
            mfr = p.get("manufacturer") or ("Qorvo" if "qorvo" in path.name else "Skyworks")
            specs = p.get("key_specs") or {}
            text = " ".join([p.get("summary") or p.get("description") or "", *map(str, specs.values())])
            auto = p.get("automotive")
            if auto is None and "AEC-Q" in text:
                auto = True
            pref = [k for k in specs if _SPEC_PREF.search(k)][:3] or list(specs)[:2]
            bits = [p.get("package") or "", *[f"{k} {specs[k]}" for k in pref], "automotive" if auto else ""]
            desc = p.get("summary") or p.get("description") or ""
            status = str(p.get("status") or "")
            out.setdefault(fn, []).append(
                {
                    "mpn": p["mpn"],
                    "manufacturer": mfr,
                    "url": p.get("product_url") or p.get("source") or "",
                    # three states: automotive (stated), not_automotive (stated no), None (not stated)
                    "values": {"qualification": "automotive" if auto else "not_automotive" if auto is False else None},
                    "detail": " · ".join(
                        b for b in [*bits, status if status and status not in ("Active", "Standard") else ""] if b
                    ),
                    "description": desc[:240],
                    "full": False,
                    "preview": "preview" in status.lower(),
                    "risk": bool(_RISK.search(status)),
                }  # fmt: skip
            )
    return out


@lru_cache
def catalog_rows() -> list[dict]:
    """Every catalogue part as a browse row (Parts page): manufacturer, top category, sub-category, part number,
    description, package, lifecycle, product page."""
    rows = []
    for path, data in _catalog_docs():
        for p in data.get("parts") or []:
            mfr = p.get("manufacturer") or ("Qorvo" if "qorvo" in path.name else "Skyworks")
            cat = [c.strip() for c in str(p.get("category") or "Other").split(">")]
            desc = p.get("description") or p.get("summary") or ""
            url = p.get("product_url") or p.get("source") or ""
            rows.append(
                {
                    "manufacturer": mfr,
                    "category": cat[0],
                    "sub": " > ".join(cat[1:]),
                    "mpn": p["mpn"],
                    "description": desc,
                    "package": p.get("package") or "",
                    "status": str(p.get("status") or "unknown"),
                    "url": url,
                    "automotive": p.get("automotive"),  # True / False as stated by the source, None = not stated
                    "datasheet": p.get("datasheet_url") or "",
                }  # fmt: skip
            )
    return rows


def qorvo_parts() -> dict[str, list[dict]]:
    """Qorvo catalogue parts by function (kept for callers that only want Qorvo)."""
    return {k: [c for c in v if c["manufacturer"] == "Qorvo"] for k, v in catalog_parts().items()}


def _reference_parts(session: Session, family: str):
    return (
        select(Part)
        .join(Part.manufacturer)
        .where(Part.family == family, Manufacturer.role == ManufacturerRole.reference)
        .order_by(Part.mpn)
    )


# parameters shown next to a part in the picker, with their unit
SHOWN = {"channel_config": "", "isolation_rating_kvrms": " kVrms", "configuration": "", "freq_range_ghz": " GHz",
         "peak_source_a": " A", "qualification": ""}  # fmt: skip


def _series(mpn: str) -> str:
    """Base part number without grade / package letters (SI8234AB-AM -> SI8234), so the best options are
    different parts, not variants of one."""
    m = re.match(r"[A-Z]+\d+(?:[A-Z]\d{2,})?", re.split(r"[-.]", mpn.upper())[0])
    return m.group(0) if m else mpn.upper()


_CAND_CACHE: dict[tuple, list[dict] | None] = {}
_VERSION: dict[str, tuple[float, tuple]] = {}


def _data_version(session: Session) -> tuple:
    """Changes when parts are added or removed; checked at most every 30 s per database."""
    url = str(session.get_bind().url)
    now = time.monotonic()
    hit = _VERSION.get(url)
    if hit and now - hit[0] < 30:
        return hit[1]
    n, top = session.execute(select(func.count(Part.id), func.max(Part.id))).one()
    v = (url, n, top)
    _VERSION[url] = (now, v)
    return v


def _candidates(session: Session, key: str) -> list[dict] | None:
    """Candidates per function, cached until the parts change: the business pages ask for all ~160 functions on
    every request, which used to repeat the same queries each time."""
    k = (key, _data_version(session))
    if k not in _CAND_CACHE:
        if len(_CAND_CACHE) > 2000:
            _CAND_CACHE.clear()
        _CAND_CACHE[k] = _candidates_uncached(session, key)
    return _CAND_CACHE[k]


def _candidates_uncached(session: Session, key: str) -> list[dict] | None:
    """Every part that can fill a function, with the values the requirements look at; None for customer parts."""
    f = catalogue()["functions"].get(key) or {}
    src = f.get("source")
    if src == "external":
        return None
    out = []
    if isinstance(src, dict) and "family" in src:
        for p in session.scalars(_reference_parts(session, src["family"])).unique():
            values = {pv.key: pv.value for pv in p.params}
            bits = [p.package.code]
            for k, unit in SHOWN.items():
                v = values.get(k)
                if v not in (None, "", []):
                    bits.append(f"{'-'.join(map(str, v)) if isinstance(v, list) else v}{unit}")
            out.append({"mpn": p.mpn, "manufacturer": p.manufacturer.name, "url": f"/parts/{p.id}",
                        "detail": " · ".join(bits), "values": values, "description": p.description or "",
                        "full": True, "preview": p.lifecycle_status.value == "preview",
                        "risk": p.lifecycle_status.value not in ("active", "preview")})  # fmt: skip
    elif isinstance(src, dict) and "broadcast" in src:
        for d in broadcast.catalog():
            if d["role"] != src["broadcast"]:
                continue
            feats = d.get("features") or [*d["analog"], *d["digital_iq"], *d["digital_decode"]]
            size = f"{d['tuners']}T" if d.get("tuners") else f"{d['channels']} ch" if d.get("channels") else ""
            aec = d.get("aec_q100")
            values = {
                "qualification": "automotive" if aec is True else "not_automotive" if aec is False else None,
                "tuners": d.get("tuners"),
                "channels": d.get("channels"),
                "feature": feats,
                "decode": d["digital_decode"],
            }
            detail = " · ".join(x for x in (size, " ".join(feats)) if x)
            desc = {"tuner": "AM/FM / digital radio tuner", "coprocessor": "digital radio demodulator",
                    "receiver": "single-chip radio receiver"}.get(d["role"], "")  # fmt: skip
            out.append(dict(mpn=d["mpn"], manufacturer="Skyworks", url="/broadcast", values=values, risk=False,
                            detail=detail, description=desc, full=True, preview=False))  # fmt: skip
    have = {_norm_mpn(c["mpn"]) for c in out}
    broadcast_fn = isinstance(src, dict) and "broadcast" in src
    for c in catalog_parts().get(key, []):
        if broadcast_fn and c["manufacturer"] == "Skyworks":
            continue
        if _norm_mpn(c["mpn"]) not in have:
            have.add(_norm_mpn(c["mpn"]))
            out.append(c)
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def meets(values: dict, r: dict, answer) -> bool:
    """Does a part meet one requirement? A part without the value does not (unknown is not assumed)."""
    v = values.get(r["param"])
    if v in (None, "", []):
        return False
    op = r.get("op", "eq")
    if op == "contains":
        items = v if isinstance(v, list) else [v]
        return any(str(answer).lower() in str(x).lower() for x in items)
    if op == "gte":
        a, b = _num(v[0] if isinstance(v, list) else v), _num(answer)
        return a is not None and b is not None and a >= b
    if isinstance(v, list):
        return str(answer) in map(str, v)
    a, b = _num(v), _num(answer)
    return a == b if a is not None and b is not None else str(v).lower() == str(answer).lower()


def _filter(cands: list[dict], key: str, answers: dict) -> list[dict]:
    reqs = {r["id"]: r for r in catalogue()["functions"].get(key, {}).get("requirements") or []}
    for rid, ans in (answers or {}).items():
        r = reqs.get(rid)
        if r is None or ans in (None, "", False):
            continue
        want = r.get("value", ans) if ans is True else ans
        cands = [c for c in cands if meets(c["values"], r, want)]
    return cands


def requirements(session: Session) -> dict[str, list[dict]]:
    """Requirement questions per function, with 'auto' choices resolved from the parts in Cross List."""
    out = {}
    for key, f in catalogue()["functions"].items():
        reqs = f.get("requirements") or []
        if not reqs:
            continue
        cands = None
        resolved = []
        for r in reqs:
            r = dict(r)
            if r.get("choices") == "auto":
                cands = cands if cands is not None else (_candidates(session, key) or [])
                vals = set()
                for c in cands:
                    v = c["values"].get(r["param"])
                    for x in v if isinstance(v, list) else [v]:
                        if x not in (None, ""):
                            vals.add(str(x))
                r["choices"] = sorted(vals, key=lambda x: (_num(x) is None, _num(x) or 0, x))
            resolved.append(r)
        out[key] = resolved
    return out


def counts(session: Session, answers: dict | None = None) -> dict[str, int | None]:
    """Parts per function that meet the answered requirements; None for customer parts."""
    answers = answers or {}
    out = {}
    for key in catalogue()["functions"]:
        cands = _candidates(session, key)
        out[key] = None if cands is None else len(_filter(cands, key, answers.get(key) or {}))
    return out


def _rank(c: dict, answers: dict) -> tuple:
    """Best first: active before NRND / obsolete, production before preview, full Cross List parameters before
    catalogue-only data, automotive first when automotive is asked for, then part number."""
    auto_wanted = bool((answers or {}).get("automotive"))
    is_auto = (c.get("values") or {}).get("qualification") == "automotive"
    return (c["risk"], bool(c.get("preview")), not c.get("full"), auto_wanted and not is_auto, c["mpn"])


def _why(c: dict, rank: int, key: str, answers: dict, n: int) -> str:
    """One line on why a part is listed first: rank, requirements met, lifecycle, grade, data depth."""
    reqs = {r["id"]: r for r in catalogue()["functions"].get(key, {}).get("requirements") or []}
    met = [
        reqs[k]["label"] + (f" {v}" if v not in (True, "true") else "")
        for k, v in (answers or {}).items()
        if k in reqs and v not in (None, "", False)
    ]
    bits = ["best match" if rank == 0 else "next best (a different device)"]
    if met:
        bits.append("meets " + ", ".join(met))
    if c["risk"]:
        bits.append("lifecycle risk (NRND / obsolete)")
    else:
        bits.append("preview, not yet in production" if c.get("preview") else "active")
    if (c.get("values") or {}).get("qualification") == "automotive":
        bits.append("AEC-Q100")
    bits.append("full Cross List parameters" if c.get("full") else "catalogue data only (package, key specs)")
    bits.append(f"{n} fit in total")
    return "; ".join(bits)


def parts_for(session: Session, key: str, q: str = "", answers: dict | None = None, top: int = 2) -> dict:
    """Matching parts per manufacturer: the best `top` distinct series first (active before NRND /
    obsolete), then all of them."""
    cands = _filter(_candidates(session, key) or [], key, answers or {})
    if q:
        qq = q.upper().replace("-", "")
        cands = [c for c in cands if qq in c["mpn"].upper().replace("-", "") or q.lower() in c["detail"].lower()]
    groups = {}
    for c in sorted(cands, key=lambda c: _rank(c, answers or {})):
        groups.setdefault(c["manufacturer"], []).append(c)
    result = []
    for mfr, items in groups.items():
        best, seen = [], set()
        for c in items:
            s = _series(c["mpn"])
            if s not in seen:
                seen.add(s)
                best.append(c)
            if len(best) == top:
                break

        def strip(c):
            v = c.get("values") or {}
            implies = {k: v[k] for k in ("qualification", "isolation_class", "feature", "decode") if v.get(k)}
            keep = {k: c[k] for k in ("mpn", "url", "detail", "risk")}
            return {**keep, "description": c.get("description", ""), "implies": implies}

        result.append(
            {
                "manufacturer": mfr,
                "best": [dict(strip(c), why=_why(c, i, key, answers or {}, len(items))) for i, c in enumerate(best)],
                "all": [strip(c) for c in items[:200]],
                "total": len(items),
            }
        )
    return {"total": len(cands), "manufacturers": result}
