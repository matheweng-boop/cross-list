"""Novosense source: novosns.com product tables and datasheets.

fetch()  saves the category table and datasheets (resumable)
build()  combines them with data/sources/novosense.yaml (package outlines)
"""

import hashlib
import json
import re
from datetime import date
from pathlib import Path

import yaml

from app.config import PROJECT_ROOT
from app.parsing.pins import canonicalize, fwd_rev, parse_pin_diagrams
from app.sources.http import get

API = "https://wwwapi.novosns.com"
SITE = "https://www.novosns.com"
FACTS_FILE = PROJECT_ROOT / "data" / "sources" / "novosense.yaml"
RAW_DIR = PROJECT_ROOT / "var" / "raw" / "novosense"
DATASHEET_DIR = PROJECT_ROOT / "var" / "datasheets" / "novosense"
STATUS = {"active": "active", "preview": "preview", "nrnd": "nrnd", "not recommended": "nrnd", "eol": "obsolete"}
AGENCIES = ("UL", "VDE", "CSA", "CQC", "TUV")


def _table_path(family: str) -> Path:
    return RAW_DIR / f"findlist_{family}.json"


def fetch(family: str = "digital_isolator", log=print) -> None:
    facts = yaml.safe_load(FACTS_FILE.read_text())
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DATASHEET_DIR.mkdir(parents=True, exist_ok=True)
    code = facts["categories"][family]
    _table_path(family).write_bytes(get(f"{API}/nvs/official/findList?menuCode={code}"))
    for url, name in _datasheets(family).items():
        path = DATASHEET_DIR / name
        if not path.exists():
            path.write_bytes(get(SITE + url, pause=1.5))
            log(f"datasheet {name}")


def _rows(family: str) -> list[dict]:
    return json.loads(_table_path(family).read_text())["data"]["productList"]


def _datasheet_of(row: dict) -> tuple[str, str] | None:
    for key in ("shujushoucewanzhengbanlianjieen", "shujushoucewanzhengbanlianjiecn"):
        if row.get(key):
            files = json.loads(row[key])
            en = [f for f in files if "_EN" in f["fileName"].upper()] or files
            return en[0]["fileUrl"], en[0]["fileName"]
    return None


def _datasheets(family: str) -> dict[str, str]:
    return dict(filter(None, (_datasheet_of(r) for r in _rows(family))))


# ------------------------------------------------------------------ datasheets

REV_TITLE_RE = re.compile(r"Datasheet \(EN\)\s*(?:Rev\.?\s*)?(\d+\.\d+)")
HISTORY_RE = re.compile(r"^(?:Rev\.?\s*)?(\d+\.\d+)\s+.*?(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})", re.M)


class Datasheet:
    def __init__(self, pdf: Path):
        from app.parsing.datasheet import extract_pages

        self.path, self.name = pdf, pdf.name
        txt = pdf.with_suffix(".txt")
        self.ok = pdf.read_bytes()[:4] == b"%PDF"
        self.pages: list[str] = []
        if self.ok:
            if txt.exists():
                self.pages = txt.read_text().split("\n\f\n")
            else:
                self.pages = extract_pages(pdf)
                txt.write_text("\n\f\n".join(self.pages))
        text = "\n".join(self.pages)
        m = REV_TITLE_RE.search(text)
        self.revision = m.group(1) if m else None
        history = [
            (r, date(int(y), int(mo), int(d))) for r, y, mo, d in HISTORY_RE.findall(self._section("Revision History"))
        ]
        self.first_issue = min((d for _, d in history), default=None)
        self.revision_date = max((d for _, d in history), default=None)
        self.sha256 = hashlib.sha256(pdf.read_bytes()).hexdigest()
        self._pinouts: dict[str, list[str]] | None = None

    def _section(self, title: str) -> str:
        for text in self.pages:
            for m in re.finditer(re.escape(title), text, re.I):
                if not re.match(r"\s*\.{3,}", text[m.end() : m.end() + 8]):
                    return text[m.start() :]
        return ""

    def page_of(self, pattern: str) -> int | None:
        return next((i for i, t in enumerate(self.pages, 1) if re.search(pattern, t, re.I)), None)

    # -- values from the electrical tables (first occurrence = 5 V section)
    def first_number(self, pattern: str) -> tuple[float, int] | None:
        rx = re.compile(pattern, re.I)
        for i, text in enumerate(self.pages, 1):
            m = rx.search(text)
            if m:
                return float(m.group(1)), i
        return None

    def agencies(self) -> list[str]:
        sec = self._section("Regulatory Information")[:1500].upper()
        return sorted(a for a in AGENCIES if re.search(rf"\b{a}\b", sec))

    def pinouts(self) -> dict[str, list[str]]:
        """{device: normalised pinout} from the pin drawings, else the pin table."""
        if self._pinouts is None:
            self._pinouts = {}
            section = next((t for t in self.pages[1:6] if "Pin Configuration" in t), "")
            for device, pin_map in parse_pin_diagrams(section).items():
                pins = canonicalize(pin_map)
                if pins:
                    self._pinouts[device] = pins
            if not self._pinouts:
                self._pinouts = self._pin_table()
        return self._pinouts

    def _pin_table(self) -> dict[str, list[str]]:
        import pdfplumber

        out: dict[str, list[str]] = {}
        idx = next((i for i, t in enumerate(self.pages[:8]) if re.search(r"Pin (Configuration|Description)", t)), None)
        if idx is None:
            return out
        with pdfplumber.open(self.path) as pdf:
            for page in pdf.pages[idx : idx + 2]:
                for table in page.extract_tables():
                    header = [re.sub(r"\s+", "", str(c or "")).upper() for c in table[0]]
                    if "SYMBOL" not in header:
                        continue
                    sym = header.index("SYMBOL")
                    devices = {c: h for c, h in enumerate(header) if re.fullmatch(r"NSI\d{4}[A-Z0-9]*", h)}
                    if not devices:
                        devices = {c: "*" for c in range(sym) if any(str(r[c] or "").strip().isdigit() for r in table)}
                    maps: dict[str, dict[int, str]] = {d: {} for d in devices.values()}
                    for row in table[1:]:
                        name = re.sub(r"\s+", "", str(row[sym] or ""))
                        for c, dev in devices.items():
                            for pin in re.findall(r"\d+", str(row[c] or "")):
                                if name:
                                    maps[dev][int(pin)] = name
                    for dev, pm in maps.items():
                        pins = canonicalize(pm)
                        if pins:
                            out[dev] = pins
                if out:
                    return out
        return out


# ------------------------------------------------------------------ build


def _range(text: str | None) -> list[float] | None:
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", (text or "").replace("~", " ").replace("to", " "))]
    return [min(nums), max(nums)] if len(nums) >= 2 else None


def _num(text) -> float | None:
    m = re.search(r"\d+(?:\.\d+)?", str(text or ""))
    return float(m.group()) if m else None


def build(family: str = "digital_isolator", log=print) -> dict:
    facts = yaml.safe_load(FACTS_FILE.read_text())
    alias = {a.upper().replace(" ", ""): p["code"] for p in facts["packages"] for a in p["aliases"]}
    sheets: dict[str, Datasheet] = {}
    parts, skipped = [], []
    for row in _rows(family):
        opn = row["id"]
        pkg = alias.get(str(row.get("package", "")).upper().replace(" ", ""))
        ds = _datasheet_of(row)
        sheet = None
        if ds and (DATASHEET_DIR / ds[1]).exists():
            sheet = sheets.setdefault(ds[1], Datasheet(DATASHEET_DIR / ds[1]))
        if pkg is None:
            skipped.append(f"{opn}: package {row.get('package')} has no outline in data/sources/novosense.yaml")
            continue
        split = re.match(r"(\d+)\s*/\s*(\d+)", str(row.get("parameter3", "")))
        expect = (int(split.group(1)), int(split.group(2))) if split else None
        params: dict = {}
        src: dict = {}

        def put(key, value, source, params=params, src=src):
            if value is not None:
                params[key], src[key] = value, source

        table = "Novosense product table"
        cls = str(row.get("parameter7", "")).strip().lower()
        put("isolation_class", cls if cls in ("basic", "reinforced") else None, table)
        put("isolation_rating_kvrms", _num(row.get("parameter8")), table)
        put("default_output", str(row.get("parameter4", "")).strip().lower() or None, table)
        put("data_rate_mbps", _num(row.get("parameter5")), table)
        put("cmti_kv_us", _num(row.get("parameter6")), table)
        put("vdd_range_v", _range(row.get("parameter1")), table)
        put("temp_range_c", _range(str(row.get("parameter10", "")).replace("-", " -").replace("~", " ")), table)
        put("qualification", "automotive" if "auto" in str(row.get("rating", "")).lower() else "industrial", table)
        put("integrated_power", "none", table)
        put("surge_10kv", (_num(row.get("parameter9")) or 0) >= 10, table)
        if expect:
            put("channel_config", f"{expect[0]}/{expect[1]}", table)

        pinout, notes = [], []
        if sheet and sheet.ok:
            where = sheet.name
            for key, pattern in (
                ("prop_delay_ns", r"Propagation Delay\s+t ?P[LH]{2}\s+(?:[\d.]+\s+)?(?:[\d.]+\s+)?([\d.]+)\s*ns"),
                ("pwd_ns", r"Pulse Width Distortion\s+PWD\s+(?:[\d.]+\s+)?([\d.]+)\s*ns"),
                ("skew_ns", r"Channel-to-Channel\s+t ?SK\S*\s+(?:[\d.]+\s+)?([\d.]+)\s*ns"),
                ("creepage_mm", r"External Creepage\s+CPG\s+([\d.]+)"),
                ("viorm_vpk", r"VIORM\s+([\d.]+)\s*V ?PEAK"),
            ):
                found = sheet.first_number(pattern)
                if found:
                    put(key, found[0], f"{where} p.{found[1]}")
            agencies = sheet.agencies()
            put("certifications", agencies or None, f"{where} regulatory information")
            base = re.match(r"(NSI\d{4})", opn, re.I)
            candidates = sheet.pinouts()
            pins = candidates.get(base.group(1).upper()) if base else None
            if pins is None and len(candidates) == 1:
                pins = next(iter(candidates.values()))
            if pins and (expect is None or fwd_rev(pins) == expect) and len(pins) in (8, 10, 16):
                pinout = pins
                src["pinout"] = f"{where} p.{sheet.page_of('Pin Configuration') or '?'}"
                put("enable_pins", _enable(pins), src["pinout"])
            else:
                notes.append("Pinout not read from the datasheet; fit cannot be checked.")
        else:
            notes.append("Datasheet not available as a readable PDF.")

        parts.append(
            {
                "mpn": opn,
                "manufacturer": facts["manufacturer"]["name"],
                "family": family,
                "description": f"{row.get('partnumber', '')} digital isolator, {row.get('parameter3', '')}",
                "package": pkg,
                "pinout": pinout if pinout and len(pinout) == _pins(facts, pkg) else [],
                "datasheet": sheet.name if sheet and sheet.ok else None,
                "datasheet_url": SITE + ds[0] if ds else None,
                "product_url": f"{SITE}/en/product/{opn}",
                "notes": " ".join(notes) or None,
                "lifecycle": {
                    "status": STATUS.get(str(row.get("status", "")).strip().lower(), "unknown"),
                    "release_date": sheet.first_issue if sheet else None,
                    "revision": sheet.revision if sheet else None,
                    "revision_date": sheet.revision_date if sheet else None,
                    "source": f"Novosense product table: {row.get('status')}; release date = first datasheet revision",
                },
                "params": params,
                "param_sources": src,
            }
        )
    return {
        "source": "novosns.com product table and datasheets",
        "manufacturers": [facts["manufacturer"]],
        "packages": [{k: v for k, v in p.items() if k not in ("aliases", "evidence")} for p in facts["packages"]],
        "datasheets": [
            {"file": n, "url": None, "sha256": s.sha256, "revision": s.revision, "revision_date": s.revision_date}
            for n, s in sorted(sheets.items())
            if s.ok
        ],
        "parts": parts,
        "skipped": skipped,
    }


def _pins(facts: dict, code: str) -> int:
    return next(p["pin_count"] for p in facts["packages"] if p["code"] == code)


def _enable(pins: list[str]) -> str:
    ens = sorted({p for p in pins if re.fullmatch(r"EN\d?", p)})
    return f"{'+'.join(ens)} active-high" if ens else "none"
