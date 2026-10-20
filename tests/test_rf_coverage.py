"""RF coverage by band: frequency / power parsing, the GNSS and diversity remap, and the page."""

from app.services import blocks
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
