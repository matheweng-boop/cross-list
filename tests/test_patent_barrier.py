"""Patent barrier in the priority score (owner, 6 Nov 2026): "some metric between similarity to our technology, distance
to our technology, and difficulty in recreating that technology", from US family counts of ours and the strongest
competitors per technology platform; a signed adjustment of at most ± 6 points replaced the depth-based bonus. Also the
portfolio totals, the ex-Silicon Labs I&A column and the eight areas added that day."""

from urllib.parse import urlparse

import pytest

from app.services import patents
from app.services import priority as pr

try:  # the browser fixture (a tab on the live app, checked at 390 px afterwards); skipped without Playwright
    from tests.test_browser import page  # noqa: F401
except pytest.skip.Exception:
    pass

NEW = ("pcie_timing", "isolated_sensing", "desat_gate_drivers", "ntn", "gnss_antijam", "motor_hvac", "robotics",
       "efuse")  # fmt: skip


def rivals(*counts, recent=0.0):
    """Competitors a, b, c ... with these 5-year counts and this share filed in the last 3 years."""
    return {chr(97 + i): {"last5": n, "last3": round(n * recent)} for i, n in enumerate(counts)}


# ---- the maths ----------------------------------------------------------------------------------------------------
def test_parity_and_middling_difficulty_give_no_adjustment():
    cfg = pr.config()["patents"]
    assert cfg["similarity_weight"] + cfg["difficulty_weight"] == pytest.approx(1.0)
    d = cfg["difficulty"]
    assert d["density"] + d["crowding"] + d["recency"] == pytest.approx(1.0)
    assert pr.barrier_points(50, 4) == 0.0 and pr.barrier_points(50, None) == 0.0  # barrier 50 -> 0
    p = pr.barrier_parts(40, rivals(40))  # parity
    assert p["similarity"] == 0.5 and p["lead"] == "a" and p["lead_n"] == 40


def test_dominance_gives_a_penalty_and_the_cap_holds(monkeypatch):
    weak = pr.barrier_parts(5, rivals(400, 300, 250, 220, recent=0.6))  # they dominate, crowded and recent
    assert weak["similarity"] < 0.05 and weak["crowded"] == 4 and weak["difficulty"] == 1.0
    assert weak["barrier"] >= 95 and pr.barrier_points(weak["barrier"], 4) <= -5.5
    strong = pr.barrier_parts(200, rivals(10, 2))  # we dominate, a thin field
    assert strong["barrier"] <= 25 and pr.barrier_points(strong["barrier"], 4) > 2
    for b in range(0, 101, 5):
        for dist in (0, 1, 2, 3, 4, None):
            assert abs(pr.barrier_points(b, dist)) <= pr.config()["patents"]["cap"]
    monkeypatch.setitem(pr.config()["patents"], "points", 60)  # a big weight still stops at the cap
    assert pr.barrier_points(100, 4) == -6.0 and pr.barrier_points(0, 4) == 6.0


def test_part_similarity_lowers_the_barrier():
    them = rivals(100, 30)
    few, many = pr.barrier_parts(10, them), pr.barrier_parts(150, them)
    assert few["similarity"] < many["similarity"] and few["difficulty"] == many["difficulty"]
    assert many["barrier"] < few["barrier"]
    assert pr.barrier_parts(0, rivals(0, 0))["similarity"] == 0.5  # no data either side: parity, not a penalty


def test_part_difficulty_density_crowding_recency_and_process():
    base = pr.barrier_parts(50, rivals(100, 10))
    denser = pr.barrier_parts(50, rivals(300, 10))
    assert denser["density"] > base["density"]
    crowded = pr.barrier_parts(50, rivals(100, 60, 55))
    assert crowded["crowded"] == 3 and crowded["crowding"] == 1.0 and crowded["difficulty"] > base["difficulty"]
    recent = pr.barrier_parts(50, rivals(100, 10, recent=0.6))
    assert recent["recency"] == 1.0 and recent["barrier"] > base["barrier"]
    gap = pr.barrier_parts(50, rivals(100, 10), process_gap="SiC MOSFET process")
    flag = pr.config()["patents"]["difficulty"]["process_gap"]
    assert gap["difficulty"] == pytest.approx(min(1.0, base["difficulty"] + flag), abs=1e-3)
    # the process flag comes from capabilities.yaml (a divested line), not from a guess
    assert "power_fets" in pr.process_gaps() and "SiC" in pr.process_gaps()["power_fets"]
    assert "power_amplifier" not in pr.process_gaps()  # GaAs HBT is ours


def test_part_distance_only_scales_the_effect():
    """Distance is already in likeliness (feasibility) and the Opportunity score, so it never changes the barrier, only
    how much it moves the priority: more when we are far."""
    sc = [pr.distance_scale(d) for d in (0, 1, 2, 3, 4)]
    assert sc == sorted(sc) and sc[-1] == 1.0
    assert pr.distance_scale(None) == pr.config()["patents"]["distance_scale"]["none"]
    assert abs(pr.barrier_points(80, 4)) > abs(pr.barrier_points(80, 0))
    eff = [pr.patent_effect("power_amplifier", d) for d in (0, 4)]
    assert eff[0]["barrier"] == eff[1]["barrier"] and abs(eff[1]["points"]) >= abs(eff[0]["points"])
    assert "far from our process" in eff[1]["words"]["distance"] and "near" in eff[0]["words"]["distance"]


def test_the_line_in_plain_words():
    e = pr.patent_effect("filter_saw_baw", 3)
    assert e["platform"] == "baw" and e["line"].startswith("Patents (US, 5 years): ours ")
    assert "→ barrier " in e["line"] and e["line"].endswith(f"{e['points']:+g}")
    assert any(w in e["words"]["similarity"] for w in ("similar to our BAW filters work", "little of ours"))
    assert e["words"]["difficulty"].split(" (")[0] in ("hard to recreate", "moderate to recreate", "easy to recreate")
    assert "not legal advice" in e["note"] and e["date"] == "2026-11-06"
    assert pr.patent_effect("pol_ldo") is None and pr.patent_effect("no_such_function") is None


def test_the_score_carries_the_adjustment_and_no_longer_the_bonus():
    row = {"fn": "filter_saw_baw", "key": "filter_saw_baw", "label": "x", "reach": 4, "background": 0,
           "feasibility": 3, "distance": 3, "gap_type": "true_gap"}  # fmt: skip
    p = pr.annotate([row])[0]["priority"]
    assert p["L"] == pytest.approx(0.4)  # 0.3 + 0.1 for a platform of ours, no patent bonus in L any more
    assert p["score"] == pytest.approx(max(0, min(100, p["base"] + p["adj"])), abs=0.05)
    assert p["adj"] == p["patent"]["points"] and "(patents) = " in pr.example({"priority": p})
    assert "patent_bonus" not in pr.config()["likeliness"]


# ---- the data files -----------------------------------------------------------------------------------------------
def test_new_areas_in_the_platform_format():
    for k in NEW:
        e = patents.platforms()[k]
        for f in ("label", "query", "count", "skyworks", "qorvo", "depth", "leader", "trend", "date", "check"):
            assert e.get(f) is not None, (k, f)
        assert ".aanm." in e["query"] and ".ti,ab,clm." in e["query"] and str(e["date"]) == "2026-11-06"
        assert sum(e["trend"]["skyworks"]) == e["skyworks"] and sum(e["trend"]["qorvo"]) == e["qorvo"]
        chk = e["check"]
        assert chk["status"] in ("confirmed", "partly") and chk["evidence"], k
        if e["count"]:  # at least one example spot-checked: record found, title and assignee, and the PDF
            assert any("record found" in x and "title matches" in x for x in chk["evidence"]), k
            assert any("application/pdf" in x for x in chk["evidence"]), k
        for co in patents.COMPANIES:
            for x in e["examples"][co]:
                assert x["id"].startswith("US") and x["title"] and urlparse(x["url"]).hostname in patents.USPTO_HOSTS
    assert "gate_driver" in patents.platforms()["desat_gate_drivers"]["functions"]
    assert "gate_driver" not in patents.platforms()["isolation"]["functions"]  # the specific area wins


def test_portfolio_totals_per_year():
    text = patents.FILE.read_text()  # one block each (a repeated key would silently win in YAML)
    assert text.count("\nportfolio:\n") == 1 and text.count("\nplatforms:\n") == 1
    pf = patents.portfolio()
    assert str(pf["searched"]) == "2026-11-06" and ".aanm." in pf["query_skyworks"]
    for co in ("skyworks", "qorvo"):
        t = pf[co]
        assert t["total"] > 1000 and sum(t["trend"]) == t["total"]
        assert sum(t["per_year"][y] for y in pf["years"]) <= t["total"]
        assert set(pf["years"]) <= set(t["per_year"])


def test_ex_silicon_labs_column_kept_apart():
    for k in ("isolation", "timing"):
        x = patents.platforms()[k]["ex_silabs"]
        assert x["label"] == "ex-Silicon Labs I&A (likely transferred to Skyworks)" and x["count"] >= 0
        assert sum(x["trend"]) == x["count"] and "likely" in x["note"]
        assert all("@ad<20210701" in q and "silicon laboratories" in q for q in x["queries"])
    iso = patents.platforms()["isolation"]
    assert iso["skyworks"] + iso["qorvo"] >= iso["count"]  # not merged into the Skyworks count


def test_competitor_file_format():
    c = patents.competitors()
    assert str(c["searched"]) == "2026-11-06" and "not legal advice" in c["disclaimer"] and c["window"] == "2021-2026"
    for k, e in c["platforms"].items():
        assert k in patents.platforms(), k
        assert 1 <= len(e["competitors"]) <= 4 and set(e["competitors"]) <= set(c["names"]), k
        assert "@ad>=20200101" in e["query"] and ".aanm." in e["query"], k
        for v in e["competitors"].values():
            assert v["last5"] >= v["last3"] >= 0 and v["last5"] == v["last3"] + v["prior3"]
        o = e["ours"]
        assert o["last5"] == o["last3"] + o["prior3"]
    for k, p in patents.platforms().items():  # every platform with a function has competitor counts
        if p.get("functions"):
            assert k in c["platforms"], k


# ---- the pages ----------------------------------------------------------------------------------------------------
def test_method_page_shows_the_counts(client):
    html = client.get("/business/method").text
    assert 'id="patents"' in html and "Whole US portfolio" in html
    pf = patents.portfolio()
    assert f"Skyworks <b>{pf['skyworks']['total']}</b>" in html and f"Qorvo group <b>{pf['qorvo']['total']}</b>" in html
    assert "ex-Silicon Labs I&amp;A (likely transferred to Skyworks)" in html
    row = next(r for r in pr.patent_table() if r["key"] == "baw")
    name, n = row["rivals"][0]
    assert f"{name} {n}" in html and "BAW filters" in html
    assert "Distance to our technology" in html and "not legal advice" in html


def test_gap_card_says_why(client):
    html = client.get("/business/opportunities?show=all").text
    assert 'class="pt-why small"' in html and "Patents: barrier " in html


@pytest.mark.browser
def test_browser_gap_card_patent_reason(page):  # noqa: F811
    """One gap card's patent reason opens with a tap (no hover on the iPad) and fits a phone."""
    pytest.importorskip("playwright.sync_api")
    from tests.test_browser import go

    go(page, "/business/opportunities?show=all")
    why = page.locator("article.csg-card details.pt-why").first
    why.locator("summary").click()
    assert why.get_by_text("Patents (US, 5 years): ours").is_visible()


@pytest.mark.browser
def test_browser_method_patent_tables_fit_a_phone(page):  # noqa: F811
    """The method page's patent tables (portfolio per year, competitors per platform) stay inside 390 px."""
    pytest.importorskip("playwright.sync_api")
    from tests.test_browser import go

    go(page, "/business/method#patents")
    assert page.locator("#patents").is_visible() and page.locator("table.pt-comp").count() == 1
