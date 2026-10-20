"""Engineering knowledge > Interactive visuals: the page renders and its reference lines come from the cross lists."""

import json
import re

from app.services import visuals


def test_page_renders_with_reference_data(client):
    page = client.get("/visuals")
    assert page.status_code == 200 and "/static/visuals.js" in page.text
    raw = re.search(r'<script id="vz-data" type="application/json">(.*?)</script>', page.text, re.S).group(1)
    data = json.loads(raw)
    assert set(data) == {"cmti", "drivers", "creepage"}


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
