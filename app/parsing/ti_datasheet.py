"""Parse TI isolator datasheets: per-package insulation table and pin function table.

TI datasheets lay these tables out consistently:

* "Insulation Specifications": one column per package ("16-DW 16-DFP 16-DBQ").
* "Pin Functions": one row per pin name, one column of pin numbers per device.
"""

import re
from dataclasses import dataclass, field

PKG_COL_RE = re.compile(r"\b(\d{1,2})-([A-Z]{1,4})\b|\b([A-Z]{1,4})-(\d{1,2})\b")
NUM_RE = re.compile(r"[>≥<]?\s?(\d+(?:\.\d+)?)")


@dataclass
class Insulation:
    packages: list[str]  # TI package designators in column order, e.g. ["DW", "DFP", "DBQ"]
    page: int
    creepage_mm: dict[str, float] = field(default_factory=dict)
    clearance_mm: dict[str, float] = field(default_factory=dict)
    viorm_vpk: dict[str, float] = field(default_factory=dict)
    viosm_vpk: dict[str, float] = field(default_factory=dict)
    viso_vrms: dict[str, float] = field(default_factory=dict)

    def isolation_class(self, pkg: str) -> str | None:
        """IEC 60747-17 reinforced isolation requires a surge rating of at least 10 kV."""
        v = self.viosm_vpk.get(pkg)
        return None if v is None else "reinforced" if v >= 10000 else "basic"


def _row_values(line: str, n: int) -> list[float] | None:
    nums = [float(x) for x in NUM_RE.findall(line)]
    return nums[-n:] if len(nums) >= n else None


def _find_section(pages: list[str], title: str) -> tuple[int, str] | None:
    """(page number, text from the title to the end of that page and the next)."""
    for i, text in enumerate(pages):
        for m in re.finditer(re.escape(title), text):
            before = text[max(0, m.start() - 3) : m.start()]
            tail = text[m.end() : m.end() + 40]
            if "..." in tail or ". ." in tail or "...." in before:
                continue  # table of contents entry
            nxt = pages[i + 1] if i + 1 < len(pages) else ""
            return i + 1, text[m.start() :] + "\n" + nxt
    return None


def parse_insulation(pages: list[str]) -> Insulation | None:
    found = _find_section(pages, "Insulation Specifications")
    if not found:
        return None
    page, text = found
    lines = text.splitlines()
    packages: list[str] = []
    for line in lines[:15]:
        cols = PKG_COL_RE.findall(line)
        words = [w for w in line.split() if w not in ("PARAMETER", "TEST", "CONDITIONS", "UNIT", "PACKAGE")]
        if cols and len(cols) * 2 >= len(words):  # a header line made of package names
            packages = [c[1] or c[2] for c in cols]
            break
    if not packages:
        return None
    n = len(packages)
    ins = Insulation(packages, page)
    for i, line in enumerate(lines):
        low = line.lower()
        target = None
        if re.search(r"\bcpg\b|external creepage", low):
            target = ins.creepage_mm
        elif re.search(r"\bclr\b|external clearance", low):
            target = ins.clearance_mm
        elif "ac voltage (bipolar)" in low:
            target = ins.viorm_vpk
        elif "iosm" in low.replace(" ", ""):
            target = ins.viosm_vpk
        elif "withstand isolation voltage" in low:
            target = ins.viso_vrms
        if target is None or target:
            continue
        values = _row_values(line, n) or _row_values(lines[i + 1] if i + 1 < len(lines) else "", n)
        if values:
            target.update(zip(packages, values, strict=True))
    return ins


# ------------------------------------------------------------------ pins

# A hyphen marks a pin a device does not have; an em dash is the "type" of supply pins.
PIN_ROW_RE = re.compile(r"^([A-Z][A-Z0-9_/]*?)\s+((?:(?:\d+(?:\s*,\s*\d+)*|-)\s+)+)(?:(?:I/O|I|O|—|P|G)(?=\s|$))?")
GROUP_RE = re.compile(r"\d+(?:\s*,\s*\d+)*|-")


def parse_pin_table(pages: list[str]) -> tuple[int, list[str], dict[str, list[list[int]]]] | None:
    """(page, device names in column order, {pin name: [pins per column]})."""
    found = _find_section(pages, "Pin Functions")
    if not found:
        return None
    page, text = found
    lines = text.splitlines()
    header = " ".join(lines[1:6])
    devices = []
    for name in re.findall(r"\b(ISO[A-Z]?\d{3,4}[A-Z0-9-]*)", header):
        base = name.rstrip(",")
        if base not in devices:
            devices.append(base)
    rows: dict[str, list[list[int]]] = {}
    counts: dict[int, int] = {}
    pending_v = None
    for line in lines[1:80]:
        line = line.strip()
        if line.startswith("(1)") or line.lower().startswith("copyright"):
            break
        if pending_v and re.fullmatch(r"(CC|DD)\d", line):
            rows["V" + line] = rows.pop(pending_v)
            pending_v = None
            continue
        m = PIN_ROW_RE.match(line + " ")
        if not m:
            continue
        name = m.group(1)
        groups = GROUP_RE.findall(m.group(2))
        cols = [[] if g == "-" else [int(x) for x in re.split(r"\s*,\s*", g)] for g in groups]
        if name == "V":  # VCC1 / VDD1 split across lines by the subscript
            pending_v = f"V#{len(rows)}"
            name = pending_v
        rows[name] = cols
        counts[len(cols)] = counts.get(len(cols), 0) + 1
    if not rows:
        return None
    ncols = max(counts, key=counts.get)
    rows = {k: v for k, v in rows.items() if len(v) == ncols}
    # Devices sharing a pinout are sometimes grouped in one column ("ISO6440, ISO6440F").
    if len(devices) != ncols:
        devices = [d for d in devices if not re.search(r"\d+F$", d)]
    return page, devices[:ncols] if len(devices) >= ncols else devices, rows


SUPPLY = {"VCC1": "VDD1", "VDD1": "VDD1", "VCCI": "VDD1", "VCC2": "VDD2", "VDD2": "VDD2", "VCCO": "VDD2"}


def canonical_pinout(rows: dict[str, list[list[int]]], col: int, pin_count: int) -> list[str] | None:
    """Pin list in the normalised vocabulary used across manufacturers."""
    pins: dict[int, str] = {}
    channels: dict[str, dict[str, int]] = {}
    for name, cols in rows.items():
        for pin in cols[col]:
            if name in SUPPLY:
                fn = SUPPLY[name]
            elif m := re.fullmatch(r"(IN|OUT)([A-H])", name):
                channels.setdefault(m.group(2), {})[m.group(1)] = pin
                continue
            else:
                fn = name
            pins[pin] = fn
    half = pin_count // 2
    side1 = []
    for letter, ends in channels.items():
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
