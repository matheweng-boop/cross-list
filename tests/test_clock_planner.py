"""Clock planner (owner, 2 Nov 2026, item 18): divider maths, VCO choice, part matching, the page, save and share."""

from fractions import Fraction as F

import pytest
from sqlalchemy import select

from app.models import ClockPlan
from app.services import clock_planner as cp


def req(outputs, in1="25", kind="crystal", **kw):
    form = {"in1": in1, "in1_kind": kind, "f": [str(o[0]) for o in outputs], "n": [str(o[1]) for o in outputs],
            "fmt": [o[2] for o in outputs], "v": [str(o[3]) if len(o) > 3 else "" for o in outputs]}  # fmt: skip
    form.update({k: str(v) for k, v in kw.items()})
    return cp.build_request(form)


# ---------------------------------------------------------------- maths


def test_lcm_of_fractions():
    assert cp.lcm([F(625, 4), F(125)]) == 625  # 156.25 and 125 MHz
    assert cp.lcm([F(100), F(100, 3)]) == 100
    assert cp.lcm([F(25), F(100), F(156.25)]) == 2500
    assert cp.first_multiple(F(625), F(13200), F(14256)) == 13750
    assert cp.first_multiple(F(5000), F(13200), F(14256)) is None


def test_parse_frequencies_as_typed():
    assert cp.parse_mhz("156.25") == F(625, 4)
    assert cp.parse_mhz("100/3") == F(100, 3)
    assert cp.parse_mhz("33,333 MHz") == F(33333, 1000)
    assert cp.parse_mhz("") is None and cp.parse_mhz("abc") is None and cp.parse_mhz("-5") is None
    assert cp.parse_mhz("1/0") is None


def test_all_integer_from_one_vco():
    """Ethernet 156.25 + 125 MHz on Si5341: VCO 13.75 GHz, both dividers integer (88 and 110 in total)."""
    r = req([("156.25", 4, "LVDS"), ("125", 2, "LVDS")], in1="48")
    pl = cp.plan(r, cp.architecture("Si5341A"))
    assert pl["vco"] == 13750 and pl["all_integer"] and not pl["problems"]
    totals = {row["f"]: row["total"] for row in pl["rows"]}
    assert totals == {F(625, 4): 88, F(125): 110}
    assert all(row["r"] % 2 == 0 for row in pl["rows"])  # MultiSynth parts: output divider R even
    assert not pl["feedback_integer"]  # 13750 / 48 is not an integer: fractional feedback


def test_fractional_outputs_named_and_the_most_integer_vco():
    """156.25 + 100 + 33.33 MHz: no VCO in 13.2-14.256 GHz divides by all three; the plan keeps the most integer."""
    r = req([("156.25", 2, "LVDS"), ("100", 2, "HCSL"), ("100/3", 1, "LVCMOS")])
    pl = cp.plan(r, cp.architecture("Si5341A"))
    assert not pl["all_integer"] and pl["fractional"] == [F(625, 4)]
    assert pl["vco"] == 13200 and pl["feedback_integer"]  # 13200 = 132 x 25 MHz: integer feedback too
    frac = next(row for row in pl["rows"] if not row["integer"])
    assert frac["n"] == F(13200) / F(625, 2) and "6/25" in frac["n_text"]
    # the same outputs on Si5332 (VCO 2.375-2.625 GHz, est): 2500 MHz makes all three integer
    pl2 = cp.plan(r, cp.architecture("Si5332A-GM1"))
    assert pl2["vco"] == 2500 and pl2["all_integer"]
    assert {row["f"]: row["total"] for row in pl2["rows"]} == {F(625, 4): 16, F(100): 25, F(100, 3): 75}


def test_vco_prefers_integer_feedback_between_equals():
    choice = cp.choose_vco([F(200)], (13200, 14256), F(25))
    assert choice["vco"] == 13200 and choice["feedback_integer"]
    # 156.25 MHz alone: 13281.25 MHz is the lowest multiple, 13750 MHz is also 550 x 25 MHz (integer feedback)
    choice = cp.choose_vco([F(625, 4)], (13200, 14256), F(25))
    assert choice["vco"] == 13750 and choice["feedback_integer"]
    assert cp.choose_vco([F(625, 4)], (13200, 14256))["vco"] == F(53125, 4)
    choice = cp.choose_vco([F(200)], (13200, 14256), F(27))  # lcm(200, 27) = 5400: no multiple in range
    assert choice["vco"] == 13200 and not choice["feedback_integer"]
    nothing = cp.choose_vco([F(20000)], (13200, 14256))  # above the VCO: no integer divider at all
    assert nothing["integer"] == set() and 13200 <= nothing["vco"] <= 14256


def test_grouping_by_output_divider():
    # Si5332: R may be 1 or even; 100 and 25 share one divider (R = 1 and 4), 100/3 needs its own (R = 3 is odd)
    groups = cp.group_outputs([F(100), F(25), F(100, 3)], "si5332")
    assert [g["members"] for g in groups] == [[F(100), F(25)], [F(100, 3)]]
    # MultiSynth parts: base 2 x 100 = 200, so 100 (R 2), 33.33 (R 6) and 25 (R 8) share it
    groups = cp.group_outputs([F(100), F(25), F(100, 3)], "multisynth")
    assert len(groups) == 1 and groups[0]["base"] == 200


def test_too_few_dividers():
    six = [(str(f), 1, "LVDS") for f in (100, 125, 156.25, 161.1328125, 212.5, 322.265625)]
    pl = cp.plan(req(six), cp.architecture("Si5342"))
    assert any("N dividers; the part has 2" in p for p in pl["problems"])


def test_output_outside_every_parts_range():
    """A 5 GHz output: no part of ours fits, and the plan names it as outside the part's range."""
    r = req([("5000", 1, "LVDS")])
    m = cp.match(r)
    assert m["ours"] and not any(x["fits"] for x in m["ours"])
    assert all(any(label == "Frequency" and ok is False for label, ok, _ in x["checks"]) for x in m["ours"])
    pick = cp.chosen(r, m)
    pl = cp.plan(r, pick["arch"], pick["part"])
    assert any("outside this part's output range" in p for p in pl["problems"]) and not pl["rows"]
    assert cp.fmt_low(0.0001) == "100 Hz" and cp.fmt_low(0.024) == "24 kHz" and cp.fmt_low(5) == "5"


def test_multi_pll_and_buffer_and_oscillator():
    r = req([("156.25", 2, "LVDS"), ("100", 2, "LVDS"), ("122.88", 2, "LVDS")], kind="clock", in1="25")
    pl = cp.plan(r, cp.architecture("Si5397"))
    assert len(pl["plls"]) >= 2 and not pl["problems"] and all(row["integer"] for row in pl["rows"])
    for p in pl["plls"]:
        assert all((p["vco"] / f).denominator == 1 for f in p["members"])
    buf = cp.plan(req([("100", 8, "HCSL")], in1="100", kind="clock"), cp.architecture("Si53208-A01"))
    assert not buf["problems"]
    buf = cp.plan(req([("125", 8, "HCSL")], in1="100", kind="clock"), cp.architecture("Si53208-A01"))
    assert buf["problems"]
    xo = cp.plan(req([("156.25", 1, "LVDS"), ("100", 1, "LVDS")]), cp.architecture("Si545"))
    assert any("one output" in p for p in xo["problems"])


# ---------------------------------------------------------------- part matching


def _fit(r, mpn):
    return next(x for x in cp.match(r)["ours"] if x["part"]["mpn"] == mpn)


def test_matching_reasons():
    r = req([("100", 8, "HCSL", 1.8)], pcie="gen5", jit="300")
    assert _fit(r, "Si5332A-GM2")["fits"]
    six = _fit(r, "Si5332A-GM1")  # 6 outputs for 8
    assert not six["fits"] and ("Outputs", False, "only 6 outputs; you need 8") in six["checks"]
    si5341 = _fit(r, "Si5341A")  # no PCIe compliance stated
    assert ("PCIe", False, "compliant to no generation stated") in si5341["checks"]
    buf = _fit(r, "Si53208-A01")  # a buffer from a crystal
    assert any(label == "Input" and ok is False for label, ok, _ in buf["checks"])


def test_matching_automotive_jitter_formats_and_supply():
    r = req([("100", 2, "HCSL", 1.8), ("25", 3, "LVCMOS", 3.3)], jit="1000", auto="1")
    m = cp.match(r)
    fits = [x["part"]["mpn"] for x in m["ours"] if x["fits"]]
    assert fits and all(mpn.startswith("Si5332A-AM") for mpn in fits)
    assert any(c[0] == "Automotive" and c[1] is False for c in _fit(r, "Si5341A")["checks"])
    tight = _fit(req([("156.25", 1, "LVDS")], jit="100"), "Si5332A-GM1")
    assert ("Jitter", False, "190 fs typ, above your 100 fs") in tight["checks"]
    cml = _fit(req([("156.25", 1, "CML")]), "Si5332A-GM1")
    assert ("Formats", False, "no CML") in cml["checks"]
    cmos = _fit(req([("200", 1, "LVCMOS")]), "Si5332A-GM1")  # Si5332 LVCMOS to 170 MHz
    assert any(c[0] == "Frequency" and c[1] is False and "LVCMOS only to 170" in c[2] for c in cmos["checks"])
    low = _fit(req([("100", 1, "LVDS", 1.5)]), "Si5341A")  # no 1.5 V output bank on Si5341
    assert ("Supply", False, "no 1.5 V output supply") in low["checks"]


def test_competitors_are_the_same_kind():
    m = cp.match(req([("156.25", 4, "LVDS"), ("125", 2, "LVDS")], in1="48", jit="200"))
    assert m["competitors"] and all(x["part"]["manufacturer"] != "Skyworks" for x in m["competitors"])
    kinds = {x["part"]["values"]["function_type"] for x in m["ours"] if x["fits"]}
    assert {x["part"]["values"]["function_type"] for x in m["competitors"]} <= kinds


def test_presets_all_give_a_plan():
    for p in cp.presets():
        out = cp.run(cp.build_request({"preset": [p["key"]]}))
        assert out["pick"] and out["pick"]["fits"], p["key"]
        assert not out["plan"]["problems"], (p["key"], out["plan"]["problems"])
        assert out["svg"].startswith("<svg") and "MHz" in out["svg"]
        assert out["jitter"]["rows"] and out["jitter"]["rows"][0]["typ"]


def test_jitter_typ_first_then_max():
    r = req([("156.25", 4, "LVDS"), ("125", 2, "LVDS")], in1="48", jit="120")
    pick = cp.chosen(r, cp.match(r))
    pl = cp.plan(r, pick["arch"], pick["part"])
    row = cp.jitter(r, pick["arch"], pl, pick["part"])["rows"][0]
    assert (row["typ"], row["max"], row["ok"], row["max_ok"]) == (90, 140, True, False)  # Si5341, integer, crystal


# ---------------------------------------------------------------- pages


@pytest.mark.smoke
def test_planner_page_blank_and_with_a_preset(client):
    r = client.get("/clocks")
    assert r.status_code == 200 and "<h1>Clock planner</h1>" in r.text and "ClockBuilder Pro" in r.text
    assert "https://www.skyworksinc.com/Application-Pages/Clockbuilder-Pro-Software" in r.text
    blank = client.get("/clocks?in1=&in1_kind=crystal&in2=&f=&n=&fmt=LVDS&v=&jit=&jit_unit=fs&pcie=none&type=")
    assert blank.status_code == 200 and "Which parts fit" not in blank.text
    page = client.get("/clocks?preset=pcie5x8").text
    assert "Which parts fit" in page and "Si5332A-GM2" in page and "Frequency plan for" in page
    assert "<svg" in page and "All outputs come from one VCO with integer dividers" in page


def test_planner_odd_values_give_a_page_with_a_note(client):
    r = client.get("/clocks?f=abc&f=100&n=x&fmt=NOPE&v=9&jit=-1&pcie=gen9&in1=zz&part=%3Cb%3E")
    assert r.status_code == 200 and "is not a frequency in MHz" in r.text and 'value="&lt;b&gt;"' in r.text


def test_menu_and_tabs(client):
    from app.web import nav

    products = next(s for s in nav.NAV if s[0] == "products")
    assert ("Clock planner", "/clocks") in [(i[0], i[1]) for i in products[2]]
    assert nav.state("/clocks/plans/3")["item"] == "/clocks"
    assert nav.state("/clocks/plans")["active_tab"] == "/clocks/plans"
    assert client.get("/clocks/plans").status_code == 200


def test_save_reopen_rename_delete(client, session):
    data = cp.to_form(cp.build_request({"preset": ["ethernet"]}))
    r = client.post("/api/clocks/plans", json={"name": "Switch card", "data": data})
    assert r.status_code == 200
    pid, url = r.json()["id"], r.json()["url"]
    assert url == f"/clocks/plans/{pid}"
    page = client.get(url).text
    assert "<h1>Switch card</h1>" in page and "Frequency plan for" in page and "156.25" in page
    assert "Save changes" in page
    assert "Switch card" in client.get("/clocks/plans").text
    assert client.put(f"/api/clocks/plans/{pid}", json={"name": "Renamed", "data": {}}).json()["name"] == "Renamed"
    assert client.get(f"/api/clocks/plans/{pid}").json()["data"]["f"] == ["156.25", "125"]
    assert client.post("/api/clocks/plans", json={"name": "x", "data": {"f": [""]}}).status_code == 400
    assert client.post(f"/clocks/plans/{pid}/delete", follow_redirects=False).status_code == 303
    assert session.scalar(select(ClockPlan.id)) is None
    assert client.get(url).status_code == 404
