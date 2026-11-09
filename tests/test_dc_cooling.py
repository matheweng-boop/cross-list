"""Data center > Cooling and HVAC (owner, 2 Nov 2026: "Also add cooling and HVAC to data centers"): a new sub-system
with four block diagrams after public sources, a deep dive in the full format, and our parts named from the
catalogue."""

import re

from app.services import blocks, library
from app.services import systems as sy

NEW = (
    "Data-center CRAH / CRAC air handler or chiller drive",
    "Liquid cooling distribution unit for AI racks",
    "Data-center fan wall / EC fan array",
    "Rear-door heat exchanger with active fans",
)


def _fn(b) -> str:
    return b["fn"] if isinstance(b, dict) else b.split()[0]


def test_cooling_is_a_data_center_sub_system_with_its_diagrams_and_deep_dive():
    dc = sy.get("datacenter")
    keys = [x["key"] for x in dc["subsystems"]]
    assert "cooling" in keys and {"rack-power", "backup", "networking", "server-board"} <= set(keys)
    sub = sy.sub("datacenter", "cooling")
    assert sub["title"] == "Cooling and HVAC" and sub["elements"] and sub["topics"] == ["dc_cooling"]
    names = [blocks.templates()[i]["name"] for i in sub["idx"]]
    for prefix in NEW:
        assert sum(n.startswith(prefix) for n in names) == 1, prefix
    assert "HVAC motor control (AC input, PFC + 3-phase inverter) (TI)" in names  # reused from Motor drives
    assert sy.topic_place("dc_cooling") == ("datacenter", "cooling")


def test_cooling_diagrams_validate_and_cite_public_sources():
    fns = blocks.catalogue()["functions"]
    for t in blocks.templates():
        if not t["name"].startswith(NEW):
            continue
        assert re.search(r"\(after [^()]+\)$", t["name"]), t["name"]
        assert t["category"] == "Enterprise & data center"
        assert t["note"].startswith("After ") and t["sources"][0]["doc"] in t["note"]
        assert all(s["url"].startswith("https://") and s["title"] for s in t["sources"])
        ids = [g["id"] for g in t["groups"]]
        assert len(ids) == len(set(ids)) >= 5
        assert all(g["blocks"] and all(_fn(b) in fns for b in g["blocks"]) for g in t["groups"]), t["name"]
        assert all(a in ids and b in ids for a, b, _ in t["links"]), t["name"]
        used = {_fn(b) for g in t["groups"] for b in g["blocks"]}
        assert {"rs485_transceiver", "mcu"} <= used, t["name"]  # every unit has a controller and a building link
    cdu = next(t for t in blocks.templates() if t["name"].startswith(NEW[1]))
    used = {_fn(b) for g in cdu["groups"] for b in g["blocks"]}
    assert {"gate_driver", "isolated_amplifier", "temperature_sensor", "env_sensor", "efuse_hotswap"} <= used


def test_cooling_deep_dive_has_the_full_format_and_names_catalogue_parts():
    t = library.topic("dc_cooling")
    refs = set(library.refs_by_id(t))
    assert len(t["design_rules"]) >= 12 and len(t["trends"]) >= 5 and t["open_questions"]
    assert t["why_customer"] and t["competitors"] and t["market"]
    for m in t["market"]:
        assert set(m.get("refs") or []) <= refs and (m.get("refs") or "est" in m["text"]), m
    areas = " ".join(r["area"] for r in t["design_rules"]).lower()
    for word in ("efficiency", "isolation", "sensor", "redundancy", "leak"):
        assert word in areas, word
    trends = " ".join(x["text"] for x in t["trends"])
    for word in ("cold plates", "Immersion", "48 V", "800 V"):
        assert word in trends, word
    catalogue = {r["mpn"] for r in blocks.catalog_rows()}
    named = [p for s in t["skyworks_fit"] for p in s["parts"]]
    assert named and set(named) <= catalogue, set(named) - catalogue
    assert any(not s["parts"] and s["note"].startswith("Gap") for s in t["skyworks_fit"])  # gaps shown honestly


def test_cooling_pages_render(client):
    html = client.get("/library/dc_cooling").text
    for anchor in (
        'id="customer"',
        'id="competitors"',
        'id="market"',
        'id="rules"',
        'id="ours"',
        "Full research notes",
    ):
        assert anchor in html, anchor
    assert "/visuals#bldc" in html  # links the BLDC circuit visual by keyword
    lib = client.get("/library").text
    assert 'id="card-datacenter-cooling"' in lib and 'href="/library/dc_cooling"' in lib
    assert client.get("/blocks/new?library=dc_cooling").status_code == 200
