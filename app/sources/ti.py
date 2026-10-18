"""Texas Instruments source: ti.com selection-tool data and datasheets.

fetch()  saves the digital-isolator table, per-device orderable part numbers
         and datasheets under var/raw/ti and var/datasheets/ti. Each file is
         saved as soon as it is fetched, and existing files are skipped, so an
         interrupted fetch resumes where it stopped.
"""

import hashlib
import json
import re
from pathlib import Path

from app.config import PROJECT_ROOT
from app.sources.http import get

BASE_URL = "https://www.ti.com"
RAW_DIR = PROJECT_ROOT / "var" / "raw" / "ti"
DATASHEET_DIR = PROJECT_ROOT / "var" / "datasheets" / "ti"
FAMILIES = {"digital_isolator": 3121}


def gpn_table_url(family_id: int) -> str:
    return (
        f"{BASE_URL}/selectionmodel/api/gpn/result-list?destinationId={family_id}&destinationType=GPT&mode=parametric"
    )


def opn_url(gpn: str) -> str:
    return f"{BASE_URL}/selectionmodel/api/opn/result-list?gpn={gpn}"


def datasheet_url(gpn: str) -> str:
    return f"{BASE_URL}/lit/ds/symlink/{gpn.lower()}.pdf"


def fetch(family: str = "digital_isolator", log=print, datasheets: bool = True) -> None:
    (RAW_DIR / "opn").mkdir(parents=True, exist_ok=True)
    DATASHEET_DIR.mkdir(parents=True, exist_ok=True)
    table_path = RAW_DIR / f"gpn_{FAMILIES[family]}.json"
    if not table_path.exists():
        table_path.write_bytes(get(gpn_table_url(FAMILIES[family])))
    gpns = [r["genericPartNumber"] for r in json.loads(table_path.read_text())["results"]]
    log(f"{len(gpns)} devices")
    for i, gpn in enumerate(gpns, 1):
        path = RAW_DIR / "opn" / f"{gpn}.json"
        if not path.exists():
            path.write_bytes(get(opn_url(gpn)))
        if datasheets:
            pdf = DATASHEET_DIR / f"{gpn.lower()}.pdf"
            if not pdf.exists():
                try:
                    body = get(datasheet_url(gpn), pause=1.5)
                except RuntimeError:
                    log(f"no datasheet for {gpn}")
                    continue
                if body[:4] == b"%PDF":
                    pdf.write_bytes(body)
                else:
                    log(f"{gpn}: datasheet link did not return a PDF")
        if i % 20 == 0:
            log(f"{i}/{len(gpns)}")


if __name__ == "__main__":
    fetch()


# ------------------------------------------------------------------ build

TI_STATUS = {
    "ACTIVE": "active",
    "PREVIEW": "preview",
    "NRND": "nrnd",
    "LIFEBUY": "last_time_buy",
    "OBSOLETE": "obsolete",
}
CERT_NAMES = {"DIN": "VDE", "VDE": "VDE", "UL": "UL", "CSA": "CSA", "CQC": "CQC", "TUV": "TUV"}


def _params(entry: dict) -> dict[str, list[str]]:
    return {p["name"]: p["value"].get("base", []) for p in entry.get("paramList", [])}


def _one(values: list[str] | None, scale: float = 1.0) -> float | None:
    if not values or len(values) != 1:
        return None
    try:
        return round(float(values[0]) * scale, 6)
    except ValueError:
        return None


def default_output_from_opn(opn: str, gpn: str) -> str | None:
    """TI convention: an "F" right after the device number (in the device name, as in
    ISO7641FC, or in the orderable number, as in ISO6440FDWR) means default-low output."""
    if gpn.startswith("ISOW"):
        return None  # the convention does not hold for the integrated-power ISOW parts
    if re.match(r"^ISO\d{3,4}[A-Z]*F", gpn):
        return "low"
    rest = opn[len(gpn) :] if opn.startswith(gpn) else None
    if rest is None:
        base = gpn.split("-")[0]
        rest = opn[len(base) :] if opn.startswith(base) else None
    if rest is None:
        return None
    return "low" if rest.startswith("F") else "high"


def _fwd_rev(text: str | None) -> tuple[int, int] | None:
    m = re.match(r"(\d+)\s*forward\s*/\s*(\d+)\s*reverse", text or "", re.I)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _pinout_fwd_rev(pins: list[str], pin_count: int) -> tuple[int, int]:
    half = pin_count // 2
    fwd = sum(1 for i, p in enumerate(pins, 1) if i <= half and p.startswith("IN") and p[2:].isalpha())
    rev = sum(1 for i, p in enumerate(pins, 1) if i <= half and p.startswith("OUT") and p[3:].isalpha())
    return fwd, rev


def _enable_text(pins: list[str]) -> str:
    ens = sorted({p for p in pins if re.fullmatch(r"EN\d?", p)})
    if ens:
        return f"{'+'.join(ens)} active-high"
    if any(p in ("DISABLE", "CTRL") for p in pins):
        return "disable/control pin"
    return "none"


class _Putter:
    """Store a value and where it came from, skipping missing values."""

    def __init__(self, params: dict, sources: dict):
        self.params, self.sources = params, sources

    def __call__(self, key: str, value, source: str | None) -> None:
        if value is not None:
            self.params[key], self.sources[key] = value, source


class DatasheetInfo:
    """Everything read from one TI datasheet (cached per file)."""

    def __init__(self, pdf: Path):
        from app.parsing.datasheet import detect_revision, extract_pages
        from app.parsing.ti_datasheet import (
            certification_agencies,
            certified_classes,
            parse_insulation,
            parse_pin_table,
        )

        txt = pdf.with_suffix(".txt")
        if txt.exists():
            self.pages = txt.read_text().split("\n\f\n")
        else:
            self.pages = extract_pages(pdf)
            txt.write_text("\n\f\n".join(self.pages))
        self.name = pdf.name
        self.revision, self.revision_date, self.first_issue = detect_revision(self.pages)
        self.insulation = parse_insulation(pdf, self.pages)
        self.classes = certified_classes(pdf, self.pages)
        self.pins = parse_pin_table(pdf, self.pages)
        self.agencies = certification_agencies(self.pages)

    def pinout(self, gpn: str, package: str, pin_count: int, fwd_rev: tuple[int, int] | None):
        """(pinout, page) for a device in a package, checked against its channel split."""
        from app.parsing.ti_datasheet import canonical_pinout

        if not self.pins:
            return None, None
        t = self.pins
        candidates = list(range(len(t.columns) or 1))
        if t.by_package:
            candidates = [i for i, c in enumerate(t.columns) if c == package] or candidates
        else:
            base = gpn.split("-")[0]
            named = [i for i, c in enumerate(t.columns) if c and (c == gpn or c.split("-")[0] in (base, base + "X"))]
            candidates = named or candidates
        matches = []
        for i in candidates:
            pins = canonical_pinout(t.rows, i)
            if pins and len(pins) == pin_count and (fwd_rev is None or _pinout_fwd_rev(pins, pin_count) == fwd_rev):
                matches.append(pins)
        unique = {tuple(m) for m in matches}
        return (list(unique.pop()), t.page) if len(unique) == 1 else (None, None)


def build(family: str = "digital_isolator", log=print) -> dict:
    table = json.loads((RAW_DIR / f"gpn_{FAMILIES[family]}.json").read_text())
    sheets: dict[str, DatasheetInfo] = {}
    packages: dict[str, dict] = {}
    parts, skipped = [], []
    for gentry in table["results"]:
        gpn = gentry["genericPartNumber"]
        gparams = _params(gentry)
        opn_file = RAW_DIR / "opn" / f"{gpn}.json"
        pdf = DATASHEET_DIR / f"{gpn.lower()}.pdf"
        if not opn_file.exists():
            skipped.append(f"{gpn}: no orderable part list")
            continue
        sheet = None
        if pdf.exists():
            sheet = sheets.setdefault(pdf.name, DatasheetInfo(pdf))
        seen: set[tuple] = set()
        for o in sorted(json.loads(opn_file.read_text()), key=lambda o: len(o["orderablePartNumber"])):
            opn = o["orderablePartNumber"]
            if opn.startswith("X"):
                continue  # experimental pre-production samples
            p = _params(o)
            pkg_name = (p.get("TI package name") or [""])[0]
            pin_count = int(_one(p.get("Pin count")) or 0)
            default = (p.get("Default output") or [None])[0] if len(p.get("Default output") or []) == 1 else None
            default_src = "TI product table"
            if default is None or "," in str(default):
                default, default_src = default_output_from_opn(opn, gpn), "inferred from TI part-number convention"
            key = (pkg_name, default)
            if key in seen:
                continue  # tape-and-reel / green-package duplicates
            seen.add(key)
            code = f"{(p.get('Industry package type') or ['?'])[0]}-{pin_count} ({pkg_name})"
            packages.setdefault(
                code,
                {
                    "code": code,
                    "name": f"TI {pkg_name} {pin_count}-pin",
                    "pin_count": pin_count,
                    "pitch_mm": _one(p.get("Pitch")),
                    "body_length_mm": _one(p.get("Body size length")),
                    "body_width_mm": _one(p.get("Body size width")),
                    "span_mm": _one(p.get("Package size width")),
                    "height_mm": _one(p.get("Maximum package height")),
                },
            )
            fwd_rev = _fwd_rev(
                (p.get("Forward/reverse channels") or gparams.get("Forward/reverse channels") or [""])[0]
            )
            params: dict = {}
            src: dict = {}
            put = _Putter(params, src)
            put(
                "integrated_power",
                {"No": "none", "Yes": "isolated dc-dc"}.get((p.get("Integrated isolated power") or [""])[0]),
                "TI product table",
            )
            put("default_output", default.lower() if default else None, default_src)
            put("data_rate_mbps", _one(p.get("Data ratemax"), 1e-6), "TI product table")
            put("prop_delay_ns", _one(p.get("Propagation delay timemax"), 1e9), "TI product table")
            put("pwd_ns", _one(p.get("Pulse-width distortionmax"), 1e9), "TI product table")
            put("skew_ns", _one(p.get("Channel-to-channel output skewmax"), 1e9), "TI product table")
            put("cmti_kv_us", _one(p.get("CMTImin"), 1e-3), "TI product table")
            put(
                "idd_per_channel_ma",
                _one(p.get("Current consumption per channel (1 Mbps)typ"), 1e3),
                "TI product table",
            )
            vmin, vmax = _one(p.get("Supply voltagemin")), _one(p.get("Supply voltagemax"))
            put("vdd_range_v", [vmin, vmax] if vmin is not None and vmax is not None else None, "TI product table")
            tmin, tmax = _one(p.get("Operating temperaturemin")), _one(p.get("Operating temperaturemax"))
            put("temp_range_c", [tmin, tmax] if tmin is not None and tmax is not None else None, "TI product table")
            if sheet and sheet.agencies:
                put("certifications", sheet.agencies, f"{sheet.name} safety certifications")
            else:
                certs = sorted({CERT_NAMES.get(c, c) for c in (p.get("Certifications") or [])})
                put("certifications", certs or None, "TI product table")
            put(
                "qualification",
                "automotive" if gentry.get("rating", {}).get("automotive") else "industrial",
                "TI product table",
            )

            # Insulation per package from the datasheet; TI's single values otherwise.
            ins = sheet.insulation if sheet else None
            col = None
            if ins:
                col = pkg_name if pkg_name in ins.packages else ("*" if ins.packages == ["*"] else None)
            where = f"{sheet.name} p.{ins.page}" if ins else None
            if col:
                put("creepage_mm", ins.creepage_mm.get(col), where)
                put("viorm_vpk", ins.viorm_vpk.get(col), where)
                viso = ins.viso_vrms.get(col)
                put("isolation_rating_kvrms", viso / 1000 if viso else None, where)
            if "creepage_mm" not in params:
                put("creepage_mm", _one(p.get("Creepagemin"), 1e3), "TI product table")
            if "isolation_rating_kvrms" not in params:
                put(
                    "isolation_rating_kvrms",
                    _one(p.get("Withstand isolation voltage (VISO)"), 1e-3),
                    "TI product table",
                )
            cls = p.get("Isolation rating") or []
            if sheet and pkg_name in sheet.classes:
                put("isolation_class", sheet.classes[pkg_name], f"{sheet.name} safety certifications")
            elif len(cls) == 1:
                put("isolation_class", cls[0].lower(), "TI product table")
            elif (
                set(c.lower() for c in cls) == {"basic", "reinforced"}
                and ins
                and col
                and len(set(ins.viso_vrms.values())) == 2
            ):
                put(
                    "isolation_class",
                    "reinforced" if ins.viso_vrms.get(col) == max(ins.viso_vrms.values()) else "basic",
                    f"inferred: TI lists Basic and Reinforced; {sheet.name} gives this package the "
                    + ("higher" if ins.viso_vrms.get(col) == max(ins.viso_vrms.values()) else "lower")
                    + " withstand voltage",
                )

            pinout, pin_page = sheet.pinout(gpn, pkg_name, pin_count, fwd_rev) if sheet else (None, None)
            notes = []
            if pinout:
                fr = _pinout_fwd_rev(pinout, pin_count)
                params["channel_config"] = f"{fr[0]}/{fr[1]}"
                src["channel_config"] = f"{sheet.name} p.{pin_page}"
                params["enable_pins"], src["enable_pins"] = _enable_text(pinout), f"{sheet.name} p.{pin_page}"
            else:
                notes.append("Pinout not read from the datasheet; fit cannot be checked.")
                if fwd_rev:
                    params["channel_config"], src["channel_config"] = f"{fwd_rev[0]}/{fwd_rev[1]}", "TI product table"

            title = gentry.get("localization", {}).get("en-US", {}).get("title", "")
            parts.append(
                {
                    "mpn": opn,
                    "manufacturer": "TI",
                    "family": family,
                    "description": f"{gpn}: {title}"[:300],
                    "package": code,
                    "pinout": pinout or [],
                    "datasheet": sheet.name if sheet else None,
                    "datasheet_url": datasheet_url(gpn),
                    "product_url": f"{BASE_URL}/product/{gpn}",
                    "notes": " ".join(notes) or None,
                    "lifecycle": {
                        "status": TI_STATUS.get(o["productStatus"]["name"], "unknown"),
                        "release_date": sheet.first_issue if sheet else None,
                        "revision": sheet.revision if sheet else None,
                        "revision_date": sheet.revision_date if sheet else None,
                        "source": f"TI product status: {o['productStatus']['name']}; "
                        "release date = first datasheet issue",
                    },
                    "params": params,
                    "param_sources": {**src, **({"pinout": f"{sheet.name} p.{pin_page}"} if pinout else {})},
                }
            )
    datasheets = []
    for name, s in sorted(sheets.items()):
        path = DATASHEET_DIR / name
        datasheets.append(
            {
                "file": name,
                "url": f"{BASE_URL}/lit/ds/symlink/{name}",
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "revision": s.revision,
                "revision_date": s.revision_date,
            }
        )
    return {
        "source": "ti.com selection tool and datasheets",
        "manufacturers": [{"name": "TI", "role": "competitor", "website": BASE_URL}],
        "packages": list(packages.values()),
        "datasheets": datasheets,
        "parts": parts,
        "skipped": skipped,
    }
