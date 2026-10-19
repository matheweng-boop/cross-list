import re

from app.services import broadcast

TUNER_JOBS = {
    "off",
    "dab2",
    "fm_pd_ts",
    "amfm_audio",
    "fm_audio",
    "am_audio",
    "fm_pd",
    "fm_mrc",
    "fm_scan",
    "am_scan",
    "dab",
    "fm_dab_scan",
    "drm",
}
DEMOD_JOBS = {
    "unused",
    "dab_audio2",
    "dab_link",
    "dab_scan",
    "hd_scan",
    "hd_audio",
    "hd_data",
    "hd_mrc",
    "dab_audio",
    "dab_scanless",
    "dab_mrc",
    "drm_audio",
    "cdr_audio",
}
FNS = set(re.findall(r"^\| `(\w+)` \|", (broadcast.DEVICES_DIR.parent / "SCHEMA.md").read_text(), re.M))


def test_device_files_are_consistent():
    docs = broadcast.documents()
    assert len(docs) >= 20
    for doc in docs:
        nums = [p["n"] for p in doc.get("pins") or []]
        assert nums == sorted(nums) and len(nums) == len(set(nums)), doc["doc"]
        for p in (doc.get("pins") or []) + (doc.get("signals") or []):
            assert p["fn"] in FNS, (doc["doc"], p)
        assert doc.get("role") in broadcast.ROLES or all(x.get("role") in broadcast.ROLES for x in doc["parts"])


def test_catalog_has_tuners_receivers_and_coprocessors():
    by_role = {r: [d["mpn"] for d in broadcast.catalog() if d["role"] == r] for r in broadcast.ROLES}
    assert "Si47962" in by_role["tuner"] and "Si4689-A10" in by_role["receiver"]
    assert any(m.startswith("Si46922") for m in by_role["coprocessor"])
    si47961 = next(d for d in broadcast.catalog() if d["mpn"] == "Si47961")
    assert si47961["digital_iq"] == ["HD"] and si47961["tuners"] == 2  # DRM/DAB are Si47962 only


def test_signal_only_devices_get_unnumbered_pins():
    si4689 = next(d for d in broadcast.catalog() if d["mpn"] == "Si4689-A10")
    assert not si4689["numbered"] and si4689["pins"] and all(p["num"] == "" for p in si4689["pins"])


def test_configuration_presets_reference_known_parts_pins_and_jobs():
    conf = broadcast.configurations()
    parts = {d["mpn"]: d for d in broadcast.catalog()}
    for hw in conf["hardware"]:
        assert set(hw["regions"]) <= set(conf["regions"])
        ants = {a["id"] for a in hw["antennas"]}
        for slot, mpn in hw["ics"].items():
            assert mpn is None or mpn in parts, (hw["name"], slot)
        for slot, pins in (hw.get("rf") or {}).items():
            names = {p["name"] for p in parts[hw["ics"][slot]]["pins"]}
            for pin, feed in pins.items():
                assert pin in names, (hw["name"], slot, pin)
                if feed.startswith("loop:"):
                    src, out = feed[5:].split(".")
                    assert out in {p["name"] for p in parts[hw["ics"][src]]["pins"]}
                else:
                    assert feed in ants
    for sw in conf["software"]:
        assert sw["region"] in conf["regions"]
        for jobs in sw["tuners"].values():
            assert set(jobs) <= TUNER_JOBS, sw["name"]
        for c in sw.get("channels") or []:
            assert c["job"] in DEMOD_JOBS


def test_explanations_cover_every_job():
    ex = broadcast.explanations()
    for key in TUNER_JOBS:
        assert f"job:{key}" in ex
    for key in DEMOD_JOBS:
        assert f"djob:{key}" in ex
    for region in broadcast.configurations()["regions"]:
        assert f"region:{region}" in ex


def test_pages_and_config_api(client):
    assert "Si47962" in client.get("/broadcast").text
    html = client.get("/broadcast/configurations/new").text
    assert 'id="bc-catalog"' in html and "Superset" in html and 'data-region="Europe"' in html
    created = client.post(
        "/api/broadcast/configs", json={"name": "Test", "data": {"devices": [{"id": "d1", "mpn": "Si47962"}]}}
    ).json()
    assert client.get(f"/api/broadcast/configs/{created['id']}").json()["data"]["devices"][0]["mpn"] == "Si47962"
    client.put(f"/api/broadcast/configs/{created['id']}", json={"name": "Renamed", "data": {}})
    listing = client.get("/broadcast/configurations").text
    assert "Renamed" in listing
    assert client.get(f"/broadcast/configurations/{created['id']}").status_code == 200
    client.post(f"/broadcast/configurations/{created['id']}/delete")
    assert client.get(f"/broadcast/configurations/{created['id']}").status_code == 404


def test_audio_twins_exist_and_carry_audio():
    parts = {d["mpn"]: d for d in broadcast.catalog()}
    twins = {"Si47961": "Si47971", "Si47962": "Si47972", "Si47951": "Si47921", "Si47952": "Si47912"}
    for plain, audio in twins.items():
        assert not any("audio dsp" in o.lower() for o in parts[plain]["options"])
        assert any("audio dsp" in o.lower() for o in parts[audio]["options"]), audio
        assert set(parts[plain]["digital_iq"]) <= set(parts[audio]["digital_iq"]) | {"DRM"}, (plain, audio)


def test_feature_matrix_covers_tuners_and_layouts():
    tf = broadcast.tuner_features()
    cat = {d["mpn"]: d for d in broadcast.catalog()}
    for t in tf["tuners"]:
        assert set(t["features"]) <= set(tf["features"]), t["mpn"]
        assert t["layout"] in tf["layouts"]
        assert t["mpn"] in cat and cat[t["mpn"]]["role"] == "tuner"
    # single tuners that fit the dual-tuner layout
    assert cat["Si47951"]["layout"] == cat["Si47961"]["layout"]
    assert cat["Si47982"]["layout"] == cat["Si47972"]["layout"] and cat["Si47982"]["borrowed_pins"] == "Si47971"
    assert cat["Si47901"]["layout"] != cat["Si47961"]["layout"]


def test_overview_has_feature_matrix(client):
    html = client.get("/broadcast").text
    assert "Tuner selection by feature" in html and "Si47992" in html and "data-feat-filter" in html
