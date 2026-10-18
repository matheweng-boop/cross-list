"""Skyworks RF switches: product table and lifecycle from skyworksinc.com, facts from the datasheets.

fetch()  saves the switch table (all categories), datasheets and lifecycle statuses (resumable)
build()  combines them with data/sources/skyworks_switches.yaml, which holds what was read
         from each datasheet (package, pinout, limits). The datasheet wins over the web table;
         conflicts are listed in the part's notes.
"""

import hashlib
import json
import re
import time
import urllib.parse
from pathlib import Path

import yaml

from app.config import PROJECT_ROOT
from app.sources.http import get
from app.sources.skyworks import LIFECYCLE_MAP, fetch_lifecycle

SITE = "https://www.skyworksinc.com"
FACTS_FILE = PROJECT_ROOT / "data" / "sources" / "skyworks_switches.yaml"
RAW_DIR = PROJECT_ROOT / "var" / "raw" / "skyworks_switches"
DATASHEET_DIR = PROJECT_ROOT / "var" / "datasheets" / "skyworks_switches"
MECH_OUT = PROJECT_ROOT / "data" / "mechanical_skyworks_switches.yaml"
CATEGORIES = (
    "SPST RF Switches", "SPDT (SP2T) RF Switches", "SP3T RF Switches", "SP4T RF Switches",
    "High Throw Count Switches (Band Distribution, Linear Tx/Rx, Rx Diversity, General Purpose Signal Routing)",
    "DPDT Antenna Diversity Switches", "High Power SPDT and SPST PIN Diode Switches", "Antenna Swap Switches",
    "Ultra Linear (SVLTE) Switches", "Carrier Aggregation Switches", "Antenna Tuning Switches",
    "Antenna Switch Modules", "High Throw Count (>4T) Switches / Antenna Switch Modules (ASM)",
    "Differential Receive Filter Switches",
)  # fmt: skip
MANUFACTURER = {"name": "Skyworks", "role": "reference", "website": SITE}


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", str(html))).strip()


def _mpn(row: dict) -> str:
    m = re.search(r'link-title"[^>]*>\s*([^<\s]+)', row["Product"])
    return m.group(1).strip() if m else ""


def fetch_category(category: str) -> list[dict]:
    payload = {
        "SearchText": None, "MarketList": None, "SolutionList": None, "ApplicationList": None,
        "CategoryList": [category], "FamilyList": ["Switches"], "DocumentTypeList": None,
        "IsParameterSearch": False, "FrequecyMinGhz": 0, "FrequecyMaxGhz": 0,
    }  # fmt: skip
    body = get(SITE + "/api/feature/search/getspecification/", json.dumps(payload).encode(), "application/json")
    data = json.loads(body)
    return json.loads(data["Products"]) if data.get("Products") else []


def fetch(log=print) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DATASHEET_DIR.mkdir(parents=True, exist_ok=True)
    table: dict[str, dict] = {}
    for category in CATEGORIES:
        for row in fetch_category(category):
            table.setdefault(_mpn(row), {"category": category, **row})
    (RAW_DIR / "table.json").write_text(json.dumps(table))
    log(f"switch table: {len(table)} parts")
    urls = {}
    for mpn, row in table.items():
        m = re.search(r'href="(/-/media/[^"]+\.pdf)"', row["Product"])
        urls[mpn] = SITE + m.group(1) if m else None
        path = DATASHEET_DIR / Path(urllib.parse.urlparse(urls[mpn] or "").path).name
        if urls[mpn] and not path.exists():
            path.write_bytes(get(urls[mpn].replace(" ", "%20")))
    (RAW_DIR / "datasheet_urls.json").write_text(json.dumps(urls, indent=1))
    state_path = RAW_DIR / "lifecycle.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {"done": [], "statuses": {}}
    for mpn in table:
        prefix = re.split(r"[-_]", mpn)[0]
        if prefix not in state["done"]:
            for opn, status in fetch_lifecycle(prefix):
                state["statuses"][opn.upper()] = status
            state["done"].append(prefix)
            state_path.write_text(json.dumps(state))
            time.sleep(0.5)


def _num(text) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", str(text or ""))
    return float(m.group(0)) if m else None


def _nums(text) -> list[float]:
    return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", str(text or ""))]


def table_params(row: dict) -> dict:
    """What the web table says, in rules units; typical values, worst case of a range."""
    desc = _text(row.get("Description (Absorptive/ Reflective)", ""))
    out = {}
    if m := re.match(r"(SP\d+T|SPDT|SPST|DPDT|[0-9]P[0-9]T)", desc.upper()):
        out["configuration"] = m.group(1).replace("SP2T", "SPDT")
    if "(A)" in desc:
        out["termination"] = "absorptive"
    elif "(R)" in desc:
        out["termination"] = "reflective"
    lo, hi = _num(row.get("Frequency (GHz) Min")), _num(row.get("Frequency (GHz) Max"))
    if lo is not None and hi is not None:
        out["freq_range_ghz"] = [lo, hi]
    if il := _nums(_text(row.get("Typ IL (dB)", ""))):
        out["insertion_loss_db"] = max(il)
    if iso := _nums(_text(row.get("Typ Isol (dB)", ""))):
        out["isolation_db"] = min(iso)
    if ip3 := _nums(_text(row.get("Typ IIP3 (dBm)", ""))):
        out["iip3_dbm"] = min(ip3)
    if p1 := _nums(_text(row.get("Typ IP<sub>1 dB</sub> (dBm)", ""))):
        out["p1db_dbm"] = min(p1)
    logic = _text(row.get("Control Logic", "")).upper()
    if logic in ("GPIO", "MIPI"):
        out["control_interface"] = logic
    return out


def _package_code(pkg: dict) -> str:
    dims = f"{pkg['body_length_mm']:g}x{pkg['body_width_mm']:g}"
    return f"{pkg['type']}-{pkg['pins']} {dims}"


def _package(pkg: dict) -> dict:
    ep = pkg.get("exposed_pad_mm")
    return {
        "code": _package_code(pkg),
        "name": pkg.get("name") or _package_code(pkg),
        "pin_count": pkg["pins"],
        "pitch_mm": pkg["pitch_mm"],
        "body_length_mm": pkg["body_length_mm"],
        "body_width_mm": pkg["body_width_mm"],
        "span_mm": pkg.get("span_mm") or pkg["body_width_mm"],
        "height_mm": pkg.get("height_mm"),
        "exposed_pad": bool(ep),
    }


class _Putter:
    """Collects parameter values: datasheet first, web table as fallback, conflicts noted."""

    def __init__(self, web: dict, sheet_ref: str | None):
        self.web, self.sheet_ref = web, sheet_ref
        self.params, self.sources, self.conflicts = {}, {}, []

    def __call__(self, key: str, value, web_key: str | None = None) -> None:
        w = self.web.get(web_key) if web_key else None
        if value is None:
            if w is not None:
                self.params[key], self.sources[key] = w, "Skyworks product table"
            return
        self.params[key], self.sources[key] = value, self.sheet_ref
        if w is not None and str(w).lower() != str(value).lower() and not _close(w, value):
            self.conflicts.append(f"{key}: datasheet {value}, web table {w}")


def mechanical(facts: dict) -> dict:
    """Terminal sizes and land patterns per package code, in data/mechanical.yaml's format."""
    out = {}
    for mpn, f in sorted((facts.get("parts") or {}).items()):
        pkg, sheet = f.get("package") or {}, f.get("datasheet")
        if not (pkg.get("terminal_width_mm") and pkg.get("terminal_length_mm")) or not pkg.get("pins"):
            continue
        if not all(pkg.get(k) for k in ("type", "pitch_mm", "body_length_mm", "body_width_mm")):
            continue
        entry = {
            "lead_width_mm": list(pkg["terminal_width_mm"]),
            "lead_length_mm": list(pkg["terminal_length_mm"]),
            "sides": pkg.get("sides", 2),
            "source": f"{sheet} p{pkg.get('page')} ({mpn})",
        }
        if lp := f.get("land_pattern"):
            spacing = lp.get("row_spacing_mm") or lp.get("row_spacing_x_mm")
            if lp.get("pad_length_mm") and lp.get("pad_width_mm") and spacing:
                pattern = {
                    "name": "Recommended",
                    "pad_length_mm": lp["pad_length_mm"],
                    "pad_width_mm": lp["pad_width_mm"],
                    "row_spacing_mm": spacing,
                    "source": f"{sheet} p{lp.get('page')}",
                }
                if lp.get("row_spacing_y_mm"):
                    pattern["row_spacing_y_mm"] = lp["row_spacing_y_mm"]
                entry["land_patterns"] = [pattern]
        out.setdefault(_package_code(pkg), entry)
    return {"Skyworks": out}


def _status(mpn: str, statuses: dict) -> str:
    text = statuses.get(mpn.upper())
    if text is None:  # web table lists some parts by base number only
        found = {v for k, v in statuses.items() if k.startswith(mpn.upper() + "-")}
        text = found.pop() if len(found) == 1 else None
    return text


def build(log=print) -> dict:
    facts = yaml.safe_load(FACTS_FILE.read_text())
    table = json.loads((RAW_DIR / "table.json").read_text())
    urls = json.loads((RAW_DIR / "datasheet_urls.json").read_text())
    statuses = json.loads((RAW_DIR / "lifecycle.json").read_text())["statuses"]
    packages: dict[str, dict] = {}
    datasheets: dict[str, dict] = {}
    parts, skipped = [], []
    for mpn, row in table.items():
        f = (facts.get("parts") or {}).get(mpn)
        if not f:
            skipped.append(f"{mpn}: no datasheet facts")
            continue
        pkg = f.get("package") or {}
        if not all(pkg.get(k) for k in ("type", "pins", "pitch_mm", "body_length_mm", "body_width_mm")):
            skipped.append(f"{mpn}: package not read from the datasheet")
            continue
        package = _package(pkg)
        if packages.setdefault(package["code"], package) != package:
            log(f"{mpn}: package {package['code']} differs from an earlier part with the same code")
        sheet = f.get("datasheet")
        if sheet and sheet not in datasheets and (DATASHEET_DIR / sheet).exists():
            datasheets[sheet] = {
                "file": sheet,
                "url": urls.get(mpn),
                "sha256": hashlib.sha256((DATASHEET_DIR / sheet).read_bytes()).hexdigest(),
                "revision": f.get("revision"),
                "revision_date": f.get("revision_date"),
            }
        web = table_params(row)
        sheet_ref = f"{sheet} (datasheet)" if sheet else None
        put = _Putter(web, sheet_ref)
        put("configuration", f.get("configuration"), web_key="configuration")
        put("termination", f.get("termination"), web_key="termination")
        put("control_interface", f.get("control_interface"), web_key="control_interface")
        fr = [f.get("freq_min_ghz"), f.get("freq_max_ghz")]
        put("freq_range_ghz", fr if None not in fr else None, web_key="freq_range_ghz")
        put("max_input_power_dbm", f.get("max_input_power_dbm"))
        put("qualification", "automotive" if f.get("aec_q100") else "industrial")
        params, sources, conflicts = put.params, put.sources, put.conflicts
        put("insertion_loss_db", f.get("insertion_loss_db"), web_key="insertion_loss_db")
        put("isolation_db", f.get("isolation_db"), web_key="isolation_db")
        put("p1db_dbm", f.get("p1db_dbm"), web_key="p1db_dbm")
        put("iip3_dbm", f.get("iip3_dbm"), web_key="iip3_dbm")
        put("vdd_range_v", f.get("vdd_v"))
        put("control_high_v", f.get("control_high_v"))
        put("temp_range_c", f.get("temp_c"))
        put("switching_time_ns", f.get("switching_time_ns"))
        if f.get("esd_hbm_v"):
            put("esd_hbm_kv", round(f["esd_hbm_v"] / 1000, 2))
        if f.get("pinout_page"):
            sources["pinout"] = f"{sheet} p.{f['pinout_page']}"
        status_text = _status(mpn, statuses)
        notes = "; ".join(
            x for x in [f.get("notes") or "", *(f"Conflict, datasheet used: {c}" for c in conflicts)] if x
        )
        parts.append(
            {
                "mpn": mpn,
                "manufacturer": "Skyworks",
                "family": "rf_switch",
                "description": f"{params.get('configuration', '')} RF switch, "
                f"{fr[0] if fr[0] is not None else '?'}–{fr[1] if fr[1] is not None else '?'} GHz",
                "package": package["code"],
                "pinout": f.get("pinout") or [],
                "datasheet": sheet if sheet in datasheets else None,
                "datasheet_url": urls.get(mpn),
                "product_url": f"{SITE}/en/Products/switches/{mpn}",
                "notes": notes or None,
                "lifecycle": {
                    "status": LIFECYCLE_MAP.get((status_text or "").strip().lower(), "unknown"),
                    "revision": f.get("revision"),
                    "revision_date": f.get("revision_date"),
                    "source": f"Skyworks lifecycle lookup: {status_text or 'not listed'}",
                },
                "params": params,
                "param_sources": sources,
            }
        )
    header = "# Generated by app/sources/skyworks_switches.py from data/sources/skyworks_switches.yaml\n"
    MECH_OUT.write_text(header + yaml.safe_dump(mechanical(facts), sort_keys=False, width=200))
    return {
        "source": "skyworksinc.com switch table, lifecycle lookup and datasheets",
        "manufacturers": [MANUFACTURER],
        "packages": list(packages.values()),
        "datasheets": list(datasheets.values()),
        "parts": parts,
        "skipped": skipped,
    }


def _close(a, b) -> bool:
    try:
        if isinstance(a, list) and isinstance(b, list):
            return all(abs(float(x) - float(y)) <= 0.05 * max(abs(float(x)), 1) for x, y in zip(a, b, strict=True))
        return abs(float(a) - float(b)) <= 0.05 * max(abs(float(a)), 1)
    except (TypeError, ValueError):
        return False
