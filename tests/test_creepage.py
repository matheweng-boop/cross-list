"""Creepage and high-voltage applications: the ISO7821DWW report, the creepage specification guide, the systems
library's 800 V requirement and the applications that need more than 8 mm."""

import html
import re
from pathlib import Path
from urllib.parse import quote

from app.config import PROJECT_ROOT
from app.services import blocks, library, prelim
from app.services import price_model as pm
from app.services import reports as rp

# ---- from tests/test_fb_1021_creepage.py -----------------------------------------------------------------------------
# Owner feedback 21 Oct ("especially pollution degrees and requirements"): the ISO7821DWW report answers its creepage
# question, the creepage specification guide carries the pollution-degree / material-group explanation and the
# IEC 60664-1
# table, the systems library states the 800 V requirement, and TI's public ISO7821 list prices are stored.

# basic insulation, material group I (mm): working voltage -> (PD1, PD2, PD3)
TABLE = {400: (1.0, 2.0, 5.0), 500: (1.3, 2.5, 6.3), 630: (1.8, 3.2, 8.0), 800: (2.4, 4.0, 10), 1000: (3.2, 5.0, 12.5)}


def _num(x: float) -> str:
    return f"{x:g}" if x >= 10 else f"{x:.1f}"


def test_creepage_guide_explains_pollution_degree_material_group_and_the_table(client):
    page = html.unescape(client.get("/engineering/creepage_mm").text)
    for term in ("PD1", "PD2", "PD3", "PD4", "CTI", "IIIa", "IIIb", "Reinforced = 2 × basic", "IEC 60747-17",
                 "ISO 6469-3", "IEC 61800-5-1", "IEC 62109-1", "SLUP419", "MINMAX"):  # fmt: skip
        assert term in page, term
    assert "Not modelled" not in page
    for v, (pd1, pd2, pd3) in TABLE.items():
        row = re.search(rf"<tr><td>{v}</td>(.*?)</tr>", page)
        assert row, v
        cells = re.findall(r"<td>([^<]*)</td>", row.group(1))
        assert cells[0] == _num(pd1) and cells[1] == _num(pd2) and cells[4] == _num(pd3), (v, cells)


def test_iso7821dww_report_answers_the_creepage_question(client):
    r = rp.report("iso7821dww-isolation")
    page = html.unescape(client.get("/business/reports/iso7821dww-isolation").text)
    heads = [page.index(h) for h in ("1. Adjacent products and technologies", "2. Where else we see opportunities",
                                     "3. Market trend", "4. Creepage, pollution degree and what 800 V systems need",
                                     "Open questions", "Sources")]  # fmt: skip
    assert heads == sorted(heads)
    assert "8.0 mm at 800 V and 10 mm at 1000 V" in page and "$2.60" in page and "$2.64" in page
    assert "not verified here" not in page and "No new web research" not in page
    opq = page[page.index("Open questions") : page.index("Sources", page.index("Open questions"))]
    assert "What creepage and working voltage do 800 V OEMs require" not in opq
    assert "pollution degree" in r["summary"] and "10 mm at 1000 V" in r["summary"]
    assert "not verified here" not in " ".join(x["text"] for x in rp.learn(r))


def test_library_topic_states_the_800v_requirement():
    t = library.topic("traction_asil_d")
    d11 = next(x for x in t["design_rules"] if x["id"] == "d11")
    assert "8.0 mm at 800 V" in d11["rule"] and "pollution degree 3" in d11["rule"]
    assert not any("not verified here" in q for q in t["open_questions"])
    assert "/engineering/creepage_mm" in {k["href"] for k in library.related_to(d11["rule"])["knowledge"]}
    ids = {s["id"] for s in library.sources()}
    assert {"creepageGuides", "creepageBlocked"} <= ids


def test_ti_iso7821_list_prices():
    lp = pm.list_prices()
    for mpn in ("ISO7821DW", "ISO7821DWR", "ISO7821DWW", "ISO7821DWWR"):
        p = lp[mpn]
        assert p["maker"] == "TI" and p["source"] == "TI store" and str(p["retrieved"]) == "2026-10-21", mpn
        qs = [q for q, _ in p["breaks"]]
        assert qs == [1, 100, 250, 1000] and all(b[1] > 0 for b in p["breaks"]), mpn
    assert lp["ISO7821DWWR"]["breaks"][-1][1] <= lp["ISO7821DWR"]["breaks"][-1][1]  # no premium on reels
    assert lp["ISO7821DWW"]["breaks"][-1][1] > lp["ISO7821DW"]["breaks"][-1][1]  # tubes: extra-wide costs more


def test_creepage_visual_has_pollution_degree():
    js = Path(PROJECT_ROOT / "app/web/static/visuals.js").read_text()
    block = js[js.index("const CREEP =") : js.index('id: "creep"')]
    assert "CREEP3" in block and "[800, 10, 11, 12.5]" in block and "[1000, 3.2]" in block
    assert 'k: "pd"' in js


# ---- from tests/test_fb_1021_hv_apps.py ------------------------------------------------------------------------------
# Owner feedback 21 Oct ("what about potential other applications ... and a block diagram"): the applications that need
# more than 8 mm creepage are ranked in the ISO7821DWW report, five block diagrams are added for them (1500 V solar,
# 1500 V storage, 800 V DC data center, railway auxiliary converter, wind converter), category search finds them, and
# the extra-wide case follows the preliminary-case template.

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
    for _, t in _new_templates().values():  # linked by name, so adding diagrams never moves a link
        assert f"/blocks/new?diagram={quote(t['name'])}" in sec
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
