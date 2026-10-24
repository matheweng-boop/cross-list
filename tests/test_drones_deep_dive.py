"""Drones deep dive (owner, 24 Oct 2026: "do a deep dive for Drones as well"): every Drones sub-system has a deep
dive and at least two diagrams, the topic pages render with the customer, competitor and market sections, and the
topics name parts that are in our catalogue."""

import pytest

from app.services import blocks, library
from app.services import systems as sy

DRONE_TOPICS = ["drone_flight_power", "drone_radio_links", "drone_cellular"]


def test_every_drone_sub_system_has_a_deep_dive_and_two_diagrams():
    drones = sy.get("drones")
    keys = {t["key"] for t in library.topics()}
    assert [x["key"] for x in drones["subsystems"]] == ["flight", "radio-links", "cellular-link"]
    for x in drones["subsystems"]:
        assert len(x["idx"]) >= 2, x["key"]
        assert x["topics"] and set(x["topics"]) <= keys, x["key"]
    assert sy.topic_place("drone_flight_power") == ("drones", "flight")
    assert sy.topic_place("drone_radio_links") == ("drones", "radio-links")
    assert sy.topic_place("drone_cellular") == ("drones", "cellular-link")


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
    for x in sy.get("drones")["subsystems"]:
        assert any(names[i] in new for i in x["idx"]), x["key"]


def test_automotive_topics_keep_the_old_format():
    t = library.topic("tcu_rf")
    assert "market" not in t and "competitors" not in t  # optional sections: older topics render as before
