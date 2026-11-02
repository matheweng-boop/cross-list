"""Analog Devices gate drivers and isolated amplifiers (data/real/adi_gate_drivers.yaml, adi_isolated_amplifiers.yaml):
facts read from the owner-uploaded ADI datasheets, and every value traced to a datasheet page."""

import copy
import re
from functools import lru_cache
from pathlib import Path

import pytest

from app import yamlio
from app.matching.rules import load_all_rules

DATA = Path(__file__).resolve().parents[1] / "data" / "real"
FILES = ("adi_gate_drivers.yaml", "adi_isolated_amplifiers.yaml")


@lru_cache
def _data(name: str) -> dict:
    return yamlio.load((DATA / name).read_text())


@lru_cache
def _parts(name: str) -> dict[str, dict]:
    """Parts with ``like`` resolved, as the loader resolves them."""
    resolved: dict[str, dict] = {}
    for raw in _data(name)["parts"]:
        spec = copy.deepcopy(resolved[raw["like"]]) if "like" in raw else {}
        if "like" in raw:
            spec.pop("lifecycle", None)
        params = {**spec.get("params", {}), **raw.get("params", {})}
        spec.update({k: v for k, v in raw.items() if k not in ("like", "params")})
        spec["params"] = params
        resolved[spec["mpn"]] = spec
    return resolved


def _p(mpn: str) -> dict:
    for name in FILES:
        if mpn in _parts(name):
            return _parts(name)[mpn]
    raise KeyError(mpn)


def test_one_part_per_ordering_code():
    gd, ia = set(_parts(FILES[0])), set(_parts(FILES[1]))
    # ADuM4121/-1 12, ADuM4122 6, ADuM4136 2, ADuM4137 2, ADuM4138 2, ADuM4177 2 (ordering guides)
    assert len(gd) == 26
    assert {"ADuM4121-1CRIZ-RL", "ADuM4122BRIZ", "ADuM4136BRWZ-RL", "ADuM4137WBRNZ", "ADuM4138WBRNZ-RL",
            "ADUM4177WBRNZ-RL"} <= gd  # fmt: skip
    # ADuM3195/4195 8 (Rev. B p.22), ADuM4195-1 4 (Rev. C p.16)
    assert len(ia) == 12
    assert {"ADuM3195WBRQZ-RL7", "ADuM4195BRIZ-RL", "ADUM4195-1WBRIZ-R7"} <= ia


@pytest.mark.parametrize("name", FILES)
def test_every_value_has_a_datasheet_page(name):
    sheets = {d["file"] for d in _data(name)["datasheets"]}
    for mpn, spec in _parts(name).items():
        sources = spec["param_sources"]
        assert spec["datasheet"] in sheets, mpn
        for key in [*spec["params"], "pinout"]:
            src = sources.get(key)
            assert src, f"{mpn}: {key} has no source"
            assert src.startswith(spec["datasheet"]) and re.search(r"\bp\.\d", src), f"{mpn}: {key}: {src}"


@pytest.mark.parametrize("name", FILES)
def test_parameters_and_pinouts_fit_the_rules(name):
    rules = load_all_rules()
    data = _data(name)
    pkgs = {p["code"]: p for p in data["packages"]}
    for mpn, spec in _parts(name).items():
        assert spec["manufacturer"] == "Analog Devices"
        assert not set(spec["params"]) - {p.key for p in rules[spec["family"]].params}, mpn
        pinout = data["pinouts"][spec["pinout"]]
        assert len(pinout) == pkgs[spec["package"]]["pin_count"], mpn
        # the datasheets state no production status
        assert spec.get("lifecycle", {}).get("status", "unknown") == "unknown", mpn


@pytest.mark.parametrize("name", FILES)
def test_datasheets_are_owner_uploads(name):
    for d in _data(name)["datasheets"]:
        assert re.fullmatch(r"[0-9a-f]{64}", d["sha256"])
        assert d["origin"] == "owner upload, 30 Oct 2026"
        assert re.match(r"https?://www\.analog\.com/", d["url"])
        assert d["revision"] and d["revision_date"]


def test_adum4177_peak_currents():
    # Rev. 0 p.1: "40 A source, 30 A sink peak short-circuit (typical)"; p.6: 20 A / 15 A per output pin, 0 Ω
    p = _p("ADUM4177WBRNZ")
    assert (p["params"]["peak_source_a"], p["params"]["peak_sink_a"]) == (40.0, 30.0)
    for key in ("peak_source_a", "peak_sink_a"):
        assert "ADuM4177.pdf p.1" in p["param_sources"][key] and "p.6" in p["param_sources"][key]
    assert p["params"]["isolation_rating_kvrms"] == 5.7 and p["params"]["qualification"] == "automotive"
    assert _p("ADUM4177WBRNZ-RL")["params"] == p["params"]


def test_uvlo_grades_and_thermal_shutdown_option():
    # ADuM4121 / ADuM4122 p.3: VDD2 positive-going threshold typ 4.4 / 7.3 / 11.3 V for grades A / B / C
    for base in ("ADuM4121", "ADuM4121-1", "ADuM4122"):
        got = [_p(f"{base}{g}RIZ")["params"]["uvlo_v"] for g in "ABC"]
        assert got == [4.4, 7.3, 11.3], base
    assert "without thermal shutdown" in _p("ADuM4121-1BRIZ")["notes"]
    assert "Miller clamp" in _p("ADuM4121CRIZ")["params"]["protection"]


def test_desat_drivers_and_insulation_class():
    a36, a38 = _p("ADuM4136BRWZ")["params"], _p("ADuM4138WBRNZ")["params"]
    assert a36["isolation_class"] == "basic" and a36["creepage_mm"] == 7.8  # ADuM4136 p.4
    assert {"desaturation", "soft shutdown"} <= set(a36["protection"])
    assert {"desaturation", "overcurrent", "Miller clamp"} <= set(a38["protection"])  # ADuM4138 p.1
    assert "overcurrent" in _p("ADuM4137WBRNZ")["params"]["protection"]
    assert "desaturation" not in _p("ADuM4137WBRNZ")["params"]["protection"]  # split-emitter OC only
    # no CMTI in the ADuM4137 / ADuM4138 electrical tables: left out, not guessed
    assert "cmti_kv_us" not in a38 and "cmti_kv_us" not in _p("ADuM4137WBRNZ")["params"]


def test_automotive_only_for_w_grades():
    for name in FILES:
        for mpn, spec in _parts(name).items():
            auto = "WBR" in mpn.upper()  # W = qualified for automotive applications (ordering guides)
            assert (spec["params"]["qualification"] == "automotive") == auto, mpn


def test_isolated_amplifier_facts():
    a31, a41, a1 = _p("ADuM3195BRQZ")["params"], _p("ADuM4195BRIZ")["params"], _p("ADUM4195-1BRIZ")["params"]
    assert (a31["isolation_rating_kvrms"], a31["creepage_mm"]) == (3.0, 3.5)  # Rev. B p.7, Table 5
    assert (a41["isolation_rating_kvrms"], a41["creepage_mm"]) == (5.0, 8.7)  # Rev. B p.7, Table 6
    assert a1["offset_uv"] == 5000.0 and a41["offset_uv"] == 6000.0  # ±5 mV / ±6 mV max at 25 °C
    for p in (a31, a41, a1):
        assert p["output_type"] == "analog, single-ended" and p["sense_type"] == "voltage"
        assert p["bandwidth_khz"] == 210.0 and p["cmti_kv_us"] == 100.0


@pytest.mark.parametrize("name", FILES)
def test_sha256_matches_the_upload_when_present(name):
    import hashlib

    up = Path("/root/.claude/uploads")
    found = {f.name.split("-", 1)[1].lower(): f for f in up.glob("*/*.pdf")} if up.is_dir() else {}
    checked = 0
    for d in _data(name)["datasheets"]:
        f = found.get(d["file"].lower())
        if f is not None:
            assert hashlib.sha256(f.read_bytes()).hexdigest() == d["sha256"], d["file"]
            checked += 1
    if not checked:
        pytest.skip("uploaded PDFs not on this machine")
