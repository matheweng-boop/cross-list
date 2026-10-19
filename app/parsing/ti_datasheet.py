"""Parse TI isolator datasheets: per-package insulation table and pin function table.

TI datasheets lay these tables out consistently:

* "Insulation Specifications": one column per package ("16-DW 16-DFP 16-DBQ").
* "Pin Functions": one row per pin name, one column of pin numbers per device.
"""

import re
from dataclasses import dataclass, field


@dataclass
class Insulation:
    packages: list[str]  # TI package designators in column order, e.g. ["DW", "DFP", "DBQ"]
    page: int
    creepage_mm: dict[str, float] = field(default_factory=dict)
    clearance_mm: dict[str, float] = field(default_factory=dict)
    viorm_vpk: dict[str, float] = field(default_factory=dict)
    viosm_vpk: dict[str, float] = field(default_factory=dict)
    viso_vrms: dict[str, float] = field(default_factory=dict)
    columns: dict[int, str] = field(default_factory=dict)  # table column -> package

    def isolation_class(self, pkg: str) -> str | None:
        """IEC 60747-17 reinforced isolation requires a surge rating of at least 10 kV."""
        v = self.viosm_vpk.get(pkg)
        return None if v is None else "reinforced" if v >= 10000 else "basic"


def _num(cell) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)", str(cell or "").replace(" ", ""))
    return float(m.group(1)) if m else None


INSULATION_KEYS = [
    ("creepage_mm", r"^cpg|externalcreepage|externaltracking"),
    ("clearance_mm", r"^clr|externalclearance|externalairgap"),
    ("viorm_vpk", r"acvoltage\(bipolar\)|maximumrepetitivepeak|^viorm"),
    ("viosm_vpk", r"maximumsurge|^viosm"),
    ("viso_vrms", r"withstandisolationvoltage|^viso"),
]
PKG_HEADER_RE = re.compile(r"^(?:\d{1,2}-)?([A-Z]{1,4})(?:-\d{1,2})?$")


def parse_insulation(pdf_path, pages: list[str]) -> Insulation | None:
    """Per-package insulation values from the "Insulation Specifications" table."""
    import pdfplumber

    starts = [
        i
        for i, t in enumerate(pages)
        if re.search(r"Insulation Specifications|Insulation Characteristics", t, re.I)
        and not re.search(r"Insulation (Specifications|Characteristics)\s*\.{3,}", t, re.I)
    ]
    if not starts:
        return None
    ins = None
    with pdfplumber.open(pdf_path) as pdf:
        for i in (starts[0], starts[0] + 1):
            if i >= len(pdf.pages):
                break
            for table in pdf.pages[i].extract_tables():
                ins = _read_insulation_table(table, i + 1, ins)
    return ins if ins and (ins.creepage_mm or ins.viorm_vpk) else None


def _read_insulation_table(table: list[list], page: int, ins: Insulation | None) -> Insulation | None:
    value_cols: dict[int, str] = {}
    body = 0
    for r, row in enumerate(table[:4]):
        found = {}
        for c, cell in enumerate(row):
            text = re.sub(r"\s+", "", str(cell or "")).upper()
            m = PKG_HEADER_RE.match(text)
            if m and text not in ("UNIT", "VALUE", "CLR", "CPG", "DTI", "CTI"):
                found[c] = m.group(1)
        if found:
            value_cols, body = found, r + 1
            break
    if not value_cols:
        if ins is not None:  # continuation of the table on the next page
            value_cols = dict(ins.columns)
        else:
            for r, row in enumerate(table[:3]):
                for c, cell in enumerate(row):
                    if re.sub(r"\s+", "", str(cell or "")).upper() in ("VALUE", "SPECIFICATION"):
                        value_cols, body = {c: "*"}, r + 1
            if not value_cols:
                return ins
    if ins is None:
        ins = Insulation(list(value_cols.values()), page, columns=value_cols)
    for row in table[body:]:
        label = "".join(str(c or "") for c in row[: min(value_cols)]).lower().replace(" ", "").replace("\n", "")
        for key, rx in INSULATION_KEYS:
            target = getattr(ins, key)
            if target or not re.search(rx, label):
                continue
            values = {pkg: _num(row[c]) for c, pkg in value_cols.items() if c < len(row)}
            if all(v is not None for v in values.values()):
                target.update(values)
    return ins


# ------------------------------------------------------------------ pins

ABSENT = {"", "—", "–", "-", "n/a", "NA"}
PKG_LABEL_RE = re.compile(r"^(?:\d{1,2}-)?([A-Z]{1,4})(?:-\d{1,2})?$")


@dataclass
class PinTable:
    page: int
    columns: list[str]  # device names ("ISO7741") or package designators ("DW")
    by_package: bool
    rows: dict[str, list[list[int]]]  # pin name -> pins per column


def _clean_name(cell) -> str:
    return re.sub(r"\s+", "", str(cell or "")).upper()


def _pins(cell) -> list[int] | None:
    text = str(cell or "").strip()
    if text in ABSENT:
        return []
    nums = re.findall(r"\d+", text)
    return [int(n) for n in nums] if nums and re.fullmatch(r"[\d,\s]+", text) else None


def parse_pin_table(pdf_path, pages: list[str]) -> PinTable | None:
    """Pin function table, read with pdfplumber's table extraction."""
    import pdfplumber

    candidates = [
        i
        for i, t in enumerate(pages)
        if re.search(r"Pin Functions|Pin Descriptions|Terminal Functions|Pin Configuration", t, re.I)
        and not re.search(r"(Pin|Terminal) Functions\s*\.{3,}", t, re.I)
    ]
    with pdfplumber.open(pdf_path) as pdf:
        for i in candidates[:4]:
            for table in pdf.pages[i].extract_tables():
                parsed = _parse_pin_rows(table)
                if parsed:
                    columns, by_package, rows = parsed
                    return PinTable(i + 1, columns, by_package, rows)
    return None


def _parse_pin_rows(table: list[list]) -> tuple[list[str], bool, dict] | None:
    if len(table) < 4:
        return None
    header_text = " ".join(str(c) for row in table[:3] for c in row if c)
    if "NAME" not in header_text.upper() and "PIN" not in header_text.upper():
        return None
    # Column labels: the header cells between the name column and "Type"/"I/O".
    labels: dict[int, str] = {}
    body_start = 0
    for r, row in enumerate(table[:4]):
        found = False
        for c, cell in enumerate(row[1:], 1):
            text = re.sub(r"\s+", "", str(cell or ""))
            if re.match(r"^ISO", text, re.I):
                for name in re.findall(r"ISO[A-Z]?\d{3,4}[A-Z0-9-]*", text, re.I):
                    labels.setdefault(c, name.upper().rstrip(",-"))
                found = True
            elif PKG_LABEL_RE.match(text) and text not in ("NO.", "I", "O", "NAME", "PIN"):
                labels.setdefault(c, PKG_LABEL_RE.match(text).group(1))
                found = True
        if found:
            body_start = r + 1
    rows: dict[str, list[list[int]]] = {}
    last = None
    cols = sorted(labels) or None
    for row in table[body_start or 1 :]:
        name = _clean_name(row[0])
        if cols is None:  # single-device table: the first numeric column
            cols = [next((c for c, cell in enumerate(row[1:], 1) if _pins(cell)), None)]
            if cols[0] is None:
                cols = None
                continue
        values = [_pins(row[c]) if c < len(row) else None for c in cols]
        if any(v is None for v in values):
            continue
        if not name and last:  # continuation row: more pins for the previous name
            rows[last] = [a + b for a, b in zip(rows[last], values, strict=True)]
            continue
        if not name or name in ("NAME", "PIN"):
            continue
        rows[name] = values
        last = name
    if len(rows) < 4 or cols is None:
        return None
    columns = [labels.get(c, "") for c in cols]
    by_package = bool(columns) and all(c and not c.startswith("ISO") for c in columns)
    return columns, by_package, rows


SUPPLY = {"VCC1": "VDD1", "VDD1": "VDD1", "VCCI": "VDD1", "VCC2": "VDD2", "VDD2": "VDD2", "VCCO": "VDD2"}


def column_pin_count(rows: dict[str, list[list[int]]], col: int) -> int:
    return max((p for cols in rows.values() for p in cols[col]), default=0)


def canonical_pinout(rows: dict[str, list[list[int]]], col: int, pin_count: int | None = None) -> list[str] | None:
    """Pin list in the normalised vocabulary used across manufacturers."""
    pin_count = pin_count or column_pin_count(rows, col)
    pins: dict[int, str] = {}
    channels: dict[str, dict[str, int]] = {}
    for name, cols in rows.items():
        for pin in cols[col]:
            if name in SUPPLY:
                fn = SUPPLY[name]
            elif m := re.fullmatch(r"(IN|OUT)([A-H]?)", name):
                channels.setdefault(m.group(2) or "A", {})[m.group(1)] = pin
                continue
            else:
                fn = name
            pins[pin] = fn
    half = pin_count // 2
    side1 = []
    for ends in channels.values():
        if set(ends) != {"IN", "OUT"}:
            return None
        s1 = ends["IN"] if ends["IN"] <= half else ends["OUT"]
        side1.append((s1, ends["IN"] <= half, ends))
    for idx, (_, _forward, ends) in enumerate(sorted(side1, key=lambda s: s[0])):
        letter = "ABCDEFGH"[idx]
        pins[ends["IN"]], pins[ends["OUT"]] = f"IN{letter}", f"OUT{letter}"
    if sorted(pins) != list(range(1, pin_count + 1)):
        return None
    return [pins[p] for p in range(1, pin_count + 1)]


def certified_classes(pdf_path, pages: list[str]) -> dict[str, str]:
    """{package: "reinforced" | "basic"} from the VDE column of the Safety-Related
    Certifications table, e.g. "2121 VPK (DW-16, DWV-8, Reinforced), 1414 VPK (D-8, Basic)"
    or "Reinforced certificate: 40040142 (DW-16)"."""
    import pdfplumber

    heading = re.compile(r"^\d+(?:\.\d+)+\s+Safety-Related Certifications\s*$", re.M)
    page_idx = next((i for i, t in enumerate(pages) if heading.search(t)), None)
    if page_idx is None:
        return {}
    with pdfplumber.open(pdf_path) as pdf:
        tables = pdf.pages[page_idx].extract_tables()
    for table in tables:
        header = [re.sub(r"\s+", "", str(c or "")).upper() for c in table[0]]
        if "VDE" not in header:
            continue

        def cell_of(name: str, table=table, header=header) -> str:
            col = header.index(name)
            return " ".join(str(row[col] or "") for row in table[1:] if col < len(row)).replace("\n", " ")

        found = classes_from_text(cell_of("VDE"))
        # VDE may give a package only a voltage ("566 VPK (DBQ-16)"); CSA (IEC 62368-1) and TUV (EN 61010-1)
        # then state "Reinforced insulation ... 370 VRMS (DBQ-16)". CQC (GB 4943.1) is not used: it can rate a
        # package basic that the IEC / EN standards rate reinforced.
        # CSA decides before TUV: they can disagree (ISO7720 D-8: CSA basic, TUV reinforced).
        for agency in ("CSA", "TUV"):
            if agency in header:
                for pkg, cls in _sentence_classes(cell_of(agency)).items():
                    found.setdefault(pkg, cls)
        # a table was found: its cells are the answer, even when empty. The page text below would mix the
        # columns ("Basic certificate" of one agency next to a package of another).
        return found
    # No table found: "Reinforced certificate: … (DW-16) … Basic certificate: … (DBQ-16)"
    m = heading.search(pages[page_idx])
    return classes_from_text(pages[page_idx][m.end() : m.end() + 1500])


def _sentence_classes(text: str) -> dict[str, str]:
    """Insulation class per package in agency statements. A sentence that opens with the class
    ("Reinforced insulation per ... (DW-16) and 370 V (DBQ-16)") gives it to every package; otherwise each
    package takes the next class word after it ("600 V (DW-16) reinforced insulation and 400 V (D-8) basic")."""
    out: dict[str, str] = {}
    for sentence in text.split(";"):
        toks = [
            (m.group(1).lower(), None) if m.group(1) else (None, m.group(2))
            for m in re.finditer(r"\b(Reinforced|Basic)\b|\b([A-Z]{1,4})-\d{1,2}\b", sentence, re.I)
            if m.group(1) or m.group(2).isupper()
        ]
        if not toks or not any(c for c, _ in toks):
            continue
        if toks[0][0]:
            for _, pkg in toks:
                if pkg:
                    out.setdefault(pkg, toks[0][0])
            continue
        pending: list[str] = []
        for cls, pkg in toks:
            if pkg:
                pending.append(pkg)
            else:
                for x in pending:
                    out.setdefault(x, cls)
                pending = []
    return out


def classes_from_text(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    # "(DW-16, DWV-8, Reinforced)"
    for inside in re.findall(r"\(([^()]*)\)", text):
        cls = re.search(r"\b(Reinforced|Basic)\b", inside, re.I)
        if cls:
            for pkg in re.findall(r"\b([A-Z]{1,4})-\d{1,2}\b", inside):
                out.setdefault(pkg, cls.group(1).lower())
    if out:
        return out
    # "Reinforced certificate: 40040142 (DW-16)"
    last = None
    for tok in re.finditer(r"\b(Reinforced|Basic)\b|\b([A-Z]{1,4})-\d{1,2}\b", text):
        if tok.group(1):
            last = tok.group(1).lower()
        elif last:
            out.setdefault(tok.group(2), last)
    return out


AGENCIES = ("VDE", "CSA", "UL", "CQC", "TUV")


def certification_agencies(pages: list[str]) -> list[str]:
    """Agencies named in the header row of the Safety-Related Certifications table."""
    heading = re.compile(r"^\d+(?:\.\d+)+\s+Safety-Related Certifications\s*$", re.M)
    for text in pages:
        m = heading.search(text)
        if m:
            header = text[m.end() : m.end() + 200].strip().splitlines()[0]
            found = [a for a in AGENCIES if re.search(rf"\b{a}\b", header.upper())]
            return sorted(found)
    return []
