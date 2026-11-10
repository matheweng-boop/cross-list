"""Case "Skyworks UL2X low-latency wireless audio in the car" (owner, 10 Nov 2026: "full research and business case"):
the research sits in the case's In depth block in the owner's order (what it is, adjacent products first, then use
cases and other opportunities, then the links and the market), the case renders with its diagram, the library has the
in-car diagram under Cockpit and body, and nothing names a site or claims an automotive grade the parts do not have."""

import html

from app.services import autograde, blocks, digest, prelim, site_guard
from app.services import reports as rp

SLUG = "auto-ul2x-audio"
DIAGRAM = ("In-car low-latency wireless audio (rear-seat hub, passenger headphones, karaoke microphones, game "
           "controllers; Bluetooth for own devices) (after Skyworks and HARMAN public material)")  # fmt: skip


def test_entry_answers_the_owner_with_a_recommendation():
    r = rp.report(SLUG)
    assert r["kind"] == "idea" and r["app_type"] == "Automotive" and r["feasibility"] == 2
    assert "UL2X" in r["question"] and rp.story_problems(r) == [] and rp.has_background(SLUG)
    assert r["answer"]["text"].startswith("Watch") and r["answer"]["conf"] == "low"
    assert "auto-wireless-audio" in r["see_also"]
    report = rp.report("auto-wireless-audio")
    assert SLUG in report["see_also"] and any(s.get("case") == SLUG for s in report["next_steps"])
    c = prelim.raw(SLUG)
    assert digest.words(c["gist"]) <= digest.MAX_WORDS and len(c["abstract"]) == 3


def test_depth_tables_follow_the_owners_order_and_are_complete():
    d = prelim.raw(SLUG)["depth"]
    ids = [t["id"] for t in d["tables"]]
    assert ids == ["what", "adjacent", "uses", "other", "links", "market", "needs"]
    for t in d["tables"]:
        assert t["rows"] and all(len(row) == len(t["columns"]) for row in t["rows"]), t["id"]
    text = " ".join(str(c) for t in d["tables"] for row in t["rows"] for c in row)
    for s in ("SKY76360-22", "SKY76361-52", "2.4 GHz", "8 ms", "9 ms", "1 µs", "0 to 70 °C", "QPF4239Q",
              "QPQ2254Q", "Si5332-AM", "AEC-Q100 Grade 3", "PPAP", "ISO/SAE 21434", "karaoke", "HARMAN", "GMAP",
              "est"):  # fmt: skip
        assert s in text, s
    ranks = [row[-1] for row in d["tables"][2]["rows"]]
    assert ranks[:4] == ["1", "2", "3", "4"]
    assert not site_guard.hits(text + " " + d["intro"] + " " + " ".join(d["points"]))


def test_case_page_renders_research_diagram_and_sources(client):
    page = html.unescape(client.get(f"/business/reports/{SLUG}").text)
    assert 'id="in-depth"' in page and "What UL2X is (Skyworks public pages)" in page
    assert page.index("Adjacent products and technologies") < page.index("Car use cases, ranked")
    assert page.index("Car use cases, ranked") < page.index("Market sizing")
    assert client.get(f"/blocks/new?case={SLUG}").status_code == 200
    bg = html.unescape(client.get(f"/business/reports/{SLUG}/background").text)
    for s in ("Requests made for this case", "Wireless-Gaming", "LC3Characterization_WP.pdf", "car.harman.com",
              "licence"):  # fmt: skip
        assert s in bg, s
    for name in (f"{SLUG}.background.html",):
        text = (rp.BODIES / name).read_text()
        assert not site_guard.hits(text) and "qorvo.com/" not in text and "data centre" not in text


def test_grades_match_the_site_rule():
    for mpn in ("QPF4239Q", "SKYA21040", "QPQ2254Q", "SKY5A2108", "Si5332A-AM1", "ACT4751MQI101"):
        assert autograde.is_aec(mpn), mpn
    for mpn in ("SKY76360-22", "SKY76361-32", "SKY76361-52", "SKY76303-21"):
        assert not autograde.is_aec(mpn), mpn


def test_library_has_the_in_car_diagram_under_cockpit(client):
    t = next(x for x in blocks.templates() if x["name"] == DIAGRAM)
    assert t["category"] == "Automotive systems" and len(t["groups"]) == 6
    from app.services import systems as sy

    cockpit = next(s for sys_ in sy.systems() for s in sys_["subsystems"] if s["key"] == "cockpit")
    assert DIAGRAM in cockpit["diagrams"]
