"""Analog Devices digital isolators (data/real/adi_digital_isolators.yaml), read from public ADI datasheets the owner
uploaded on 30 Oct 2026 (analog.com blocks automated access). The checks are facts printed in the datasheets."""

import re
from functools import lru_cache
from pathlib import Path

import pytest

from app import yamlio
from app.matching.rules import load_all_rules

FILE = Path(__file__).resolve().parents[1] / "data" / "real" / "adi_digital_isolators.yaml"
pytestmark = pytest.mark.smoke
PAGE = re.compile(r"\.pdf p\.\d+")


@lru_cache
def data() -> dict:
    return yamlio.load(FILE.read_text())


def parts() -> dict[str, dict]:
    return {p["mpn"]: p for p in data()["parts"]}


def test_maker_and_origin():
    d = data()
    assert d["manufacturers"] == [{"name": "Analog Devices", "role": "competitor", "website": "https://www.analog.com"}]
    assert "owner upload, 30 Oct 2026" in d["source"]
    for sheet in d["datasheets"]:
        assert sheet["origin"] == "owner upload, 30 Oct 2026" and len(sheet["sha256"]) == 64
        assert sheet["url"].startswith("https://www.analog.com/media/en/technical-documentation/data-sheets/")
    assert {p["manufacturer"] for p in d["parts"]} == {"Analog Devices"}


def test_every_value_cites_a_datasheet_page():
    sheets = {s["file"] for s in data()["datasheets"]}
    rules = {p.key for p in load_all_rules()["digital_isolator"].params}
    for p in data()["parts"]:
        assert p["datasheet"] in sheets
        assert set(p["params"]) <= rules, p["mpn"]
        keys = set(p["params"]) | ({"pinout"} if p["pinout"] else set())
        assert keys == set(p["param_sources"]), p["mpn"]
        for key, src in p["param_sources"].items():
            assert PAGE.search(src) and src.startswith(p["datasheet"]), (p["mpn"], key, src)
        assert p["lifecycle"]["status"] == "unknown"  # the datasheets state none; analog.com was not checked


def test_adum1411():
    """adum1410_1411_1412.pdf Rev. N: 3 inputs on side 1, 1 on side 2 (p.23); 10 Mbps B grade, 1 Mbps A grade
    (p.4-5); 2500 V rms (p.11); CTRL1/CTRL2 default-output pins on pins 7 and 10 (p.15-16), open = high."""
    b, a = parts()["ADuM1411BRWZ"], parts()["ADuM1411ARWZ"]
    assert b["params"]["channel_config"] == a["params"]["channel_config"] == "3/1"
    assert b["param_sources"]["channel_config"].startswith("adum1410_1411_1412.pdf p.23")
    assert b["params"]["data_rate_mbps"] == 10.0 and a["params"]["data_rate_mbps"] == 1.0
    assert b["params"]["isolation_rating_kvrms"] == 2.5 and b["params"]["temp_range_c"] == [-40.0, 105.0]
    assert b["pinout"][6] == "CTRL1" and b["pinout"][9] == "CTRL2" and b["pinout"][5] == "VOD"
    assert b["params"]["default_output"] == "high" and "CTRL" in b["param_sources"]["default_output"]
    assert b["params"]["qualification"] == "industrial"
    assert {m for m in parts() if m.startswith("ADuM141") and m[8] in "AB"} == {
        f"ADuM141{n}{g}RWZ{r}" for n in "012" for g in "AB" for r in ("", "-RL")}


def test_fail_safe_and_enable_options():
    """adum140d...pdf Rev. K p.29: E1 = fail-safe high with output enable, D0 = low with input disable; W models are
    the automotive ones (p.28)."""
    p = parts()
    assert p["ADuM141E1BRWZ"]["params"]["default_output"] == "high"
    assert p["ADuM141E1BRWZ"]["params"]["enable_pins"] == "EN1+EN2 active-high"
    assert p["ADuM141D0BRZ"]["params"]["default_output"] == "low"
    assert p["ADuM141D0BRZ"]["params"]["enable_pins"].startswith("DISABLE1+DISABLE2")
    assert p["ADuM141E1WBRWZ"]["params"]["qualification"] == "automotive"
    assert p["ADuM141E1BRWZ"]["params"]["qualification"] == "industrial"
    assert p["ADuM141E0BRZ"]["params"]["isolation_rating_kvrms"] == 3.0
    assert p["ADuM141E0BRWZ"]["params"]["isolation_rating_kvrms"] == 3.75
    assert p["ADuM241E1WBRWZ"]["params"]["isolation_rating_kvrms"] == 5.0


def test_adum1400_grades():
    """adum1400_1401_1402.pdf Rev. M: A 1 Mbps, B 10 Mbps, C 90 Mbps; W = automotive, -40 to +125 C (p.31-32)."""
    p = parts()
    assert [p[f"ADuM1401{g}RWZ"]["params"]["data_rate_mbps"] for g in "ABC"] == [1.0, 10.0, 90.0]
    assert p["ADuM1401WTRWZ"]["params"]["qualification"] == "automotive"
    assert p["ADuM1401WTRWZ"]["params"]["temp_range_c"] == [-40.0, 125.0]
    assert p["ADuM1400ARW"]["params"]["channel_config"] == "4/0"
