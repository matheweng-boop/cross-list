"""Owner, 25 Oct 2026: more block-diagram sources; the library diagrams under "Other" become more systems; the kick
sensor and the interior radar (child presence) get their own diagrams under UWB in the car; the UWB anchor gets a
clock block from a public reference design; new public reference designs show on /reference-designs."""

import re

import pytest

from app.services import blocks, refdesigns
from app.services import portfolio as pf
from app.services import systems as sy

NEW_SYSTEMS = ("industrial", "aerospace", "consumer", "home", "medical")
NEW = {  # name prefix -> (system, sub-system)
    "Kick-to-open sensor module": ("automotive", "car-access"),
    "Interior radar for child presence detection": ("automotive", "car-access"),
    "Automotive smart power closure": ("automotive", "cockpit"),
    "UWB + Bluetooth LE module for anchors and tags": ("consumer", "connectivity"),
    "Smartwatch with UWB": ("consumer", "wearables-xr"),
    "Drone power management, ESC, flight controller and gimbal": ("drones", "flight"),
    "48 V intermediate bus converter": ("datacenter", "rack-power"),
    "SATCOM user terminal": ("aerospace", "satcom"),
    "Satellite ground station power supply": ("aerospace", "satcom"),
    "SATCOM Ku-band block upconverter": ("aerospace", "satcom"),
    "Redundant L-band amplifier": ("aerospace", "satcom"),
    "Ka-band LEO gateway": ("aerospace", "satcom"),
    "Phased-array beamforming network": ("aerospace", "radar"),
    "AESA radar T/R module": ("aerospace", "radar"),
}


def _index(prefix: str) -> int:
    hits = [i for i, t in enumerate(blocks.templates()) if t["name"].startswith(prefix)]
    assert len(hits) == 1, prefix
    return hits[0]


def test_other_is_regrouped_into_new_systems_with_sub_systems():
    keys = [s["key"] for s in sy.systems()]
    assert keys[:4] == ["automotive", "datacenter", "drones", "cellular"] and set(NEW_SYSTEMS) <= set(keys)
    for k in NEW_SYSTEMS:
        s = sy.get(k)
        assert len(s["subsystems"]) >= 3, k
        for x in s["subsystems"]:
            assert x["idx"] and x["elements"] and x["title"] and x["summary"], (k, x["key"])
    assert sy.unassigned() == []  # nothing left under Other


def test_new_diagrams_validate_cite_sources_and_sit_in_their_sub_system():
    lib = blocks.templates()
    fns = blocks.catalogue()["functions"]
    for prefix, place in NEW.items():
        i = _index(prefix)
        t = lib[i]
        assert re.search(r"\(after [^()]+\)$", t["name"]), t["name"]  # marks itself "after <source>"
        assert t["sources"] and all(s["url"].startswith("https://") and s["doc"] and s["title"] for s in t["sources"])
        assert t["note"].startswith("After ") and all(s["doc"] in t["note"] for s in t["sources"][:1])
        ids = {g["id"] for g in t["groups"]}
        assert len(ids) == len(t["groups"]) >= 5
        for g in t["groups"]:
            assert g["blocks"] and all(b.split()[0] in fns for b in g["blocks"]), (prefix, g["id"])
        assert all(a in ids and b in ids for a, b, _ in t["links"]), prefix
        assert place in sy.place_of(i), (prefix, sy.place_of(i))
        assert "(after" not in blocks.display_name(t) and "Murata" not in blocks.display_name(t)


def test_kick_sensor_and_interior_radar_have_their_own_diagrams_under_uwb_in_the_car():
    names = [blocks.templates()[i]["name"] for i in sy.sub("automotive", "car-access")["idx"]]
    kick = next(n for n in names if n.startswith("Kick-to-open"))
    radar = next(n for n in names if n.startswith("Interior radar for child presence"))
    t = blocks.templates()[_index(kick)]
    assert any(s["url"] == "https://www.ti.com/solution/automotive-kick-to-open-module" for s in t["sources"])
    fns = {b for g in t["groups"] for b in g["blocks"]}
    assert {"touch_controller", "ultrasonic_afe", "radar_transceiver", "lin_transceiver", "mcu"} <= fns
    t = blocks.templates()[_index(radar)]
    assert {"radar_transceiver", "mcu", "can_transceiver"} <= {b for g in t["groups"] for b in g["blocks"]}
    assert any("infineon.com" in s["url"] for s in t["sources"])


def test_uwb_anchor_has_a_clock_block_from_a_public_reference_design():
    t = blocks.templates()[_index("Smart car access (UWB anchors")]
    clock = next(g for g in t["groups"] if g["id"] == "uwb_clock")
    assert clock["blocks"] == ["crystal_oscillator"] and "MURATA-2AB-DS" in clock["source"]
    assert ["uwb_clock", "uwb_anchor_outside", "reference clock"] in t["links"]
    docs = {s["doc"]: s["url"] for s in t["sources"]}
    assert docs["MURATA-2AB-DS"].startswith("https://www.murata.com/") and "MURATA-2BP" in docs


def test_qorvo_uwb_and_skyworks_timing_pair_appears_with_a_reason():
    pairs = pf.together_in(sy.sub("automotive", "car-access")["idx"])["synergies"]
    pair = next(x for x in pairs if (x["skyworks"], x["qorvo"]) == ("crystal_oscillator", "uwb_soc"))
    assert pair["reason"] and "38.4 MHz" in pair["reason"]


def test_new_public_reference_designs_are_listed():
    rows = {(d["vendor"], d["id"]): d for d in refdesigns.designs()}
    assert ("Skyworks", "SKY-RD-TIMING-NXP") in rows and ("Murata", "LBUA5QJ2AB-828") in rows
    for (vendor, _), d in rows.items():
        if vendor in ("Skyworks", "Murata"):
            assert d["url"].startswith("https://www.skyworksinc.com/") or d["url"].startswith("https://www.murata.com/")
            assert d["_type"] != refdesigns.OTHER_TYPE, d["id"]


@pytest.mark.parametrize("key", NEW_SYSTEMS)
def test_pages_pick_up_the_new_systems(client, key):
    s = sy.get(key)
    assert f'id="sys-{key}"' in client.get("/library").text
    lib = client.get("/blocks").text
    assert f'id="area-{key}"' in lib and lib.index(f'id="area-{key}"') < lib.index('id="other-areas"')
    x = s["subsystems"][0]
    one = client.get(f"/blocks?system={key}&sub={x['key']}").text
    assert f'id="sub-{x["key"]}"' in one
    xs = client.get(f"/blocks/cross-sell?sel={key}:{x['key']}").text
    assert x["title"] in xs and f'value="{key}:{x["key"]}"' in xs


def test_presentation_topics_include_the_new_systems():
    from app.services import presentation

    groups = {t["group"] for t in presentation.topics()}
    for k in NEW_SYSTEMS:
        assert sy.get(k)["title"] in groups, k
