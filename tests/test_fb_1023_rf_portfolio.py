"""Owner feedback 23 Oct 2026: the RF coverage by band table (smaller type, colour code, key) and the Skyworks + Qorvo
"Which line to offer" section (bigger parts, room above "Used in", similar or further design effort)."""

import re
from pathlib import Path

from app.services import portfolio as pf

CSS = (Path(__file__).resolve().parent.parent / "app" / "web" / "static" / "app.css").read_text()


def _contrast(fg: str, bg: str) -> float:
    def lum(h: str) -> float:
        c = [int(h.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    a, b = sorted((lum(fg), lum(bg)), reverse=True)
    return (a + 0.05) / (b + 0.05)


def _rule(selector: str) -> str:
    m = re.search(re.escape(selector) + r"(?![\w-])[^{]*\{([^}]*)\}", CSS)
    assert m, selector
    return m.group(1)


def test_rf_coverage_table_colour_code_and_key(client):
    html = client.get("/business/rf-coverage").text
    assert 'class="rf-matrix stack-table rf-small"' in html  # smaller, no-wrap type on this table only
    assert html.count("rf-small") == 1
    key = html.split('class="rf-key small"')[1].split("</div>")[0]
    for cls in ("rf-ok", "rf-risk", "rf-r", "rf-need", "rf-comp", "rf-none"):
        assert cls in key
    assert "struck through" in key and "applications that need it" in key and "competitor makers" in key
    # active green, NRND grey and struck through (not red), applications solid blue, competitors solid red
    assert "line-through" in _rule(".rf-small .rf-r") and "#595959" in _rule(".rf-small .rf-r")
    pairs = [("#14532d", "#cdebd5"), ("#595959", "#cdebd5"), ("#ffffff", "#1d4ed8"), ("#ffffff", "#b91c1c"),
             ("#4a4a4a", "#ececec")]  # fmt: skip
    assert "#1d4ed8" in _rule(".rf-small .rf-need") and "#b91c1c" in _rule(".rf-small .rf-comp")
    assert all(_contrast(f, b) >= 4.5 for f, b in pairs)
    assert "white-space: nowrap !important" in _rule("  .stack-table.rf-matrix.rf-small th")


def test_rf_coverage_slot_status_marks(client):
    from app.services import rf_coverage as rf

    p = next(p for p in rf.parts() if p["bands"] and p["functions"])
    html = client.get("/business/rf-coverage", params={"fn": p["functions"][0], "band": p["bands"][0]}).text
    assert 'class="rf-st-ok"' in html or 'class="rf-st-risk"' in html


def test_pick_matches_rule():
    m = pf.pick_matches()
    wifi = m["wifi_fem"]
    assert wifi["verdict"] == "similar" and all(p["similar"] for p in wifi["pairs"])
    assert {p["qorvo"]["mpn"] for p in wifi["pairs"]} >= {"QPF4216", "QPF4659"}  # same band picked, 2.4 / 6 GHz
    iot = m["iot_short_range"]  # front-end modules against SoCs: extra parts around the other line's part
    assert iot["verdict"] == "effort" and all("different function" in p["reasons"][0] for p in iot["pairs"])
    lna = {p["skyworks"]["mpn"]: p for p in m["lna_sub6_gnss"]["pairs"]}
    assert not lna["SKY55951-11"]["similar"] and "different band" in lna["SKY55951-11"]["reasons"][0]
    assert "isolation" not in m and "beamformers_mmwave" not in m  # one line only: nothing to pair
    assert pf._same_job("rf_frontend", "wifi_fem") and not pf._same_job("lna", "power_amplifier")
    assert pf._ghz({"Frequency Min (MHz)": "2.4", "Frequency Max (MHz)": "2.5"}, "") == (2.4, 2.5)
    assert pf._supply({"Supply Voltage (V)": "2.85-4.5", "Supply Current Typ (mA)": "80"}) == (2.85, 4.5)


def test_portfolio_offer_section(client):
    html = client.get("/portfolio").text
    pick = html.split('id="pick"')[1].split('id="categories"')[0]
    assert 'class="badge pf-part"' in pick and 'class="small muted pf-used">Used in:' in pick
    assert "Further design effort required" in pick and 'class="pf-sim">Similar' in pick
    assert pf.MATCH_RULE in pick.replace("&#39;", "'") and pf.MATCH_RULE.startswith("est:")
    assert pick.index('class="pf-match small"') < pick.index("pf-used")
    assert "font-size: .95rem" in _rule(".pf-parts .badge.pf-part") and "margin-top: 1rem" in _rule(".pf-used")
    assert _contrast("#ffffff", "#1c6b3a") >= 4.5 and _contrast("#ffffff", "#9a3412") >= 4.5
