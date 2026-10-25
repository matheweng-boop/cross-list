"""Owner's comments of 24 Oct 2026: the 1–11 GHz filter report explores wideband filters; the eFuse bigger picture
lists its key applications with library diagrams; the ACT88321 concept item 0 is corrected; SKY5A2105 is reviewed."""

import html
import re
from pathlib import Path

from app.services import key_apps
from app.services import reports as rp
from app.services import reviews as rv

ROOT = Path(__file__).resolve().parents[1]
BODY = ROOT / "app/web/templates/business/reports/filters-1-11ghz.html"
THREAD = '<p class="rpt-thread"><b>For the decision:</b>'


# ---- 1. wideband filters in the filter report ------------------------------------------------------------------------
def test_filter_report_has_a_wideband_section_with_its_thread_line():
    body = BODY.read_text()
    sec = next(s for s in re.split(r"<h2>", body)[1:] if s.startswith("2. Wideband filters"))
    for h in ("Where wideband or tunable filtering is needed", "Technologies and their trade-offs", "Who makes them",
              "Where Skyworks + Qorvo stand", "What a wideband product could be"):  # fmt: skip
        assert f"<h3>{h}</h3>" in sec, h
    for need in ("Software-defined", "Test and measurement", "SIGINT", "Satellite user terminals", "UWB",
                 "Wi-Fi 6E / 7", "n77", "anti-jam", "Wideband receivers"):  # fmt: skip
        assert need.lower() in sec.lower(), need
    for tech in ("LTCC", "Ceramic", "Cavity", "BAW", "SAW", "coupling coefficient", "XBAR", "Tunable",
                 "Switched filter bank", "IPD"):  # fmt: skip
        assert tech in sec, tech
    for maker in ("Mini-Circuits", "Knowles", "Murata", "Anatech"):
        assert maker in sec, maker
    assert "Trans-Tech" in sec and "QPB1055" in sec and "est" in sec
    assert sec.count(THREAD) == 1 and "wideband" in sec.split(THREAD)[1].lower()
    # sections were renumbered behind the new one
    assert "<h2>3. Where else we see opportunities</h2>" in body and "<h2>4. Market trend</h2>" in body


def test_filter_report_storyline_follows_the_wideband_rework(client):
    r = rp.report("filters-1-11ghz")
    assert rp.story_problems(r) == [] and "wideband" in r["decision"].lower() and r["decision"].endswith("?")
    assert "est" in r["answer"]["text"] and "wideband" in r["answer"]["text"].lower()
    assert "wideband" in r["tags"] and "wide passbands" in r["say_externally"]
    assert any("passband" in s["what"] for s in r["next_steps"])
    page = html.unescape(client.get("/business/reports/filters-1-11ghz").text)
    assert "Wideband filters: where they are needed" in page and page.count('class="rpt-thread"') >= 5
    bg = client.get("/business/reports/filters-1-11ghz/background")
    assert bg.status_code == 200 and "Wideband filters: detail" in bg.text and "BFCN-5100+" in bg.text


# ---- 2. eFuse key applications ---------------------------------------------------------------------------------------
def test_efuse_key_applications_count_library_diagrams():
    d = key_apps.for_function("efuse_hotswap")
    by = {a["key"]: a for a in d["applications"]}
    assert set(by) == {"automotive", "drones", "datacenter", "industrial", "telecom", "consumer"}
    for a in by.values():
        assert a["n"] == len(a["diagrams"]) > 0 and a["volts"] and a["amps"] and a["why"], a["key"]
        assert all(x["href"].startswith("/blocks/new?template=") for x in a["diagrams"])
    assert any("Drone battery" in x["name"] for x in by["drones"]["diagrams"])
    assert any("power distribution box" in x["name"] for x in by["automotive"]["diagrams"])
    placed = {x["i"] for a in by.values() for x in a["diagrams"]} | {x["i"] for x in d["other"]}
    assert len(placed) == d["n_using"]
    assert key_apps.for_function("pol_ldo") is None


def test_efuse_bigger_picture_shows_key_applications_with_links(client):
    page = html.unescape(client.get("/business/evidence/efuse_hotswap").text)
    assert 'id="key-apps"' in page and "Key applications" in page
    for t in ("Automotive", "Drones", "Data centre", "Industrial", "Telecom", "Consumer", "Zonal", "Anti-spark",
              "USB PD", "−48 V", "800 V DC"):  # fmt: skip
        assert t in page, t
    assert 'href="/business/reports/auto-hv-hot-swap"' in page and 'href="/library/drone_flight_power"' in page
    assert page.count('href="/blocks/new?template=') >= 20
    assert 'id="key-apps"' not in client.get("/business/evidence/pol_ldo").text


# ---- 3. ACT88321 concept item 0 ------------------------------------------------------------------------------------
def test_act88321_buck1_item_is_corrected_in_place():
    r = rv.get("qorvo-act88321-pmic")
    b0 = r["concept"]["blocks"][0]
    assert b0["name"].startswith("Buck1") and "COT" in b0["what"] and "3.1-5.8 A" in b0["what"]
    assert "+/-25 %" in b0["what"] and "fixed at power-up" in b0["name"]
    assert r["concept"]["blocks"][1]["name"].startswith("Buck2")  # order kept, so review keys stay valid
    assert "concept.0" in rv.item_keys(r) and "marked wrong on 24 Oct 2026" in r["open_questions"][-1]


# ---- 4. SKY5A2105 technology review --------------------------------------------------------------------------------
def test_sky5a2105_review_validates_and_answers_the_request(client, session):
    errs, warns = rv.problems()
    assert not [e for e in errs + warns if "sky5a2105" in e]
    r = rv.get("skyworks-sky5a2105-v2x-fem")
    assert r and r["parts"] == ["SKY5A2105"] and r["app_area"] == "Automotive" and r["family"] == "v2x_fem"
    assert len(r["applications"]) == 4 and len(r["key_features"]) >= 5
    assert any("differentiator" in f["why_it_matters"] for f in r["key_features"])
    assert client.get("/reviews/skyworks-sky5a2105-v2x-fem").status_code == 200
    client.post("/reviews/request", data={"mpn": "SKY5A2105", "question": "Features and differentiator",
                                          "application": "Automotive"})  # fmt: skip
    e = next(e for e in rv.requests(session) if e["row"].mpn == "SKY5A2105")
    assert e["status"] == "done" and e["review"]["slug"] == "skyworks-sky5a2105-v2x-fem"
