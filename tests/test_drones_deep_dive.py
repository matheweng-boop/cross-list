"""Drones deep dive (owner, 24 Oct 2026: "do a deep dive for Drones as well"): every Drones sub-system has a deep
dive and at least two diagrams, the topic pages render with the customer, competitor and market sections, and the
topics name parts that are in our catalogue."""

import pytest

from app.services import blocks, library
from app.services import systems as sy

DRONE_TOPICS = [
    "drone_flight_power",
    "drone_radio_links",
    "drone_cellular",
    "drone_satellite_link",  # owner, 2 Nov 2026
    "drone_navigation",
    "drone_antijam",
]


def test_every_drone_sub_system_has_a_deep_dive_and_two_diagrams():
    drones = sy.get("drones")
    keys = {t["key"] for t in library.topics()}
    assert [x["key"] for x in drones["subsystems"]] == [
        "flight",
        "radio-links",
        "cellular-link",
        "satellite-link",
        "navigation",
        "anti-jamming",
    ]
    for x in drones["subsystems"]:
        assert len(x["idx"]) >= 2, x["key"]
        assert x["topics"] and set(x["topics"]) <= keys, x["key"]
    assert sy.topic_place("drone_flight_power") == ("drones", "flight")
    assert sy.topic_place("drone_radio_links") == ("drones", "radio-links")
    assert sy.topic_place("drone_cellular") == ("drones", "cellular-link")
    assert sy.topic_place("drone_satellite_link") == ("drones", "satellite-link")
    assert sy.topic_place("drone_navigation") == ("drones", "navigation")
    assert sy.topic_place("drone_antijam") == ("drones", "anti-jamming")


@pytest.mark.parametrize("key", DRONE_TOPICS)
def test_drone_topic_has_the_full_format(key):
    t = library.topic(key)
    refs = set(library.refs_by_id(t))
    assert len(t["design_rules"]) >= 12 and len(t["trends"]) >= 5 and t["open_questions"]
    assert all(
        r["kind"] in ("rule", "consideration") and r["conf"] in ("high", "med", "low") for r in t["design_rules"]
    )
    assert all(r.get("retrieved") for r in t["references"])
    assert t["why_customer"] and t["competitors"] and t["market"]
    for m in t["market"]:
        assert set(m.get("refs") or []) <= refs, m
        assert m.get("refs") or "est" in m["text"], m  # an unsourced market line is marked as our estimate
    catalogue = {r["mpn"] for r in blocks.catalog_rows()}
    named = [p for s in t["skyworks_fit"] for p in s["parts"]]
    assert named and set(named) <= catalogue, set(named) - catalogue


@pytest.mark.parametrize("key", DRONE_TOPICS)
def test_drone_topic_pages_render(client, key):
    html = client.get(f"/library/{key}").text
    for anchor in (
        'id="customer"',
        'id="competitors"',
        'id="market"',
        'id="rules"',
        'id="ours"',
        "Full research notes",
    ):
        assert anchor in html, anchor
    assert client.get(f"/blocks/new?library={key}").status_code == 200


def test_library_shows_the_drone_deep_dives(client):
    html = client.get("/library").text
    for key in DRONE_TOPICS:
        assert f'href="/library/{key}"' in html


def test_new_drone_diagrams_open():
    names = [t["name"] for t in blocks.templates()]
    new = [
        n for n in names if n.startswith(("Drone ESC", "Drone battery", "Drone control link", "Drone cellular link"))
    ]
    assert len(new) == 4
    for x in sy.get("drones")["subsystems"][:3]:
        assert any(names[i] in new for i in x["idx"]), x["key"]


def test_automotive_topics_keep_the_old_format():
    t = library.topic("tcu_rf")
    assert "market" not in t and "competitors" not in t  # optional sections: older topics render as before


# ---- owner, 2 Nov 2026: "For Drones: add NTN/DTC, drone connectivity, drone navigation"; "drone disturbance" read as
# anti-jamming. Three new sub-systems with their own diagrams and deep dives, a "which link when" table on the radio
# links page, and cross-links between Navigation and Anti-jamming.
NEW_SUBS = {"satellite-link": 3, "navigation": 3, "anti-jamming": 4}


def test_new_drone_sub_systems_have_their_diagrams():
    names = [t["name"] for t in blocks.templates()]
    subs = {x["key"]: x for x in sy.get("drones")["subsystems"]}
    for key, n in NEW_SUBS.items():
        assert len(subs[key]["idx"]) == n, key
    sat = [names[i] for i in subs["satellite-link"]["idx"]]
    assert (
        any("NTN" in n for n in sat)
        and any("direct-to-cell" in n for n in sat)
        and any("satellite modem" in n for n in sat)
    )
    nav = [names[i] for i in subs["navigation"]["idx"]]
    assert (
        any("RTK" in n for n in nav)
        and any("sensor-fusion" in n for n in nav)
        and any(n.startswith("UWB positioning") for n in nav)
    )
    aj = [names[i] for i in subs["anti-jamming"]["idx"]]
    assert (
        any("CRPA" in n for n in aj)
        and any("hardened GNSS" in n for n in aj)
        and any("command-and-control" in n for n in aj)
    )


def test_link_choice_table_and_gnss_cross_links(client):
    radio = client.get("/library/drone_radio_links").text
    assert 'id="k-drone_link_choice"' in radio and "Which link when" in radio and "Direct-to-cell" in radio
    for key, other in (("drone_navigation", "/library/drone_antijam"), ("drone_antijam", "/library/drone_navigation")):
        html = client.get(f"/library/{key}").text
        assert other in html and "/engineering/gnss_how_it_works" in html and "/reviews/how/gnss" in html
    aj = client.get("/library/drone_antijam").text
    assert "/visuals#ip3" in aj and "/visuals#dbm" in aj
    assert "/visuals#link" in client.get("/library/drone_satellite_link").text


def test_new_drone_sub_system_diagrams_open(client):
    names = [t["name"] for t in blocks.templates()]
    for key in NEW_SUBS:
        for i in sy.get("drones")["subsystems"][[x["key"] for x in sy.get("drones")["subsystems"]].index(key)]["idx"]:
            assert client.get(f"/blocks/new?template={i}").status_code == 200, names[i]
