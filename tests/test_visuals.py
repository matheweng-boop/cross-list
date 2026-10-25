"""Engineering knowledge > Interactive visuals: the page renders and its reference lines come from the cross lists."""

import json
import re

from app.services import visuals


def test_page_renders_with_reference_data(client):
    page = client.get("/visuals")
    assert page.status_code == 200 and "/static/visuals.js" in page.text
    raw = re.search(r'<script id="vz-data" type="application/json">(.*?)</script>', page.text, re.S).group(1)
    data = json.loads(raw)
    assert set(data) == {"cmti", "drivers", "creepage", "bands"}  # bands: RF bands data for the ranges (24 Oct)


def test_reference_parts_are_exact_part_numbers():
    for label, mpn, _ours in visuals.CMTI_REFS + visuals.DRIVER_REFS:
        assert label and mpn == mpn.strip().upper()


def test_iso6441_cmti_is_the_datasheet_minimum():
    import yaml

    from app.config import PROJECT_ROOT

    parts = yaml.safe_load((PROJECT_ROOT / "data" / "real" / "ti_digital_isolators.yaml").read_text())["parts"]
    p = {x["mpn"]: x["params"] for x in parts}
    assert p["ISO6441FDWR"]["cmti_kv_us"] == 200 and p["ISO6441DBQR"]["cmti_kv_us"] == 150
    assert p["ISO6441FDWR"]["data_rate_mbps"] == 150 and p["ISO6441DWRQ1"]["cmti_kv_us"] == 200


def test_rf_parts_for_the_receiver_visuals(client):
    parts = client.get("/api/visuals/rf-parts").json()["parts"]
    assert parts and {p["stage"] for p in parts} >= {"lna", "switch", "filter"}
    assert all(p["mfr"] in ("Skyworks", "Qorvo") and p["fmin"] <= p["fmax"] for p in parts)
    lna = next(p for p in parts if p["mpn"] == "SKY67151-396LF")
    assert lna["stage"] == "lna" and lna["nf"] == 0.25 and lna["fmin"] == 0.7 and lna["fmax"] == 3.8


def test_spec_parsing():
    assert visuals._nums("0.4-3.0") == [0.4, 3.0] and visuals._nums("-75") == [-75.0]
    n = visuals._rf_numbers({"Frequency Range (GHz)": "0.4-3.0", "Gain Typ. (dB)": "16", "OIP3 (dBm)": "30"}, "lna")
    assert n == {"fmin": 0.4, "fmax": 3.0, "gain": 16.0, "oip3": 30.0, "iip3": 14.0}
    assert visuals._rf_numbers({"Frequency Range": "1710-1950", "Gain (dB)": "26"}, "gain")["fmax"] == 1.95
