"""Skyworks isolated gate drivers beyond Si823x: Si8239x, Si823Hx, Si8252x, Si827x, Si826x, Si8220/21,
Si8281-84, Si8285/86, Si82Ax-Fx and Si82900.

    fetch()  downloads the public datasheets into var/gate_drivers (one request at a time, 6 s apart) and
             looks up the lifecycle status of ordering codes that the catalogue does not list
    build()  writes data/real/skyworks_gate_drivers_more.yaml and data/mechanical_skyworks_gate_drivers.yaml

The ordering codes are read from each datasheet's ordering guide (pdftotext); every code is decoded with the
rules of that ordering guide and checked against the UVLO / isolation columns of its own row. Parameter
values were transcribed from the electrical tables; each one carries its table in ``param_sources`` and the
page is found in the PDF text at build time. Lifecycle status comes from data/catalog/skyworks_parts.yaml
(Skyworks lifecycle lookup), or from the lookup itself for codes the catalogue does not list.
"""

import hashlib
import json
import re
import subprocess
import time
import urllib.parse
import urllib.request
from functools import cache
from pathlib import Path

import yaml

from app import yamlio
from app.config import PROJECT_ROOT

BASE_URL = "https://www.skyworksinc.com"
DS_URL = BASE_URL + "/-/media/SkyWorks/SL/documents/public/"
PDF_DIR = PROJECT_ROOT / "var" / "gate_drivers"
RAW_DIR = PROJECT_ROOT / "var" / "raw" / "skyworks_gate_drivers"
CATALOG = PROJECT_ROOT / "data" / "catalog" / "skyworks_parts.yaml"
OUT = PROJECT_ROOT / "data" / "real" / "skyworks_gate_drivers_more.yaml"
MECH_OUT = PROJECT_ROOT / "data" / "mechanical_skyworks_gate_drivers.yaml"
USER_AGENT = "Mozilla/5.0 (CrossList datasheet importer)"
PAUSE_S = 6.0

LIFECYCLE_MAP = {"active": "active", "in production": "active", "preview": "preview", "samples only": "preview",
                 "nrnd": "nrnd", "not recommended for new designs": "nrnd", "last time buy": "last_time_buy",
                 "obsolete": "obsolete"}

# ------------------------------------------------------------------ datasheets

SHEETS = {
    "si8239x": ("si8239x-data-sheet.pdf", "data-sheets/si8239x-data-sheet.pdf", "206709A", "2023-09-28"),
    "si823hx": ("Si823Hx-DataSheet.pdf", "data-sheets/Si823Hx-DataSheet.pdf", "206414A", "2022-11-01"),
    "si8252x": ("si8252x-datasheet.pdf", "data-sheets/si8252x-datasheet.pdf", "206413B", "2024-07-09"),
    "si827x": ("Si827x.pdf", "data-sheets/Si827x.pdf", "206327E", "2026-01-23"),
    "si826x": ("Si826x.pdf", "data-sheets/Si826x.pdf", "1.51", "2021-10-26"),
    "si8220": ("Si8220-21.pdf", "data-sheets/Si8220-21.pdf", "1.5", "2021-08-25"),
    "si8281": ("Si8281-82-83-84.pdf", "data-sheets/Si8281-82-83-84.pdf", "206406A", "2022-10-21"),
    "si8285": ("si8285-86-data-sheet.pdf", "data-sheets/si8285-86-data-sheet.pdf", "2.0", "2021-10-12"),
    "si82ax": ("Si82Ax-datasheet.pdf", "data-sheets/Si82Ax-datasheet.pdf", "207062A", "2025-01-20"),
    "si82bx": ("Si82Bx-datasheet.pdf", "data-sheets/Si82Bx-datasheet.pdf", "207063B", "2026-01-13"),
    "si82cx": ("Si82Cx-datasheet.pdf", "data-sheets/Si82Cx-datasheet.pdf", "207064A", "2025-01-20"),
    "si82dx": ("Si82Dx-datasheet.pdf", "data-sheets/Si82Dx-datasheet.pdf", "207065A", "2025-01-20"),
    "si82ex": ("Si82Ex-datasheet.pdf", "data-sheets/Si82Ex-datasheet.pdf", "206857C", "2026-01-20"),
    "si82fx": ("Si82Fx-datasheet.pdf", "data-sheets/Si82Fx-datasheet.pdf", "206821A", "2024-05-20"),
    "si829x": ("Si829x-product-summary.pdf", "product-summaries/Si829x-product-summary.pdf", "207561A", "2026-09-15"),
}

# ------------------------------------------------------------------ packages

PACKAGES = {
    # codes shared with skyworks_si86.yaml / skyworks_si823x.yaml (identical bodies, see the datasheet tables)
    "SOIC-8N": dict(name="SOIC-8 narrow body", pin_count=8, pitch_mm=1.27, body_length_mm=4.9, body_width_mm=3.9,
                    span_mm=6.0, height_mm=1.75),
    "SSO-8": dict(name="Stretched SO-8 (wide body)", pin_count=8, pitch_mm=1.27, body_length_mm=5.84,
                  body_width_mm=7.49, span_mm=11.5, height_mm=2.79),
    "SOIC-16N": dict(name="SOIC-16 narrow body", pin_count=16, pitch_mm=1.27, body_length_mm=9.9, body_width_mm=3.9,
                     span_mm=6.0, height_mm=1.75),
    "SOIC-16W": dict(name="SOIC-16 wide body", pin_count=16, pitch_mm=1.27, body_length_mm=10.3, body_width_mm=7.5,
                     span_mm=10.3, height_mm=2.65),
    "SOIC-14W (IS3)": dict(name="SOIC-14 wide body, increased creepage (16-position body, positions 12 and 13 "
                           "empty)", pin_count=14, pitch_mm=1.27, body_length_mm=10.3, body_width_mm=7.5,
                           span_mm=10.3, height_mm=2.65, positions_total=16,
                           pin_positions=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 14, 15, 16]),
    "SOIC-20W": dict(name="SOIC-20 wide body", pin_count=20, pitch_mm=1.27, body_length_mm=12.8, body_width_mm=7.5,
                     span_mm=10.3, height_mm=2.65),
    # new bodies
    "SOIC-24W": dict(name="SOIC-24 wide body", pin_count=24, pitch_mm=1.27, body_length_mm=15.4, body_width_mm=7.5,
                     span_mm=10.3, height_mm=2.65),
    "DFN-14 (5x5)": dict(name="DFN-14 5 x 5 mm", pin_count=14, pitch_mm=0.65, body_length_mm=5.0,
                         body_width_mm=5.0, span_mm=5.0, height_mm=0.9, exposed_pad=False),
    "LGA-13 (5x5)": dict(name="LGA-13 5 x 5 mm (14-position grid, position 11 empty)", pin_count=13,
                         pitch_mm=0.65, body_length_mm=5.0, body_width_mm=5.0, span_mm=5.0, height_mm=0.93,
                         exposed_pad=False, positions_total=14,
                         pin_positions=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 13, 14]),
    "DIP-8 GW": dict(name="DIP-8 gull-wing (surface mount)", pin_count=8, pitch_mm=2.54, body_length_mm=9.65,
                     body_width_mm=6.35, span_mm=9.65, height_mm=4.19),
    "SDIP-6": dict(name="Stretched SO-6 (SDIP6, wide body)", pin_count=6, pitch_mm=1.27, body_length_mm=4.58,
                   body_width_mm=7.5, span_mm=11.5, height_mm=2.65),
    "SSOP-36W": dict(name="SSOP-36 wide body", pin_count=36, pitch_mm=0.8, body_length_mm=15.4, body_width_mm=7.5,
                     span_mm=10.3, height_mm=2.65),
}

PACKAGE_NOTES = {
    "DFN-14 (5x5)": "Si823Hx-DataSheet.pdf Table 7.5 (D = E = 5.00 nom, e 0.65, A max 0.90, 7 pads per side, "
    "no exposed pad).",
    "LGA-13 (5x5)": "Si82Ex-datasheet.pdf Figure 49 and Si827x.pdf Figure 33 (identical drawings): 5 +/- 0.075 mm "
    "square, 0.83 +/- 0.1 mm high, 0.65 mm pitch, 7 pad positions per side. The bottom view and the pinouts "
    "(Si82Ex Figures 9-12, Si827x Figures 2-3) leave the position opposite pin 4 empty: pins 8-10 at positions "
    "8-10, pins 11-13 at positions 12-14. Not the same body as TI's LGA-13 NPL (1.0 mm high).",
    "DIP-8 GW": "Si826x.pdf Table 17: D 9.40-9.90, E1 6.10-6.60, E2 (lead span) 9.40-9.90, A max 4.19, e 2.54.",
    "SDIP-6": "Si826x.pdf Table 19: D 4.58, E1 7.50, E 11.50, A max 2.65, e 1.27.",
    "SSOP-36W": "Si829x-product-summary.pdf Table 8: D 15.20-15.60, E1 7.40-7.60, E 10.05-10.55, A max 2.65, "
    "e 0.80.",
    "SOIC-24W": "Si8281-82-83-84.pdf section 6.3 (JEDEC MS-013 AD): D 15.40, E1 7.50, E 10.30, A max 2.65.",
}

# Land patterns of the new bodies (format of data/mechanical.yaml)
MECHANICAL = {
    "SOIC-24W": {
        "lead_width_mm": [0.31, 0.51], "lead_length_mm": [0.40, 1.27], "sides": 2,
        "source": "Si8281-82-83-84.pdf section 6.3",
        "land_patterns": [{"name": "Recommended", "pad_length_mm": 1.90, "pad_width_mm": 0.60,
                           "row_spacing_mm": 9.40, "source": "Si8281-82-83-84.pdf Table 6.2"}],
    },
    "DFN-14 (5x5)": {
        "lead_width_mm": [0.25, 0.35], "lead_length_mm": [0.50, 0.70], "sides": 2,
        "source": "Si823Hx-DataSheet.pdf Table 7.5",
        "note": "b = pad width, L = pad length; pads pulled back L1 0.05-0.15 from the body edge; no exposed pad",
        "land_patterns": [{"name": "Recommended", "pad_length_mm": 0.80, "pad_width_mm": 0.40,
                           "row_spacing_mm": 4.20, "source": "Si823Hx-DataSheet.pdf Table 8.5",
                           "note": "X1 0.80 is the pad dimension along the lead, Y1 0.40 across it (Figure 8.5); "
                           "NSMD pads"}],
    },
    "LGA-13 (5x5)": {
        "lead_width_mm": [0.25, 0.35], "lead_length_mm": [0.55, 0.75], "sides": 2,
        "source": "Si82Ex-datasheet.pdf Figure 49 (Detail A: pad 0.3 +/- 0.05 x 0.65 +/- 0.1)",
        "note": "pad positions 0.65 mm apart, 13 of 14 used (position opposite pin 4 empty)",
        "land_patterns": [{"name": "Recommended", "pad_length_mm": 0.65, "pad_width_mm": 0.30,
                           "row_spacing_mm": 4.15, "source": "Si82Ex-datasheet.pdf Figure 52 (metallization, "
                           "13X 2.075 from the centre line)"}],
    },
    "DIP-8 GW": {
        "lead_width_mm": [0.35, 0.55], "lead_length_mm": [0.38, 0.89], "sides": 2,
        "source": "Si826x.pdf Table 17",
        "land_patterns": [{"name": "Recommended", "pad_length_mm": 1.70, "pad_width_mm": 0.65,
                           "row_spacing_mm": 8.90, "source": "Si826x.pdf Table 18",
                           "note": "Table 18 gives min-max (C 8.85-8.90, X 0.60-0.65, Y 1.65-1.70); max used"}],
    },
    "SDIP-6": {
        "lead_width_mm": [0.31, 0.51], "lead_length_mm": [0.40, 1.27], "sides": 2,
        "source": "Si826x.pdf Table 19",
        "land_patterns": [{"name": "Recommended", "pad_length_mm": 2.05, "pad_width_mm": 0.60,
                           "row_spacing_mm": 10.50, "source": "Si826x.pdf Table 20",
                           "note": "Table 20 gives min-max (C 10.45-10.50, X 0.55-0.60, Y 2.00-2.05); max used"}],
    },
    "SSOP-36W": {
        "lead_width_mm": [0.25, 0.35], "lead_length_mm": [0.40, 1.27], "sides": 2,
        "source": "Si829x-product-summary.pdf Table 8",
        "note": "no land pattern in the product summary",
    },
}

# ------------------------------------------------------------------ pinouts


def to14(p16: list[str]) -> list[str]:
    """WB SOIC-14 (IS3) bond-out of a 16-pin pinout: positions 12 and 13 (NC) have no lead."""
    assert p16[11] == p16[12] == "NC", p16
    return p16[:11] + p16[13:]


def dual16(in1, in2, p5, p6, p7="NC", p8="VDDI"):
    return [in1, in2, "VDDI", "GNDI", p5, p6, p7, p8, "GNDB", "VOB", "VDDB", "NC", "NC", "GNDA", "VOA", "VDDA"]


def soic8(*pins):
    return list(pins)


# ------------------------------------------------------------------ helpers


@cache
def page_texts(pdf: str) -> list[str]:
    out = subprocess.run(["pdftotext", "-layout", str(PDF_DIR / pdf), "-"], capture_output=True, text=True,
                         check=True).stdout
    return out.split("\f")


def page_of(pdf: str, needle: str) -> int | None:
    """First page (1-based) whose text contains ``needle`` (whitespace-insensitive), skipping the contents."""
    pat = re.compile(r"\s+".join(map(re.escape, needle.split())))
    hits = [i + 1 for i, t in enumerate(page_texts(pdf)) if pat.search(t)]
    real = [p for p in hits if not re.search(r"\.\s\.\s\.\s\.", page_texts(pdf)[p - 1])]
    return (real or hits or [None])[0]


def src(pdf: str, needle: str, what: str) -> str:
    p = page_of(pdf, needle)
    return f"{pdf} p.{p} ({what})" if p else f"{pdf} ({what})"


def ordering_rows(pdf: str, pattern: str) -> dict[str, str]:
    """OPN -> the text of its ordering-guide row, for every OPN in the PDF that matches ``pattern``."""
    rows = {}
    for text in page_texts(pdf):
        if not re.search(r"Ordering\s+Guide", text) or re.search(r"\.\s\.\s\.\s\.", text):
            continue  # ordering-guide pages only (not the contents or revision history)
        for line in text.splitlines():
            if not re.match(pattern, line.strip()):
                continue  # table rows start with the ordering code
            for m in re.finditer(pattern, line):
                rows.setdefault(m.group(0), line)
    return rows


def sha256(pdf: str) -> str:
    return hashlib.sha256((PDF_DIR / pdf).read_bytes()).hexdigest()


def base_name(opn: str) -> str:
    """Catalogue spelling: no die revision letter (Si8220BB-D-IS -> Si8220BB-IS)."""
    return re.sub(r"-[A-Z]-", "-", opn)


# ------------------------------------------------------------------ series decoders
# Each returns (package, pinout, params, description, notes) for one ordering code.

UVLO_GBCE = {"G": 4, "B": 8, "C": 12, "E": 15}


def common(qual_auto: bool, temp=(-40, 125)) -> dict:
    return {"qualification": "automotive" if qual_auto else "industrial", "temp_range_c": list(temp)}


def decode_si8239x(opn: str, row: str):
    m = re.fullmatch(r"Si8239(\d)([ABC])([BD])(4?)-(I|A)S(\d?)", opn)
    n, u, iso, dg4, grade, suf = m.groups()
    n = int(n)
    uvlo = {"A": 6, "B": 8, "C": 12}[u]
    pkg = {"1": "SOIC-16N", "": "SOIC-16W", "3": "SOIC-14W (IS3)"}[suf]
    pwm = n in (4, 8)
    if pwm:
        p16 = dual16("PWM", "NC", "EN", "DT", "RDY")
    elif n == 7:
        p16 = dual16("VIA", "VIB", "EN", "NC", "NC")
    else:
        p16 = dual16("VIA", "VIB", "EN", "NC", "RDY")
    pin = to14(p16) if pkg.startswith("SOIC-14") else p16
    hsls = n in (2, 3, 4, 8)
    deglitch = n == 3 or dg4 == "4"
    prot = ["UVLO"] + (["overlap protection"] if hsls else []) + ["enable"]
    prot += ["programmable dead time"] if pwm else []
    prot += ["input glitch filter"] if deglitch else []
    p = {
        "isolation_rating_kvrms": {"B": 2.5, "D": 5.0}[iso],
        "isolation_class": "basic",
        "creepage_mm": 4.01 if pkg == "SOIC-16N" else 8.0,
        **common(grade == "A"),
        "cmti_kv_us": 35,
        "channel_config": "dual",
        "input_type": "PWM input" if pwm else "dual input",
        "peak_source_a": 2.0,
        "peak_sink_a": 4.0,
        "uvlo_v": uvlo,
        "output_supply_v": [6.5, 24],
        "protection": prot,
        "deadtime": "programmable" if pwm else "none",
        "theta_ja_c_w": 63 if pkg == "SOIC-16N" else 59,
        "iq_ma": 1.5 if n == 7 else 2.8,
        "rise_time_ns": 12,
        "fall_time_ns": 12,
        "pwd_ns": 5.6,
    }
    if pwm:
        p["prop_delay_ns"] = 135 if dg4 else 55
    elif n != 3:
        p["prop_delay_ns"] = 40
    kind = {0: "dual driver, enhanced UVLO, RDY", 1: "dual driver, enhanced UVLO, RDY", 2: "HS/LS driver, RDY",
            3: "HS/LS driver, enhanced UVLO, RDY, deglitch", 4: "PWM-input HS/LS driver, RDY",
            5: "dual driver, RDY", 6: "dual driver, RDY", 7: "dual driver"}.get(n, "PWM-input HS/LS driver, RDY")
    if pwm:
        kind += ", 40-600 ns dead time, deglitch" if dg4 else ", 10-200 ns dead time"
    if n in (0, 4, 5, 7):
        kind += ", 1 ms delayed start-up"
    desc = f"Si8239{n} 4.0 A isolated {kind}, {uvlo} V UVLO, {p['isolation_rating_kvrms']:g} kVrms"
    notes = None
    if n == 3:
        notes = ("Propagation delay omitted: Table 4.1 gives 20-40 ns for Si82390/1/2/3/5/6/7 'with no de-glitch', "
                 "but Si82393 has the de-glitch option and no separate value is given.")
    return pkg, pin, p, desc, notes


def decode_si823hx(opn: str, row: str):
    m = re.fullmatch(r"Si823H(\d)([ABCT])([BCD])-(I|A)([SM])(\d?)", opn)
    n, u, iso, grade, sm, suf = m.groups()
    n = int(n)
    t = "T" if u == "T" else ""  # Si823H9T: 12 V UVLO, DIS input, single VO output
    uvlo = {"A": 6, "B": 8, "C": 12, "T": 12}[u]
    en = "DIS" if t or n in (1, 3, 6, 8) else "EN"
    if sm == "M":
        pkg = "DFN-14 (5x5)"
    elif n == 9:
        pkg = "SSO-8" if suf == "4" else "SOIC-8N"
    else:
        pkg = {"1": "SOIC-16N", "3": "SOIC-14W (IS3)"}[suf]
    pwm = n in (4, 8)
    hsls = n in (1, 2, 3, 4, 8)
    if n == 9:
        pin = (soic8("VDDI", "VI", "DIS", "GNDI", "VDD", "VO", "NC", "GND") if t else
               soic8("VI", "VDDI", "GNDI", "EN", "GND", "VO-", "VO+", "VDD"))
    elif pkg.startswith("DFN"):
        pin = ["GNDI", "PWM" if pwm else "VIA", "VIB", "VDDI", en, "DT" if hsls else "NC", "VDDI", "GNDB", "VOB",
               "VDDB", "NC", "GNDA", "VOA", "VDDA"]
    else:
        p16 = dual16("PWM", "NC", en, "DT") if pwm else dual16("VIA", "VIB", en, "DT" if hsls else "NC")
        pin = to14(p16) if pkg.startswith("SOIC-14") else p16
    prot = ["UVLO"] + (["overlap protection"] if hsls else []) + ["disable" if en == "DIS" else "enable"]
    prot += ["programmable dead time"] if hsls else []
    prot += ["input glitch filter"] if n == 3 else []
    p = {
        "isolation_rating_kvrms": {"B": 2.5, "C": 3.75, "D": 5.0}[iso],
        "creepage_mm": {"SOIC-16N": 3.9, "SOIC-8N": 3.9, "SSO-8": 8.0, "SOIC-14W (IS3)": 8.0, "DFN-14 (5x5)": 3.5}[pkg],
        **common(grade == "A"),
        "cmti_kv_us": 125,
        "channel_config": "single" if n == 9 else "dual",
        "input_type": "single input" if n == 9 else "PWM input" if pwm else "dual input",
        "peak_source_a": 4.0,
        "peak_sink_a": 4.0,
        "uvlo_v": uvlo,
        "output_supply_v": [5.5, 30],
        "prop_delay_ns": 116 if n == 3 else 58 if pwm else 30,
        "protection": prot,
        "deadtime": "programmable" if hsls else "none",
        "theta_ja_c_w": {"SOIC-16N": 63, "SOIC-8N": 110, "SSO-8": 90, "SOIC-14W (IS3)": 59, "DFN-14 (5x5)": 105}[pkg],
        "iq_ma": 1.3,
        "rise_time_ns": 12,
        "fall_time_ns": 12,
    }
    if not pwm:
        p["pwd_ns"] = 10 if n == 3 else 5
    kind = ("single driver" + (" (VO+/VO- split outputs)" if not t else "") if n == 9 else
            "PWM-input HS/LS driver" if pwm else "HS/LS driver" if hsls else "dual driver")
    if n == 3:
        kind += ", deglitch"
    if n == 7:
        kind += ", 1 ms delayed start-up"
    desc = f"Si823H{n}{t} 4.0 A isolated {kind}, {en}, {uvlo} V UVLO, {p['isolation_rating_kvrms']:g} kVrms"
    notes = None
    if pkg.startswith("DFN") and pwm:
        notes = "Figure 6.4 labels DFN-14 pin 3 'VIB' for all of Si823H1/3/5/6/8; transcribed as printed."
    return pkg, pin, p, desc, notes


def decode_si8252x(opn: str, row: str):
    m = re.fullmatch(r"Si8252([01])([ABC])D-(I|A)S3", opn)
    n, u, grade = m.groups()
    uvlo = {"A": 5, "B": 8, "C": 12}[u]
    en = "DIS" if n == "0" else "EN"
    pin = ["VIA", "VIB", "VDDIH", "GNDI", en, "DT", "NC", "VDDIH", "GNDB", "VOB", "VDDB", "GNDA", "VOA", "VDDA"]
    p = {
        "isolation_rating_kvrms": 5.0, "creepage_mm": 8.0, **common(grade == "A"), "cmti_kv_us": 125,
        "channel_config": "dual", "input_type": "dual input", "peak_source_a": 4.0, "peak_sink_a": 4.0,
        "uvlo_v": uvlo, "output_supply_v": [5.5, 30], "prop_delay_ns": 30,
        "protection": ["UVLO", "overlap protection", "disable" if en == "DIS" else "enable",
                       "programmable dead time"],
        "deadtime": "programmable", "theta_ja_c_w": 59, "iq_ma": 1.3, "rise_time_ns": 12, "fall_time_ns": 12,
        "pwd_ns": 5.6,
    }
    desc = f"Si8252{n} 4.0 A isolated HS/LS driver, 4.5-20 V VDDIH, {en}, {uvlo} V UVLO, 5 kVrms, WB SOIC-14"
    return "SOIC-14W (IS3)", pin, p, desc, None


def decode_si827x(opn: str, row: str):
    m = re.fullmatch(r"Si827([1345])([ABDG])([AB])([14]?)(D?)-(I|A|Z)([SM])(\d?)", opn)
    n, u, iso, dt, dg, grade, sm, suf = m.groups()
    n = int(n)
    uvlo = {"G": 3, "A": 5, "B": 8, "D": 12}[u]
    lga = sm == "M"
    pkg = "LGA-13 (5x5)" if lga else "SOIC-8N" if n == 1 else "SOIC-16N"
    if n == 1:
        pin = soic8("VI", "VDDI", "GNDI", "EN", "GND", "VO-", "VO+", "VDD")
    elif n == 4:
        pin = (["NC", "PWM", "NC", "GNDI", "EN", "DT", "VDDI", "GNDB", "VOB", "VDDB", "GNDA", "VOA", "VDDA"] if lga
               else dual16("PWM", "NC", "EN", "DT"))
    else:
        pin = (["NC", "VIA", "VIB", "GNDI", "EN", "NC", "VDDI", "GNDB", "VOB", "VDDB", "GNDA", "VOA", "VDDA"] if lga
               else dual16("VIA", "VIB", "EN", "NC"))
    deglitch = dg == "D"
    hsls = n in (3, 4)
    prot = ["UVLO"] + (["overlap protection"] if hsls else []) + ["enable"]
    prot += ["programmable dead time"] if n == 4 else []
    prot += ["input glitch filter"] if deglitch else []
    p = {
        "isolation_rating_kvrms": {"A": 1.0, "B": 2.5}[iso],
        "isolation_class": "basic",
        "creepage_mm": 3.5 if lga else 3.9,
        **common(grade == "A", (-55, 125) if grade == "Z" else (-40, 125)),
        "cmti_kv_us": 200 if deglitch else 150,
        "channel_config": "single" if n == 1 else "dual",
        "input_type": "single input" if n == 1 else "PWM input" if n == 4 else "dual input",
        "peak_source_a": 1.8,
        "peak_sink_a": 4.0,
        "uvlo_v": uvlo,
        "output_supply_v": [4.2, 30],
        "prop_delay_ns": (105 if deglitch else 75) if n == 4 else (75 if deglitch else 60),
        "protection": prot,
        "deadtime": "programmable" if n == 4 else "none",
        "theta_ja_c_w": 109 if lga else 115 if n == 1 else 104,
        "iq_ma": 7.9,
        "rise_time_ns": 10.5,
        "fall_time_ns": 13.3,
        "pwd_ns": (47 if deglitch else 19) if n == 4 else 8,
    }
    kind = {1: "single driver (VO+/VO- split outputs)", 3: "HS/LS driver", 4: "PWM-input HS/LS driver",
            5: "dual driver"}[n]
    if n == 4:
        kind += ", 10-200 ns dead time" if dt == "1" else ", 20-700 ns dead time"
    kind += ", deglitch" if deglitch else ", low jitter"
    desc = f"Si827{n} 4.0 A isolated {kind}, {uvlo} V UVLO, {p['isolation_rating_kvrms']:g} kVrms"
    notes = "-ZS: -55 to +125 C ambient, no automotive-grade code (ordering guide note 7)." if grade == "Z" else None
    return pkg, pin, p, desc, notes


def decode_si826x(opn: str, row: str):
    m = re.fullmatch(r"Si8261([AB])([ABC])([CD])(?:-C)?-(I|A)([SP])", opn)
    drv, u, iso, grade, sp = m.groups()
    uvlo = {"A": 5, "B": 8, "C": 12}[u]
    pkg = "SDIP-6" if iso == "D" else "DIP-8 GW" if sp == "P" else "SOIC-8N"
    pin = (["ANODE", "NC", "CATHODE", "GND", "VO", "VDD"] if pkg == "SDIP-6" else
           ["NC", "ANODE", "CATHODE", "NC", "GND", "VO", "VO", "VDD"])
    p = {
        "isolation_rating_kvrms": {"C": 3.75, "D": 5.0}[iso], "isolation_class": "reinforced",
        "creepage_mm": {"SOIC-8N": 3.9, "DIP-8 GW": 7.0, "SDIP-6": 8.3}[pkg], **common(grade == "A"),
        "cmti_kv_us": 35, "channel_config": "single", "input_type": "LED emulator input",
        "peak_source_a": 0.4 if drv == "A" else 1.8, "peak_sink_a": 0.6 if drv == "A" else 4.0, "uvlo_v": uvlo,
        "output_supply_v": [6.5, 30], "prop_delay_ns": 60, "protection": ["UVLO", "input glitch filter"],
        "theta_ja_c_w": 105 if pkg == "SDIP-6" else 110, "rise_time_ns": 5.5, "fall_time_ns": 8.5, "pwd_ns": 28,
    }
    desc = (f"Si8261 {'0.6' if drv == 'A' else '4.0'} A isolated gate driver with LED emulator (opto-compatible) "
            f"input, {uvlo} V UVLO, {p['isolation_rating_kvrms']:g} kVrms")
    return pkg, pin, p, desc, None


def decode_si8220(opn: str, row: str):
    m = re.fullmatch(r"Si822([01])([BCD])([BCD])-D-IS", opn)
    n, u, iso = m.groups()
    uvlo = {"B": 8, "C": 10, "D": 12.5}[u]
    wb = iso == "D"
    pin = (["CATHODE", "NC", "NC", "ANODE", "NC", "NC", "CATHODE", "NC", "VSS", "NC", "NC", "NC", "VO", "NC", "VDD",
            "VSS"] if wb else ["NC", "ANODE", "CATHODE", "NC", "VSS", "VO", "VO", "VDD"])
    big = n == "0"
    p = {
        "isolation_rating_kvrms": {"B": 2.5, "C": 3.75, "D": 5.0}[iso], "isolation_class": "basic",
        "creepage_mm": 8.0 if wb else 4.01, **common(False), "channel_config": "single",
        "input_type": "LED emulator input", "peak_source_a": 1.5 if big else 0.3, "peak_sink_a": 2.5 if big else 0.5,
        "uvlo_v": uvlo, "output_supply_v": [6.5, 24], "prop_delay_ns": 60, "protection": ["UVLO"],
        "theta_ja_c_w": 100 if wb else 140, "rise_time_ns": 20 if big else 30, "fall_time_ns": 20 if big else 30,
    }
    desc = (f"Si822{n} {'2.5' if big else '0.5'} A isolated gate driver with opto (LED emulator) input, {uvlo:g} V "
            f"UVLO, {p['isolation_rating_kvrms']:g} kVrms")
    notes = "CMTI omitted: Table 1 gives only a typical 30 kV/us. Rise/fall time = Table 1 maximum (no typical)."
    return ("SOIC-16W" if wb else "SOIC-8N"), pin, p, desc, notes


def decode_si8281(opn: str, row: str):
    m = re.fullmatch(r"Si828([1234])([BCDE])([CD])-(I|A)S", opn)
    n, u, iso, grade = m.groups()
    n = int(n)
    uvlo = {"B": 9, "C": 12, "D": 13, "E": 15}[u]
    sw = ["VSW", "VDDP"] if n in (1, 3) else ["RSN", "ESW"]
    if n in (1, 2):
        pkg = "SOIC-20W"
        pin = ["GNDP", *sw, "VDDA", "GNDA", "RSTb", "FLTb", "RDY", "IN+", "IN-", "VSSB", "VMID", "CLMP", "VL", "VH",
               "VDDB", "DSAT", "NC", "COMP", "VSNS"]
    else:
        pkg = "SOIC-24W"
        pin = ["GNDP", *sw, "VDDA", "SH/FC", "SS", "GNDA", "RSTb", "FLTb", "RDY", "IN+", "IN-", "VSSB", "NC", "VSSB",
               "VMID", "CLMP", "VL", "VH", "VDDB", "DSAT", "NC", "COMP", "VSNS"]
    p = {
        "isolation_rating_kvrms": {"C": 3.75, "D": 5.0}[iso], "creepage_mm": 8.0, **common(grade == "A"),
        "cmti_kv_us": 125, "channel_config": "single", "input_type": "complementary input", "peak_source_a": 2.7,
        "peak_sink_a": 5.5, "uvlo_v": uvlo, "output_supply_v": [{9: 10.0, 12: 13.2, 13: 14.0, 15: 16.0}[uvlo], 30],
        "prop_delay_ns": 50, "protection": ["UVLO", "desaturation", "soft shutdown", "Miller clamp"],
        "theta_ja_c_w": 74, "iq_ma": 6.8, "rise_time_ns": 5.5, "fall_time_ns": 8.5, "pwd_ns": 5,
    }
    dcdc = "integrated switch" if n in (1, 3) else "external switch"
    extra = ", shutdown/frequency/soft-start control" if n in (3, 4) else ""
    desc = (f"Si828{n} 4 A isolated single gate driver with DESAT, soft shutdown, Miller clamp and integrated DC-DC "
            f"controller ({dcdc}{extra}), {uvlo} V UVLO, {p['isolation_rating_kvrms']:g} kVrms")
    return pkg, pin, p, desc, None


def decode_si8285(opn: str, row: str):
    m = re.fullmatch(r"Si828([56])([BCDE])([CD])-(I|A)S", opn)
    n, u, iso, grade = m.groups()
    uvlo = {"B": 9, "C": 12, "D": 13, "E": 15}[u]
    if n == "5":
        pin = ["GNDA", "VDDA", "NC", "RSTb", "FLTb", "RDY", "IN+", "IN-", "VSSB", "VMID", "CLMP", "VL", "VH", "VDDB",
               "DSAT", "NC"]
    else:
        pin = ["IN+", "IN-", "VDDA", "GNDA", "RSTb", "FLTb", "NC", "NC", "VSSB", "VSSB", "VO", "VDDB", "VDDB", "DSAT",
               "NC", "VMID"]
    p = {
        "isolation_rating_kvrms": {"C": 3.75, "D": 5.0}[iso], "isolation_class": "basic", "creepage_mm": 8.0,
        **common(grade == "A"), "cmti_kv_us": 125, "channel_config": "single", "input_type": "complementary input",
        "peak_source_a": 2.7, "peak_sink_a": 5.5, "uvlo_v": uvlo,
        "output_supply_v": [{9: 10.0, 12: 13.2, 13: 14.0, 15: 16.0}[uvlo], 30], "prop_delay_ns": 50,
        "protection": ["UVLO", "desaturation", "soft shutdown"] + (["Miller clamp"] if n == "5" else []),
        "theta_ja_c_w": 73, "iq_ma": 2.6, "rise_time_ns": 5.5, "fall_time_ns": 8.5, "pwd_ns": 5,
    }
    what = "split VH/VL outputs, Miller clamp, RDY" if n == "5" else "single VO output, HCPL-316J pin-compatible"
    desc = (f"Si828{n} 4 A isolated single gate driver with DESAT and soft shutdown, {what}, {uvlo} V UVLO, "
            f"{p['isolation_rating_kvrms']:g} kVrms, WB SOIC-16")
    return "SOIC-16W", pin, p, desc, None


# Si82Ax-Fx (shared ordering-code scheme: Si82<X><nn><deglitch><UVLO><isolation>-<grade><S|M><package>)

SINGLE_PINS = {
    "28": ("VDDI", "VI", "DIS", "GNDI", "GND", "NC", "VO", "VDD"),
    "30": ("VDDI", "VI", "EN", "GNDI", "VDD", "VO+", "VO-", "GND"),
    "40": ("VDDI", "VI+", "VI-", "GNDI", "VDD", "VO+", "VO-", "GND"),
    "41": ("VDDI", "VI+", "VI-", "GNDI", "VDD", "VO", "MC", "GND"),
    "43": ("VDDI", "VI+", "VI-", "GNDI", "GND", "VDD", "VO+", "VO-"),
    "44": ("VDDI", "VI+", "VI-", "GNDI", "GND", "VDD", "VO", "MC"),
    "47": ("VDDI", "VI+", "VI-", "GNDI", "GND", "MC", "VO", "VDD"),
    "50": ("VDDI", "VI", "SPD±", "GNDI", "VDD", "VO+", "VO-", "GND"),
    "60": ("VDDI", "VI", "SPD+", "GNDI", "VDD", "VO+", "VO-", "GND"),
    "70": ("VDDI", "VI", "SPD-", "GNDI", "VDD", "VO+", "VO-", "GND"),
}

# per series: peak (source, sink) or per-UVLO peaks, prop delay max per deglitch code, rise/fall, iq, theta, notes
VCD_PEAK = {4: 1.5, 8: 2.5, 12: 3.5, 15: 4.0}  # SelVCD speed 7, both directions
VCD_RISE_FALL = {4: (16, 22), 8: (16, 19), 12: (17, 18), 15: (17, 20)}
SI82X = {
    "A": dict(peak=(1.16, 1.09), prop={"A": 31.4, "B": 55.8}, rf=(18.5, 14.5), iq=0.81,
              theta={"SOIC-8N": 104, "SSO-8": 103}, drive="1 A voltage-mode"),
    "B": dict(peak=(7.5, 7.5), prop={"A": 38.2, "B": 63.1}, rf=(8.3, 8.6), iq=0.81,
              theta={"SOIC-8N": 101, "SSO-8": 99}, drive="6 A voltage-mode"),
    "C": dict(peak=None, prop={"A": 43.4, "B": 72.6, "E": 144}, rf=None, iq=1.15,
              theta={"SOIC-8N": 101, "SSO-8": 99}, drive="SelVCD current-source"),
    "D": dict(peak=(1.16, 1.09), prop={"A": 32, "B": 58}, rf=(18.5, 14.5), iq=1.03,
              theta={"SOIC-16N": 61, "SOIC-14W (IS3)": 69}, drive="1 A voltage-mode"),
    "E": dict(peak=(7.5, 7.5), prop={"A": 40, "B": 65}, rf=(8.3, 8.6), iq=1.03,
              theta={"SOIC-16N": 63, "SOIC-14W (IS3)": 59, "LGA-13 (5x5)": 116}, drive="6 A voltage-mode"),
    "F": dict(peak=None, prop={"A": 40, "B": 65, "E": 140}, rf=None, iq=1.57,
              theta={"SOIC-16N": 63, "SOIC-14W (IS3)": 59}, drive="SelVCD current-source"),
}


def decode_si82x(opn: str, row: str):
    m = re.fullmatch(r"Si82([A-F])(\d\d)([ABE])([GBCE])([BCE])-(I|A)([SM])(\d?)", opn)
    x, nn, dg, u, iso, grade, sm, suf = m.groups()
    cfg = SI82X[x]
    uvlo = UVLO_GBCE[u]
    single = x in "ABC"
    if single:
        pkg = "SSO-8" if suf == "4" else "SOIC-8N"
        pin = list(SINGLE_PINS[nn])
    else:
        pkg = "LGA-13 (5x5)" if sm == "M" else "SOIC-14W (IS3)" if suf == "3" else "SOIC-16N"
        pwm = nn[0] in "89"
        en = "DIS" if nn[0] in "28" else "EN"
        if pkg.startswith("LGA"):
            pin = ["GNDI", "PWM" if pwm else "VIA", "NC" if pwm else "VIB", "VDDI", en, "DT", "VDDI", "GNDB", "VOB",
                   "VDDB", "GNDA", "VOA", "VDDA"]
        else:
            p7, p8 = ("SPD-", "SPD+") if x == "F" else ("NC", "VDDI")
            p16 = dual16("PWM", "NC", en, "DT", p7, p8) if pwm else dual16("VIA", "VIB", en, "DT", p7, p8)
            pin = to14(p16) if pkg.startswith("SOIC-14") else p16
    mc = x in "CF" or nn in ("41", "44", "47")
    if cfg["peak"]:
        src_a, sink_a = cfg["peak"]
        if mc and x == "B":
            sink_a = 3.66
    else:
        src_a = sink_a = VCD_PEAK[uvlo]
    rise, fall = cfg["rf"] or VCD_RISE_FALL[uvlo]
    if x == "B" and mc:
        fall = 7.5
    prot = ["UVLO"]
    if single:
        comp = nn[0] == "4"
        prot += ["overlap protection"] if comp else []
        prot += ["disable"] if nn == "28" or x == "C" else ["enable"] if nn == "30" else []
        input_type = "complementary input" if comp else "single input"
    else:
        prot += ["overlap protection", "disable" if en == "DIS" else "enable", "programmable dead time"]
        input_type = "PWM input" if pwm else "dual input"
    prot += ["Miller clamp"] if mc else []
    prot += ["input glitch filter"] if dg != "A" else []
    lga = pkg.startswith("LGA")
    p = {
        "isolation_rating_kvrms": {"B": 2.5, "C": 3.75, "E": 6.0}[iso],
        **({} if lga else {"isolation_class": "reinforced"}),
        **({} if lga else {"creepage_mm": 8.0 if pkg in ("SSO-8", "SOIC-14W (IS3)") else 3.9}),
        **common(grade == "A"),
        "cmti_kv_us": 200,
        "channel_config": "single" if single else "dual",
        "input_type": input_type,
        "peak_source_a": src_a,
        "peak_sink_a": sink_a,
        "uvlo_v": uvlo,
        "output_supply_v": [5, 30],
        "prop_delay_ns": cfg["prop"][dg],
        "protection": prot,
        **({} if single else {"deadtime": "programmable"}),
        "theta_ja_c_w": cfg["theta"][pkg],
        "iq_ma": cfg["iq"],
        "rise_time_ns": rise,
        "fall_time_ns": fall,
        "pwd_ns": 10,
    }
    if single:
        outs = {"28": "VO output, DIS", "30": "VO+/VO- split outputs, EN", "40": "VO+/VO- split outputs",
                "41": "VO output + Miller clamp pin", "43": "VO+/VO- split outputs (alternate pinout)",
                "44": "VO output + Miller clamp pin (alternate pinout)",
                "47": "VO output + Miller clamp pin (alternate pinout)", "50": "VO+/VO- outputs, SPD± drive select",
                "60": "VO+/VO- outputs, SPD+ drive select", "70": "VO+/VO- outputs, SPD- drive select"}[nn]
        kind = f"single-channel {cfg['drive']} gate driver, {'VI+/VI-' if nn[0] == '4' else 'VI'} input, {outs}"
    else:
        kind = (f"dual-channel {cfg['drive']} gate driver, {'PWM input HS/LS' if pwm else 'universal VIA/VIB'}, "
                f"{en}, programmable dead time")
    dgl = {"A": "", "B": ", 30 ns deglitch", "E": ", 90 ns deglitch"}[dg]
    desc = f"Si82{x}{nn} {kind}{dgl}, {uvlo} V UVLO, {p['isolation_rating_kvrms']:g} kVrms"
    notes = None
    if lga:
        notes = ("LGA-13: the datasheet gives no creepage / IEC 60747-17 data for this package (Tables 11 and 13 "
                 "cover NB SOIC-16 and WB SOIC-14 only).")
    return pkg, pin, p, desc, notes


def decode_si829x(opn: str, row: str):
    m = re.fullmatch(r"Si82900([AB])([AB])-AU", opn)
    if not m:
        return None  # Si82910/11/13: two-package chipset (input side + output side), not a single driver
    vpos, spi = m.groups()
    pin = ["CSb", "SCLK", "SDO", "SDI", "GNDI", "GNDI", "FLT1b", "FLT2b", "VDDI", "GNDI", "IN_MON", "IN", "FOS",
           "FOS_SEL", "RSTb", "AOUT2", "AOUT1", "ENUM", "VGREG", "VOLF", "GNDR", "MCOUT", "GNDO_PWR", "GM", "MID", "VO",
           "VDDO_PWR", "VOHF", "VDREG", "VDDR", "GNDR", "TV1/VREF", "TV2/FOSX_SEL", "IV1", "IV2/FOSX", "DESAT"]
    p = {
        "isolation_rating_kvrms": 6.0, "isolation_class": "reinforced", **common(True), "channel_config": "single",
        "input_type": "single input", "peak_source_a": 15, "peak_sink_a": 15, "output_supply_v": [18, 30],
        "protection": ["UVLO", "overlap protection", "programmable dead time", "input glitch filter", "Miller clamp",
                       "desaturation", "soft shutdown"],
        "deadtime": "programmable",
    }
    desc = (f"Si82900 15 A SPI-configurable isolated safety gate driver (ProVCD, ISO 26262) for EV traction "
            f"inverters, VPOS regulator {'enabled' if vpos == 'A' else 'disabled'}, "
            f"{'chip select / enumeration' if spi == 'A' else 'daisy-chain'} SPI addressing, 6 kVRMS")
    notes = ("From the Si829x product summary (no full datasheet is public): output current and UVLO are "
             "SPI-programmable, so UVLO, CMTI minimum, delays and creepage are not given. Peak current = the "
             "15 A maximum constant sink/source current.")
    return "SSOP-36W", pin, p, desc, notes


# series key -> (decoder, OPN regex in the ordering guide, uvlo/isolation check columns)
SERIES = {
    "si8239x": (decode_si8239x, r"Si8239\d[ABC][BD]4?-[IA]S\d?\b"),
    "si823hx": (decode_si823hx, r"Si823H\d[ABCT][BCD]-[IA][SM]\d?\b"),
    "si8252x": (decode_si8252x, r"Si8252[01][ABC]D-[IA]S3\b"),
    "si827x": (decode_si827x, r"Si827[1345][ABDG][AB][14]?D?-[IAZ][SM]\d?\b"),
    "si826x": (decode_si826x, r"Si8261[AB][ABC][CD](?:-C-I[SP]|-A[SP])\b"),
    "si8220": (decode_si8220, r"Si822[01][BCD][BCD]-D-IS\b"),
    "si8281": (decode_si8281, r"Si828[1-4][BCDE][CD]-[IA]S\b"),
    "si8285": (decode_si8285, r"Si828[56][BCDE][CD]-[IA]S\b"),
    "si82ax": (decode_si82x, r"Si82A\d\d[ABE][GBCE][BCE]-[IA][SM]\d?\b"),
    "si82bx": (decode_si82x, r"Si82B\d\d[ABE][GBCE][BCE]-[IA][SM]\d?\b"),
    "si82cx": (decode_si82x, r"Si82C\d\d[ABE][GBCE][BCE]-[IA][SM]\d?\b"),
    "si82dx": (decode_si82x, r"Si82D\d\d[ABE][GBCE][BCE]-[IA][SM]\d?\b"),
    "si82ex": (decode_si82x, r"Si82E\d\d[ABE][GBCE][BCE]-[IA][SM]\d?\b"),
    "si82fx": (decode_si82x, r"Si82F\d\d[ABE][GBCE][BCE]-[IA][SM]\d?\b"),
    "si829x": (decode_si829x, r"Si829\d\d[AB]?[AB]-A[UF]\b"),
}

# ------------------------------------------------------------------ parameter sources (table titles)

SOURCES = {
    "si8239x": {
        "isolation_rating_kvrms": ("Top Marking Explanation", "top marking: B = 2.5 kV, D = 5.0 kV"),
        "isolation_class": ("Table 4.2. Regulatory Information", "VDE 0884-10 basic insulation"),
        "creepage_mm": ("Table 4.3. Insulation and Safety-Related", "Table 4.3"),
        "qualification": ("Industrial and Automotive Grade OPNs", "ordering guide: -A codes AEC-Q100"),
        "cmti_kv_us": ("Common Mode Transient Immunity", "Table 4.1, min"),
        "channel_config": ("Table 1.1. Si8239x Ordering Guide", "ordering guide"),
        "input_type": ("Table 1.1. Si8239x Ordering Guide", "ordering guide"),
        "peak_source_a": ("Output Short-Circuit Pulsed Source", "Table 4.1, IOH test (Figure 4.2), typ"),
        "peak_sink_a": ("Output Short-Circuit Pulsed Source", "Table 4.1, IOL test (Figure 4.1), typ"),
        "uvlo_v": ("Table 1.1. Si8239x Ordering Guide", "ordering guide; thresholds Table 4.1"),
        "output_supply_v": ("Table 4.1. Electrical Characteristics", "Table 4.1"),
        "prop_delay_ns": ("Pulse Width Distortion", "Table 4.1, max (PWM parts: tpLH incl. dead time)"),
        "protection": ("Table 1.1. Si8239x Ordering Guide", "ordering guide, section 2.7"),
        "temp_range_c": ("Table 4.8. Absolute Maximum Ratings", "Table 4.1 note 1"),
        "deadtime": ("Table 1.1. Si8239x Ordering Guide", "ordering guide dead-time column"),
        "theta_ja_c_w": ("Table 4.7. Thermal Characteristics", "Table 4.7"),
        "iq_ma": ("Table 4.1. Electrical Characteristics", "Table 4.1, IDDI(Q) typ"),
        "rise_time_ns": ("Output Rise and Fall Time", "Table 4.1, max, CL 200 pF"),
        "fall_time_ns": ("Output Rise and Fall Time", "Table 4.1, max, CL 200 pF"),
        "pwd_ns": ("Pulse Width Distortion", "Table 4.1, max"),
        "pinout": ("Figure 6.1. Si8239x SOIC-16", "Figure 6.1; IS3 has pins 12-13 missing"),
    },
    "si823hx": {
        "isolation_rating_kvrms": ("Table 1.1. Si823Hx Ordering Guide", "ordering guide"),
        "creepage_mm": ("Table 4.3. Insulation and Safety-Related", "Table 4.3"),
        "qualification": ("Industrial and Automotive Grade OPNs", "ordering guide: -A codes AEC-Q100"),
        "cmti_kv_us": ("Common Mode Transient Immunity", "Table 4.1, min"),
        "channel_config": ("Table 1.1. Si823Hx Ordering Guide", "ordering guide"),
        "input_type": ("Table 1.1. Si823Hx Ordering Guide", "ordering guide"),
        "peak_source_a": ("Output Short-Circuit Pulsed Source", "Table 4.1, typ, CL 220 nF"),
        "peak_sink_a": ("Output Short-Circuit Pulsed Sink", "Table 4.1, typ, CL 220 nF"),
        "uvlo_v": ("Table 1.1. Si823Hx Ordering Guide", "ordering guide; thresholds Table 4.1"),
        "output_supply_v": ("Table 4.1. Electrical Characteristics", "Table 4.1 driver supply voltage"),
        "prop_delay_ns": ("Propagation Delay Skew", "Table 4.1, max (H4/8: tpLH incl. dead time)"),
        "protection": ("Table 1.1. Si823Hx Ordering Guide", "ordering guide and notes"),
        "temp_range_c": ("Table 1.1. Si823Hx Ordering Guide", "ordering guide note"),
        "deadtime": ("Table 1.1. Si823Hx Ordering Guide", "ordering guide dead-time column"),
        "theta_ja_c_w": ("Table 4.5. Thermal Characteristics", "Table 4.5"),
        "iq_ma": ("Table 4.1. Electrical Characteristics", "Table 4.1, IDDI(Q) typ"),
        "rise_time_ns": ("Output Rise and Fall Time", "Table 4.1, max, CL 200 pF"),
        "fall_time_ns": ("Output Rise and Fall Time", "Table 4.1, max, CL 200 pF"),
        "pwd_ns": ("Propagation Delay Skew", "Table 4.1, max"),
        "pinout": ("Figure 6.2. Si823Hx NB SOIC-16", "Figures 6.1-6.4"),
    },
    "si8252x": {
        "isolation_rating_kvrms": ("Si8252xOrdering Guide", "ordering guide"),
        "creepage_mm": ("Table 6. Insulation and Safety-Related", "Table 6"),
        "qualification": ("Industrial and Automotive Grade OPNs", "ordering guide: -A codes AEC-Q100"),
        "cmti_kv_us": ("Common Mode Transient Immunity", "Table 4, min"),
        "channel_config": ("Si8252xOrdering Guide", "ordering guide"),
        "input_type": ("Si8252xOrdering Guide", "ordering guide"),
        "peak_source_a": ("Pulsed Source Current", "Table 4, typ, CL 220 nF"),
        "peak_sink_a": ("Pulsed Source Current", "Table 4, typ, CL 220 nF (sink row IOA(SCL))"),
        "uvlo_v": ("Si8252xOrdering Guide", "ordering guide; thresholds Table 4"),
        "output_supply_v": ("Table 4. Electrical Characteristics", "Table 4"),
        "prop_delay_ns": ("Propagation Delay Skew", "Table 4, max"),
        "protection": ("Si8252xOrdering Guide", "ordering guide and notes"),
        "temp_range_c": ("Si8252xOrdering Guide", "ordering guide note 5"),
        "deadtime": ("Programmed Dead Time", "Table 4"),
        "theta_ja_c_w": ("Table 8. Thermal Characteristics", "Table 8"),
        "iq_ma": ("Table 4. Electrical Characteristics", "Table 4, IDDI(Q) typ"),
        "rise_time_ns": ("Output Rise and Fall Time", "Table 4, max, CL 200 pF"),
        "fall_time_ns": ("Output Rise and Fall Time", "Table 4, max, CL 200 pF"),
        "pwd_ns": ("Pulse Width Distortion", "Table 4, max"),
        "pinout": ("Figure 1. Si82520/1 WB SOIC-14", "Figure 1"),
    },
    "si827x": {
        "isolation_rating_kvrms": ("Table 23. Si827x Ordering Guide", "ordering guide"),
        "isolation_class": ("Table 10. Regulatory Information", "VDE 60747-17 basic insulation"),
        "creepage_mm": ("Table 11. Insulation and Safety-Related", "Table 11"),
        "qualification": ("8.1. Industrial and Automotive Grade OPNs", "ordering guide: -A codes AEC-Q100"),
        "cmti_kv_us": ("Common-mode transient immunity", "Table 8, min (deglitch 200, low jitter 150)"),
        "channel_config": ("Table 4. Si827x Family Overview", "Table 4"),
        "input_type": ("Table 4. Si827x Family Overview", "Table 4"),
        "peak_source_a": ("High-level peak output current", "Table 8, typ, VDD 15 V"),
        "peak_sink_a": ("Low-level peak output current", "Table 8, typ, VDD 15 V"),
        "uvlo_v": ("Table 23. Si827x Ordering Guide", "ordering guide; thresholds Table 8"),
        "output_supply_v": ("Table 8. Electrical Characteristics", "Table 8"),
        "prop_delay_ns": ("Si8271/3/5 with low jitter", "Table 8, max"),
        "protection": ("Table 4. Si827x Family Overview", "Table 4, ordering guide"),
        "temp_range_c": ("Table 8. Electrical Characteristics", "Table 8 conditions; -ZS -55 C"),
        "deadtime": ("Table 4. Si827x Family Overview", "Table 4"),
        "theta_ja_c_w": ("Table 9. Thermal Characteristics", "Table 9"),
        "iq_ma": ("Table 8. Electrical Characteristics", "Table 8, input IDDQ typ"),
        "rise_time_ns": ("Rise time", "Table 8, typ, CL 200 pF"),
        "fall_time_ns": ("Fall time", "Table 8, typ, CL 200 pF"),
        "pwd_ns": ("Pulse width distortion", "Table 8, max"),
        "pinout": ("1. Pin Descriptions", "Tables 1-3"),
    },
    "si826x": {
        "isolation_rating_kvrms": ("Table 13. Si826x Ordering Guide", "ordering guide"),
        "isolation_class": ("Table 6. VDE 0884-10 Insulation", "VDE 0884-10 reinforced (Tables 3 and 6)"),
        "creepage_mm": ("Table 4. Insulation and Safety-Related", "Table 4, min"),
        "qualification": ("8.1. Automotive Grade OPNs", "Table 14: -A codes automotive grade"),
        "cmti_kv_us": ("Transient Immunity", "Table 2, min"),
        "channel_config": ("Table 13. Si826x Ordering Guide", "ordering guide"),
        "input_type": ("Table 11. Pin Descriptions", "LED emulator input"),
        "peak_source_a": ("Output High Current", "Table 2, typ"),
        "peak_sink_a": ("Output Low Current", "Table 2, typ"),
        "uvlo_v": ("Table 13. Si826x Ordering Guide", "ordering guide; thresholds Table 2"),
        "output_supply_v": ("Table 1. Recommended Operating Conditions", "Table 1"),
        "prop_delay_ns": ("Propagation delay (Low-to-High)", "Table 2, max"),
        "protection": ("Input noise filter cut-off", "Table 2 (UVLO, input noise filter)"),
        "temp_range_c": ("Table 1. Recommended Operating Conditions", "Table 1"),
        "theta_ja_c_w": ("Table 8. Thermal Characteristics", "Table 8"),
        "rise_time_ns": ("Rise time", "Table 2, typ, CL 200 pF"),
        "fall_time_ns": ("Fall time", "Table 2, typ, CL 200 pF"),
        "pwd_ns": ("Pulse Width Distortion", "Table 2, max"),
        "pinout": ("Table 11. Pin Descriptions", "Tables 11-12"),
    },
    "si8220": {
        "isolation_rating_kvrms": ("Table 14. Si8220/21 Ordering Guide", "ordering guide"),
        "isolation_class": ("Table 2. Regulatory Information", "IEC 60747-5-5 basic insulation"),
        "creepage_mm": ("Table 3. Insulation and Safety-Related", "Table 3"),
        "qualification": ("Table 14. Si8220/21 Ordering Guide", "ordering guide: no automotive-grade codes"),
        "channel_config": ("Table 14. Si8220/21 Ordering Guide", "ordering guide"),
        "input_type": ("Table 14. Si8220/21 Ordering Guide", "opto input (LED emulator)"),
        "peak_source_a": ("Output High Current", "Table 1, typ"),
        "peak_sink_a": ("Output Low Current", "Table 1, typ"),
        "uvlo_v": ("Table 14. Si8220/21 Ordering Guide", "ordering guide; thresholds Table 1"),
        "output_supply_v": ("Table 1. Electrical Characteristics", "Table 1"),
        "prop_delay_ns": ("Propagation Delay Time to High", "Table 1, max"),
        "protection": ("Table 1. Electrical Characteristics", "Table 1 UVLO"),
        "temp_range_c": ("Table 14. Si8220/21 Ordering Guide", "ordering guide"),
        "theta_ja_c_w": ("Table 7. Thermal Characteristics", "Table 7"),
        "rise_time_ns": ("Output Rise and Fall Time", "Table 1, max"),
        "fall_time_ns": ("Output Rise and Fall Time", "Table 1, max"),
        "pinout": ("Table 12. Pin Descriptions", "Tables 12-13"),
    },
    "si8281": {
        "isolation_rating_kvrms": ("Table 1.1. Si8281/82/83/84 Ordering Guide", "ordering guide"),
        "creepage_mm": ("Table 4.4. Insulation and Safety-Related", "Table 4.4"),
        "qualification": ("Table 1.1. Si8281/82/83/84 Ordering Guide", "ordering guide note 3"),
        "cmti_kv_us": ("Common Mode Transient Immunity", "Table 4.1, min"),
        "channel_config": ("Table 5.1. Si8281/82 Pin Descriptions", "single driver"),
        "input_type": ("Table 5.1. Si8281/82 Pin Descriptions", "IN+/IN- complementary input"),
        "peak_source_a": ("High Drive Peak Output Current", "Table 4.1, typ"),
        "peak_sink_a": ("Low Drive Peak Output Current", "Table 4.1, typ"),
        "uvlo_v": ("Table 1.1. Si8281/82/83/84 Ordering Guide", "ordering guide; thresholds Table 4.1"),
        "output_supply_v": ("Table 4.1. Electrical Specifications", "Table 4.1 per UVLO grade"),
        "prop_delay_ns": ("Propagation Delay (Low-to-High)", "Table 4.1, max"),
        "protection": ("Desaturation Detector Parameters", "Table 4.1 (UVLO, DESAT, soft shutdown, Miller clamp)"),
        "temp_range_c": ("Table 4.1. Electrical Specifications", "Table 4.1 conditions"),
        "theta_ja_c_w": ("Table 4.6. Thermal Characteristics", "Table 4.6"),
        "iq_ma": ("Input Supply Quiescent Current", "Table 4.1, IDDA(Q) typ"),
        "rise_time_ns": ("Rise Time", "Table 4.1, typ, CL 200 pF"),
        "fall_time_ns": ("Fall Time", "Table 4.1, typ, CL 200 pF"),
        "pwd_ns": ("Pulse Width Distortion", "Table 4.1, max"),
        "pinout": ("Table 5.1. Si8281/82 Pin Descriptions", "Tables 5.1-5.2"),
    },
    "si8285": {
        "isolation_rating_kvrms": ("Table 1.1. Si8285/86 Ordering Guide", "ordering guide"),
        "isolation_class": ("Table 4.3. Regulatory Information", "IEC 60747-17 basic insulation"),
        "creepage_mm": ("Table 4.4. Insulation and Safety-Related", "Table 4.4"),
        "qualification": ("Table 1.1. Si8285/86 Ordering Guide", "ordering guide note 3"),
        "cmti_kv_us": ("Common Mode Transient Immunity", "Table 4.1, min"),
        "channel_config": ("Table 5.1. Si8285/86 Pin Descriptions", "single driver"),
        "input_type": ("Table 5.1. Si8285/86 Pin Descriptions", "IN+/IN- complementary input"),
        "peak_source_a": ("High Drive Peak Output Current", "Table 4.1, typ"),
        "peak_sink_a": ("Low Drive Peak Output Current", "Table 4.1, typ"),
        "uvlo_v": ("Table 1.1. Si8285/86 Ordering Guide", "ordering guide"),
        "output_supply_v": ("Table 4.1. Electrical Specifications", "Table 4.1 per UVLO grade"),
        "prop_delay_ns": ("Propagation Delay (Low-to-High)", "Table 4.1, max"),
        "protection": ("Desaturation Detector Parameters", "Table 4.1"),
        "temp_range_c": ("Table 4.1. Electrical Specifications", "Table 4.1 conditions"),
        "theta_ja_c_w": ("Table 4.8. Thermal Characteristics", "Table 4.8"),
        "iq_ma": ("Input Supply Quiescent Current", "Table 4.1, IDDA(Q) typ"),
        "rise_time_ns": ("Rise Time", "Table 4.1, typ, CL 200 pF"),
        "fall_time_ns": ("Fall Time", "Table 4.1, typ, CL 200 pF"),
        "pwd_ns": ("Pulse Width Distortion", "Table 4.1, max"),
        "pinout": ("Table 5.1. Si8285/86 Pin Descriptions", "Table 5.1"),
    },
    "si829x": {
        "isolation_rating_kvrms": ("Table 9. Si829x Ordering Guide", "ordering guide"),
        "isolation_class": ("60747-17 (reinforced insulation)", "front page: VDE 60747-17 reinforced (pending)"),
        "qualification": ("AEC-Q100 qualified", "front page: AEC-Q100, automotive-grade manufacturing"),
        "channel_config": ("1. Description", "single driver"),
        "input_type": ("Table 1. Input Side", "IN (IN_MON monitors the complementary input)"),
        "peak_source_a": ("Table 9. Si829x Ordering Guide", "maximum constant current 15 A"),
        "peak_sink_a": ("Table 9. Si829x Ordering Guide", "maximum constant current 15 A"),
        "output_supply_v": ("VDDO 18 V to 30 V", "front page"),
        "protection": ("Fast overcurrent protection", "front page feature list"),
        "temp_range_c": ("Wide operating range", "front page"),
        "deadtime": ("Programmable dead-time", "front page"),
        "pinout": ("Figure 1. Si82900 36-Pin WB SSOP", "Figure 1"),
    },
}


def si82x_sources(x: str) -> dict:
    og = f"Si82{x}x Ordering Guide" if x in "CF" else f"Si82{x}xx Ordering Guide" if x != "E" else "Si82Ex Ordering Guide"
    gate = "Gate Driver Characteristics"
    return {
        "isolation_rating_kvrms": (og, "ordering guide"),
        "isolation_class": ("IEC60747-17 Insulation Characteristics", "VDE 60747-17 reinforced insulation"),
        "creepage_mm": ("Insulation and Safety-Related Specifications", "insulation table"),
        "qualification": ("Automotive-Grade devices", "ordering guide notes: -A codes automotive grade"),
        "cmti_kv_us": ("transient immunity", "timing table, min"),
        "channel_config": (og, "ordering guide"),
        "input_type": (og, "ordering guide inputs column"),
        "peak_source_a": ("Peak Output Current" if x not in "CF" else "Output Current", f"{gate}, typ"
                          + (" at VDD 18 V" if x not in "CF" else " at speed 7 for the UVLO grade")),
        "peak_sink_a": ("Peak Output Current" if x not in "CF" else "Output Current", f"{gate}, typ"
                        + (" at VDD 18 V" if x not in "CF" else " at speed 7 for the UVLO grade")),
        "uvlo_v": (og, "ordering guide; thresholds in Power Supply Characteristics"),
        "output_supply_v": ("Gate driver supply", "Power Supply Characteristics"),
        "prop_delay_ns": ("Propagation Delay", "Timing Characteristics, max for the deglitch option"),
        "protection": (og, "ordering guide and Device Operation"),
        "temp_range_c": ("Operating temperature", "Absolute Maximum Ratings / operating range"),
        "deadtime": ("Dead", "DT pin, Timing Characteristics"),
        "theta_ja_c_w": ("Thermal Characteristics", "junction-to-ambient, 2s2p"),
        "iq_ma": ("Quiescent", "Power Supply Characteristics, IDDIQ typ"),
        "rise_time_ns": ("Output rise time" if x not in "EF" else "Output Rise Time", "Timing Characteristics, typ"),
        "fall_time_ns": ("Output fall time" if x not in "EF" else "Output Fall Time", "Timing Characteristics, typ"),
        "pwd_ns": ("Pulse width distortion" if x not in "EF" else "Pulse Width Distortion", "Timing, max"),
        "pinout": ("Device Pinouts", "section 1.1"),
    }


for _x in "ABCDEF":
    SOURCES[f"si82{_x.lower()}x"] = si82x_sources(_x)

# ------------------------------------------------------------------ catalogue / lifecycle


def catalogue() -> dict[str, dict]:
    data = yamlio.load(CATALOG.read_text())
    out = {}
    for p in data["parts"]:
        if p.get("function") == "gate_driver" and p.get("category", "").startswith("Isolation"):
            out[p["mpn"].upper()] = p
    return out


def lookup_statuses() -> dict[str, str]:
    path = RAW_DIR / "lifecycle.json"
    return json.loads(path.read_text())["statuses"] if path.exists() else {}


def all_opns() -> dict[str, list[tuple[str, str]]]:
    out = {}
    for key, (_, pattern) in SERIES.items():
        rows = ordering_rows(SHEETS[key][0], pattern)
        out[key] = sorted(rows.items())
    return out


# ------------------------------------------------------------------ fetching


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=90) as resp:
        body = resp.read()
    time.sleep(PAUSE_S)
    return body


def fetch(log=print) -> None:
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    for pdf, path, _, _ in SHEETS.values():
        if not (PDF_DIR / pdf).exists():
            (PDF_DIR / pdf).write_bytes(_get(DS_URL + path))
            log(f"datasheet {pdf}")
    # lifecycle for ordering codes the catalogue does not list (one lookup per base part number)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / "lifecycle.json"
    state = json.loads(path.read_text()) if path.exists() else {"done": [], "statuses": {}}
    cat = catalogue()
    prefixes = set()
    for rows in all_opns().values():
        for opn, _ in rows:
            if base_name(opn).upper() not in cat:
                prefixes.add(re.match(r"Si8\d*[A-Z]?\d*", opn).group(0).upper())
    for prefix in sorted(prefixes - set(state["done"])):
        url = BASE_URL + "/Product-Lifecycle-Status-Lookup?" + urllib.parse.urlencode({"PartNumber": prefix})
        text = _get(url).decode("utf-8", "ignore")
        m = re.search(r"var productStatusData = (\[.*?\]);", text, re.S)
        rows = re.findall(r'\[\s*"([^"]+)"\s*,\s*"([^"]*)"', m.group(1)) if m else []
        for opn, status in rows:
            state["statuses"][opn.upper()] = status
        state["done"].append(prefix)
        path.write_text(json.dumps(state))
        log(f"lifecycle {prefix}: {len(rows)} rows")


# ------------------------------------------------------------------ build


def _check_row(opn: str, row: str, p: dict, check_iso: bool = True) -> None:
    """The decoded UVLO and isolation rating must appear in the ordering-guide row of the code."""
    if "uvlo_v" in p:
        u = p["uvlo_v"]
        if not re.search(rf"(?<![\d.]){u:g}\s?V?\b", row.split(opn, 1)[1]):
            raise ValueError(f"{opn}: UVLO {u} not in row {row!r}")
    iso = p["isolation_rating_kvrms"]
    if check_iso and not re.search(rf"(?<![\d.]){iso:g}(\.0)?\b", row):
        raise ValueError(f"{opn}: isolation {iso} not in row {row!r}")


def build(log=print) -> dict:
    cat = catalogue()
    statuses = lookup_statuses()
    packages, datasheets, parts, used_cat = {}, [], [], set()
    for key, rows in all_opns().items():
        decoder = SERIES[key][0]
        pdf, path, rev, rev_date = SHEETS[key]
        sources = {k: src(pdf, needle, what) for k, (needle, what) in SOURCES[key].items()}
        n_series = 0
        for opn, row in rows:
            got = decoder(opn, row)
            if got is None:
                continue
            pkg, pinout, params, desc, notes = got
            if key != "si829x":  # Si8239x: the isolation rating is only in the top-marking code
                _check_row(opn, row, params, check_iso=key != "si8239x")
            assert len(pinout) == PACKAGES[pkg]["pin_count"], (opn, pkg, len(pinout))
            packages[pkg] = PACKAGES[pkg]
            c = cat.get(base_name(opn).upper()) or cat.get(opn.upper())
            if c:
                used_cat.add(c["mpn"].upper())
                status = {"Active": "active", "Preview": "preview"}.get(c.get("status"), "unknown")
                life_src = f"Skyworks lifecycle lookup via data/catalog/skyworks_parts.yaml: {c.get('status')}"
            else:
                st = statuses.get(opn.upper()) or statuses.get(base_name(opn).upper())
                status = LIFECYCLE_MAP.get((st or "").strip().lower(), "unknown")
                life_src = f"Skyworks lifecycle lookup: {st or 'not listed'} (code not in the catalogue)"
            p_sources = {k: v for k, v in sources.items() if k in params or k == "pinout"}
            parts.append({
                "mpn": opn.upper(),
                "manufacturer": "Skyworks",
                "family": "gate_driver",
                "description": desc,
                "package": pkg,
                "pinout": pinout,
                "datasheet": pdf,
                "datasheet_url": DS_URL + path,
                "product_url": (c or {}).get("product_url"),
                "notes": notes,
                "lifecycle": {"status": status, "revision": rev, "revision_date": rev_date, "source": life_src},
                "params": params,
                "param_sources": p_sources,
            })
            n_series += 1
        datasheets.append({"file": pdf, "url": DS_URL + path, "sha256": sha256(pdf), "revision": rev,
                           "revision_date": rev_date})
        log(f"{key}: {n_series} parts")
    missing = sorted(set(cat) - used_cat)
    return {"packages": packages, "datasheets": datasheets, "parts": parts, "catalogue_not_covered": missing}


HEADER = """\
# Skyworks isolated gate drivers not covered by skyworks_si823x.yaml: Si8239x, Si823Hx, Si8252x, Si827x,
# Si826x, Si8220/21, Si8281-84, Si8285/86, Si82Ax/Bx/Cx/Dx/Ex/Fx and Si82900.
# Generated by app/sources/skyworks_gate_drivers.py from the public datasheets (var/gate_drivers) and the
# Skyworks catalogue (data/catalog/skyworks_parts.yaml). Every ordering code of each datasheet's ordering
# guide is listed (tape-and-reel "R" codes are not), industrial (-I) and automotive (-A) columns; MPNs are
# upper case ("Si" and "SI" are interchangeable per every ordering guide). qualification = automotive for
# the -A codes only (the ordering guides state AEC-Q100 for the automotive-grade flow).
#
# Conventions (data/sources/GATE_DRIVER_DATA.md), plus for single-channel drivers:
#   input_type: "single input" (VI, with EN/DIS or SPD), "complementary input" (VI+/VI- or IN+/IN-),
#   "LED emulator input" (opto-compatible ANODE/CATHODE input, Si826x and Si8220/21).
#   peak_source_a / peak_sink_a: typical; Si82Ax/Bx/Dx/Ex at VDD = 18 V (the row with a guaranteed
#   minimum); SelVCD parts (Si82Cx/Fx) at speed 7 for the UVLO grade's test supply; Si82Bx parts with a
#   Miller-clamp pin sink through VO only (3.66 A).
#   prop_delay_ns: maximum for the code's deglitch / dead-time option. rise/fall: typ where given, else max.
#   isolation_class: only where the datasheet states a component insulation standard (IEC/VDE 60747-17,
#   VDE 0884-10, IEC 60747-5-5); omitted for Si823Hx, Si8252x and Si8281-84 (only IEC 62368-1 system ratings)
#   and for LGA-13 codes. creepage_mm is the nominal external creepage of the package from the insulation table.
#
# Packages: SOIC-8N, SSO-8, SOIC-16N, SOIC-16W, SOIC-14W (IS3) and SOIC-20W reuse the codes of
# skyworks_si86.yaml / skyworks_si823x.yaml (same bodies per the outline tables). New bodies:
"""


def write(log=print) -> None:
    data = build(log)
    head = HEADER + "".join(f"#   {code}: {PACKAGE_NOTES[code]}\n" for code in PACKAGE_NOTES if code in data["packages"])
    head += "#\n# Catalogue gate-driver codes not covered (no current public datasheet lists them):\n"
    for i in range(0, len(data["catalogue_not_covered"]), 8):
        head += "#   " + ", ".join(data["catalogue_not_covered"][i : i + 8]) + "\n"
    out = {
        "source": "Skyworks gate-driver datasheets (see datasheets), transcribed 2026-10-20",
        "manufacturers": [{"name": "Skyworks", "role": "reference", "website": "https://www.skyworksinc.com"}],
        "packages": [{"code": code, **spec} for code, spec in data["packages"].items()],
        "datasheets": data["datasheets"],
        "parts": data["parts"],
    }
    OUT.write_text(head + yaml.safe_dump(out, sort_keys=False, allow_unicode=True, width=120))
    mech_head = ("# Lead and PCB land pattern data for the new Skyworks gate-driver packages of\n"
                 "# data/real/skyworks_gate_drivers_more.yaml (format: data/mechanical.yaml). Packages already in\n"
                 "# data/mechanical.yaml / mechanical_si823x.yaml are not repeated (a repeated key would replace them).\n")
    mech = {"Skyworks": {k: v for k, v in MECHANICAL.items() if k in data["packages"]}}
    MECH_OUT.write_text(mech_head + yaml.safe_dump(mech, sort_keys=False, allow_unicode=True, width=200))
    log(f"{len(data['parts'])} parts -> {OUT}")


if __name__ == "__main__":
    write()
