"""Owner requests of 23 Oct 2026 (Research & ideas): the hot-swap at 400 / 800 V research topic and the integrated
isolated current-sensing product idea for EV charging."""

import html

from sqlalchemy.orm import Session

from app.db import get_engine
from app.services import library, prelim
from app.services import reports as rp

HOT = "auto-hv-hot-swap"
CS = "iso-current-sense-charging"


def test_both_entries_validate():
    hot, cs = rp.report(HOT), rp.report(CS)
    assert hot and cs, "missing from reports.yaml or no body template"
    assert hot["kind"] == "report" and cs["kind"] == "idea"
    for r in (hot, cs):
        assert r["status"] in rp.STATUSES and r["feasibility"] in rp.FEASIBILITY and r.get("feasibility_why")
        assert r["app_type"] in ("Automotive", "Power and charging")
        assert r.get("question") and r.get("summary") and r.get("sources") and r.get("tags")
        assert [x["age"] for x in rp.learn(r)] == list(rp.LEARN_AGES)
        assert all(k in (r.get("bu_opener") or {}) for k in ("question", "pros", "cons", "vs"))
        assert rp.has_background(r["slug"])
        assert all(rp.report(s) for s in r.get("see_also") or []), r["see_also"]
    # the case follows the business-case layout and links the library topic
    c = prelim.raw(CS)
    assert c["fn"] == "isolated_amplifier" and prelim.headline(c)["id"] == "f-dcdc"
    assert prelim.derived_feasibility(CS) == cs["feasibility"] == 2
    assert {"traction_asil_d"} <= set(c["library"])
    assert any(x["slug"] == CS for x in library.cases_using("traction_asil_d"))


def test_hot_swap_report_renders_and_answers_the_owner(client):
    page = html.unescape(client.get(f"/business/reports/{HOT}").text)
    assert 'class="rpt"' in page
    for t in ("pre-charge", "HVIL", "ISO 6469-3", "ISO 21498", "TPSI3050-Q1", "TPSI2140-Q1", "Si8751", "Si828x",
              "Si89", "800 V DC", "data centre", "est"):  # fmt: skip
        assert t in page, t
    assert "/library/traction_asil_d" in page and f"/business/reports/{CS}" in page
    bg = html.unescape(client.get(f"/business/reports/{HOT}/background").text)
    assert "$2.299" in bg and "$2.896" in bg and "not read" in bg


def test_current_sense_case_renders_with_error_budget_and_prices(client):
    page = html.unescape(client.get(f"/business/reports/{CS}").text)
    assert "Advantages" in page and "AMC3301" in page and "TMCS1123" in page
    bg = html.unescape(client.get(f"/business/reports/{CS}/background").text)
    for t in ("AN1270", "–0.530 / +0.484 %", "$1.65", "3.35 billion", "Si86Px"):
        assert t in bg, t
    with Session(get_engine()) as s:
        case = prelim.case(s, CS)
    assert case["revenue"] and all(v["unit"] for v in case["revenue"])
    listing = client.get("/business/reports").text
    assert f"/business/reports/{HOT}" in listing and f"/business/reports/{CS}" in listing
