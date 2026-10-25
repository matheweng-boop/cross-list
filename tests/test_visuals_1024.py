"""Owner feedback 24 Oct 2026 on Engineering knowledge > Interactive visuals: show applications as frequency ranges
from the RF bands data ("FM is not only at 100 MHz"), and a new "Hex, binary and registers" visual."""

import json
import re
import shutil
import subprocess

import pytest

from app.config import PROJECT_ROOT
from app.services import library, rf_bands, visuals

STATIC = PROJECT_ROOT / "app" / "web" / "static"
JS = (STATIC / "visuals.js").read_text()
HEX_JS = STATIC / "vz" / "hex.js"


def _ranges(band_id: str) -> list[list[float]]:
    return [[float(lo), float(hi)] for lo, hi, _ in rf_bands.band(band_id)["ranges"]]


def test_band_ranges_for_the_visuals_match_the_rf_bands_data():
    bands = visuals.band_ranges()
    for bid in ("fm", "am", "dab", "gnss_l1", "gnss_l2", "gnss_l5", "ism24", "wifi5", "wifi6", "uwb5", "uwb9", "b8"):
        assert [r[:2] for r in bands[bid]["ranges"]] == _ranges(bid), bid
    assert [r[:2] for r in bands["fm"]["ranges"]] == [[76.0, 108.0]]
    assert [r[:2] for r in bands["am"]["ranges"]] == [[0.148, 0.283], [0.53, 1.71]]
    assert [r[:2] for r in bands["dab"]["ranges"]] == [[174.0, 240.0]]
    sub = {lab: (lo, hi) for lo, hi, lab in bands["fm"]["sub"]}
    assert (
        sub["Japan"] == (76.0, 95.0) and sub["most countries"] == (87.5, 108.0) and sub["OIRT (legacy)"] == (65.8, 74.0)
    )
    assert not any(b["group"] == "ieee" for b in bands.values())


def test_visuals_page_carries_the_same_band_ranges(client):
    page = client.get("/visuals").text
    data = json.loads(re.search(r'<script id="vz-data" type="application/json">(.*?)</script>', page, re.S).group(1))
    for bid in ("fm", "am", "dab"):
        assert [r[:2] for r in data["bands"][bid]["ranges"]] == _ranges(bid), bid


def test_frequency_visuals_use_the_band_ranges_not_single_frequencies():
    # wavelength chart: AM, FM and DAB (and the others) drawn as bands from the data, no single-frequency markers
    wave = re.search(r"const WAVE_BANDS = (\[.*?\]);", JS, re.S).group(1)
    ids = re.findall(r'\["([a-z0-9_]+)"', wave)
    assert {"am", "fm", "dab", "b8", "gnss_l1", "gnss_l5", "ism24", "wifi5", "wifi6", "uwb9", "radar_77"} <= set(ids)
    assert set(ids) <= set(visuals.band_ranges())
    assert '[0.1, "FM"]' not in JS and "bands: appBands(WAVE_BANDS, 1e-3)" in JS
    # FM intermodulation: the FM band by region, the FM and DAB checks from the data
    assert 'appBands([["fm"]], 1, true)' in JS and 'inR("dab", p.f)' in JS and "f >= 76 && f <= 108;" not in JS
    # one-frequency calculations keep the value and show the range strip: dBm blocker, noise figure, link budget
    assert JS.count("bandStrip(v.f * 1000") == 3 and JS.count("bandOut(v.f * 1000") >= 4
    assert "carrier is about 100 MHz" not in JS
    # separate visuals: the DAB block inside Band III, UWB channels as ranges
    assert "bandStrip(fc," in (STATIC / "vz" / "dab.js").read_text()
    assert 'bandText("uwb9")' in (STATIC / "vz" / "uwb.js").read_text()


def test_hex_visual_is_registered_and_included(client):
    assert library.VISUALS["hex"][:2] == ("Hex, binary and registers", "/visuals#hex")
    inc = (PROJECT_ROOT / "app" / "web" / "templates" / "engineering" / "visuals" / "_hex.html").read_text()
    assert "/static/vz/hex.js" in inc and "/static/vz/hex.css" in inc
    page = client.get("/visuals").text
    assert '<script src="/static/vz/hex.js"></script>' in page
    assert page.index("/static/vz/hex.js") < page.index("/static/visuals.js")  # registers before the engine runs
    assert client.get("/static/vz/hex.js").status_code == 200 and client.get("/static/vz/hex.css").status_code == 200
    src = HEX_JS.read_text()
    for part in ("window.VZ_ADD", 'id: "hex"', "nibbles", "Byte order", "BCD", "Gray code", "ASCII", "Si47xx", "Si5xx",
                 "Isolators and gate drivers", "Parity and CRC"):  # fmt: skip
        assert part in src, part


@pytest.mark.skipif(not shutil.which("node"), reason="needs node to run the visual's maths")
def test_hex_converter_maths():
    script = f"""
      global.window = {{}}; require({json.dumps(str(HEX_JS))}); const H = window.VZ_HEX;
      console.log(JSON.stringify({{
        ff_hex: H.parse("0xFF", 16, 8).value, ff_bin: H.bin(255, 8), ff_from_bin: H.parse("1111 1111", 2, 8).value,
        ff_dec: H.parse("255", "u", 8).value, ff_hexs: H.hex(255, 8), ff_signed: H.signed(0xFF, 8),
        m1_16: H.hex(H.parse("-1", "s", 16).value, 16), m1_32: H.hex(H.parse("-1", "s", 32).value, 32),
        min16: H.parse("-32768", "s", 16).value, too_big: !!H.parse("256", "u", 8).error,
        too_small: !!H.parse("-129", "s", 8).error, bad_hex: !!H.parse("0x1G", 16, 8).error,
        swap16: H.hex(H.swap(0x1234, 16), 16), swap32: H.hex(H.swap(0x12345678, 32), 32),
        bytes32: H.bytes(0x12345678, 32), oct: H.oct(8, 8),
        field: H.fieldValue(0xB5, 7, 4), fields: H.fields("[7:4] MODE, [3] EN, [9:8] OUT", 8),
        bcd: H.bcd(59), from_bcd: H.fromBcd(0x59, 8), not_bcd: H.fromBcd(0x5A, 8),
        gray5: H.gray(5), back: H.fromGray(H.gray(181)), a: H.ascii(0x41), lf: H.ascii(10), ones: H.ones(0xB5)
      }}));"""
    r = json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)
    assert (
        r["ff_hex"] == r["ff_from_bin"] == r["ff_dec"] == 255 and r["ff_bin"] == "11111111" and r["ff_hexs"] == "0xFF"
    )
    assert r["ff_signed"] == -1
    assert r["m1_16"] == "0xFFFF" and r["m1_32"] == "0xFFFFFFFF" and r["min16"] == 0x8000
    assert r["too_big"] and r["too_small"] and r["bad_hex"]
    assert r["swap16"] == "0x3412" and r["swap32"] == "0x78563412" and r["bytes32"] == [0x12, 0x34, 0x56, 0x78]
    assert r["oct"] == "0o10"
    assert r["field"] == 0xB and r["fields"] == [{"hi": 7, "lo": 4, "name": "MODE"}, {"hi": 3, "lo": 3, "name": "EN"}]
    assert r["bcd"] == "0101 1001" and r["from_bcd"] == 59 and r["not_bcd"] is None
    assert r["gray5"] == 7 and r["back"] == 181 and r["a"] == "A" and r["lf"].startswith("LF") and r["ones"] == 5
