"""Engineering knowledge > Interactive visuals: the page renders and its reference lines come from the cross lists."""

import json
import re
import shutil
import subprocess

import pytest

from app.config import PROJECT_ROOT
from app.services import engineering, knowledge, library, rf_bands, rf_notes, visuals
from tests.conftest import PAGE_TIMEOUT


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


# ---- from tests/test_rf_visuals_1023.py ------------------------------------------------------------------------------
# Owner feedback 23 Oct 2026 on the RF visuals: RF bands by type and application, the dBm ladder's plain
# explanations, real Skyworks parts in the noise-figure cascade, and the FM intermodulation visual.

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


# ---- from tests/test_visuals_1023_e.py -------------------------------------------------------------------------------
# Owner feedback 23 Oct 2026 (worker E): UWB, DAB and three-step turn-on visuals in their own files, the UWB signal
# path note, library rule d12, and "why it matters to the customer" on more guides and RF / timing notes.

STATIC = PROJECT_ROOT / "app" / "web" / "static"
NEW = ("uwb", "dab", "turnon")


def test_new_visuals_are_own_files_and_load_before_the_engine(client):
    page = client.get("/visuals").text
    engine = page.index('src="/static/visuals.js"')
    for v in NEW:
        js = (STATIC / "vz" / f"{v}.js").read_text()
        assert "window.VZ_ADD" in js and f'id: "{v}", group:' in js
        assert -1 < page.index(f'src="/static/vz/{v}.js"') < engine
        assert client.get(f"/static/vz/{v}.js").status_code == 200
        assert library.VISUALS[v][1] == f"/visuals#{v}"
        block = js.split(f'id: "{v}", group:')[1]
        fams = {p["key"] for p in knowledge.data()["products"]}
        assert set(re.findall(r"/knowledge#p-([a-z_]+)", block)) <= fams
        ids = {t["id"] for t in rf_notes.topics()}
        assert set(re.findall(r'"(phys_[a-z_]+)"\]', block)) <= ids
    assert "window.VZ_ADD" in (STATIC / "visuals.js").read_text()


def test_visual_content_owner_asked_for():
    uwb = (STATIC / "vz" / "uwb.js").read_text()
    for s in ("-41.3", "499.2", "c · ToF", "DS-TWR", "relay", "distance bounding", "first path", "/library/auto_uwb",
              "QPF5100Q", "/engineering/uwb_signal_path"):
        assert s in uwb, s
    dab = (STATIC / "vz" / "dab.js").read_text()
    for s in ("1.536 MHz", "I/Q in plain words", "DQPSK", "864", "ensemble", "DLS", "slideshow", "Si468", "Si469"):
        assert s in dab, s
    on = (STATIC / "vz" / "turnon.js").read_text()
    for s in ("Step 1", "Step 2", "Step 3", "Overshoot", "CISPR 25", "Si829", "/engineering/emc_eft_cispr", "est"):
        assert s in on, s


def test_uwb_signal_path_note(client):
    assert "uwb_signal_path" in engineering.NOTES
    page = client.get("/engineering/uwb_signal_path").text
    for s in ("Why it matters to the customer", "group delay", "paired-echo", "LNA", "PA", "Filter", "compression",
              'href="/visuals#uwb"', 'href="/library/auto_uwb"', "kn-est"):
        assert s in page, s
    assert "/engineering/uwb_signal_path" in client.get("/engineering").text


def test_library_rule_d12_carries_the_owner_point(client):
    d12 = next(d for d in library.topic("auto_uwb")["design_rules"] if d["id"] == "d12")
    assert "Preserve the TX and RX pulse" in d12["rule"] and "compression" in d12["rule"] and d12["kind"] == "rule"
    assert client.get("/library/auto_uwb").status_code == 200


def test_every_spec_guide_and_the_rf_and_timing_notes_have_customer_points(client):
    why = knowledge.data()["why_it_matters"]
    assert set(engineering.NOTES) <= set(why)
    notes = {t["id"]: t for t in rf_notes.topics()}
    for n in ("rf_switches", "filter_fundamentals", "cascaded_noise_figure", "phase_noise_oscillators", "pll_synthesis",
              "phase_noise_and_pll", "vco_design_tradeoffs", "lpwan_uwb_iot_links"):
        assert notes[n].get("why") and all(w["kind"] in knowledge.KINDS for w in notes[n]["why"]), n
    assert not knowledge.problems()
    cards = {p["key"]: p for p in knowledge.by_product()}
    for k in ("rf_switches", "front_ends", "filters", "timing", "uwb"):
        assert cards[k]["points"], k
    page = client.get("/rf-notes").text
    assert page.count("Why it matters to the customer") >= 30
    assert "/rf-notes#phase_noise_oscillators" in client.get("/knowledge").text
    assert "Why it matters to the customer" in client.get("/engineering/deadtime").text


# ---- from tests/test_visuals_1024.py ---------------------------------------------------------------------------------
# Owner feedback 24 Oct 2026 on Engineering knowledge > Interactive visuals: show applications as frequency ranges
# from the RF bands data ("FM is not only at 100 MHz"), and a new "Hex, binary and registers" visual.
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


# ---- from tests/test_radio_visuals_1025.py ---------------------------------------------------------------------------
# Owner feedback 25 Oct 2026 on Engineering knowledge > Interactive visuals: DAB blocks and ensembles drawn better
# (Band III raster, 96 ms frame, sub-channels you can click), a step-by-step signal flow for DAB, FM and AM, and an
# RDS section (57 kHz in the MPX, groups and blocks, decode example, RBDS).
VZ = STATIC / "vz"
RADIO_NEW = ("flow", "rds")
node = pytest.mark.skipif(not shutil.which("node"), reason="needs node to run the visuals' JavaScript")

# Loads the shared sketch helpers and the three radio visuals with a stand-in for the engine; prints JSON.
HARNESS = """
global.window = {};
for (const f of ["sketch", "dab", "flow", "rds"]) require(%s + "/" + f + ".js");
const V = [], C = {blue: "#1", orange: "#2", green: "#3", purple: "#4", teal: "#5", red: "#6", grey: "#7"};
const num = x => String(+(+x).toPrecision(4)), esc = s => String(s);
const log10 = Math.log10, bandStrip = () => "";
for (const add of window.VZ_ADD) add({V, C, num, esc, log10, bandStrip});
const vis = id => V.find(v => v.id === id);
const run = (id, over) => {
  const v = vis(id);
  return v.compute({...Object.fromEntries(v.controls.map(c => [c.k, c.value])), ...over}, 0);
};
%s
"""


def _node(body: str):
    script = HARNESS % (json.dumps(str(VZ)), body)
    return json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)


def test_new_visuals_are_registered_included_and_load_before_the_engine(client):
    page = client.get("/visuals").text
    engine = page.index('src="/static/visuals.js"')
    for v in RADIO_NEW:
        js = (VZ / f"{v}.js").read_text()
        assert "window.VZ_ADD" in js and f'id: "{v}", group: "Broadcast radio"' in js
        assert -1 < page.index(f'src="/static/vz/{v}.js"') < engine
        assert library.VISUALS[v][1] == f"/visuals#{v}"
        assert client.get(f"/static/vz/{v}.js").status_code == 200
    assert page.index("/static/vz/sketch.js") < page.index("/static/vz/dab.js") < page.index("/static/vz/flow.js")
    assert client.get("/static/vz/radio.css").status_code == 200 and "/static/vz/radio.css" in page
    tuners = next(p for p in knowledge.data()["products"] if p["key"] == "tuners")
    assert {"dab", "flow", "rds"} <= set(tuners["visuals"])
    for f in ("sketch", "flow", "rds", "dab"):  # no other site, no library
        src = (VZ / f"{f}.js").read_text()
        assert "http://" not in src and "https://" not in src and "import " not in src


def test_owner_content_is_in_the_sources():
    dab = (VZ / "dab.js").read_text()
    for s in (
        '["5A", 174.928]',
        '["12C", 227.360]',
        '["13F", 239.200]',
        "Blocks and ensembles",
        "FIC",
        "MSC",
        "CIF",
        "data-dab-blk",
        "data-dab-svc",
        "Sub-channel",
        "Start address",
        "Protection",
        "96 ms",
    ):
        assert s in dab, s
    flow = (VZ / "flow.js").read_text()
    for s in (
        "Illustrative",
        "What changed",
        "Next ›",
        "‹ Prev",
        "data-fl-step",
        "19 kHz",
        "MPX",
        "De-emphasis",
        "Envelope",
        "Viterbi",
        "FFT",
        "On our chips",
        "/broadcast",
        "Si469",
        "Si4706",
        "Si4734",
    ):
        assert s in flow, s
    rds = (VZ / "rds.js").read_text()
    for s in ("57 kHz", "1187.5", "PI", "PS", "RadioText", "TP", "TA", "AF", "CT", "RBDS", "IEC 62106", "made up"):
        assert s in rds, s


@node
def test_every_step_renders_for_dab_fm_and_am():
    r = _node("""
      const out = {};
      for (const sys of ["dab", "fm", "am"]) out[sys] = window.VZ_FLOW.CHAINS[sys].map((_, i) => {
        const x = run("flow", {sys, step: i + 1});
        return {title: x.html.match(/Step \\d+ of \\d+: ([^<]+)/)[1], svgs: (x.html.match(/<svg/g) || []).length,
                bad: /NaN|undefined|Infinity/.test(x.html), what: x.html.includes("What changed:")};
      });
      console.log(JSON.stringify(out));""")
    for sys, steps in r.items():
        assert len(steps) == 9, sys
        assert all(s["svgs"] >= 2 and s["what"] and not s["bad"] for s in steps), sys
    titles = {sys: " ".join(s["title"] for s in steps) for sys, steps in r.items()}
    assert (
        "antenna" in titles["dab"]
        and "FFT" in titles["dab"]
        and "Viterbi" in titles["dab"]
        and "Audio out" in titles["dab"]
    )
    assert "MPX" in titles["fm"] and "Stereo" in titles["fm"] and "De-emphasis" in titles["fm"]
    assert "Envelope" in titles["am"] and "Mixer" in titles["am"]


@node
def test_dab_ensemble_highlights_the_block_and_the_service():
    r = _node("""
      const a = run("dab", {}), b = run("dab", {blk: "178.352", svc: "3", eep: "1A"});
      console.log(JSON.stringify({a: a.html, b: b.html, bo: b.outputs}));""")
    a, b = r["a"], r["b"]
    assert (
        'data-dab-blk="227.36" tabindex="0" role="button" aria-label="Block 12C, 227.36 MHz" aria-pressed="true"' in a
    )
    assert a.count("data-dab-blk=") == 38 and "12C · 227.36 MHz · 1.536 MHz wide" in a
    assert 'data-dab-svc="0"' in a and "CU 0–71" in a  # City Pop, 96 kbit/s at EEP-3A = 72 CU from CU 0
    assert "Block 5C" in b and 'aria-label="Block 5C, 178.352 MHz" aria-pressed="true"' in b
    assert "Sport Live" in b and "EEP-1A, code rate 1/4" in b and "does not fit" in b  # 1A needs 1032 CU > 864


@node
def test_rds_groups_decode_with_real_check_words():
    r = _node("""
      const R = window.VZ_RDS;
      const st = {pi: 0xD3C2, ps: "BIZ FM  ", af: [89.1, 94.6, 101.3], rt: "Hello", utc: [2026, 10, 25, 17, 42],
                  offsetHalfHours: 2, ms: 1, stereo: 1, ab: 0, tp: 1, ta: 1, pty: 10};
      const g0 = R.group("0A", 3, st), g2 = R.group("2A", 0, st), g4 = R.group("4A", 0, st);
      const x = run("rds", {}), y = run("rds", {reg: "rbds", grp: "2A", seg: 1});
      console.log(JSON.stringify({c8000: R.check(0x8000), c1: R.check(1),
        pi: R.rbdsPi("WXYZ"), k: R.rbdsPi("KAAA"),
        g0: g0.map(b => b.info), ok: [g0, g2, g4].every(g => g.every(b => R.syndromeOk(b.info, b.cw, b.off))),
        g2: g2.map(b => b.info), mjd: R.mjd(2026, 10, 25), back: R.fromMjd(R.mjd(2026, 10, 25)),
        g4: g4.map(b => b.info),
        af: [R.afCode(89.1), R.afMhz(16)], x: x.html, y: y.html, yo: y.outputs}));""")
    assert r["c8000"] == 0x077 and r["c1"] == 0x1B9  # first and last rows of the RDS parity matrix
    assert r["ok"]
    assert r["g0"] == [0xD3C2, 0x055F, 0x478A, 0x2020]  # TP, PTY 10, TA, music, stereo, segment 3; AF 94.6 / 101.3
    assert r["g2"] == [0xD3C2, 0x2540, 0x4865, 0x6C6C]  # "Hell"
    assert r["back"] == [2026, 10, 25] and r["g4"][2] >> 1 == r["mjd"] & 0x7FFF
    assert r["pi"] == 21672 + 676 * 23 + 26 * 24 + 25 and r["k"] == 4096 and r["af"] == [16, 89.1]
    assert (
        "57 kHz" in r["x"] and "Where RDS sits" in r["x"] and "BIZ FM" in r["x"] and "RBDS in North America" in r["x"]
    )
    assert "Country" in r["y"] and "RadioText characters 5–8" in r["y"]


# --- browser, 390 px phone ------------------------------------------------------------------------------------------
@pytest.mark.browser
def test_radio_visuals_click_through_on_a_phone(chromium, live_server):
    expect = pytest.importorskip("playwright.sync_api").expect
    from tests.test_browser import Watch, overflow

    watch = Watch(live_server)
    ctx = chromium.new_context(
        base_url=live_server, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
    )
    page = watch.attach(ctx.new_page())
    page.set_default_timeout(PAGE_TIMEOUT)
    try:
        page.goto("/visuals#dab", wait_until="load")
        panel = page.locator("#vz-panel")
        expect(panel.locator(".dab-ens h3")).to_have_text("Blocks and ensembles")
        panel.locator('[data-dab-blk="178.352"]').click()
        expect(panel.locator('select[data-k="blk"]')).to_have_value("178.352")
        expect(panel.locator(".dab-ens")).to_contain_text("Block 5C")
        panel.locator('tr[data-dab-svc="1"]').click()
        expect(panel.locator('select[data-k="svc"]')).to_have_value("1")
        expect(panel.locator(".dab-detail")).to_contain_text("News 24")
        assert overflow(page) <= 1

        page.goto("/visuals#flow", wait_until="load")
        expect(panel.locator(".fl-now h3")).to_contain_text("Step 1 of 9")
        panel.locator(".fl-nav", has_text="Next").click()
        expect(panel.locator(".fl-now h3")).to_contain_text("Step 2 of 9")
        panel.locator('.fl-blk[data-fl-step="6"]').click()
        expect(panel.locator(".fl-now h3")).to_contain_text("OFDM")
        panel.locator('select[data-k="sys"]').select_option("fm")
        expect(panel.locator(".fl-now h3")).to_contain_text("MPX")
        panel.locator(".fl-nav", has_text="Prev").click()
        expect(panel.locator(".fl-now h3")).to_contain_text("Step 5 of 9")
        panel.locator('select[data-k="sys"]').select_option("am")
        panel.locator('.fl-blk[data-fl-step="6"]').click()
        expect(panel.locator(".fl-now h3")).to_contain_text("Envelope")
        assert overflow(page) <= 1

        page.goto("/visuals#rds", wait_until="load")
        expect(panel.locator(".rd")).to_contain_text("57 kHz")
        expect(panel.locator(".rd-blk")).to_have_count(4)
        expect(panel.locator(".rd-ps")).to_have_text("BI______")
        panel.locator('select[data-k="grp"]').select_option("2A")
        expect(panel.locator(".rd-blk").first).to_contain_text("Block 1")
        panel.locator('select[data-k="reg"]').select_option("rbds")
        expect(panel.locator(".vz-kpis")).to_contain_text("Country")
        assert overflow(page) <= 1
    finally:
        ctx.close()
    assert not watch.errors, watch.errors
