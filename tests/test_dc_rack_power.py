"""Data center > Rack power (owner, 9 Nov 2026: "Do a Data Center Rack Power deep dive in Systems & applications"): a
deep dive in the full format, two new block diagrams after public sources next to the three earlier ones, and our
parts named from the catalogue only."""

import re

from app.services import blocks, library
from app.services import systems as sy

NEW = (
    "Open Rack v3 power shelf with battery backup",
    "AI compute tray power from the 48 / 54 V busbar to the GPU core",
)


def _fn(b) -> str:
    return b["fn"] if isinstance(b, dict) else b.split()[0]


def test_rack_power_sub_system_has_its_diagrams_and_deep_dive():
    sub = sy.sub("datacenter", "rack-power")
    assert sub["topics"] == ["dc_rack_power"] and sy.topic_place("dc_rack_power") == ("datacenter", "rack-power")
    names = [blocks.templates()[i]["name"] for i in sub["idx"]]
    assert len(names) == 5
    for prefix in (*NEW, "Server / telecom AC/DC power supply unit", "48 V intermediate bus converter",
                   "AI data-center 800 V DC power"):  # fmt: skip
        assert sum(n.startswith(prefix) for n in names) == 1, prefix


def test_new_rack_power_diagrams_validate_and_cite_public_sources():
    fns = blocks.catalogue()["functions"]
    found = 0
    for t in blocks.templates():
        if not t["name"].startswith(NEW):
            continue
        found += 1
        assert re.search(r"\(after [^()]+\)$", t["name"]), t["name"]
        assert t["category"] == "Enterprise & data center"
        assert t["note"].startswith("After ") and all(s["doc"] in t["note"] for s in t["sources"])
        assert all(s["url"].startswith("https://") and s["title"] for s in t["sources"])
        ids = [g["id"] for g in t["groups"]]
        assert len(ids) == len(set(ids)) >= 8
        assert all(g["blocks"] and all(_fn(b) in fns for b in g["blocks"]) for g in t["groups"]), t["name"]
        assert all(a in ids and b in ids for a, b, _ in t["links"]), t["name"]
    assert found == 2
    shelf = next(t for t in blocks.templates() if t["name"].startswith(NEW[0]))
    used = {_fn(b) for g in shelf["groups"] for b in g["blocks"]}
    assert {"gate_driver", "digital_isolator", "isolated_amplifier", "battery_monitor", "efuse_hotswap"} <= used
    assert any("opencompute.org" in s["url"] for s in shelf["sources"])
    tray = next(t for t in blocks.templates() if t["name"].startswith(NEW[1]))
    used = {_fn(b) for g in tray["groups"] for b in g["blocks"]}
    assert {"efuse_hotswap", "power_module", "multiphase", "power_loss_protection"} <= used


def test_rack_power_deep_dive_has_the_full_format_and_names_catalogue_parts():
    t = library.topic("dc_rack_power")
    refs = set(library.refs_by_id(t))
    assert len(t["references"]) == 6 and len(t["design_rules"]) >= 12 and len(t["trends"]) >= 5
    assert t["why_customer"] and t["competitors"] and t["market"] and t["open_questions"]
    for m in t["market"]:
        assert set(m.get("refs") or []) <= refs and "est" in m["segment"] + m["text"], m
    areas = " ".join(r["area"] for r in t["design_rules"]).lower()
    for word in ("efficiency", "hold-up", "transient", "isolation", "creepage", "cmti", "redundancy", "pmbus",
                 "hot-swap"):  # fmt: skip
        assert word in areas, word
    trends = " ".join(x["text"] for x in t["trends"])
    for word in ("800 V DC", "Solid-state transformers", "GaN", "Vertical power delivery", "Battery backup"):
        assert word in trends, word
    catalogue = {r["mpn"] for r in blocks.catalog_rows()}
    named = [p for s in t["skyworks_fit"] for p in s["parts"]]
    assert named and set(named) <= catalogue, set(named) - catalogue
    gaps = {s["fn"] for s in t["skyworks_fit"] if not s["parts"] and s["note"].startswith("Gap")}
    assert {"efuse_hotswap", "multiphase"} <= gaps  # the tray-side gaps are shown honestly
    assert "data centre" not in (library.FOLDER / "topics" / "dc_rack_power.yaml").read_text().lower()


def test_rack_power_pages_render(client):
    html = client.get("/library/dc_rack_power").text
    for anchor in ('id="customer"', 'id="competitors"', 'id="market"', 'id="rules"', 'id="ours"',
                   "Full research notes", "Si8273AB-IS1", "PAC22140"):  # fmt: skip
        assert anchor in html, anchor
    assert "/visuals#creep" in html and "/visuals#cmti" in html
    lib = client.get("/library").text
    assert 'id="card-datacenter-rack-power"' in lib and 'href="/library/dc_rack_power"' in lib
    assert client.get("/blocks/new?library=dc_rack_power").status_code == 200
