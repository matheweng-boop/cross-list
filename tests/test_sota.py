"""Products > State of the art (owner, 8 Nov 2026): the best value each maker offers per key figure, per category and
sub-type, and "vs best" under every cross (app/services/sota.py)."""

import io

import pytest
from openpyxl import load_workbook

from app.matching.rules import load_all_rules
from app.services import crosslist as cl
from app.services import sota
from app.web import nav
from tests.conftest import ids

FILES = ("ti_digital_isolators", "skyworks_si86", "ti_gate_drivers", "skyworks_si823x", "ti_isolated_amplifiers",
         "skyworks_isolated_amplifiers", "skyworks_switches", "psemi_switches", "skyworks_timing", "ti_timing")  # fmt: skip
PRELOAD = {"sota_data": (FILES, None)}


@pytest.fixture
def sota_data(session):
    """Real isolators, gate drivers, isolated amplifiers, RF switches and timing parts (Skyworks and competitors)."""


DS = "x-datasheet.pdf p.3"


def part(i, mpn, maker, ours=False, family="digital_isolator", src=DS, **values):
    return {"id": i, "mpn": mpn, "maker": maker, "ours": ours, "family": family, "values": values,
            "sources": dict.fromkeys(values, src)}  # fmt: skip


ISO = dict(channel_config="4/0", integrated_power="none")
FIXTURE = [
    part(1, "SKY-A", "Skyworks", True, isolation_rating_kvrms=5.0, data_rate_mbps=150, cmti_kv_us=100,
         prop_delay_ns=10, temp_range_c=[-40, 125], creepage_mm=8.0, qualification="automotive", **ISO),
    part(2, "SKY-B", "Skyworks", True, src="Skyworks product table", isolation_rating_kvrms=5.0, data_rate_mbps=100,
         cmti_kv_us=150, prop_delay_ns=8, **ISO),
    part(3, "TI-C", "TI", isolation_rating_kvrms=5.7, data_rate_mbps=200, cmti_kv_us=100, prop_delay_ns=12,
         temp_range_c=[-40, 150], **ISO),
    part(4, "ADI-E", "Analog Devices", data_rate_mbps=150, prop_delay_ns=6, **ISO),
    part(5, "ADI-USB", "Analog Devices", data_rate_mbps=480, prop_delay_ns=1, channel_config="USB 2.0 (D+/D-)",
         integrated_power="none"),
    part(6, "SKY-I2C", "Skyworks", True, data_rate_mbps=1.7, channel_config="0/0 + 2 bidir", integrated_power="none"),
    part(7, "SKY-PWR", "Skyworks", True, data_rate_mbps=100, channel_config="2/2",
         integrated_power="isolated dc-dc"),
]  # fmt: skip


@pytest.fixture
def iso():
    return sota.build(FIXTURE)["digital_isolator"]


def test_best_per_maker_and_figure_respects_the_direction(iso):
    g = iso["general"]
    assert [m.name for m in g.makers] == ["Skyworks", "Analog Devices", "TI"]  # ours first, then by part count, name
    sky = g.makers[0]
    assert sky.n == 2 and sky.ours and sky.automotive == 1
    # higher is better: data rate, isolation (a tie: the datasheet value is shown, "and 1 other")
    assert sky.cells["data_rate_mbps"].value == 150 and sky.cells["data_rate_mbps"].mpn == "SKY-A"
    assert sky.cells["isolation_rating_kvrms"].mpn == "SKY-A" and sky.cells["isolation_rating_kvrms"].others == 1
    # lower is better: delay
    assert sky.cells["prop_delay_ns"].value == 8 and g.best["prop_delay_ns"] == 6
    assert g.market["prop_delay_ns"].maker == "Analog Devices"
    # a range: the top of the temperature range
    assert g.best["temp_range_c"] == 150 and g.ours["temp_range_c"].value == 125
    # the best in each column is marked, for every maker that has it
    assert "data_rate_mbps" in g.makers[2].best and "prop_delay_ns" in g.makers[1].best
    assert "data_rate_mbps" not in sky.best
    # a product-table value is marked, a datasheet page is not
    assert sky.cells["cmti_kv_us"].table and not sky.cells["data_rate_mbps"].table
    assert sky.cells["data_rate_mbps"].where == "x-datasheet.pdf p.3"


def test_sub_types_keep_usb_and_i2c_out_of_general_purpose(iso):
    assert list(iso) == ["general", "i2c", "usb", "power"]
    assert iso["general"].best["data_rate_mbps"] == 200  # not the USB part's 480 Mbps
    assert iso["usb"].best["data_rate_mbps"] == 480 and [m.name for m in iso["usb"].makers] == ["Analog Devices"]
    assert iso["i2c"].makers[0].cells["data_rate_mbps"].mpn == "SKY-I2C"
    assert iso["power"].makers[0].cells["data_rate_mbps"].mpn == "SKY-PWR"
    assert iso["general"].label == "General purpose" and iso["i2c"].label == "I²C"


def test_sub_types_of_the_other_categories():
    st = sota.subtype
    assert st("gate_driver", {"channel_config": "single", "protection": ["UVLO"]}) == "single"
    assert st("gate_driver", {"channel_config": "single", "protection": ["desaturation", "UVLO"]}) == "single_desat"
    assert st("gate_driver", {"channel_config": "dual", "input_type": "dual input"}) == "dual"
    assert st("gate_driver", {"channel_config": "dual", "input_type": "PWM input"}) == "half_bridge"
    assert st("isolated_amplifier", {"output_type": "analog, differential", "sense_type": "current (shunt)"}) == \
        "amp_current"  # fmt: skip
    assert st("isolated_amplifier", {"output_type": "digital bitstream (CMOS)", "sense_type": "voltage"}) == \
        "mod_voltage"  # fmt: skip
    assert [st("rf_switch", {"configuration": c}) for c in ("SPST", "2xSPST", "SPDT", "SP4T", "SP10T", "DPDT",
                                                             "SPDT+SPDT")] == \
        ["spst", "spst", "spdt", "sp3t_4t", "sp5t_up", "multi_pole", "multi_pole"]  # fmt: skip
    assert st("timing", {"function_type": "jitter_attenuator"}) == "jitter_attenuator"
    assert st("rf_switch", {}) is None


def test_the_gap_line(iso):
    cat = sota.category("digital_isolator")
    line = sota.gap_line(cat, iso["general"])
    assert line.startswith("Our gaps at a glance: ")
    assert "data rate (150 vs 200 Mbps, TI)" in line and "delay (8 vs 6 ns, Analog Devices)" in line
    assert "isolation (5.0 vs 5.7 kVrms, TI)" in line and "max temp (125 vs 150 °C, TI)" in line
    assert "CMTI" not in line  # ours (150) beats every other maker
    assert sota.gap_line(cat, iso["usb"]) == "Our gaps at a glance: we have no USB part in our data."
    assert "none" in sota.gap_line(cat, iso["i2c"])


def test_vs_best_tags_and_reading(iso):
    cat = sota.category("digital_isolator")
    theirs = {"isolation_rating_kvrms": 2.5, "data_rate_mbps": 10, "cmti_kv_us": 35, "prop_delay_ns": 30}
    offered = next(p["values"] for p in FIXTURE if p["mpn"] == "SKY-A")
    vb = sota.compare(cat, iso["general"], theirs, offered, "SKY-A")
    rows = {r["fig"]["key"]: r for r in vb["rows"]}
    assert rows["isolation_rating_kvrms"]["tags"] == ["top", "leads"]  # our best, and TI's 5.7 leads
    assert rows["cmti_kv_us"]["tags"] == ["better"]  # SKY-B has 150; no other maker beats it
    assert rows["prop_delay_ns"]["tags"] == ["better", "leads"]
    assert rows["data_rate_mbps"]["tags"] == ["top", "leads"]
    assert rows["prop_delay_ns"]["vs_theirs"] == "better" and rows["isolation_rating_kvrms"]["vs_theirs"] == "better"
    assert [sota.TAGS[t] for t in ("top", "better", "leads")] == ["our top", "we have better", "market leads"]
    text = vb["reading"]
    assert text.startswith("The offered part matches or beats theirs on all 4 compared figures; it is our best on ")
    assert "We have a stronger part on CMTI (SKY-B, 150 kV/µs), delay (SKY-B, 8 ns)." in text
    assert "Other makers lead on isolation (TI 5.7 kVrms), data rate (TI 200 Mbps)" in text
    # theirs better on a figure: said so
    worse = sota.compare(cat, iso["general"], {**theirs, "data_rate_mbps": 200}, offered)
    assert "matches or beats theirs on 3 of 4 figures and falls short on data rate" in worse["reading"]


def test_every_numeric_priority_1_rule_is_a_key_figure():
    """The figures come from the cross engine's priority-1 rules; sota.yaml says which way is better, the same way."""
    rules = load_all_rules()
    for cat in sota.config():
        figs = {f["key"]: f for f in sota.figures(cat)}
        for p in rules[cat["family"]].by_priority(1):
            if p.kind == "number" and p.direction in ("higher", "lower"):
                assert p.key in figs and figs[p.key].get("p1"), (cat["family"], p.key)
                assert figs[p.key]["direction"] == p.direction, (cat["family"], p.key)
        for f in figs.values():
            assert f["direction"] in ("higher", "lower") and f["label"], f
        assert all(f.get("count") == "automotive" for f in cat["figures"] if "key" not in f)


def test_nav_lists_state_of_the_art_under_products():
    products = next(s for s in nav.NAV if s[0] == "products")
    assert [label for label, _, _ in products[2]] == [
        "Search & replacements", "Cross a list", "Part knowledge", "Compare", "State of the art", "Price estimate",
        "Solution price builder", "Clock planner"]  # fmt: skip
    assert nav.place("/state-of-the-art") == ("products", "/state-of-the-art")


def test_the_page_per_category(client, session, sota_data):
    r = client.get("/state-of-the-art")
    assert r.status_code == 200 and "<h1>State of the art</h1>" in r.text
    for label in ("Digital isolators", "Isolated gate drivers", "Isolated amplifiers / modulators", "RF switches",
                  "Timing"):  # fmt: skip
        assert f">{label}</a>" in r.text
    assert "Our gaps at a glance: " in r.text and sota.SCOPE_NOTE.replace("'", "&#39;") in r.text
    for cat in ("digital_isolator", "gate_driver", "isolated_amplifier", "rf_switch", "timing"):
        page = client.get(f"/state-of-the-art?cat={cat}")
        assert page.status_code == 200 and 'class="sota-table"' in page.text, cat
        assert "sota-ours" in page.text and 'data-best="1"' in page.text and "Our gaps at a glance" in page.text, cat
        for key, g in sota.table(session).get(cat, {}).items():
            sub = client.get(f"/state-of-the-art?cat={cat}&sub={key}")
            assert sub.status_code == 200 and f'aria-current="true">{g.label} ' in sub.text.replace("&amp;", "&")
    # a typed address with an unknown category or sub-type falls back to the first
    assert client.get("/state-of-the-art?cat=nope&sub=nope").status_code == 200


def test_the_table_is_built_once_per_data_load(session, sota_data, monkeypatch):
    first = sota.table(session)
    monkeypatch.setattr(sota, "build", lambda parts: pytest.fail("built again"))
    assert sota.table(session) is first


def test_part_page_shows_vs_best_under_a_cross(client, sota_data):
    html = client.get(f"/parts/{ids(client, 'ISO7741DWR')}").text
    assert '<details class="sota-vs">' in html and "Best in our data" in html and "Reading: " in html
    assert "our top" in html or "we have better" in html


def test_cross_a_list_folds_vs_best_and_the_excel_has_the_best_columns(client, sota_data):
    html = client.post("/cross-list", data={"parts": "ISO7741DWR\nSI8641BD-IS"}).text
    assert html.count('<details class="sota-vs">') >= 1 and "Reading: " in html
    r = client.post("/cross-list.xlsx", data={"parts": "ISO7741DWR"})
    ws = load_workbook(io.BytesIO(r.content))["Cross list"]
    head = [c.value for c in ws[1]]
    assert head == cl.EXPORT_HEADER and head[-4:] == ["Our best (key figures)", "Best in our data", "Verified",
                                                      "Your comment"]  # fmt: skip
    row = [c.value for c in ws[2]]
    assert "Isolation" in row[-4] and "Data rate" in row[-3] and "(" in row[-3]
