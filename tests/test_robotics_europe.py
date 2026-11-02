"""Robotics (European view) (owner, 3 Nov 2026: "For Factory automation, something for robotics would be good. Focus
on a Euro-centric view for this."): a new Industrial sub-system with three new block diagrams plus the existing robot
and servo diagrams, and a Euro-centric deep dive that links back to factory automation, motor drives and the circuit
visuals."""

import re

import pytest

from app.services import blocks, library, refmatch, site_guard
from app.services import systems as sy

KEY = "robotics_europe"
NEW = (
    "Six-axis industrial robot - controller, EtherCAT joint chain",
    "Autonomous mobile robot (AMR) for European warehouses and factories",
    "Robot end-of-arm tool and tool changer with IO-Link Wireless",
)
KEPT = (  # existing robot and servo diagrams, now also under Robotics, still under Motor drives and robots
    "Industrial servo drive (single axis, AC motor) (TI)",
    "AC servo drive with EtherCAT",
    "Humanoid / collaborative robot joint motor drive (48 V) (TI)",
)
BLOCKED = ("qorvo.com", "nxp.com", "analog.com", "microchip.com", "onsemi.com", "eur-lex", "iso.org", "mouser",
           "digikey")  # fmt: skip


def _index(prefix: str) -> int:
    hits = [i for i, t in enumerate(blocks.templates()) if t["name"].startswith(prefix)]
    assert len(hits) == 1, prefix
    return hits[0]


def test_robotics_is_an_industrial_sub_system_with_its_deep_dive():
    x = sy.sub("industrial", "robotics")
    assert x["title"] == "Robotics (European view)" and x["topics"] == [KEY] and len(x["elements"]) >= 4
    assert sy.topic_place(KEY) == ("industrial", "robotics")
    for p in NEW + KEPT:
        assert _index(p) in x["idx"], p
    motion = sy.sub("industrial", "motion")["idx"]
    for p in KEPT:  # still under Motor drives and robots
        assert _index(p) in motion, p
    hrefs = [h for _, h in x["links"]]
    assert any("sub=factory-automation" in h for h in hrefs) and any("sub=motion" in h for h in hrefs)
    assert {"/visuals#bldc", "/visuals#bootstrap", "/visuals#isosense"} <= set(hrefs)
    for sub in ("factory-automation", "motion"):  # and back from the two neighbours
        assert ("Robotics (European view): deep dive", f"/library/{KEY}") in sy.sub("industrial", sub)["links"]


@pytest.mark.parametrize("prefix", NEW)
def test_new_robot_diagram_is_valid_cited_and_names_our_parts_and_gaps(prefix):
    i = _index(prefix)
    t = blocks.templates()[i]
    fns = blocks.catalogue()["functions"]
    assert re.search(r"\(after [^()]+\)$", t["name"]) and "(after" not in blocks.display_name(t)
    assert t["note"].startswith("After ") and "Our parts that fit:" in t["note"] and "Gaps:" in t["note"]
    assert t["sources"] and all(s["url"].startswith("https://") and s["doc"] in t["note"] for s in t["sources"])
    assert not any(b in s["url"] for s in t["sources"] for b in BLOCKED)
    ids = {g["id"] for g in t["groups"]}
    assert len(ids) == len(t["groups"]) >= 7
    for g in t["groups"]:
        assert g["blocks"] and all(b.split()[0] in fns for b in g["blocks"]), g["id"]
    assert all(a in ids and b in ids for a, b, _ in t["links"])
    assert site_guard.hits(t["note"]) == []
    assert ("industrial", "robotics") in sy.place_of(i)


def test_new_diagrams_hold_the_sockets_the_owner_asked_for():
    def fns(prefix):
        return {b.split()[0] for g in blocks.templates()[_index(prefix)]["groups"] for b in g["blocks"]}

    arm = fns(NEW[0])
    assert {"gate_driver", "isolated_amplifier", "digital_isolator", "isolated_digital_input", "isolated_smart_switch",
            "rs485_transceiver", "ethernet_phy", "position_sensor", "clock_generator"} <= arm  # fmt: skip
    amr = fns(NEW[1])
    assert {"wifi_fem", "rf_frontend", "uwb_soc", "battery_monitor", "wireless_power", "motor_controller"} <= amr
    tool = fns(NEW[2])
    assert {"isolated_smart_switch", "isolated_digital_input", "wireless_power", "wireless_soc"} <= tool
    names = [blocks.templates()[_index(p)]["name"] for p in NEW]
    assert "safe torque off" in names[0] and "ISO 13849" in names[0]


def test_new_diagrams_are_in_the_reference_design_matches():
    names = {e["name"] for e in refmatch.data()["diagrams"]}
    for p in NEW:
        assert blocks.templates()[_index(p)]["name"] in names, p


def test_deep_dive_has_the_full_format_and_european_content():
    t = library.topic(KEY)
    refs = set(library.refs_by_id(t))
    assert len(t["references"]) == 6 and len(t["design_rules"]) >= 12 and len(t["trends"]) >= 5
    assert all(r.get("retrieved") for r in t["references"])
    assert not any(b in r["url"] for r in t["references"] for b in BLOCKED)
    for m in t["market"]:
        assert set(m.get("refs") or []) <= refs and (m.get("refs") or "est" in m["text"]), m
    catalogue = {r["mpn"] for r in blocks.catalog_rows()}
    named = [p for s in t["skyworks_fit"] for p in s["parts"]]
    assert named and set(named) <= catalogue, set(named) - catalogue
    assert any(not s["parts"] and s["note"].startswith("Gap") for s in t["skyworks_fit"])
    text = library._text(t)
    for word in ("ABB", "KUKA", "Midea", "Stäubli", "Comau", "Universal Robots", "Franka", "NEURA", "Agile Robots",
                 "Fanuc", "Yaskawa", "Germany", "Italy", "France", "Spain", "2023/1230", "20 January 2027",
                 "ISO 10218", "ISO/TS 15066", "13849", "AI Act", "Cyber Resilience Act", "EtherCAT", "PROFINET",
                 "TSN", "IO-Link", "10BASE-T1L", "humanoid", "reshoring", "labour shortage"):  # fmt: skip
        assert word.lower() in text.lower(), word
    assert site_guard.hits(text) == [] and "data centre" not in text


def test_deep_dive_page_links_neighbours_and_circuit_visuals(client):
    html = client.get(f"/library/{KEY}").text
    for anchor in ('id="customer"', 'id="competitors"', 'id="market"', 'id="rules"', 'id="ours"',
                   "Full research notes", "See also:"):  # fmt: skip
        assert anchor in html, anchor
    for href in ("/blocks?system=industrial&amp;sub=factory-automation#sub-factory-automation",
                 "/blocks?system=industrial&amp;sub=motion#sub-motion", "/visuals#bldc", "/visuals#bootstrap",
                 "/visuals#isosense"):  # fmt: skip
        assert f'href="{href}"' in html, href
    assert client.get(f"/blocks/new?library={KEY}").status_code == 200


def test_industrial_shows_the_robotics_card_in_both_libraries(client):
    for page, anchor in (("/library", "sys"), ("/blocks", "area")):
        html = client.get(page).text
        block = html.split(f'id="{anchor}-industrial"')[1].split('<details class="sys-block"')[0]
        assert 'id="card-industrial-robotics"' in block and "Robotics (European view)" in block
    assert f'href="/library/{KEY}"' in client.get("/library").text
