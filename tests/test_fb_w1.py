from app.services import rf_bands


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
