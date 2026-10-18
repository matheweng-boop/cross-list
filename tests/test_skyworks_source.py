"""Skyworks importer: pinout generation and table parsing (offline)."""

import json
import re

import pytest
import yaml

from app.sources import skyworks

FACTS = yaml.safe_load(skyworks.FACTS_FILE.read_text())


def pinout(base: str, package: str | None = None) -> list[str]:
    spec = FACTS["base_parts"][base]
    layout = spec["layout"]
    if isinstance(layout, dict):
        layout = layout[package]
    return skyworks.build_pinout(spec, FACTS["layouts"][layout])


# Expected values read from the datasheet pin drawings.
def test_si8641_quad_3_1():
    assert pinout("Si8641") == [
        "VDD1", "GND1", "INA", "INB", "INC", "OUTD", "EN1", "GND1",
        "GND2", "EN2", "IND", "OUTC", "OUTB", "OUTA", "GND2", "VDD2",
    ]  # fmt: skip


def test_si8640_has_nc_on_pin_7_and_si8645_has_no_enables():
    assert pinout("Si8640")[6:10] == ["NC", "GND1", "GND2", "EN2"]
    assert pinout("Si8645")[6] == pinout("Si8645")[9] == "NC"


def test_si8622_first_channel_is_reverse():
    assert pinout("Si8622", "SOIC-8N") == ["VDD1", "OUTA", "INB", "GND1", "GND2", "OUTB", "INA", "VDD2"]
    assert pinout("Si8621", "SOIC-8N") == ["VDD1", "INA", "OUTB", "GND1", "GND2", "INB", "OUTA", "VDD2"]


def test_si86s663_reverse_channels_last():
    p = pinout("Si86S663")
    assert p[1:7] == ["INA", "INB", "INC", "OUTD", "OUTE", "OUTF"]
    assert p[9:15] == ["INF", "INE", "IND", "OUTC", "OUTB", "OUTA"]


def test_i2c_and_power_layouts():
    assert pinout("Si86S602") == ["VDD1", "IOA", "INB", "GND1", "GND2", "OUTB", "IOA", "VDD2"]
    p = pinout("Si86P341")
    assert p[:6] == ["DNC", "VI", "GNDI", "GNDI", "VDD1", "GND1"] and p[9:11] == ["OUTD", "IND"]


def test_every_base_part_builds_a_complete_pinout():
    for name, spec in FACTS["base_parts"].items():
        layouts = spec["layout"].values() if isinstance(spec["layout"], dict) else [spec["layout"]]
        for layout in layouts:
            pins = skyworks.build_pinout(spec, FACTS["layouts"][layout])
            assert len(pins) == FACTS["layouts"][layout]["pins"], name


def test_wrong_channel_count_is_rejected():
    with pytest.raises(ValueError, match="channel directions"):
        skyworks.build_pinout({"dirs": "FF"}, FACTS["layouts"]["quad16"])


def test_channel_config_and_enable_text():
    assert skyworks._channel_config("FFFR") == "3/1"
    assert skyworks._channel_config("BFFB") == "2/0 + 2 bidir"
    assert skyworks._enable_pins(["NC", "EN2"]) == "EN2 active-high"
    assert skyworks._enable_pins(["SLEEP1", "NC"]) == "sleep pin (active-low)"
    assert skyworks._enable_pins([]) == "none"


def test_parse_tables(tmp_path):
    row = {
        "Product": '<a href="/-/media/x/si864x-datasheet.pdf"></a>&nbsp;<a class="link-title" '
        'href="/en/Products/Isolation/Si86xx-Digital-Isolators/SI8641BD-IS"> SI8641BD-IS </a>',
        "Package Type": "WB SOIC16",
        "Isolation Rating (kVrms)": "5.0",
        "Ecommerce": "Buy Now",
    }
    (tmp_path / "table_a.json").write_text(json.dumps({"dtProductSpecification": [row]}))
    rec = skyworks.parse_tables(tmp_path)["SI8641BD-IS"]
    assert rec["datasheet_url"].endswith("si864x-datasheet.pdf")
    assert rec["fields"] == {"Package Type": "WB SOIC16", "Isolation Rating (kVrms)": "5.0"}


def test_lifecycle_literal_with_trailing_comma():
    text = 'var productStatusData = [["SI8641BD-IS","In Production","/s", ""],["SI8641BD-ISR","","/s", ""],];'
    m = re.search(r"var productStatusData = (\[.*?\]);", text, re.S)
    assert re.findall(r'\[\s*"([^"]+)"\s*,\s*"([^"]*)"', m.group(1))[0] == ("SI8641BD-IS", "In Production")
    assert skyworks.LIFECYCLE_MAP["in production"] == "active"
