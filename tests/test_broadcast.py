import re

from app.services import broadcast

TUNER_JOBS = {
    "off",
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


def test_use_case_presets_reference_known_parts_and_jobs():
    parts = {d["mpn"]: d for d in broadcast.catalog()}
    for uc in broadcast.use_cases():
        ants = {a["id"] for a in uc["antennas"]}
        assert uc["system"] in {"AM/FM", "HD", "DAB", "DRM"}
        for slot, ic in uc["ics"].items():
            assert ic["mpn"] is None or ic["mpn"] in parts, (uc["name"], slot)
            for t in ic.get("tuners") or []:
                assert t["job"] in TUNER_JOBS
            for c in ic.get("channels") or []:
                assert c["job"] in DEMOD_JOBS
        for slot, pins in (uc.get("rf") or {}).items():
            names = {p["name"] for p in parts[uc["ics"][slot]["mpn"]]["pins"]}
            for pin, feed in pins.items():
                assert pin in names, (uc["name"], slot, pin)
                if feed.startswith("loop:"):
                    src, out = feed[5:].split(".")
                    assert out in {p["name"] for p in parts[uc["ics"][src]["mpn"]]["pins"]}
                else:
                    assert feed in ants


def test_explanations_cover_every_job():
    ex = broadcast.explanations()
    for key in TUNER_JOBS:
        assert f"job:{key}" in ex
    for key in DEMOD_JOBS:
        assert f"djob:{key}" in ex


def test_pages_and_config_api(client):
    assert "Si47962" in client.get("/broadcast").text
    html = client.get("/broadcast/configurations/new").text
    assert 'id="bc-catalog"' in html and "North America HD" in html
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
