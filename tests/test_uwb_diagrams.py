"""Public UWB block diagrams (owner, 28 Oct 2026: "if we can find more block diagrams, please do so") and the UWB
application entries they feed: valid data, links, function ids mapped, matched to the library diagrams."""

import pytest

from app.services import blocks, refdesigns, refmatch, site_guard
from app.services import systems as sy

NEW_DESIGNS = {  # (vendor, id) -> functions the diagram must show
    ("Murata", "LBUA0ZZ2HQ"): {"uwb_soc", "filter_saw_baw", "crystal_oscillator"},
    ("Murata", "LBUA2ZZ2DK"): {"uwb_soc", "ble_soc", "crystal_oscillator"},
    ("Infineon", "AIROC-UWB-TSL100"): {"uwb_soc", "crystal_oscillator"},
    ("Infineon", "IFX-APP-SMART-DOOR-LOCK"): {"uwb_soc", "ble_soc", "nfc_frontend", "tvs_esd", "pol_ldo"},
    ("Infineon", "IFX-APP-CAR-ACCESS"): {"uwb_soc", "ble_soc", "radar_transceiver"},
    ("MobileKnowledge", "MK-UWB-KIT-ROBOTICS"): {"uwb_soc", "ble_soc", "antenna"},
    ("MobileKnowledge", "MK-UWB-KIT-RTLS-2"): {"uwb_soc", "ble_soc"},
    ("Google", "AOSP-UWB-STACK"): {"uwb_soc"},
    ("University of Turku / EPFL (arXiv)", "ARXIV-2003.04380"): {"uwb_soc"},
}
NEW_APPS = {  # name prefix -> (system, sub-system)
    "UWB radar in the car": ("automotive", "car-access"),
    "Smart door lock with UWB": ("home", "smart-home"),
    "UWB radar presence and vital-sign sensor": ("home", "smart-home"),
    "UWB real-time locating system": ("industrial", "factory-automation"),
    "UWB positioning for mobile robots and drones": ("industrial", "motion"),
    "Tap-free payment and store access with UWB": ("consumer", "computing"),
    "Sports player tracking with UWB": ("consumer", "wearables-xr"),
    "UWB between the car and its surroundings": ("automotive", "car-access"),
}
BLOCKED = ("qorvo.com", "nxp.com", "www.qualcomm.com", "mouser", "digikey", "archive.org")


def _designs() -> dict:
    return {(d["vendor"], d["id"]): d for d in refdesigns.designs()}


@pytest.mark.parametrize("key", list(NEW_DESIGNS))
def test_new_uwb_diagram_is_valid_and_its_functions_map(key):
    d = _designs()[key]
    fns = blocks.catalogue()["functions"]
    assert set(d["functions"]) <= set(fns) and NEW_DESIGNS[key] <= set(d["functions"])
    assert d["url"].startswith("https://") and not any(b in d["url"] for b in BLOCKED)
    for v in (d.get("documents") or {}).values():
        for u in v if isinstance(v, list) else [v]:
            assert u.startswith("https://") and not any(b in u for b in BLOCKED)
    assert d["summary"] and d["applications"] and d["markets"]
    assert d["_type"] != refdesigns.OTHER_TYPE
    assert site_guard.hits(d["summary"]) == []


def test_uwb_diagrams_count_toward_found_in_and_based_on():
    assert refmatch.fn_count("uwb_soc") >= 10
    matched = {e["name"]: e for e in refmatch.data()["diagrams"]}
    module = next(e for n, e in matched.items() if n.startswith("UWB + Bluetooth LE module for anchors and tags"))
    assert {"Murata:LBUA0ZZ2HQ", "Murata:LBUA2ZZ2DK"} <= set(module["designs"])
    car = next(e for n, e in matched.items() if n.startswith("Smart car access (UWB anchors"))
    assert "Infineon:IFX-APP-CAR-ACCESS" in car["designs"] and "uwb_soc" in car["confirmed"]
    rtls = next(e for n, e in matched.items() if n.startswith("UWB real-time locating system"))
    assert "MobileKnowledge:MK-UWB-KIT-RTLS-2" in rtls["designs"]


def test_reference_design_list_shows_the_new_diagrams(client):
    html = client.get("/reference-designs?fn=uwb_soc").text
    for _, did in NEW_DESIGNS:
        assert did in html, did


@pytest.mark.parametrize("prefix", list(NEW_APPS))
def test_new_uwb_application_entry_is_light_cited_and_placed(client, prefix):
    lib = blocks.templates()
    hits = [i for i, t in enumerate(lib) if t["name"].startswith(prefix)]
    assert len(hits) == 1, prefix
    i, t = hits[0], lib[hits[0]]
    fns = blocks.catalogue()["functions"]
    assert t["note"].startswith("After ") and "Our parts that fit:" in t["note"]
    assert t["sources"] and all(s["url"].startswith("https://") and s["doc"] in t["note"] for s in t["sources"])
    assert not any(b in s["url"] for s in t["sources"] for b in BLOCKED)
    ids = {g["id"] for g in t["groups"]}
    assert len(ids) == len(t["groups"]) >= 5
    assert any(b.split()[0] == "uwb_soc" for g in t["groups"] for b in g["blocks"])
    for g in t["groups"]:
        assert all(b.split()[0] in fns for b in g["blocks"]), g
    assert all(a in ids and b in ids for a, b, _ in t["links"])
    assert NEW_APPS[prefix] in sy.place_of(i)
    assert "(after" not in blocks.display_name(t)
    assert client.get(f"/business/applications/{i}").status_code == 200
