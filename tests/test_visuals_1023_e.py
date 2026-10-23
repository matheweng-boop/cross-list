"""Owner feedback 23 Oct 2026 (worker E): UWB, DAB and three-step turn-on visuals in their own files, the UWB signal
path note, library rule d12, and "why it matters to the customer" on more guides and RF / timing notes."""

import re

from app.config import PROJECT_ROOT
from app.services import engineering, knowledge, library, rf_notes

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
