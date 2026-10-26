# ruff: noqa: E501  (curated fact tables read better on one line each)
"""Skyworks digital isolators outside the Si86xx tables: Si80xx, Si84xx, Si87xx, Si88xx (+ two Si86xx leftovers).

    fetch()  downloads the product tables, lifecycle rows and datasheets (same public endpoints as
             app/sources/skyworks.py) into var/raw/skyworks_isolators_more and var/datasheets/skyworks
    build()  combines them with the curated facts below into data/real/skyworks_isolators_more.yaml

    python -m app.sources.skyworks_isolators_more [--offline]

The datasheet is authoritative: every curated fact carries an `evidence` regex that must be found in the
datasheet text (pdftotext -layout; the NRND watermark garbles the pdfplumber text of the Si84xx sheets),
and the page it is found on becomes the parameter source. The product table only fills gaps and is
cross-checked (differences are listed under `table_vs_datasheet`).

Si87xx parts are optocoupler replacements: a single channel with an LED-emulator (diode) input and no
input-side supply. They are kept in the digital_isolator family, but rules/digital_isolator.yaml has no
parameter for input type or output polarity, so this is spelled out in the description and notes.
"""

import json
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from datetime import date
from pathlib import Path

from app import yamlio
from app.config import PROJECT_ROOT
from app.sources import skyworks
from app.sources.skyworks import LIFECYCLE_MAP, Datasheet, _channel_config, _enable_pins, build_pinout

RAW_DIR = PROJECT_ROOT / "var" / "raw" / "skyworks_isolators_more"
DATASHEET_DIR = PROJECT_ROOT / "var" / "datasheets" / "skyworks"
TEXT_DIR = PROJECT_ROOT / "var" / "text" / "skyworks_isolators_more"
SI86_FACTS = PROJECT_ROOT / "data" / "sources" / "skyworks_si86.yaml"
OUT = PROJECT_ROOT / "data" / "real" / "skyworks_isolators_more.yaml"
PAUSE_S = 5.0  # brief: >= 5 s between requests to skyworksinc.com

# Sitecore item ids of the family tables on skyworksinc.com (from the family pages).
PRODUCT_TABLES = {
    "Si80xx": "{837C1DD7-96BB-483B-9091-30EE6F724FAD}",
    "Si84xx": "{6C88FE76-3C2A-4B32-9DC5-8D3587366904}",
    "Si87xx": "{F9950367-E767-4B86-B0FB-C6BE82E8B0DE}",
    "Si87xx automotive": "{260B130E-D7C0-4FDC-9206-C126AC46B418}",
    "Si88xx": "{5FBBC1A9-68E8-46CD-A452-C6785FB4C36B}",
    "Si88xx automotive": "{4C3F8770-0607-45CE-8AF3-651FFAA092EC}",
}
LIFECYCLE_PREFIXES = ["SI803", "SI804", "SI805", "SI806", "SI840", "SI841", "SI842", "SI843", "SI844", "SI845",
                      "SI846", "SI871", "SI872", "SI873", "SI8822", "SI8824", "SI8832", "SI8834", "SI8842",
                      "SI8844", "SI8862", "SI8864"]  # fmt: skip
# Si86xx OPNs that the Si86 importer skips (package missing from the product table) but whose
# datasheet ordering guide lists them.
SI86_LEFTOVERS = ["SI8620EB-IS", "SI8622EB-IS"]
DATASHEET_URL = "https://www.skyworksinc.com/-/media/SkyWorks/SL/documents/public/data-sheets/"

# ------------------------------------------------------------------ packages

PACKAGES = [  # identical to data/sources/skyworks_si86.yaml where the code exists there
    {"code": "SOIC-8N", "aliases": ["NB SOIC8", "NB SOIC-8", "SOIC-8"], "name": "SOIC-8 narrow body", "pin_count": 8,
     "pitch_mm": 1.27, "body_length_mm": 4.9, "body_width_mm": 3.9, "span_mm": 6.0, "height_mm": 1.75},
    {"code": "SOIC-16N", "aliases": ["NB SOIC16", "NB SOIC-16"], "name": "SOIC-16 narrow body", "pin_count": 16,
     "pitch_mm": 1.27, "body_length_mm": 9.9, "body_width_mm": 3.9, "span_mm": 6.0, "height_mm": 1.75},
    {"code": "SOIC-16W", "aliases": ["WB SOIC16", "WB SOIC-16"], "name": "SOIC-16 wide body", "pin_count": 16,
     "pitch_mm": 1.27, "body_length_mm": 10.3, "body_width_mm": 7.5, "span_mm": 10.3, "height_mm": 2.65},
    {"code": "QSOP-16", "aliases": ["QSOP16", "QSOP-16"], "name": "QSOP-16", "pin_count": 16,
     "pitch_mm": 0.635, "body_length_mm": 4.9, "body_width_mm": 3.9, "span_mm": 6.0, "height_mm": 1.75},
    {"code": "SOIC-20W", "aliases": ["WB SOIC-20", "WB SOIC20"], "name": "SOIC-20 wide body", "pin_count": 20,
     "pitch_mm": 1.27, "body_length_mm": 12.8, "body_width_mm": 7.5, "span_mm": 10.3, "height_mm": 2.65},
    # Si88x4x data sheet, Table 15 (24-pin wide-body SOIC, JEDEC MS-013 AD): D 15.40, E1 7.50, E 10.30, A 2.65 max
    {"code": "SOIC-24W", "aliases": ["WB SOIC-24", "WB SOIC24"], "name": "SOIC-24 wide body", "pin_count": 24,
     "pitch_mm": 1.27, "body_length_mm": 15.4, "body_width_mm": 7.5, "span_mm": 10.3, "height_mm": 2.65},
    # Si87xx data sheet, Table 21 (SDIP6): D 4.58, E1 7.50, E 11.50, A 2.65 max. The web table calls it "WB SOIC6".
    {"code": "SDIP-6", "aliases": ["SDIP6", "WB SOIC6"], "name": "SDIP6 stretched SO-6 (wide body)", "pin_count": 6,
     "pitch_mm": 1.27, "body_length_mm": 4.58, "body_width_mm": 7.5, "span_mm": 11.5, "height_mm": 2.65},
]  # fmt: skip

# ------------------------------------------------------------------ pin layouts (in addition to the Si86 ones)

LAYOUTS = {
    # Si88x2x (Figures 1-4): dc-dc pins fixed, two data channels
    "s8822": {"pins": 16, "ch": [[7, 10], [8, 9]], "ctl": [], "fixed": {
        1: "GNDP", 2: "VSW", 3: "VDDP", 4: "VDDA", 5: "GNDA", 6: "SH", 11: "NC", 12: "COMP", 13: "VSNS",
        14: "DNC/VREGB", 15: "VDDB", 16: "GNDB"}},
    "s8832": {"pins": 20, "ch": [[8, 13], [9, 12]], "ctl": [], "fixed": {
        1: "GNDP", 2: "VSW", 3: "VDDP", 4: "VDDA", 5: "GNDA", 6: "SH_FC", 7: "SS", 10: "NC", 11: "NC", 14: "NC",
        15: "COMP", 16: "VSNS", 17: "NC", 18: "DNC/VREGB", 19: "VDDB", 20: "GNDB"}},
    "s8842": {"pins": 16, "ch": [[7, 10], [8, 9]], "ctl": [], "fixed": {
        1: "GNDP", 2: "RSN", 3: "ESW", 4: "VDDA", 5: "GNDA", 6: "VREGA", 11: "NC", 12: "COMP", 13: "VSNS",
        14: "DNC/VREGB", 15: "VDDB", 16: "GNDB"}},
    "s8862": {"pins": 20, "ch": [[9, 12], [10, 11]], "ctl": [], "fixed": {
        1: "GNDP", 2: "RSN", 3: "ESW", 4: "VDDA", 5: "GNDA", 6: "VREGA", 7: "SH_FC", 8: "SS", 13: "NC", 14: "NC",
        15: "COMP", 16: "VSNS", 17: "NC", 18: "DNC/VREGB", 19: "VDDB", 20: "GNDB"}},
    # Si88x4x (Figures 1-4): four data channels
    "s8824": {"pins": 20, "ch": [[7, 14], [8, 13], [9, 12], [10, 11]], "ctl": [], "fixed": {
        1: "GNDP", 2: "VSW", 3: "VDDP", 4: "VDDA", 5: "GNDA", 6: "SH", 15: "COMP", 16: "VSNS", 17: "NC",
        18: "DNC/VREGB", 19: "VDDB", 20: "GNDB"}},
    "s8834": {"pins": 24, "ch": [[9, 16], [10, 15], [11, 14], [12, 13]], "ctl": [], "fixed": {
        1: "GNDP", 2: "VSW", 3: "VDDP", 4: "VDDA", 5: "GNDA", 6: "NC", 7: "SH_FC", 8: "SS", 17: "NC", 18: "NC",
        19: "COMP", 20: "VSNS", 21: "NC", 22: "DNC/VREGB", 23: "VDDB", 24: "GNDB"}},
    "s8844": {"pins": 20, "ch": [[7, 14], [8, 13], [9, 12], [10, 11]], "ctl": [], "fixed": {
        1: "GNDP", 2: "RSN", 3: "ESW", 4: "VDDA", 5: "GNDA", 6: "VREGA", 15: "COMP", 16: "VSNS", 17: "NC",
        18: "DNC/VREGB", 19: "VDDB", 20: "GNDB"}},
    "s8864": {"pins": 24, "ch": [[9, 16], [10, 15], [11, 14], [12, 13]], "ctl": [], "fixed": {
        1: "GNDP", 2: "RSN", 3: "ESW", 4: "VDDA", 5: "GNDA", 6: "VREGA", 7: "SH_FC", 8: "SS", 17: "NC", 18: "NC",
        19: "COMP", 20: "VSNS", 21: "NC", 22: "DNC/VREGB", 23: "VDDB", 24: "GNDB"}},
}  # fmt: skip

# Si87xx pinouts are not channel-shaped (LED-emulator input), so they are listed per package.
OC8 = ["NC", "ANODE", "CATHODE", "NC", "GND", "VO", "NC", "VDD"]
OC8_VE = ["NC", "ANODE", "CATHODE", "NC", "GND", "VO", "VE", "VDD"]
OC8_VL = ["NC", "ANODE", "CATHODE", "NC", "GND", "VO", "VL", "VDD"]
SDIP6 = ["ANODE", "NC", "CATHODE", "GND", "VO", "VDD"]
LOGIC8 = ["NC", "ANODE", "CATHODE", "NC", "GND", "VO", "NC", "VDD"]
LOGIC8_EN = ["NC", "ANODE", "CATHODE", "NC", "GND", "VO", "EN", "VDD"]
SI873X_8 = ["NC", "ANODE", "CATHODE", "NC", "GND", "NC", "VO", "VDD"]

# ------------------------------------------------------------------ base parts
# dirs: channel directions per slot (F forward, R reverse, B bidirectional); layout per package
# (a string = any package); ctl: control pins; pinout_evidence: text on the pinout page.
# Si87xx: `pinout` per package, `output` (output stage) and `polarity`.

B = {
    # --- Si80xx 1 kV (QSOP-16) ---
    "Si8030": {"dirs": "FFF", "layout": "tri16", "ctl": ["NC", "EN2"], "pinout_evidence": r"4\. Pin Descriptions \(Si8030/35\)"},
    "Si8035": {"dirs": "FFF", "layout": "tri16", "ctl": ["NC", "NC"], "pinout_evidence": r"4\. Pin Descriptions \(Si8030/35\)"},
    "Si8040": {"dirs": "FFFF", "layout": "quad16", "ctl": ["NC", "EN2"], "pinout_evidence": r"5\. Pin Descriptions \(Si8040/45\)"},
    "Si8045": {"dirs": "FFFF", "layout": "quad16", "ctl": ["NC", "NC"], "pinout_evidence": r"5\. Pin Descriptions \(Si8040/45\)"},
    "Si8050": {"dirs": "FFFFF", "layout": "penta16", "ctl": ["NC", "EN2"], "pinout_evidence": r"6\. Pin Descriptions \(Si8050\)"},
    "Si8055": {"dirs": "FFFFF", "layout": "penta16b", "pinout_evidence": r"7\. Pin Descriptions \(Si8055\)"},
    "Si8065": {"dirs": "FFFFFF", "layout": "hexa16", "pinout_evidence": r"8\. Pin Descriptions \(Si8065\)"},
    # --- Si840x I2C ---
    "Si8400": {"dirs": "BB", "layout": "i2c8", "pinout_evidence": r"Table 14\. Si8400/01/02 in SO-8 Package"},
    "Si8401": {"dirs": "BF", "layout": "i2c8", "pinout_evidence": r"Table 14\. Si8400/01/02 in SO-8 Package"},
    "Si8402": {"dirs": "BF", "layout": "i2c8", "pinout_evidence": r"Table 14\. Si8400/01/02 in SO-8 Package"},
    "Si8405": {"dirs": "BFRB", "layout": "i2c16", "pinout_evidence": r"Table 15\. Si8405 in Narrow-Body SO-16 Package"},
    # --- Si841x/2x ---
    "Si8410": {"dirs": "F", "layout": {"SOIC-8N": "single8", "SOIC-16W": "single16w"},
               "pinout_evidence": [r"Si8410 NB SOIC-8", r"Si8410 WB SOIC-16"]},
    "Si8420": {"dirs": "FF", "layout": {"SOIC-8N": "dual8", "SOIC-16W": "dual16w"},
               "pinout_evidence": [r"Si8420 NB SOIC-8", r"Si8420/23 WB SOIC-16"]},
    "Si8421": {"dirs": "FR", "layout": {"SOIC-8N": "dual8", "SOIC-16W": "dual16w"},
               "pinout_evidence": [r"Si8421 NB SOIC-8", r"Si8421 WB SOIC-16"]},
    "Si8422": {"dirs": "RF", "layout": {"SOIC-8N": "dual8", "SOIC-16W": "dual16w"},
               "pinout_evidence": [r"Si8422/26 NB SOIC-8", r"Si8422 WB SOIC-16"]},
    "Si8423": {"dirs": "FF", "layout": {"SOIC-8N": "dual8", "SOIC-16W": "dual16w"},
               "pinout_evidence": [r"Si8423/24 NB SOIC-8", r"Si8420/23 WB SOIC-16"]},
    # --- Si843x ---
    "Si8430": {"dirs": "FFF", "layout": "tri16", "ctl": ["NC", "EN2"], "pinout_evidence": r"NC on Si8430/35"},
    "Si8431": {"dirs": "FFR", "layout": "tri16", "ctl": ["EN1", "EN2"], "pinout_evidence": r"NC on Si8430/35"},
    "Si8435": {"dirs": "FFF", "layout": "tri16", "ctl": ["NC", "NC"], "pinout_evidence": r"NC on Si8435\."},
    # --- Si844x ---
    "Si8440": {"dirs": "FFFF", "layout": "quad16", "ctl": ["NC", "EN2"], "pinout_evidence": r"NC on Si8440/45\."},
    "Si8441": {"dirs": "FFFR", "layout": "quad16", "ctl": ["EN1", "EN2"], "pinout_evidence": r"NC on Si8440/45\."},
    "Si8442": {"dirs": "FFRR", "layout": "quad16", "ctl": ["EN1", "EN2"],
               "pinout_evidence": [r"NC on Si8440/45\.", r"A5/EN1 7 Digital Input Side 1 active high enable"]},
    "Si8445": {"dirs": "FFFF", "layout": "quad16", "ctl": ["NC", "NC"], "pinout_evidence": r"NC on Si8445\."},
    # --- Si845x ---
    "Si8450": {"dirs": "FFFFF", "layout": "penta16", "ctl": ["NC", "EN2"], "pinout_evidence": r"NC on Si8450\."},
    "Si8451": {"dirs": "FFFFR", "layout": "penta16", "ctl": ["EN1", "EN2"], "pinout_evidence": r"NC on Si8450\."},
    "Si8452": {"dirs": "FFFRR", "layout": "penta16", "ctl": ["EN1", "EN2"], "pinout_evidence": r"NC on Si8450\."},
    "Si8455": {"dirs": "FFFFF", "layout": "penta16b",
               "pinout_evidence": [r"5\. Pin Descriptions \(Si8455\)", r"Description \(Si8442\) Description \(Si8455\)"]},
    # --- Si846x ---
    "Si8460": {"dirs": "FFFFFF", "layout": "hexa16", "pinout_evidence": r"Si8460 Si8461 Si8462 Si8463"},
    "Si8461": {"dirs": "FFFFFR", "layout": "hexa16", "pinout_evidence": r"Si8460 Si8461 Si8462 Si8463"},
    "Si8462": {"dirs": "FFFFRR", "layout": "hexa16", "pinout_evidence": r"Si8460 Si8461 Si8462 Si8463"},
    "Si8463": {"dirs": "FFFRRR", "layout": "hexa16", "pinout_evidence": r"Si8460 Si8461 Si8462 Si8463"},
    # --- Si87xx open-collector (Si87xx.pdf): inverting, output low when the LED emulator is on ---
    "Si8710": {"pinout": {"SOIC-8N": OC8, "SDIP-6": SDIP6}, "output": "open-collector output", "polarity": "inverting",
               "pinout_evidence": [r"Table 11\. Pin Descriptions \(SOIC-8, DIP8\) Open Collector", r"Table 13\. Pin Descriptions \(SDIP6\) Open Collector"]},
    "Si8711": {"pinout": {"SOIC-8N": OC8_VL}, "output": "open-collector output with 20 kΩ pull-up", "polarity": "inverting",
               "pinout_evidence": r"Table 14\. Pin Descriptions \(SOIC-8, DIP8\) 20 k"},
    "Si8712": {"pinout": {"SOIC-8N": OC8_VE}, "output": "open-collector output with output enable", "polarity": "inverting",
               "enable": "VE active-high", "pinout_evidence": r"Table 12\. Pin Descriptions \(SOIC-8, DIP8\) Output Enable"},
    # --- Si871x/2x logic output ---
    "Si8715": {"pinout": {"SOIC-8N": LOGIC8, "SDIP-6": SDIP6}, "output": "push-pull logic output", "polarity": "non-inverting",
               "pinout_evidence": [r"Table 11\. Pin Descriptions \(SOIC-8, DIP8\) Pin", r"Table 13\. Pin Descriptions \(SDIP6\)"]},
    "Si8716": {"pinout": {"SOIC-8N": LOGIC8_EN}, "output": "push-pull logic output with enable (output high when disabled)",
               "polarity": "inverting", "enable": "EN active-high", "pinout_evidence": r"Table 12\. Pin Descriptions \(SOIC-8, DIP8\) with Output Enable"},
    "Si8717": {"pinout": {"SOIC-8N": LOGIC8_EN}, "output": "push-pull logic output with enable (Hi-Z when disabled)",
               "polarity": "non-inverting", "enable": "EN active-high", "pinout_evidence": r"Table 12\. Pin Descriptions \(SOIC-8, DIP8\) with Output Enable"},
    "Si8718": {"pinout": {"SOIC-8N": LOGIC8_EN}, "output": "push-pull logic output with enable (Hi-Z when disabled)",
               "polarity": "inverting", "enable": "EN active-high", "pinout_evidence": r"Table 12\. Pin Descriptions \(SOIC-8, DIP8\) with Output Enable"},
    "Si8719": {"pinout": {"SOIC-8N": LOGIC8, "SDIP-6": SDIP6}, "output": "push-pull logic output", "polarity": "inverting",
               "pinout_evidence": [r"Table 11\. Pin Descriptions \(SOIC-8, DIP8\) Pin", r"Table 13\. Pin Descriptions \(SDIP6\)"]},
    "Si8720": {"pinout": {"SOIC-8N": LOGIC8_EN}, "output": "push-pull logic output with enable (output low when disabled)",
               "polarity": "inverting", "enable": "EN active-high", "pinout_evidence": r"Table 12\. Pin Descriptions \(SOIC-8, DIP8\) with Output Enable"},
    # --- Si873x low-input-current logic output ---
    "Si8735": {"pinout": {"SOIC-8N": SI873X_8}, "output": "push-pull logic output", "polarity": "non-inverting",
               "pinout_evidence": r"Table 6\.1\. Pin Descriptions \(SOIC-8, DIP8\)"},
    "Si8736": {"pinout": {"SOIC-8N": LOGIC8_EN}, "output": "push-pull logic output with enable (output high when disabled)",
               "polarity": "inverting", "enable": "EN active-high", "pinout_evidence": r"Table 7\.1\. Pin Descriptions \(SOIC-8, DIP8\) with Output Enable"},
}  # fmt: skip
# Si88xx: four dc-dc variants x channel configurations
for _fam, _lay2, _lay4 in (
    ("Si882", "s8822", "s8824"),
    ("Si883", "s8832", "s8834"),
    ("Si884", "s8842", "s8844"),
    ("Si886", "s8862", "s8864"),
):
    for _i, _d in enumerate(["FF", "FR", "RR"]):
        B[f"{_fam}2{_i}"] = {"dirs": _d, "layout": _lay2, "pinout_evidence": f"{_fam}2{_i}"}
    for _i, _d in enumerate(["FFFF", "FFFR", "FFRR", "FRRR", "RRRR"]):
        B[f"{_fam}4{_i}"] = {"dirs": _d, "layout": _lay4, "pinout_evidence": f"{_fam}4{_i}"}

# Si88xx dc-dc options per variant (ordering guides, Table 20)
SI88_DCDC = {
    "Si8822": "internal switch, shutdown",
    "Si8824": "internal switch, shutdown",
    "Si8832": "internal switch, shutdown, frequency control, soft start",
    "Si8834": "internal switch, shutdown, frequency control, soft start",
    "Si8842": "external switch",
    "Si8844": "external switch",
    "Si8862": "external switch, shutdown, frequency control, soft start",
    "Si8864": "external switch, shutdown, frequency control, soft start",
}

# ------------------------------------------------------------------ per-datasheet facts
# Selectors: value | by_package | by_speed (letter after the base number) | by_iso (letter after that) |
# by_base. `min_kv`: the fact applies only to parts rated at least that many kVrms.

SI84_SPEED = {  # Si84xx speed grades: A = 1 Mbps, B = 150 Mbps (datasheet timing tables)
    "data_rate_mbps": {"by_speed": {"A": 1.0, "B": 150.0}, "evidence": r"Maximum Data Rate 0 — 150 Mbps",
                       "evidence_by_speed": {"A": r"Maximum Data Rate 0 — 1\.0 Mbps"}},
    "prop_delay_ns": {
        "by_speed": {"A": 35.0, "B": 9.5},
        "evidence": r"Propagation Delay tPHL, ?tPLH See Figure \d 3\.0 6\.0 9\.5 ns",
    },
    "pwd_ns": {"by_speed": {"A": 25.0, "B": 2.5}, "evidence": r"PWD See Figure \d — 1\.5 2\.5 ns"},
    "skew_ns": {"by_speed": {"A": 35.0, "B": 1.8}, "evidence": r"Channel-Channel Skew tPSK — 0\.5 1\.8 ns"},
}
SI84_COMMON = {
    "vdd_range_v": {"value": [2.7, 5.5], "evidence": r"VDD1 2\.70 — 5\.5 V"},
    "temp_range_c": {
        "value": [-40, 125],
        "evidence": r"Ambient Operating Temperature\*? TA 150 Mbps, 15 pF, 5 V –40 25 125",
    },
    "default_output": {"value": "low", "evidence": r"UP P L"},
    "isolation_rating_kvrms": {"by_iso": {"A": 1.0, "B": 2.5}, "evidence": r"2\.5 kVrms"},
    "certifications": {
        "value": ["UL", "CSA", "VDE"],
        "min_kv": 2.5,
        "evidence": r"The Si84xx is certified under UL1577",
    },
    "isolation_class": {
        "value": "basic",
        "min_kv": 2.5,
        "evidence": r"60747-5-2: Up to 560 V ?peak for basic insulation working voltage",
    },
    "viorm_vpk": {"value": 560, "evidence": r"Maximum Working Insulation Voltage VIORM 560 V peak"},
}

DATASHEETS = {
    "Si80xx-1kV.pdf": {
        "series": "Si80xx 1 kV",
        "facts": {
            "isolation_rating_kvrms": {"value": 1.0, "evidence": r"Si8030AA-B-IU 3 Low Yes 1 QSOP-16"},
            "default_output": {"value": "low", "evidence": r"The default output state of Si80xx devices is logic low"},
            "data_rate_mbps": {"value": 10.0, "evidence": r"Maximum Data Rate 0 — 10 Mbps"},
            "prop_delay_ns": {"value": 65.0, "evidence": r"Propagation Delay tPHL, tPLH See Figure 2 20 40 65 ns"},
            "pwd_ns": {"value": 30.0, "evidence": r"PWD See Figure 2 — 20 30 ns"},
            "skew_ns": {"value": 30.0, "evidence": r"Channel-Channel Skew tPSK — 20 30 ns"},
            "cmti_kv_us": {"value": 35, "evidence": r"CMTI VI = VDD or 0 V 35 50 — kV/µs"},
            "vdd_range_v": {"value": [3.15, 5.5], "evidence": r"VDD1 3\.15 — 5\.5 V"},
            "temp_range_c": {"value": [-40, 125], "evidence": r"Ambient Operating Temperature\* TA –40 25 125"},
        },
        "package": [(r".", "QSOP-16")],
        "notes": "The data sheet lists no safety certification or insulation class for the 1 kV Si80xx; its front page "
                 "states AEC-Q100 qualification (industrial -IU OPN).",
    },
    "Si840x.pdf": {
        "series": "Si840x I2C",
        "facts": {
            **SI84_COMMON,
            "data_rate_mbps": {"value": 1.7, "evidence": r"Maximum I2C bus Frequency Fmax — — 1\.7 MHz"},
            "prop_delay_ns": {"value": 40.0, "evidence": r"Side B to side A rising Tphba R2 = 499 — 20 40 ns"},
            "creepage_mm": {"by_package": {"SOIC-8N": 4.01, "SOIC-16N": 4.01}, "evidence": r"Nominal External Tracking \(Creepage\)1 L\(1O2\) 4\.01 4\.01 mm"},
            "temp_range_c": {"value": [-40, 125], "evidence": r"3\.0 V < VDD < 5\.5 V\. TA = –40 to \+125 °C"},
            "vdd_range_v": {"value": [3.0, 5.5], "evidence": r"3\.0 V < VDD < 5\.5 V\. TA = –40 to \+125 °C"},
        },
        "package": [(r"^SI840[012]", "SOIC-8N"), (r"^SI8405", "SOIC-16N")],
        "notes": "I2C isolator: open-drain bidirectional SDA/SCL channels (35 mA sink), 1.7 MHz I2C clock; data rate "
                 "and propagation delay are for the I2C channels. Not recommended for new designs (data sheet names "
                 "the Si860x as replacement).",
    },
    "Si8410.pdf": {
        "series": "Si8410/20/21",
        "facts": {**SI84_COMMON, **SI84_SPEED,
                  "creepage_mm": {"value": 4.01, "evidence": r"Nominal External Tracking \(Creepage\)1 L\(IO2\) 4\.01 mm"}},
        "package": [(r".", "SOIC-8N")],
        "notes": "Not recommended for new designs (data sheet names the Si861x as replacement).",
    },
    "Si841x-2x-DataSheet.pdf": {
        "series": "Si841x/2x",
        "facts": {
            **SI84_COMMON, **SI84_SPEED,
            "prop_delay_ns": {"by_speed": {"A": 35.0, "B": 11.0}, "evidence": r"Propagation Delay tPHL, tPLH See Figure 5\.1 Propagation 4\.0 8\.0 11 ns"},
            "pwd_ns": {"by_speed": {"A": 25.0, "B": 3.0}, "evidence": r"PWD See Figure 5\.1 Propagation — 1\.5 3\.0 ns"},
            "skew_ns": {"by_speed": {"A": 35.0, "B": 1.5}, "evidence": r"Channel-Channel Skew tPSK — 0\.5 1\.5 ns"},
            "temp_range_c": {"value": [-40, 125], "evidence": r"Ambient Operating Temperature1 TA –40 25 125"},
            "default_output": {"by_base": {"Si8410": "low", "Si8420": "low", "Si8421": "low", "Si8422": "high", "Si8423": "high"},
                               "evidence": r"Si8422AB-D-IS 1 1 1 High 2\.5 kVrms"},
            "isolation_rating_kvrms": {"by_iso": {"B": 2.5, "D": 5.0}, "evidence": r"Si8410AD-D-IS4 1 0 1 Low 5\.0 kVrms"},
            "certifications": {"value": ["UL", "CSA", "VDE"], "min_kv": 2.5, "evidence": r"The Si84xx is certified under UL1577"},
            "isolation_class": {"value": "basic", "evidence": r"60747-5-5: Up to 891 Vpeak for basic insulation working voltage"},
            "creepage_mm": {"by_package": {"SOIC-16W": 8.0, "SOIC-8N": 4.01}, "evidence": r"Nominal External Tracking \(Creepage\)1 L\(IO2\) 8\.0 min 4\.01 min mm"},
            "viorm_vpk": {"by_package": {"SOIC-16W": 891, "SOIC-8N": 560}, "evidence": r"Maximum Working Insulation Voltage VIORM 891 560 Vpeak"},
            "cmti_kv_us": {"value": 20, "evidence": r"CMTI VI = VDD or 0 V 20 45 — kV/μs"},
        },
        "package": [(r"^SI84\d\d.B", "SOIC-8N"), (r"^SI84\d\d.D", "SOIC-16W")],
        "notes": "Ordering guide note 1: all devices >1 kVrms are AEC-Q100 qualified (industrial -IS OPN). Wide-body "
                 "parts are certified reinforced under CSA 60950-1/61010-1; the VDE certificate is basic.",
    },
    "Si843x.pdf": {
        "series": "Si843x",
        "facts": {**SI84_COMMON, **SI84_SPEED,
                  "vdd_range_v": {"value": [2.7, 5.5], "evidence": r"VDD1 2\.70 — 5\.5"},
                  "temp_range_c": {"value": [-40, 125], "evidence": r"Ambient Operating Temperature\* TA 150 Mbps, 15 pF, 5 V –40 25 125"},
                  "creepage_mm": {"by_package": {"SOIC-16W": 8.0, "SOIC-16N": 4.01}, "evidence": r"Nominal External Tracking \(Creepage\)1 L\(IO2\) 8\.0 4\.01 mm"}},
        "package": [(r"-[IA]S1$", "SOIC-16N"), (r"-[IA]S$", "SOIC-16W")],
        "notes": "Not recommended for new designs (data sheet names the Si863x as replacement).",
    },
    "Si844x.pdf": {
        "series": "Si844x",
        "facts": {**SI84_COMMON, **SI84_SPEED,
                  "creepage_mm": {"by_package": {"SOIC-16W": 8.0, "SOIC-16N": 4.01}, "evidence": r"Nominal External Tracking \(Creepage\)1 L\(IO2\) 8\.0 4\.01 mm"}},
        "package": [(r"-[IA]S1$", "SOIC-16N"), (r"-[IA]S$", "SOIC-16W")],
        "notes": "Not recommended for new designs (data sheet names the Si864x as replacement).",
    },
    "Si845x.pdf": {
        "series": "Si845x",
        "facts": {**SI84_COMMON, **SI84_SPEED,
                  "creepage_mm": {"value": 4.01, "evidence": r"Nominal External Tracking \(Creepage\)1 L\(IO2\) 4\.01 mm"}},
        "package": [(r"-[IA]S1$", "SOIC-16N")],
        "notes": "Not recommended for new designs (data sheet names the Si865x as replacement).",
    },
    "Si846x.pdf": {
        "series": "Si846x",
        "facts": {**SI84_COMMON, **SI84_SPEED,
                  "creepage_mm": {"value": 3.9, "evidence": r"Nominal External Tracking \(Creepage\)1 L\(IO2\) 3\.9 ?min mm"}},
        "package": [(r"-[IA]S1$", "SOIC-16N")],
        "notes": "Not recommended for new designs (data sheet names the Si866x as replacement).",
    },
    "Si84x-5x-QSOP.pdf": {
        "series": "Si844x/5x QSOP",
        "facts": {**SI84_COMMON, **SI84_SPEED,
                  "isolation_rating_kvrms": {"value": 1.0, "evidence": r"Si8442BA-D-IU Si8642BA-C-IU 2 2 150 1 kVrms"},
                  "certifications": {"value": ["UL", "CSA", "VDE"], "evidence": r"Regulatory Certifications apply to 1\.0 kVRMS rated devices"},
                  "isolation_class": {"value": "basic", "evidence": r"60747-5-2: Up to 560 V ?peak for basic insulation working voltage"},
                  "creepage_mm": {"value": 3.6, "evidence": r"Nominal External Tracking \(Creepage\) L\(IO2\) 3\.6 mm"}},
        "package": [(r".", "QSOP-16")],
        "notes": "Not recommended for new designs (data sheet names the Si864x/Si865x as replacement).",
    },
    "Si87xx.pdf": {
        "series": "Si871x open-collector",
        "facts": {
            "isolation_rating_kvrms": {"by_iso": {"C": 3.75, "D": 5.0}, "evidence": r"Si8710AD-B-IS ACPL-W611, 5\.0 kVrms"},
            "data_rate_mbps": {"by_speed": {"A": 15.0, "B": 15.0, "C": 1.0}, "evidence": r"Si87xxC devices DC — 1 MBPS"},
            "prop_delay_ns": {"value": 60.0, "evidence": r"Propagation Delay tPHL CL = 15 pF using 350 . pull-up — — 60 ns"},
            "pwd_ns": {"value": 20.0, "evidence": r"Pulse Width Distortion PWD \| tPLH – tPHL \| — — 20 ns"},
            "cmti_kv_us": {"by_speed": {"A": 20, "B": 35, "C": 20}, "evidence": r"IF = 6 mA for Si87xxB devices 35 50 — kV/µs"},
            "vdd_range_v": {"value": [3.0, 30.0], "evidence": r"VDD Supply Voltage VDD 3 — 30 V"},
            "temp_range_c": {"value": [-40, 125], "evidence": r"Operating Temperature \(Ambient\) TA –40 — 125 °C"},
            "isolation_class": {"value": "reinforced", "evidence": r"VDE0884 Part 10: Up to 1414 Vpeak for reinforced insulation working voltage"},
            "certifications": {"value": ["UL", "CSA", "VDE", "CQC"], "evidence": r"The Si87xx is certified under GB4943\.1-2011"},
            "creepage_mm": {"by_package": {"SOIC-8N": 3.9, "SDIP-6": 8.3}, "evidence": r"\(Creepage\) CPG 3\.9 min 7\.0 min 8\.3 min mm|CPG 3\.9 min 7\.0 min 8\.3 min mm"},
            "viorm_vpk": {"by_package": {"SOIC-8N": 630, "SDIP-6": 1140}, "evidence": r"630 891 1140 V peak"},
            "surge_10kv": {"value": True, "evidence": r"6250 V x 1\.6 = 10 kV"},
        },
        "package": [(r"^SI87\d\d.C", "SOIC-8N"), (r"^SI87\d\d.D", "SDIP-6")],
        "notes": "Optocoupler replacement: LED-emulator (diode) input driven by forward current (Si87xxA/C: IF 3-15 mA, "
                 "Si87xxB: 6-30 mA), no input-side supply; output side VDD 3-30 V. The product table's 'Hi-Z' "
                 "default output reflects the open-collector stage, so default_output is not set. Data sheet: "
                 "AEC-Q100 qualified (industrial -IS OPNs too); -AS OPNs are the automotive-grade flow.",
    },
    "si871x-2x-datasheet.pdf": {
        "series": "Si871x/2x",
        "facts": {
            "isolation_rating_kvrms": {"by_iso": {"C": 3.75, "D": 5.0}, "evidence": r"Si8715BD-A-IS High CMTI 15 Mbps 5\.0 kVrms No, N/A SDIP6"},
            "data_rate_mbps": {"value": 15.0, "evidence": r"Maximum Data Rate FDATA DC — 15 MBPS"},
            "prop_delay_ns": {"value": 50.0, "evidence": r"Propagation Delay tPHL CL = 15 pF 5 — 50 ns"},
            "pwd_ns": {"value": 25.0, "evidence": r"Pulse Width Distortion PWD \| tPLH – tPHL \| — — 25 ns"},
            "cmti_kv_us": {"by_speed": {"A": 20, "B": 35}, "evidence": r"B = 15 Mbps, 35 kV/.s minimum CMTI"},
            "vdd_range_v": {"value": [2.5, 5.5], "evidence": r"VDD Supply Voltage VDD 2\.5 — 5\.5 V"},
            "temp_range_c": {"value": [-40, 125], "evidence": r"Operating Temperature \(Ambient\) TA –40 — 125 °C"},
            "isolation_class": {"value": "reinforced", "evidence": r"VDE0884-10: Up to 1414 Vpeak for reinforced insulation working voltage"},
            "certifications": {"value": ["UL", "CSA", "VDE", "CQC"], "evidence": r"The Si871x/2x is certified under GB4943\.1-2011"},
            "creepage_mm": {"by_package": {"SOIC-8N": 3.9, "SDIP-6": 8.3}, "evidence": r"L\(IO2\) 3\.9 min 7\.0 min 8\.3 min mm"},
            "viorm_vpk": {"by_package": {"SOIC-8N": 630, "SDIP-6": 1140}, "evidence": r"630 891 1140 V peak"},
            "surge_10kv": {"value": True, "evidence": r"10 kV surge withstand capability"},
        },
        "package": [(r"^SI87\d\d.C", "SOIC-8N"), (r"^SI87\d\d.D", "SDIP-6")],
        "notes": "Optocoupler replacement: LED-emulator (diode) input driven by forward current (IF 6-30 mA), no "
                 "input-side supply; output side VDD 2.5-5.5 V. The product table's default output is the state "
                 "with the output disabled, so default_output is not set. Data sheet: AEC-Q100 qualified "
                 "(industrial -IS OPNs too); -AS OPNs are the automotive-grade flow, electrically identical (note 4).",
    },
    "si873x-datasheet.pdf": {
        "series": "Si873x",
        "facts": {
            "isolation_rating_kvrms": {"value": 3.75, "evidence": r"Si8735BC-IS 3\.75 kVrms No, N/A SOIC-8"},
            "data_rate_mbps": {"value": 15.0, "evidence": r"High Speed: dc to 15 Mbps"},
            "prop_delay_ns": {"value": 50.0, "evidence": r"Propagation Delay \(High-to- tPHL CL = 15 pF 1\.5 — 50 ns"},
            "pwd_ns": {"value": 25.0, "evidence": r"Pulse Width Distortion PWD \| tPLH – tPHL \| — — 25 ns"},
            "vdd_range_v": {"value": [2.5, 5.5], "evidence": r"VDD Supply Voltage VDD 2\.5 — 5\.5 V"},
            "temp_range_c": {"value": [-40, 125], "evidence": r"Operating Temperature \(Ambient\) TA –40 — 125 °C"},
            "isolation_class": {"value": "reinforced", "evidence": r"VDE0884-10: Up to 630 Vpeak for reinforced insulation working voltage"},
            "certifications": {"value": ["VDE"], "evidence": r"The Si873x is certified according to VDE0884"},
            "creepage_mm": {"value": 3.9, "evidence": r"Nominal External Tracking L\(IO2\) 3\.9 min mm"},
            "viorm_vpk": {"value": 630, "evidence": r"Maximum Working VIORM 630 V peak"},
            "surge_10kv": {"value": True, "evidence": r"10 kV surge withstand capability"},
        },
        "package": [(r".", "SOIC-8N")],
        "notes": "Optocoupler replacement with low input current: LED-emulator input (IF 1-15 mA), no input-side "
                 "supply; output side VDD 2.5-5.5 V. CMTI not set: Table 5.2 gives only 25 kV/µs typical while the "
                 "top-marking table states 35 kV/µs minimum for grade B. CSA, UL and CQC are marked pending in the "
                 "data sheet, so only VDE is listed.",
    },
    "si88x2x.pdf": {
        "series": "Si88x2x",
        "facts": {
            "isolation_rating_kvrms": {"by_iso": {"C": 3.75, "D": 5.0}, "evidence": r"5\.0 kVRMS Insulation Rating"},
            "default_output": {"by_speed": {"B": "low", "E": "high"}, "evidence": r"Si88220EC-IS Si88220EC-AS High"},
            "data_rate_mbps": {"value": 100.0, "evidence": r"Data Rate — — 0 — 100 Mbps"},
            "prop_delay_ns": {"value": 23.0, "evidence": r"Propagation Delay tPHL 13\.0 18\.0 23\.0 ns"},
            "pwd_ns": {"value": 7.0, "evidence": r"PWD page 27 — 4\.5 7\.0 ns"},
            "skew_ns": {"value": 4.0, "evidence": r"Channel-Channel Skew tPSK — — 2\.0 4\.0 ns"},
            "cmti_kv_us": {"value": 40, "evidence": r"Transient Immunity CMTI See Figure 38, “Common-Mode 40 100 — kV/µs"},
            "vdd_range_v": {"value": [3.0, 5.5], "evidence": r"VDDB 3\.0 — 5\.5 V"},
            "temp_range_c": {"value": [-40, 125], "evidence": r"Ambient Operating Temperature TA –40 25 125 °C"},
            "isolation_class": {"value": "basic", "evidence": r"60747-17: Up to 1414 Vpeak for basic insulation working voltage"},
            "certifications": {"value": ["UL", "CSA", "VDE", "CQC"], "evidence": r"The Si88xx is certified under GB4943\.1"},
            "creepage_mm": {"value": 7.6, "evidence": r"Nominal External Tracking \(Creepage\) CRP 7\.6 mm"},
            "viorm_vpk": {"value": 1414, "evidence": r"VIORM Breakdown \(TDDB\) Test 1414 Vpeak"},
            "esd_hbm_kv": {"value": 4, "evidence": r"HBM — 4 kV"},
            "integrated_power": {"value": "isolated dc-dc controller (external transformer)",
                                 "evidence": r"on-chip isolated dc-dc converter that"},
        },
        "package": [(r"^SI88[24]2", "SOIC-16W"), (r"^SI88[36]2", "SOIC-20W")],
        "notes": "Digital isolator with integrated isolated dc-dc converter controller and power switch "
                 "(transformer external; up to 5 W with external power switch). Data sheet: AEC-Q100 qualified "
                 "(industrial -IS OPNs too); -AS OPNs are the automotive-grade flow, electrically identical.",
    },
    "Si88x4x.pdf": {
        "series": "Si88x4x",
        "facts": {
            "isolation_rating_kvrms": {"by_iso": {"C": 3.75, "D": 5.0}, "evidence": r"5\.0 kVrms Insulation Rating"},
            "default_output": {"by_speed": {"B": "low", "E": "high"}, "evidence": r"All Si88xxxEx product options are default output high on input power loss\. All Si88xxxBx product options are default low"},
            "data_rate_mbps": {"value": 100.0, "evidence": r"Data Rate 0 — 100 Mbps"},
            "prop_delay_ns": {"value": 23.0, "evidence": r"Propagation Delay tPHL 13\.0 18\.0 23\.0 ns"},
            "pwd_ns": {"value": 7.0, "evidence": r"PWD — 4\.5 7\.0 ns"},
            "skew_ns": {"value": 4.0, "evidence": r"Channel-Channel Skew tPSK — 2\.0 4\.0 ns"},
            "cmti_kv_us": {"value": 40, "evidence": r"CMTI VCM = 1500 V 40 100 — kV"},
            "vdd_range_v": {"value": [3.0, 5.5], "evidence": r"VDDB 3\.0 — 5\.5 V"},
            "temp_range_c": {"value": [-40, 125], "evidence": r"Ambient Operating Temperature TA –40 25 125 °C"},
            "isolation_class": {"value": "basic", "evidence": r"60747-17: Up to 1414 Vpeak for basic insulation working voltage"},
            "certifications": {"value": ["UL", "CSA", "VDE", "CQC"], "evidence": r"The Si88xx is certified under GB4943\.1"},
            "creepage_mm": {"value": 7.6, "evidence": r"Nominal External Tracking \(Creepage\) CRP 7\.6 mm"},
            "viorm_vpk": {"value": 1414, "evidence": r"VIORM Breakdown \(TDDB\) Test 1414 Vpeak"},
            "esd_hbm_kv": {"value": 4, "evidence": r"HBM — 4 kV"},
            "integrated_power": {"value": "isolated dc-dc controller (external transformer)",
                                 "evidence": r"on-chip isolated dc-dc converter that"},
        },
        "package": [(r"^SI88[24]4", "SOIC-20W"), (r"^SI88[36]4", "SOIC-24W")],
        "notes": "Digital isolator with integrated isolated dc-dc converter controller and power switch "
                 "(transformer external; up to 5 W with external power switch). Data sheet: AEC-Q100 qualified "
                 "(industrial -IS OPNs too); -AS OPNs are the automotive-grade flow, electrically identical.",
    },
}  # fmt: skip
# Parts the product table links to a design guide instead of the data sheet.
DATASHEET_OVERRIDE = {
    "SI88621BC-AS": "si88x2x.pdf",
    "SI88642EC-AS": "Si88x4x.pdf",
    "SI8716BC-AS": "si871x-2x-datasheet.pdf",
}

# Where each Si87xx data sheet states the output polarity (truth table / ordering guide).
POLARITY_EVIDENCE = {
    "Si87xx.pdf": r"Table 10\. Si87xx Truth Table Summary",
    "si871x-2x-datasheet.pdf": r"Inverting Output",
    "si873x-datasheet.pdf": r"Si8736 \(Inverting\)",
}

BASE_RE = re.compile(r"^SI(80\d\d|84\d\d|87\d\d|88\d\d\d)", re.I)


# ------------------------------------------------------------------ fetching


def _pause_get(url: str, data: bytes | None = None, content_type: str | None = None) -> bytes:
    time.sleep(PAUSE_S)
    return skyworks._get(url, data, content_type)


def fetch(log=print) -> None:
    """Product tables, lifecycle rows and data sheets; files already present are not fetched again."""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DATASHEET_DIR.mkdir(parents=True, exist_ok=True)
    orig_get, skyworks._get = skyworks._get, _pause_get
    try:
        for name, item_id in PRODUCT_TABLES.items():
            path = RAW_DIR / f"table_{skyworks._slug(name)}.json"
            if not path.exists():
                path.write_text(json.dumps(skyworks.fetch_product_table(item_id)))
                log(f"product table {name}")
        state_path = RAW_DIR / "lifecycle.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {"done": [], "statuses": {}}
        for prefix in LIFECYCLE_PREFIXES:
            if prefix not in state["done"]:
                for opn, status in skyworks.fetch_lifecycle(prefix):
                    state["statuses"][opn.upper()] = status
                state["done"].append(prefix)
                state_path.write_text(json.dumps(state))
        for name in DATASHEETS:
            path = DATASHEET_DIR / name
            if not path.exists():
                path.write_bytes(skyworks._get(DATASHEET_URL + name))
                log(f"datasheet {name}")
    finally:
        skyworks._get = orig_get


# ------------------------------------------------------------------ parsing


class LayoutDatasheet(Datasheet):
    """Datasheet whose pages are searched in `pdftotext -layout` text (revision still from pdfplumber)."""

    def __init__(self, path: Path):
        super().__init__(path)
        TEXT_DIR.mkdir(parents=True, exist_ok=True)
        txt = TEXT_DIR / (path.stem + ".layout.txt")
        if not txt.exists() and shutil.which("pdftotext"):
            subprocess.run(["pdftotext", "-layout", str(path), str(txt)], check=True)
        if txt.exists():
            self.pages = txt.read_text().split("\f")
        self._found = {}

    def guide_line(self, opn: str) -> tuple[str, int] | None:
        """Ordering-guide line naming ``opn``: exact, with a die-revision letter, or with a footnote digit."""
        head, _, tail = opn.upper().partition("-")
        exact = {opn.upper()}
        revised = re.compile(rf"^{re.escape(head)}-[A-D]-{re.escape(tail)}$")
        footnote = re.compile(rf"^{re.escape(head)}(?:-[A-D])?-{re.escape(tail)}\d$")
        for test in (lambda t: t in exact or revised.match(t), lambda t: footnote.match(t)):
            for page_no, text in enumerate(self.pages, 1):
                for line in text.splitlines():
                    if any(test(t.upper()) for t in line.split()):
                        return " ".join(line.split()), page_no
        return None


def _flags(raw_dir: Path) -> dict[str, dict[str, bool]]:
    """Check-mark columns per OPN (skyworks.parse_tables drops the icon, so read them here)."""
    out: dict[str, dict[str, bool]] = {}
    for path in sorted(raw_dir.glob("table_*.json")):
        for row in json.loads(path.read_text())["dtProductSpecification"]:
            opn = re.search(r'class="link-title"[^>]*>\s*([^<\s]+)', row["Product"]).group(1).upper()
            for col in ("10 kV Surge", "AEC-Q100"):
                if col in row:
                    out.setdefault(opn, {})[col] = "fa-check" in str(row[col]) or str(row[col]).lower() in (
                        "yes",
                        "true",
                    )
    return out


def _resolve(fact: dict, ctx: dict):
    """Value of a curated fact for one OPN (ctx: package, speed, iso, base letters/names and kv)."""
    if "min_kv" in fact and (ctx.get("kv") is None or ctx["kv"] < fact["min_kv"]):
        return None
    for sel in ("by_package", "by_speed", "by_iso", "by_base"):
        if sel in fact:
            return fact[sel].get(ctx[sel[3:]])
    return fact.get("value")


def _find_first(sheet: "LayoutDatasheet", patterns: str | list[str]) -> int:
    for pattern in [patterns] if isinstance(patterns, str) else patterns:
        try:
            return sheet.find(pattern)
        except ValueError:
            continue
    raise ValueError(f"{sheet.path.name}: none of {patterns!r} found")


# ------------------------------------------------------------------ build


def build(raw_dir: Path = RAW_DIR, ds_dir: Path = DATASHEET_DIR) -> dict:
    si86 = yamlio.load(SI86_FACTS.read_text())
    layouts = {**si86["layouts"], **LAYOUTS}
    records = skyworks.parse_tables(raw_dir)
    flags = _flags(raw_dir)
    statuses = json.loads((raw_dir / "lifecycle.json").read_text())["statuses"]
    for opn, status in list(statuses.items()):
        statuses.setdefault(re.sub(r"-[A-D]-", "-", opn), status)
    alias = {a.upper(): p["code"] for p in PACKAGES for a in p["aliases"] + [p["code"]]}
    bases = {k.upper(): (k, v) for k, v in B.items()}

    sheets: dict[str, LayoutDatasheet] = {}
    pin_pages: dict[tuple, int] = {}
    parts, skipped, mismatches = [], [], []
    for opn, rec in sorted(records.items()):
        f = rec["fields"]
        m = BASE_RE.match(opn)
        if not m or m.group(0).upper() not in bases:
            skipped.append((opn, "no base part facts"))
            continue
        base_name, base = bases[m.group(0).upper()]
        ds_name = DATASHEET_OVERRIDE.get(opn) or Path(urllib.parse.urlparse(rec["datasheet_url"] or "").path).name
        if ds_name not in DATASHEETS:
            skipped.append((opn, f"no curated data sheet ({ds_name or 'none'})"))
            continue
        dsf = DATASHEETS[ds_name]
        if ds_name not in sheets:
            sheets[ds_name] = LayoutDatasheet(ds_dir / ds_name)
        sheet = sheets[ds_name]
        guide = sheet.guide_line(opn)
        notes = []
        if guide is None:
            notes.append(
                "Not listed in the data sheet ordering guide; values from the data sheet's general "
                "specifications and its part-number decoding."
            )

        # package: data sheet rule (ordering guide), cross-checked with the guide line and the web table
        pkg = next((code for rx, code in dsf["package"] if re.search(rx, opn)), None)
        if guide:
            hits = [
                alias[a]
                for a in sorted(alias, key=len, reverse=True)
                if re.search(rf"(?<![\w-]){re.escape(a)}(?![\w-])", guide[0].upper())
            ]
            if hits and hits[0] != pkg:
                mismatches.append(f"{opn}: package rule {pkg}, ordering guide line says {hits[0]}")
        table_pkg = alias.get((f.get("Package Type") or "").upper())
        if table_pkg and table_pkg != pkg:
            mismatches.append(f"{opn}: table says {table_pkg}, data sheet ordering guide says {pkg}")
        if pkg is None:
            skipped.append((opn, "package unknown"))
            continue

        rest = opn[len(m.group(0)) :]
        ctx = {"package": pkg, "speed": rest[:1], "iso": rest[1:2], "base": base_name}
        ctx["kv"] = _resolve(dsf["facts"]["isolation_rating_kvrms"], ctx)
        if ctx["kv"] is None:
            skipped.append((opn, f"isolation grade {rest[1:2]!r} not in the data sheet"))
            continue

        # pinout and channel configuration
        if "pinout" in base:
            if pkg not in base["pinout"]:
                skipped.append((opn, f"no {pkg} pinout in the data sheet"))
                continue
            pinout = base["pinout"][pkg]
            channel_config, enable = "1/0", base.get("enable", "none")
        else:
            lay = base["layout"]
            lay = lay.get(pkg) if isinstance(lay, dict) else lay
            if lay is None:
                skipped.append((opn, f"no {pkg} pinout in the data sheet"))
                continue
            pinout = build_pinout(base, layouts[lay])
            channel_config, enable = _channel_config(base["dirs"]), _enable_pins(base.get("ctl", []))
        if len(pinout) != next(p["pin_count"] for p in PACKAGES if p["code"] == pkg):
            raise ValueError(f"{opn}: pinout does not fit {pkg}")
        if (base_name, ds_name) not in pin_pages:
            pin_pages[base_name, ds_name] = _find_first(sheet, base["pinout_evidence"])
        if "dirs" in base and not set(base["dirs"]) & {"B"} and f.get("Forward Channels") is not None:
            tf, tr = int(f.get("Forward Channels") or 0), int(f.get("Reverse Channels") or 0)
            if (tf, tr) != (base["dirs"].count("F"), base["dirs"].count("R")):
                mismatches.append(f"{opn}: table says {tf}/{tr}, data sheet pinout {channel_config}")

        automotive = bool(re.search(r"-A[SMUP]\d?$", opn))
        params: dict = {
            "channel_config": channel_config,
            "integrated_power": "none",
            "qualification": "automotive" if automotive else "industrial",
            "enable_pins": enable,
            "isolation_rating_kvrms": ctx["kv"],
        }
        sources = {
            "channel_config": f"{ds_name} p.{pin_pages[base_name, ds_name]} (pinout)",
            "enable_pins": f"{ds_name} p.{pin_pages[base_name, ds_name]} (pinout)",
            "integrated_power": ds_name,
            "qualification": "OPN suffix (-A = automotive-grade flow)",
            "isolation_rating_kvrms": f"{ds_name} p.{guide[1]} (ordering guide)" if guide else "OPN isolation grade",
        }
        if "pinout" in base:  # Si87xx optocoupler replacements
            params["input_type"] = "led-emulator"
            params["output_polarity"] = base["polarity"]
            sources["input_type"] = f"{ds_name} p.{sheet.find(r'Anode of LED emulator')} (pin descriptions)"
            sources["output_polarity"] = f"{ds_name} p.{sheet.find(POLARITY_EVIDENCE[ds_name])}"
        for key, fact in dsf["facts"].items():
            if key == "isolation_rating_kvrms":
                continue
            value = _resolve(fact, ctx)
            if value is None:
                continue
            # the page of the row for this speed grade (data rate: the 1 Mbps grade has its own table)
            evidence = [(fact.get("evidence_by_speed") or {}).get(ctx["speed"]), fact["evidence"]]
            params[key], sources[key] = value, f"{ds_name} p.{_find_first(sheet, [e for e in evidence if e])}"
        # the ordering guide line decides default output where it states one
        if guide and "default_output" in params:
            d = re.search(r"\b(Low|High)\b", guide[0])
            if d and d.group(1).lower() != params["default_output"]:
                raise ValueError(f"{opn}: default output {params['default_output']} vs guide {guide[0]!r}")
        # web table: cross-check, and fill what the data sheet leaves open
        checks = {
            "isolation_rating_kvrms": skyworks._num(f.get("Isolation Rating (kVrms)")),
            "data_rate_mbps": skyworks._num(f.get("Max Data Rate (Mbps)")),
            "prop_delay_ns": skyworks._num(f.get("Max Propagation Delay")),
            "default_output": (f.get("Default Output State") or "").lower() or None,
        }
        for key, tv in checks.items():
            if tv is None:
                continue
            if key not in params and not (key == "default_output" and "pinout" in base):
                params[key], sources[key] = tv, "Skyworks product table"
            elif key in params and params[key] != tv and not (key == "default_output" and "pinout" in base):
                mismatches.append(f"{opn}: table {key} = {tv}, data sheet {params[key]}")
        if "10 kV Surge" in flags.get(opn, {}) and "surge_10kv" not in params:
            params["surge_10kv"], sources["surge_10kv"] = flags[opn]["10 kV Surge"], "Skyworks product table"

        # description
        series = dsf["series"]
        if "pinout" in base:
            desc = (
                f"{base_name} optocoupler-replacement isolator: LED-emulator input (no input-side supply), "
                f"{base['polarity']} {base['output']}, {ctx['kv']:g} kVrms"
            )
        elif base_name.startswith("Si88"):
            desc = (
                f"{base_name} {channel_config} digital isolator with isolated dc-dc converter controller "
                f"({SI88_DCDC[base_name[:6]]}; external transformer), {ctx['kv']:g} kVrms"
            )
        elif base_name.startswith("Si840"):
            desc = f"{base_name} {channel_config} I2C digital isolator (open-drain bidirectional), {ctx['kv']:g} kVrms"
        else:
            desc = f"{base_name} {channel_config} digital isolator ({series}), {ctx['kv']:g} kVrms"
        if automotive:
            desc += ", automotive grade"
        notes.append(dsf["notes"])
        if "pinout" in base:
            notes.append(f"Output: {base['polarity']} {base['output']}.")
        if base_name.startswith("Si88"):
            notes.append(f"dc-dc options: {SI88_DCDC[base_name[:6]]}.")

        status_text, status_src = statuses.get(opn, ""), "Skyworks lifecycle lookup"
        if not status_text and f.get("Product Lifecycle"):
            status_text, status_src = f["Product Lifecycle"], "Skyworks product table (OPN not in the lifecycle lookup)"
        parts.append({
            "mpn": opn,
            "manufacturer": "Skyworks",
            "family": "digital_isolator",
            "description": desc,
            "package": pkg,
            "pinout": list(pinout),
            "datasheet": ds_name,
            "datasheet_url": DATASHEET_URL + ds_name,
            "product_url": rec["product_url"],
            "notes": " ".join(n for n in notes if n),
            "lifecycle": {
                "status": LIFECYCLE_MAP.get(status_text.strip().lower(), "unknown"),
                "release_date": sheet.first_issue,
                "revision": sheet.revision,
                "revision_date": sheet.revision_date,
                "source": f"{status_src}: {status_text or 'not listed'}; release date = first datasheet revision",
            },
            "params": params,
            "param_sources": {**sources, "pinout": f"{ds_name} p.{pin_pages[base_name, ds_name]}"},
        })  # fmt: skip

    # Si86xx parts the Si86 importer skips for lack of a package in the web table: the ordering guide
    # names the package ("SOIC-8"), so run that importer with the alias added and keep only those parts.
    facts = yamlio.load(SI86_FACTS.read_text())
    for p in facts["packages"]:
        if p["code"] == "SOIC-8N" and "SOIC-8" not in p["aliases"]:
            p["aliases"].append("SOIC-8")
    tmp = raw_dir / "si86_facts_with_soic8_alias.yaml"
    import yaml

    tmp.write_text(yaml.safe_dump(facts, sort_keys=False, allow_unicode=True))
    si86_data = skyworks.build(facts_file=tmp)
    extra_sheets = set()
    si86_parts = {p["mpn"]: p for p in si86_data["parts"]}
    for opn in SI86_LEFTOVERS:
        part = si86_parts.get(opn)
        if part is None:
            continue
        # The web table row is empty; the ordering guide names this OPN and its automotive twin
        # ("Si8620EB-B-IS Si8620EB-AS 2 0 150 High 2.5 SOIC-8"): take data rate, delay and supply from the twin.
        twin = si86_parts.get(opn[:-3] + "-AS")
        part["notes"] = (
            "Package from the data sheet ordering guide (the web product table leaves it blank); data rate, "
            f"propagation delay and supply range from the table row of its automotive twin {twin['mpn']}, "
            "listed on the same ordering-guide line."
            if twin
            else "Package from the data sheet ordering guide."
        )
        for key in ("data_rate_mbps", "prop_delay_ns", "vdd_range_v"):
            if twin and key in twin["params"] and key not in part["params"]:
                part["params"][key] = twin["params"][key]
                part["param_sources"][key] = f"Skyworks product table ({twin['mpn']})"
        parts.append(part)
        extra_sheets.add(part["datasheet"])

    used_pkgs = {p["package"] for p in parts}
    datasheets = [
        {"file": name, "url": DATASHEET_URL + name, "sha256": s.sha256, "revision": s.revision,
         "revision_date": s.revision_date}
        for name, s in sorted(sheets.items())
    ] + [d for d in si86_data["datasheets"] if d["file"] in extra_sheets]  # fmt: skip
    covered = {p["mpn"] for p in parts}
    for opn in SI86_LEFTOVERS:
        if opn not in covered:
            skipped.append((opn, "not built by the Si86 importer"))
    return {
        "source": f"skyworksinc.com, built {date.today().isoformat()}",
        "manufacturers": [{"name": "Skyworks", "role": "reference", "website": "https://www.skyworksinc.com"}],
        "packages": [{k: v for k, v in p.items() if k != "aliases"} for p in PACKAGES if p["code"] in used_pkgs],
        "datasheets": datasheets,
        "parts": parts,
        "skipped": [f"{opn} ({why})" for opn, why in skipped],
        "table_vs_datasheet": mismatches,
    }


def main(argv: list[str]) -> int:
    import yaml

    if "--offline" not in argv:
        fetch()
    data = build()
    header = (
        "# Skyworks Si80xx / Si84xx / Si87xx / Si88xx digital isolators (and two Si86xx OPNs the Si86 importer\n"
        "# skips). Built by app/sources/skyworks_isolators_more.py from the public product tables, lifecycle\n"
        "# lookup and data sheets on skyworksinc.com; every data sheet value cites its page.\n"
    )
    OUT.write_text(header + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=200))
    print(f"Built {len(data['parts'])} parts ({len(data['skipped'])} skipped) -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
