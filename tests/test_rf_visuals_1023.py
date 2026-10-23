"""Owner feedback 23 Oct 2026 on the RF visuals: RF bands by type and application, the dBm ladder's plain
explanations, real Skyworks parts in the noise-figure cascade, and the FM intermodulation visual."""

import json
import re

from app.config import PROJECT_ROOT
from app.services import library, rf_bands, rf_notes, visuals

JS = (PROJECT_ROOT / "app" / "web" / "static" / "visuals.js").read_text()


def test_band_types_and_ten_applications_point_to_real_bands():
    d = rf_bands.data()
    ids = {b["id"] for b in d["bands"]}
    types, apps = d["types"], d["applications"]
    assert len(apps) == 10 and all(a["label"] and a["note"] and a["bands"] for a in apps)
    for x in types + apps:
        assert set(x["bands"]) <= ids, x["id"]
    assert ids <= {b for t in types for b in t["bands"]}  # every band has a type, so every band can be shown
    labels = {t["label"] for t in types}
    assert {"AM", "FM", "DAB", "GNSS", "Wi-Fi", "UWB", "V2X", "Radar"} <= labels
    assert next(t for t in types if t["id"] == "fm")["bands"] == ["fm"]


def test_rf_bands_page_has_type_chips_and_applications(client):
    page = client.get("/rf-bands").text
    assert 'data-view="types"' in page and 'id="rbt-chart"' in page
    assert page.count('class="rbt-chip"') == len(rf_bands.data()["types"])
    assert 'data-app="car_info"' in page and 'data-app="drone"' in page and ">Mobile phone<" in page
    raw = re.search(r'<script id="rb-data" type="application/json">(.*?)</script>', page, re.S).group(1)
    data = json.loads(raw)
    assert len(data["apps"]) == 10 and data["types"]


def test_band_detail_gives_wavelength_and_antenna(client):
    fm = client.get("/rf-bands/fm").text
    assert "λ = 3.26 m" in fm and "λ/4 = 81.5 cm" in fm  # 92 MHz centre


def test_ladder_explains_every_rung_and_links_existing_notes():
    for name in ("GNSS signal at the antenna", "BLE sensitivity", "1 mW: the reference", "IIP3 of a good LNA",
                 "Strong blocker at a receiver"):  # fmt: skip
        assert f'name: "{name}"' in JS
    ids = {t["id"] for t in rf_notes.topics()}
    assert {"dbm_basics", "iip3_basics"} <= ids
    linked = set(re.findall(r"/rf-notes#([a-z0-9_]+)", JS)) | set(re.findall(r'NOTE\("([a-z0-9_]+)"\)', JS))
    assert linked and linked <= ids, linked - ids


def test_cascade_examples_use_real_skyworks_parts():
    parts = {p["mpn"]: p for p in visuals.rf_parts()}
    used = re.findall(r'part: "([A-Z0-9-]+)"', JS)
    assert len(used) >= 4
    for mpn in used:
        assert parts[mpn]["mfr"] == "Skyworks", mpn
    assert parts["SKY67151-396LF"]["nf"] == 0.25 and parts["SKY13489-001"]["il"] == 0.25
    assert "il" not in parts["SKY85922-11"]  # the filter example shows "Not Enough Data" for its loss
    assert "Not Enough Data" in JS


def test_fm_intermodulation_visual_is_listed():
    assert 'id: "fmim"' in JS and "fmim" in library.VISUALS
    assert "2A − B" in JS and "/find?q=Si47" in JS and "image" in JS
    # the default example: stations at 91.0 and 89.5 MHz put 2A - B on the tuned 92.5 MHz
    assert "value: 92.5" in JS and "value: 91," in JS and "value: 89.5" in JS and round(2 * 91 - 89.5, 1) == 92.5


def test_visuals_page_loads_the_rf_styles(client):
    assert "/static/rf_visuals.css" in client.get("/visuals").text
    assert client.get("/static/rf_visuals.css").status_code == 200
