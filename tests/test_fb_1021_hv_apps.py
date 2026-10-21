"""Owner feedback 21 Oct ("what about potential other applications ... and a block diagram"): the applications that need
more than 8 mm creepage are ranked in the ISO7821DWW report, five block diagrams are added for them (1500 V solar,
1500 V storage, 800 V DC data center, railway auxiliary converter, wind converter), category search finds them, and
the extra-wide case follows the preliminary-case template."""

import html
import re

from app.services import blocks, prelim
from app.services import reports as rp

NEW = {
    "Utility-scale PV string inverter, 1500 V DC": "1500 V",
    "Battery energy storage system, 1500 V DC": "1500 V",
    "AI data-center 800 V DC power": "800 V",
    "Railway auxiliary converter": "3 kV",
    "Wind turbine converter": "690 V",
}
SLUG = "hv-extra-wide-isolation"


def _new_templates():
    out = {}
    for i, t in enumerate(blocks.templates()):
        title = blocks.title_parts(t)[0]
        if title in NEW:
            out[title] = (i, t)
    return out


def test_new_diagrams_load_with_known_functions_and_a_reinforced_barrier():
    fns = blocks.catalogue()["functions"]
    found = _new_templates()
    assert set(found) == set(NEW)
    for title, (_, t) in found.items():
        assert NEW[title] in t["name"] and t.get("sources") and t["category"] == "Power & isolation"
        used = blocks.template_functions(t)
        assert set(used) <= set(fns), title
        assert {"digital_isolator", "gate_driver", "isolated_amplifier", "isolated_dcdc"} <= set(used), title
        ids = {g["id"] for g in t["groups"]}
        assert all(a in ids and b in ids for a, b, _ in t["links"]), title
        assert len(t["groups"]) <= 10  # modest, like the existing diagrams
        if "Railway" not in title:
            assert any("Reinforced barrier" in g["label"] for g in t["groups"]), title
        for q in t.get("questions") or []:
            assert q["id"] in blocks.question_help(), q["id"]
            for st in q.get("sets") or []:
                assert st["req"] in {r["id"] for r in fns[st["fn"]].get("requirements") or []}, (title, st)
                assert set(st["map"]) <= set(q["choices"]), (title, q["id"])


def test_creepage_requirement_filters_isolators_and_gate_drivers():
    for fn in ("digital_isolator", "gate_driver"):
        req = next(r for r in blocks.catalogue()["functions"][fn]["requirements"] if r["id"] == "creepage")
        assert req["param"] == "creepage_mm" and req["op"] == "gte" and 15 in req["choices"]
        assert blocks.meets({"creepage_mm": 15.0}, req, "15") and not blocks.meets({"creepage_mm": 14.5}, req, "15")
        assert not blocks.meets({"creepage_mm": 8.0}, req, "10")


def test_category_search_finds_the_new_applications():
    def hits(q):
        return [blocks.title_parts(t)[0] for t in blocks.templates() if blocks.search_all(blocks.template_index(t), q)]

    assert hits("rail") == ["Railway auxiliary converter"]  # supply rails ("power rail") do not count
    assert "Railway auxiliary converter" in hits("tram") and "Railway auxiliary converter" in hits("catenary")
    assert "Battery energy storage system, 1500 V DC" in hits("BESS")
    assert "Battery energy storage system, 1500 V DC" in hits("energy storage")
    assert "AI data-center 800 V DC power" in hits("data center power")
    assert "AI data-center 800 V DC power" in hits("800 VDC")
    assert "Wind turbine converter" in hits("wind")
    assert "Utility-scale PV string inverter, 1500 V DC" in hits("solar")
    assert {c["key"] for c in blocks.categories()} >= {"bess", "rail", "datacenter"}


def test_walk_through_offers_the_new_diagrams(client):
    from tests.test_walk import ids, real  # noqa: F401

    names = [blocks.display_name(t) for _, t in _new_templates().values()]
    uses = {u["name"] for u in blocks.function_uses()["digital_isolator"]}
    assert set(names) <= uses


def test_iso7821_report_ranks_the_extra_wide_applications(client):
    page = html.unescape(client.get("/business/reports/iso7821dww-isolation").text)
    heads = [page.index(h) for h in ("1. Adjacent products and technologies", "2. Where else we see opportunities",
                                     "Where extra-wide creepage really matters", "3. Market trend",
                                     "4. Creepage, pollution degree", "Open questions", "Sources")]  # fmt: skip
    assert heads == sorted(heads)
    sec = page[page.index("Where extra-wide creepage really matters") : page.index("3. Market trend")]
    rows = re.findall(r"<tr><td>(\d)</td><td>([^<]+)</td>", sec)
    assert [int(n) for n, _ in rows] == list(range(1, 9))
    assert rows[0][1].startswith("Utility solar") and rows[1][1].startswith("Battery energy storage")
    for t in ("597 GW", "106 GW", "165 GW", "≈15 mm", "/business/reports/hv-extra-wide-isolation"):
        assert t in sec, t
    for i in (i for i, _ in _new_templates().values()):
        assert f"/blocks/new?template={i}" in sec
    assert "pollution degree 2), so 8 mm covers 800 V" in page and "Covered by 8 mm" in sec
    assert "ultra-wide SOIC" in page and "AN1456" in page
    r = rp.report("iso7821dww-isolation")
    assert "hv-extra-wide-isolation" in r["summary"] and "(PD2) 8 mm covers 800 V" in r["summary"]
    assert "hv-extra-wide-isolation" in " ".join(x["text"] for x in rp.learn(r))


def test_extra_wide_case_follows_the_template(client):
    r = rp.report(SLUG)
    assert r["kind"] == "idea" and r["feasibility"] == 2 and prelim.derived_feasibility(SLUG) == 2
    assert r["app_type"] == "Power and charging" and r.get("feasibility_why") and r.get("bu_opener")
    assert [x["age"] for x in rp.learn(r)] == [5, 10, 15, 20, 25]
    c = prelim.raw(SLUG)
    assert c["headline"] == "f-uwb-iso" and c["fn"] == "digital_isolator"
    assert len(c["market_now"]) >= 8 and all(m.get("source") and m.get("conf") for m in c["market_now"])
    assert all(p["entry"] <= p["target"] <= p["premium"] for p in c["prices"]["items"])
    page = html.unescape(client.get(f"/business/reports/{SLUG}").text)
    for t in (
        "What the customer's architecture gains",
        "1. Position against the competition",
        "2. The market today",
        "6. ASP",
        "7. Raising the attach rate",
        "8. Questions to ask",
        "/business/reports/iso7821dww-isolation",
    ):
        assert t in page, t
    assert "$2.60" in page and "$3.80" in page and "AN1456" in page
    listing = client.get("/business/reports").text
    assert f"/business/reports/{SLUG}" in listing
    bg = html.unescape(client.get(f"/business/reports/{SLUG}/background").text)
    for url in (
        "developer.nvidia.com",
        "e2e.ti.com",
        "forum.wolfspeed.com",
        "woodmac.com",
        "gwec.net",
        "unife.org",
        "solarpowereurope.org",
        "ti.com/tool/TIDA-01606",
    ):
        assert url in bg, url


def test_creepage_guide_points_to_the_ranked_applications(client):
    page = html.unescape(client.get("/engineering/creepage_mm").text)
    assert "/business/reports/iso7821dww-isolation#extra-wide" in page and "1500 V DC" in page
