"""TI datasheet table parsing, using table rows as pdfplumber extracts them."""

from app.parsing.ti_datasheet import (
    _parse_pin_rows,
    _read_insulation_table,
    canonical_pinout,
    classes_from_text,
)
from app.sources.ti import _fwd_rev, _pinout_fwd_rev, default_output_from_opn

# ISO7720/ISO7721 pin table (two packages, two devices each)
ISO772X_PINS = [
    ["PIN", None, None, None, None, "", ""],
    ["NAME", "DW PACKAGE", None, "D, DWV PACKAGE", None, "I/O(1)", "DESCRIPTION"],
    [None, "ISO7720", "ISO7721", "ISO7720", "ISO7721", None, None],
    ["GND1", "1, 7", "1, 7", "4", "4", "—", "Ground connection for VCC1"],
    ["GND2", "9", "9", "5", "5", "—", "Ground connection for VCC2"],
    [None, "16", "16", None, None, None, None],
    ["INA", "4", "13", "2", "7", "I", "Input, channel A"],
    ["INB", "5", "5", "3", "3", "I", "Input, channel B"],
    ["NC", "2, 6, 8, 10, 11,\n15", "2, 6, 8, 10, 11,\n15", "—", "—", "—", "Not connected"],
    ["OUTA", "13", "4", "7", "2", "O", "Output, channel A"],
    ["OUTB", "12", "12", "6", "6", "O", "Output, channel B"],
    ["VCC1", "3", "3", "1", "1", "—", "Power supply, VCC1"],
    ["VCC2", "14", "14", "8", "8", "—", "Power supply, VCC2"],
]


def test_pin_table_with_device_columns_and_continuation_rows():
    columns, by_package, rows = _parse_pin_rows(ISO772X_PINS)
    assert columns == ["ISO7720", "ISO7721", "ISO7720", "ISO7721"] and not by_package
    assert rows["GND2"][0] == [9, 16]  # continuation row merged
    assert rows["NC"][0] == [2, 6, 8, 10, 11, 15]


def test_iso7721_soic8_is_the_mirror_of_si8621():
    _, _, rows = _parse_pin_rows(ISO772X_PINS)
    pins = canonical_pinout(rows, 3)
    assert pins == ["VDD1", "OUTA", "INB", "GND1", "GND2", "OUTB", "INA", "VDD2"]
    assert _pinout_fwd_rev(pins, 8) == (1, 1)


def test_wide_body_iso7720_pinout():
    _, _, rows = _parse_pin_rows(ISO772X_PINS)
    pins = canonical_pinout(rows, 0)
    assert pins[3:5] == ["INA", "INB"] and pins[11:13] == ["OUTB", "OUTA"] and pins[1] == "NC"


def test_insulation_table_per_package():
    table = [
        ["", "", "", "", "VALUE", "", "", ""],
        ["PARAMETER", "", "TEST CONDITIONS", "", "DW-16", "DUW- 16", "DBQ-1 6", "UNIT"],
        ["CLR", "External clearance(1)", "Shortest", "", ">8", ">21.2", ">3.7", "mm"],
        ["CPG", "External creepage(1)", "Shortest", "", ">8", ">21.2", ">3.7", "mm"],
        ["V IORM", "Maximum repetitive peak", "AC voltage (bipolar)", "", "2121", "2121", "566", "V PK"],
        ["V ISO", "Withstand isolation voltage", "V = V", "", "5000", "5700", "3000", "V RMS"],
    ]
    ins = _read_insulation_table(table, 9, None)
    assert ins.packages == ["DW", "DUW", "DBQ"]
    assert ins.creepage_mm == {"DW": 8.0, "DUW": 21.2, "DBQ": 3.7}
    assert ins.viso_vrms["DBQ"] == 3000 and ins.viorm_vpk["DW"] == 2121


def test_certification_classes():
    assert classes_from_text("2121 VPK (DW-16, DWV-8, Reinforced), 1414 VPK (D-8, Basic)") == {
        "DW": "reinforced",
        "DWV": "reinforced",
        "D": "basic",
    }
    text = "Reinforced certificate: 40040142 File number (DW-16) Basic certificate: 40047657 (DBQ-16)"
    assert classes_from_text(text) == {"DW": "reinforced", "DBQ": "basic"}


def test_default_output_convention():
    assert default_output_from_opn("ISO6440FDWR", "ISO6440") == "low"
    assert default_output_from_opn("ISO6440DWR", "ISO6440") == "high"
    assert default_output_from_opn("ISO7641FCDW", "ISO7641FC") == "low"
    assert default_output_from_opn("ISOW7721FDFMR", "ISOW7721") is None  # convention not used for ISOW


def test_forward_reverse_text():
    assert _fwd_rev("3 forward / 1 reverse") == (3, 1)
    assert _fwd_rev("") is None
