"""RF coverage by band: frequency / power parsing, the GNSS and diversity remap, and the page."""

import re
from pathlib import Path

from app.services import blocks, rf_bands
from app.services import portfolio as pf
from app.services import rf_coverage as rc


def test_frequency_parsing_formats():
    assert rc.frequency_ranges({"Frequency (MHz)": "887-925"}) == [(0.887, 0.925)]
    two = rc.frequency_ranges({"Frequency (GHz) Min.": "2.4 / 4.9", "Frequency (GHz) Max.": "2.5 / 5.875"})
    assert two == [(2.4, 2.5), (4.9, 5.875)]
    assert rc.frequency_ranges({"Frequency Min": "5 GHz", "Frequency Max": "7 GHz"}) == [(5.0, 7.0)]
    assert rc.frequency_ranges({}, "0.4 to 2.7 GHz LTE Diversity Receive Module") == [(0.4, 2.7)]
    assert rc.frequency_ranges({"IF Frequency (MHz)": "900 to 1200"}) == []  # IF is not the RF band
    assert rc.frequency_ranges({"Gain (dB)": "16"}, "Low-noise amplifier") == []  # nothing stated: not guessed


def test_power_classes():
    assert round(rc.output_power_dbm({"Output Power (W)": "8"}), 1) == 39.0
    assert rc.output_power_dbm({"P1dB (dBm)": "28", "Psat (dBm)": "31"}) == 31
    assert [rc.power_class(x) for x in (24, 35, 46, None)] == ["low", "mid", "high", None]


def test_gnss_and_diversity_parts_are_filed_specifically():
    parts = blocks.catalog_parts()
    gnss = {p["mpn"] for p in parts["gnss_lna"]}
    assert {"SKY65702-11", "SKY65611-11", "SKY5A2110"} <= gnss
    assert "SKY65611-11" in {p["mpn"] for p in parts["lna"]}  # still an LNA too
    assert "SKY53735-11" in {p["mpn"] for p in parts["diversity_rx_module"]}


def test_application_bands_and_function_limits():
    assert rc.application_bands("Smart asset tracker (GNSS + cellular)")[0] == "L"
    assert "Ku" in rc.application_bands("Satellite ground terminal")
    need, _, _, _ = rc.demand()
    assert not need["beamformer_ic"]["sub1"]  # mmWave beamformers do not create sub-1 GHz demand


def test_matrix_and_gaps():
    rows = rc.rows()
    assert sum(r["fn"] == "power_amplifier" for r in rows) == 3
    for g in rc.gaps(rows):
        cell = next(r for r in rows if r["fn"] == g["fn"] and r["power_label"] == g["power_label"])["cells"][
            g["band"]["id"]
        ]
        assert cell["need"] and (
            not cell["n"] if g["kind"] != "thin" else cell["n"] <= 2 and cell["need"] >= rc.THIN_NEED
        )


def test_page(client):
    r = client.get("/business/rf-coverage?fn=lna&band=L")
    assert r.status_code == 200
    assert "RF coverage by band" in r.text and 'id="slot"' in r.text


def test_rf_notes_page_and_search(client):
    from app.services import notes_search, rf_notes

    assert len(rf_notes.topics()) >= 40
    assert len({t["id"] for t in rf_notes.topics()}) == len(rf_notes.topics())
    r = client.get("/rf-notes")
    assert r.status_code == 200 and 'id="cascaded_noise_figure"' in r.text
    assert any(h.source == "RF note" for h in notes_search.search("reflectionless filter"))


def test_rf_templates_completed_from_public_diagrams():
    t = blocks.templates()
    ew = next(x for x in t if x["name"].startswith("Electronic warfare receiver / jammer"))
    assert {"preselector", "jammer_tx"} <= {g["id"] for g in ew["groups"]}
    assert ["antenna", "preselector", "RX"] in ew["links"]
    names = [x["name"] for x in t]
    assert any("DOCSIS 4.0 line extender" in n for n in names) and any("vector network analyzer" in n for n in names)


def test_block_bands_are_valid_and_used():
    cfg = rc.config()
    bands, powers = {b["id"] for b in cfg["bands"]}, {c["id"] for c in cfg["power_classes"]}
    names = {t["name"]: t for t in [*blocks.templates(), *blocks.background_templates()]}
    stated = rc.block_bands()
    assert stated
    for name, groups in stated.items():
        t = names[name]
        ids = {g["id"] for g in t["groups"]}
        for gid, fns in groups.items():
            assert gid in ids
            for spec in fns.values():
                assert set(spec.get("bands") or []) <= bands and spec.get("power") in powers | {None}
    need, _, unknown, n = rc.demand()
    assert unknown < n / 4  # most RF applications have stated bands
    assert any(g["kind"] == "thin" and g["fn"] == "rf_synthesizer" for g in rc.gaps(rc.rows()))


def test_rf_bands_page_and_parts():
    from app.services import rf_bands

    gnss = rf_bands.parts_for("gnss_l1")
    fam = next(g for g in gnss if g["fn"] == "gnss_lna")
    assert fam["specific"] and all(p["specific"] for p in fam["specific"])
    assert not any(
        p["specific"] for g in gnss for p in g["specific"] if p["width"] > 1
    )  # wideband parts are not specific


def test_rf_bands_routes(client):
    assert client.get("/rf-bands").status_code == 200
    r = client.get("/rf-bands/n77")
    assert r.status_code == 200 and "3300" in r.text
    assert client.get("/rf-bands/nope").status_code == 404


def test_competitor_parts_mark_who_serves_a_slot(tmp_path, monkeypatch):
    # synthetic competitor file: counted per slot, never mixed with our parts
    (tmp_path / "acme.yaml").write_text(
        "parts:\n"
        "  - {mpn: AC-X1, manufacturer: Acme, function: filter_saw_baw, freq_min_ghz: 8.5, freq_max_ghz: 10.5}\n"
        "  - {mpn: AC-X2, manufacturer: Acme, function: filter_saw_baw, freq_min_ghz: 9, freq_max_ghz: 11,\n"
        "     status: Obsolete}\n"
    )
    monkeypatch.setattr(rc, "COMPETITOR_DIR", tmp_path)
    rc.competitor_parts.cache_clear()
    try:
        rows = rc.rows()
        cell = next(r for r in rows if r["fn"] == "filter_saw_baw")["cells"]["X"]
        assert cell["comp"] == 1 and cell["rivals"] == {"Acme": 1}  # obsolete part not counted
        g = next(g for g in rc.gaps(rows) if g["fn"] == "filter_saw_baw" and g["band"]["id"] == "X")
        assert g["market"] == "competitors"
        assert all(p["manufacturer"] != "Acme" for p in rc.parts())
        assert [p["mpn"] for p in rc.slot_parts("filter_saw_baw", "X", competitors=True)] == ["AC-X1", "AC-X2"]
    finally:
        rc.competitor_parts.cache_clear()


# ---- from tests/test_fb_1023_rf_portfolio.py -------------------------------------------------------------------------
# Owner feedback 23 Oct 2026: the RF coverage by band table (smaller type, colour code, key) and the Skyworks + Qorvo
# "Which line to offer" section (bigger parts, room above "Used in", similar or further design effort).

CSS = (Path(__file__).resolve().parents[1] / "app" / "web" / "static" / "app.css").read_text()


def _contrast(fg: str, bg: str) -> float:
    def lum(h: str) -> float:
        c = [int(h.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def _rule(selector: str) -> str:
    m = re.search(re.escape(selector) + r"(?![\w-])[^{]*\{([^}]*)\}", CSS)
    assert m, selector
    return m.group(1)


def test_rf_coverage_table_colour_code_and_key(client):
    html = client.get("/business/rf-coverage").text
    assert 'class="rf-matrix stack-table rf-small"' in html  # smaller, no-wrap type on this table only
    assert html.count("rf-small") == 1
    key = html.split('class="rf-key small"')[1].split("</div>")[0]
    for cls in ("rf-ok", "rf-risk", "rf-r", "rf-need", "rf-comp", "rf-none"):
        assert cls in key
    assert "struck through" in key and "applications that need it" in key and "competitor makers" in key
    # active green, NRND grey and struck through (not red), applications solid blue, competitors solid red
    assert "line-through" in _rule(".rf-small .rf-r") and "#595959" in _rule(".rf-small .rf-r")
    pairs = [("#14532d", "#cdebd5"), ("#595959", "#cdebd5"), ("#ffffff", "#1d4ed8"), ("#ffffff", "#b91c1c"),
             ("#4a4a4a", "#ececec")]  # fmt: skip
    assert "#1d4ed8" in _rule(".rf-small .rf-need") and "#b91c1c" in _rule(".rf-small .rf-comp")
    assert all(_contrast(f, b) >= 4.5 for f, b in pairs)
    assert "white-space: nowrap !important" in _rule("  .stack-table.rf-matrix.rf-small th")


def test_rf_coverage_slot_status_marks(client):
    from app.services import rf_coverage as rf

    p = next(p for p in rf.parts() if p["bands"] and p["functions"])
    html = client.get("/business/rf-coverage", params={"fn": p["functions"][0], "band": p["bands"][0]}).text
    assert 'class="rf-st-ok"' in html or 'class="rf-st-risk"' in html


def test_pick_matches_rule():
    m = pf.pick_matches()
    wifi = m["wifi_fem"]
    assert wifi["verdict"] == "similar" and all(p["similar"] for p in wifi["pairs"])
    assert {p["qorvo"]["mpn"] for p in wifi["pairs"]} >= {"QPF4216", "QPF4659"}  # same band picked, 2.4 / 6 GHz
    iot = m["iot_short_range"]  # front-end modules against SoCs: extra parts around the other line's part
    assert iot["verdict"] == "effort" and all("different function" in p["reasons"][0] for p in iot["pairs"])
    lna = {p["skyworks"]["mpn"]: p for p in m["lna_sub6_gnss"]["pairs"]}
    assert not lna["SKY55951-11"]["similar"] and "different band" in lna["SKY55951-11"]["reasons"][0]
    assert "isolation" not in m and "beamformers_mmwave" not in m  # one line only: nothing to pair
    assert pf._same_job("rf_frontend", "wifi_fem") and not pf._same_job("lna", "power_amplifier")
    assert pf._ghz({"Frequency Min (MHz)": "2.4", "Frequency Max (MHz)": "2.5"}, "") == (2.4, 2.5)
    assert pf._supply({"Supply Voltage (V)": "2.85-4.5", "Supply Current Typ (mA)": "80"}) == (2.85, 4.5)


def test_portfolio_offer_section(client):
    html = client.get("/portfolio").text
    pick = html.split('id="pick"')[1].split('id="categories"')[0]
    assert 'class="badge pf-part"' in pick and 'class="small muted pf-used">Used in:' in pick
    assert "Further design effort required" in pick and 'class="pf-sim">Similar' in pick
    assert pf.MATCH_RULE in pick.replace("&#39;", "'") and pf.MATCH_RULE.startswith("est:")
    assert pick.index('class="pf-match small"') < pick.index("pf-used")
    assert "font-size: .95rem" in _rule(".pf-parts .badge.pf-part") and "margin-top: 1rem" in _rule(".pf-used")
    assert _contrast("#ffffff", "#1c6b3a") >= 4.5 and _contrast("#ffffff", "#9a3412") >= 4.5


# ---- from tests/test_fb_w1.py ----------------------------------------------------------------------------------------


def test_broadcast_receivers_cover_broadcast_bands():
    fm = {p["mpn"] for g in rf_bands.parts_for("fm") for p in g["specific"]}
    assert "Si47961" in fm  # automotive tuners now appear in the FM band
    am = rf_bands.parts_for("am")
    assert am and am[0]["fn"] in ("am_fm_tuner", "single_chip_radio")
    lband = {p["mpn"] for g in rf_bands.parts_for("dab_l") for p in g["specific"]}
    assert "Si47912" in lband  # L-band from the Si47912 data short
    si47942 = next(p for p in rf_bands._broadcast_parts() if p["mpn"] == "Si47942")
    assert si47942["ranges"] == [(0.168, 0.24)]  # DAB-only RF-to-I/Q tuner, Band III only


def test_feedback_pages(client):
    pf = client.get("/portfolio").text
    assert 'class="pf-legend' in pf and 'class="pf-col w-both"' in pf and "lead-" not in pf
    assert "Pick from the list" not in client.get("/compare").text
    radio = client.get("/broadcast").text
    assert 'class="fm-note"' not in radio
    assert client.get("/rf-bands?band=fm").status_code == 200
