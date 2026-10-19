"""Skyworks source: product tables, lifecycle lookup and datasheets from skyworksinc.com.

    fetch()  downloads raw data into var/raw/skyworks and var/datasheets/skyworks
    build()  combines it with data/sources/skyworks_si86.yaml into a data file
             in the format of app/services/seed.py

Everything fetched is public. Requests are made one at a time with a pause.
"""

import hashlib
import html
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date
from pathlib import Path

import yaml

from app.config import PROJECT_ROOT
from app.parsing.datasheet import detect_revision

BASE_URL = "https://www.skyworksinc.com"
FACTS_FILE = PROJECT_ROOT / "data" / "sources" / "skyworks_si86.yaml"
RAW_DIR = PROJECT_ROOT / "var" / "raw" / "skyworks"
DATASHEET_DIR = PROJECT_ROOT / "var" / "datasheets" / "skyworks"
USER_AGENT = "Mozilla/5.0 (CrossList datasheet importer)"
PAUSE_S = 1.5
RETRIES = 4

LIFECYCLE_MAP = {
    "in production": "active",
    "active": "active",
    "not recommended for new design": "nrnd",
    "not recommended for new designs": "nrnd",
    "nrnd": "nrnd",
    "last time buy": "last_time_buy",
    "obsolete": "obsolete",
    "end of life": "obsolete",
    "discontinued": "obsolete",
    "sampling": "preview",
    "samples only": "preview",
    "pre-production": "preview",
    "preview": "preview",
}

BASE_RE = re.compile(r"^SI(86(?:S\d{3}|S[A-Z]\d{2}|P\d{3}|\d{2}))", re.I)


# ------------------------------------------------------------------ fetching


def _get(url: str, data: bytes | None = None, content_type: str | None = None) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    if content_type:
        headers["Content-Type"] = content_type
    for attempt in range(RETRIES):
        req = urllib.request.Request(url, data=data, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                body = resp.read()
        except OSError:
            body = b""
        time.sleep(PAUSE_S)
        if body.strip():
            return body
        time.sleep(PAUSE_S * 2 ** (attempt + 1))  # empty reply: the site is throttling
    raise RuntimeError(f"No response from {url} after {RETRIES} attempts")


def fetch_product_table(item_id: str) -> dict:
    payload = {
        "SearchText": None, "MarketList": None, "SolutionList": None, "ApplicationList": None,
        "CategoryList": None, "FamilyList": None, "DocumentTypeList": None, "IsParameterSearch": False,
        "FrequecyMinGhz": 0, "FrequecyMaxGhz": 0, "ItemID": item_id,
    }  # fmt: skip
    body = _get(
        BASE_URL + "/api/feature/search/getsilabsproductspecification/",
        json.dumps(payload).encode(),
        "application/json; charset=utf-8",
    )
    return json.loads(json.loads(body))  # the endpoint returns JSON encoded as a JSON string


def fetch_lifecycle(prefix: str) -> list[tuple[str, str]]:
    """[(opn, status)] for part numbers starting with ``prefix`` (max 100 per query)."""
    url = BASE_URL + "/Product-Lifecycle-Status-Lookup?" + urllib.parse.urlencode({"PartNumber": prefix})
    text = _get(url).decode("utf-8", "ignore")
    m = re.search(r"var productStatusData = (\[.*?\]);", text, re.S)
    # A JavaScript literal (may have trailing commas), so read the leading string pairs.
    return re.findall(r'\[\s*"([^"]+)"\s*,\s*"([^"]*)"', m.group(1)) if m else []


def fetch(facts_file: Path = FACTS_FILE, log=print) -> None:
    facts = yaml.safe_load(facts_file.read_text())
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DATASHEET_DIR.mkdir(parents=True, exist_ok=True)

    for name, item_id in facts["product_tables"].items():
        table = fetch_product_table(item_id)
        (RAW_DIR / f"table_{_slug(name)}.json").write_text(json.dumps(table))
        log(f"product table {name}: {len(table['dtProductSpecification'])} rows")

    records = parse_tables(RAW_DIR)
    for url in sorted({r["datasheet_url"] for r in records.values() if r["datasheet_url"]}):
        path = DATASHEET_DIR / Path(urllib.parse.urlparse(url).path).name
        path.write_bytes(_get(url))
        log(f"datasheet {path.name}: {path.stat().st_size // 1024} kB")

    fetch_statuses(records, log)


def fetch_statuses(records: dict[str, dict], log=print) -> None:
    # Saved after every lookup so an interrupted run resumes where it stopped.
    path = RAW_DIR / "lifecycle.json"
    state = json.loads(path.read_text()) if path.exists() else {"done": [], "statuses": {}}
    # One lookup per base part; the lookup returns at most 100 rows, so a full
    # answer is split into base + grade lookups.
    by_base: dict[str, set[str]] = {}
    for opn in records:
        if m := BASE_RE.match(opn):
            by_base.setdefault(m.group(0), set()).add(m.group(0) + opn[m.end() : m.end() + 2])
    for base, grades in sorted(by_base.items()):
        if base in state["done"]:
            continue
        rows = fetch_lifecycle(base)
        if len(rows) >= 100:
            rows = [row for grade in sorted(grades) for row in fetch_lifecycle(grade)]
        for opn, status in rows:
            state["statuses"][opn.upper()] = status
        state["done"].append(base)
        path.write_text(json.dumps(state))
    log(f"lifecycle: {len(state['statuses'])} part numbers")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


# ------------------------------------------------------------------ parsing


def _clean(v) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", str(v or ""))).strip()


def parse_tables(raw_dir: Path) -> dict[str, dict]:
    """Merge all product tables into {OPN: record}."""
    records: dict[str, dict] = {}
    for path in sorted(raw_dir.glob("table_*.json")):
        for row in json.loads(path.read_text())["dtProductSpecification"]:
            cell = row["Product"]
            opn = re.search(r'class="link-title"[^>]*>\s*([^<\s]+)', cell).group(1).upper()
            ds = re.search(r'href="([^"]+\.pdf)"', cell)
            page = re.search(r'class="link-title" href="([^"]+)"', cell)
            rec = records.setdefault(
                opn,
                {
                    "opn": opn,
                    "datasheet_url": BASE_URL + ds.group(1) if ds else None,
                    "product_url": BASE_URL + page.group(1) if page else None,
                    "fields": {},
                },
            )
            for k, v in row.items():
                if k not in ("Product", "Ecommerce", "ECADModels") and _clean(v):
                    rec["fields"][" ".join(k.split())] = _clean(v)
    return records


def _range(text: str | None) -> list[float] | None:
    nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", (text or "").replace("–", "-"))]
    return [min(nums), max(nums)] if len(nums) >= 2 else None


def _num(text: str | None) -> float | None:
    m = re.search(r"-?\d+(?:\.\d+)?", text or "")
    return float(m.group()) if m else None


def _flag(text: str | None) -> bool:
    return (text or "").strip().lower() in ("yes", "true", "y", "1", "✓", "x")


# ------------------------------------------------------------------ datasheets


class Datasheet:
    def __init__(self, path: Path):
        from app.parsing.datasheet import extract_pages

        self.path = path
        txt = path.with_suffix(".txt")
        if txt.exists():
            self.pages = txt.read_text().split("\n\f\n")
        else:
            self.pages = extract_pages(path)
            txt.write_text("\n\f\n".join(self.pages))
        self.revision, self.revision_date, self.first_issue = detect_revision(self.pages)
        self.sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
        self._found: dict[str, int] = {}

    def ordering_line(self, opn: str) -> tuple[str, int] | None:
        """The ordering-guide line listing ``opn`` (also tried with the "-B-" revision letter)."""
        names = {opn.upper(), re.sub(r"^(SI\w+?)-(I)", r"\1-B-\2", opn.upper())}
        for page_no, text in enumerate(self.pages, 1):
            for line in text.splitlines():
                tokens = {t.upper() for t in line.split()}
                if names & tokens:
                    return line, page_no
        return None

    def find_any(self, literals: list[str]) -> int:
        """Page of the first literal text found."""
        for text in literals:
            try:
                return self.find(re.escape(text))
            except ValueError:
                continue
        raise ValueError(f"{self.path.name}: none of {literals!r} found")

    def find(self, pattern: str) -> int:
        """1-based page where ``pattern`` occurs; raises if missing."""
        if pattern not in self._found:
            rx = re.compile(pattern, re.I)
            page = next(
                (i for i, t in enumerate(self.pages, 1) if rx.search(" ".join(t.split())) or rx.search(t)), None
            )
            if page is None:
                raise ValueError(f"{self.path.name}: evidence not found: {pattern!r}")
            self._found[pattern] = page
        return self._found[pattern]


# ------------------------------------------------------------------ pinouts


def build_pinout(base: dict, layout: dict) -> list[str]:
    pins: dict[int, str] = {int(k): v for k, v in layout["fixed"].items()}
    dirs = base["dirs"]
    if len(dirs) != len(layout["ch"]):
        raise ValueError(f"{len(dirs)} channel directions for {len(layout['ch'])} slots")
    # Channels are lettered in order of their side-1 pin so that pinouts from
    # different manufacturers compare position by position.
    slots = sorted(zip(layout["ch"], dirs, strict=True), key=lambda s: s[0][0])
    for idx, ((p1, p2), d) in enumerate(slots):
        letter = "ABCDEFGH"[idx]
        side1, side2 = {"F": ("IN", "OUT"), "R": ("OUT", "IN"), "B": ("IO", "IO")}[d]
        pins[p1], pins[p2] = side1 + letter, side2 + letter
    for pin, fn in zip(layout["ctl"], base.get("ctl", []), strict=True):
        pins[pin] = fn
    missing = [p for p in range(1, layout["pins"] + 1) if p not in pins]
    if missing:
        raise ValueError(f"pins without a function: {missing}")
    return [pins[p] for p in range(1, layout["pins"] + 1)]


def _channel_config(dirs: str) -> str:
    c = Counter(dirs)
    cfg = f"{c['F']}/{c['R']}"
    return cfg + (f" + {c['B']} bidir" if c["B"] else "")


def _enable_pins(ctl: list[str]) -> str:
    if "SLEEP1" in ctl:
        return "sleep pin (active-low)"
    ens = [p for p in ctl if p.startswith("EN")]
    return f"{'+'.join(ens)} active-high" if ens else "none"


# ------------------------------------------------------------------ build


def build(facts_file: Path = FACTS_FILE, raw_dir: Path = RAW_DIR, ds_dir: Path = DATASHEET_DIR) -> dict:
    facts = yaml.safe_load(facts_file.read_text())
    records = parse_tables(raw_dir)
    lifecycle_path = raw_dir / "lifecycle.json"
    statuses = json.loads(lifecycle_path.read_text())["statuses"] if lifecycle_path.exists() else {}
    # The lookup spells part numbers with the die revision ("SI8641BD-B-IS"); the
    # product table does not ("SI8641BD-IS"). Index both spellings.
    for opn, status in list(statuses.items()):
        statuses.setdefault(re.sub(r"-[A-C]-", "-", opn), status)
    alias = {a.upper(): p["code"] for p in facts["packages"] for a in p["aliases"] + [p["code"]]}
    bases = {k.upper(): (k, v) for k, v in facts["base_parts"].items()}

    sheets: dict[str, Datasheet] = {}
    pin_pages: dict[str, int] = {}
    parts, skipped, mismatches = [], [], []
    for opn, rec in sorted(records.items()):
        m = BASE_RE.match(opn)
        f = rec["fields"]
        if not m or m.group(0).upper() not in bases or not rec["datasheet_url"]:
            skipped.append((opn, "no base part or datasheet"))
            continue
        base_name, base = bases[m.group(0).upper()]
        ds_name = Path(urllib.parse.urlparse(rec["datasheet_url"]).path).name
        if ds_name not in sheets:
            sheets[ds_name] = Datasheet(ds_dir / ds_name)
        sheet = sheets[ds_name]
        guide = sheet.ordering_line(opn)
        table_pkg = alias.get((f.get("Package Type") or "").upper())
        guide_pkg = guide_iso = guide_default = None
        if guide:
            line = guide[0]
            hits = sorted(
                ((line.upper().find(a), a) for a in alias if a in line.upper()), key=lambda h: (h[0], -len(h[1]))
            )
            guide_pkg = alias[hits[0][1]] if hits else None
            # "... <default output> <isolation kV> <package>"
            iso = re.search(r"\b(?:Low|High)\s+(\d+(?:\.\d+)?)\b", line)
            before_pkg = re.findall(r"(\d+(?:\.\d+)?)\s", line[: hits[0][0]]) if hits else []
            guide_iso = float(iso.group(1)) if iso else float(before_pkg[-1]) if before_pkg else None
            default = re.search(r"\b(Low|High)\b", line)
            guide_default = default.group(1).lower() if default else None
        # The datasheet ordering guide is authoritative; the web table has errors.
        if table_pkg and guide_pkg and table_pkg != guide_pkg:
            mismatches.append(f"{opn}: table says {table_pkg}, datasheet ordering guide says {guide_pkg}")
        pkg = guide_pkg or table_pkg
        pkg_pins = {p["code"]: p["pin_count"] for p in facts["packages"]}
        layouts = base["layout"].values() if isinstance(base["layout"], dict) else [base["layout"]]
        if pkg is not None and pkg_pins[pkg] not in {facts["layouts"][lay]["pins"] for lay in layouts}:
            mismatches.append(f"{opn}: package {pkg} does not fit the {base_name} pinout")
            pkg = None
        if pkg is None:
            skipped.append((opn, "package unknown"))
            continue
        counts = (f.get("Forward Channels"), f.get("Reverse Channels"), f.get("Bidirectional Channels"))
        c = Counter(base["dirs"])
        # Bidirectional channels are counted inconsistently in the table, so only
        # unidirectional parts are cross-checked.
        if not c["B"] and counts[0] is not None and (int(counts[0] or 0), int(counts[1] or 0)) != (c["F"], c["R"]):
            mismatches.append(f"{opn}: table says {counts[0]}/{counts[1]}, datasheet pinout {c['F']}/{c['R']}")
        dsf = facts["datasheets"][ds_name]

        layout_name = base["layout"]
        if isinstance(layout_name, dict):
            layout_name = layout_name.get(pkg) or next(iter(layout_name.values()))
        pinout = build_pinout(base, facts["layouts"][layout_name])
        notes = []
        if base.get("inferred"):
            notes.append(f"Pinout inferred: {base['inferred']}.")
        elif (base_name, ds_name) not in pin_pages:
            evidence = base["pinout_evidence"]
            pin_pages[base_name, ds_name] = sheet.find_any([evidence] if isinstance(evidence, str) else evidence)

        grade = opn[len(m.group(0)) : len(m.group(0)) + 2]
        t_option = not base_name.startswith(("Si86S", "Si86P")) and grade[1:2] == "T"
        high_cmti = base_name.startswith("Si86S") and grade[:1] in ("F", "H")
        automotive = bool(re.search(r"-A[SU]\d?$", opn)) or _flag(f.get("AEC-Q100"))

        params: dict = {
            "channel_config": _channel_config(base["dirs"]),
            "integrated_power": "none",
            "default_output": (f.get("Default Output State") or "").lower() or None,
            "isolation_rating_kvrms": _num(f.get("Isolation Rating (kVrms)")),
            "data_rate_mbps": _num(f.get("Max Data Rate (Mbps)")),
            "prop_delay_ns": _num(f.get("Max Propagation Delay")),
            "vdd_range_v": _range(f.get("Input Supply (V)") or f.get("Supply Voltage Range (V)")),
            "qualification": "automotive" if automotive else "industrial",
            "enable_pins": _enable_pins(base.get("ctl", [])),
            "surge_10kv": bool(t_option or _flag(f.get("10 kV Surge"))),
        }
        sources = {k: "Skyworks product table" for k, v in params.items() if v is not None}
        pin_source = base.get("inferred") and "pinout inferred" or f"{ds_name} pinout"
        sources.update(channel_config=pin_source, enable_pins=pin_source, integrated_power=f"{ds_name}")
        for key, fact in dsf.items():
            if "by_package" in fact:
                value = fact["by_package"].get(pkg)
            elif t_option and "t_option" in fact:
                value = fact["t_option"]
            elif high_cmti and "high_cmti" in fact:
                value = fact["high_cmti"]
            else:
                value = fact.get("value")  # facts with only `t_option` apply to T parts only
            if value is None or (key in params and params[key] is not None and "value" not in fact):
                continue
            params[key] = value
            sources[key] = f"{ds_name} p.{sheet.find(fact['evidence'])}"
        # default output state: the ordering guide decides (it is authoritative), the web table fills gaps
        if guide_default and params.get("default_output") != guide_default:
            if params.get("default_output"):
                mismatches.append(
                    f"{opn}: table says default {params['default_output']}, ordering guide says {guide_default}"
                )
            params["default_output"] = guide_default
            sources["default_output"] = f"{ds_name} p.{guide[1]} (ordering guide)"
        if params.get("isolation_rating_kvrms") is None and guide_iso:
            params["isolation_rating_kvrms"] = guide_iso
            sources["isolation_rating_kvrms"] = f"{ds_name} p.{guide[1]} (ordering guide)"
        temp = _range(f.get("Ambient Temperature Range (°C)"))
        if temp:
            params["temp_range_c"], sources["temp_range_c"] = temp, "Skyworks product table"
        params = {k: v for k, v in params.items() if v is not None}

        status_text = statuses.get(opn, "")
        parts.append(
            {
                "mpn": opn,
                "manufacturer": facts["manufacturer"]["name"],
                "family": "digital_isolator",
                "description": f"{base_name} {params['channel_config']} digital isolator"
                + (f", {params['isolation_rating_kvrms']:g} kVrms" if "isolation_rating_kvrms" in params else ""),
                "package": pkg,
                "pinout": pinout,
                "datasheet": ds_name,
                "datasheet_url": rec["datasheet_url"],
                "product_url": rec["product_url"],
                "notes": " ".join(notes) or None,
                "lifecycle": {
                    "status": LIFECYCLE_MAP.get(status_text.strip().lower(), "unknown"),
                    "release_date": sheet.first_issue,
                    "revision": sheet.revision,
                    "revision_date": sheet.revision_date,
                    "source": f"Skyworks lifecycle lookup: {status_text or 'not listed'}; "
                    "release date = first datasheet revision",
                },
                "params": params,
                "param_sources": {**sources, "pinout": f"{ds_name} p.{pin_pages[base_name, ds_name]}"}
                if (base_name, ds_name) in pin_pages
                else sources,
            }
        )

    return {
        "source": f"skyworksinc.com, built {date.today().isoformat()}",
        "manufacturers": [facts["manufacturer"]],
        "packages": [{k: v for k, v in p.items() if k != "aliases"} for p in facts["packages"]],
        "datasheets": [
            {
                "file": name,
                "url": next(r["datasheet_url"] for r in records.values() if (r["datasheet_url"] or "").endswith(name)),
                "sha256": s.sha256,
                "revision": s.revision,
                "revision_date": s.revision_date,
            }
            for name, s in sorted(sheets.items())
        ],
        "parts": parts,
        "skipped": [f"{opn} ({why})" for opn, why in skipped],
        "table_vs_datasheet": mismatches,
    }
