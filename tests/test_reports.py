"""Pre-lim product ideas and reports: the list, a report page, filters and unknown slugs."""

import html
import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.db import get_engine
from app.models import IdeaRequest
from app.services import idea_requests as ir
from app.services import inbox, key_apps, library, prelim, tam
from app.services import reports as rp
from app.services import reviews as rv
from app.services.opportunity import evidence


def test_registry_entries_have_a_body():
    items = rp.reports()
    assert items and all(r["kind"] in rp.KINDS and r["status"] in rp.STATUSES for r in items)
    assert [r["date"] for r in items] == sorted((r["date"] for r in items), reverse=True)


def test_list_links_to_each_report(client):
    page = client.get("/business/reports")
    assert page.status_code == 200
    for r in rp.reports():
        assert f'href="/business/reports/{r["slug"]}"' in page.text
    assert client.get("/business/reports?kind=idea").status_code == 200


def test_report_page_and_unknown_slug(client):
    page = client.get("/business/reports/filters-1-11ghz")
    assert page.status_code == 200 and 'class="rpt"' in page.text and "Standalone filter" in page.text
    assert client.get("/business/reports/no-such-report").status_code == 404


def test_question_is_saved_reviewed_and_answered(client):
    url = "/business/reports/filters-1-11ghz"
    r = client.post(f"{url}/ask", data={"text": "Which Trans-Tech ceramic filters cover the S band?"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"].endswith("#questions")
    assert "Which Trans-Tech ceramic filters" in client.get(url).text
    assert client.post(f"{url}/ask", data={"text": "  "}).status_code == 400
    assert client.post("/business/reports/no-such-report/ask", data={"text": "x"}).status_code == 404

    client.post(f"{url}/ask", data={"text": "What Trans-Tech ceramic filters cover S band?"})
    page = client.get("/business/reports/questions")
    assert page.status_code == 200 and "Possible duplicate of" in page.text
    assert "like #" in client.get("/business/reports/questions.txt").text

    qid = int(page.text.split('id="q', 2)[1].split('"')[0])
    r = client.post(f"/business/reports/questions/{qid}", data={"status": "good", "answer": "Two, both 2.4 GHz."},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    assert "Two, both 2.4 GHz." in client.get(url).text
    assert client.post(f"/business/reports/questions/{qid}", data={"status": "bogus"}).status_code == 400
    assert client.post("/business/reports/questions/99999", data={"status": "good"}).status_code == 404


def test_background_page_only_when_present(client):
    has = rp.has_background("filters-1-11ghz")
    assert client.get("/business/reports/filters-1-11ghz/background").status_code == (200 if has else 404)


def test_reports_grouped_by_type_and_feasibility(client):
    from app.services import reports as rp

    ideas = [r for r in rp.reports() if r["kind"] == "idea"]
    assert ideas and all(r["feasibility"] in rp.FEASIBILITY and r.get("feasibility_why") for r in ideas)
    page = client.get("/business/reports").text
    assert "Group by" in page and "Suggested next topics" in page
    assert all(f'<h2 class="rp-group">{t} ' in page for t in {r["app_type"] for r in rp.reports()})
    page = client.get("/business/reports?view=feasibility").text
    assert "Close to the portfolio" in page  # owner, 22 Oct: no separate "Reports" group, every entry is an idea


# ---- from tests/test_fb_1023_research.py -----------------------------------------------------------------------------
# Owner requests of 23 Oct 2026 (Research & ideas): the hot-swap at 400 / 800 V research topic and the integrated
# isolated current-sensing product idea for EV charging.

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
              "Si89", "800 V DC", "data center", "est"):  # fmt: skip
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


# ---- from tests/test_owner_1025_review_answers.py --------------------------------------------------------------------
# Owner's review answers of 25 Oct 2026: TPSI3050-Q1 technology review, integrated temperature sensing as the path
# to product, owner's view on LDO trends, and the elaborated current-sensor TAM estimate (figure unchanged).


def test_tpsi3050_review_loads_and_answers_the_request():
    _, errors, warnings = rv.load_dir(rv.FOLDER)
    assert errors == [] and warnings == []
    r = rv.get("ti-tpsi3050-q1-isolated-switch")
    assert r is not None and r["maker"] == "TI" and r["family"] == "isolated_switch_driver"
    assert [x["slug"] for x in rv.for_part("TPSI3050-Q1")] == ["ti-tpsi3050-q1-isolated-switch"]
    names = " ".join(b["name"] for b in r["concept"]["blocks"])
    assert "transformer" in names and "gate driver" in names  # block diagram walked through
    assert any("Si875" in c["parts"] for c in r["competitors"])  # Skyworks competitive view


def test_temperature_sensor_path_is_integrated_sensing():
    p = evidence("path")["temperature_sensor"]
    assert p["path"] == "variant"
    assert "integrated" in p["base"].lower() and "standalone" in p["base"].lower()
    assert any("sky5a2105" in s.lower() for s in p["sources"]) and "owner" in " ".join(p["sources"]).lower()
    assert any("not pursued" in m for m in p["missing"])


def test_pol_ldo_trend_carries_owner_view_and_keeps_outlook():
    t = evidence("trends")["pol_ldo"]
    assert t["outlook"] == "stable"
    text = " ".join(t["drivers"]) + t["note"]
    assert "owner, 25 oct 2026" in text.lower() and "dissipation" in text and "accuracy" in text


def test_current_sensor_tam_elaborated_figure_unchanged():
    e = next(
        x
        for x in yamlio.load((PROJECT_ROOT / "data/business/tam.yaml").read_text())["estimates"]
        if x["id"] == "current-sensor-mm"
    )
    assert e["usd"] == 3350000000 and e["value"] == "$3.35 B" and e["year"] == 2026
    assert tam.parse_cagr(e["scope"]) == 11.4
    assert "contact-based" in e["scope"] and "not given" in e["scope"]


# ---- from tests/test_idea_expand_1025.py -----------------------------------------------------------------------------
# Owner request 25 Oct 2026: "Expand this idea" under each idea on Research & ideas and on the report page, owner
# only, asked once; it shows in Site data > Requests (kind idea), the Overview count and the daily inbox, and turns into
# "Expanded" with a link once the run has written the "Applications in depth" section.

BTN = "Expand this idea"
HINT = "a deeper look at the applications before a business case"


def _slug() -> str:
    return rp.reports()[0]["slug"]


def _ask(c, slug, note="Focus on robotics", back=""):
    return c.post(f"/manage/ideas/{slug}/expand", data={"note": note, "back": back}, follow_redirects=False)


def test_owner_sees_the_button_with_its_hint_and_a_guest_does_not(owner, make_guest):
    slug = _slug()
    for path in ("/business/reports", f"/business/reports/{slug}"):
        html = owner.get(path).text
        assert BTN in html and HINT in html and f'action="/manage/ideas/{slug}/expand"' in html, path
        assert 'class="dict small" hidden' in html  # dictation, shown by the script where the browser has it
    guest, _ = make_guest()
    for path in ("/business/reports", f"/business/reports/{slug}"):
        r = guest.get(path)
        assert r.status_code == 200 and BTN not in r.text and "/manage/ideas/" not in r.text, path
    assert _ask(guest, slug).status_code == 403  # owner only, never captured as guest input


def test_request_is_stored_once_and_the_button_is_replaced(client, session):
    slug = _slug()
    r = _ask(client, slug, back="/business/reports?view=type")
    assert r.status_code == 303 and r.headers["location"] == f"/business/reports?view=type#exp-{slug}"
    row = session.scalar(select(IdeaRequest).where(IdeaRequest.slug == slug))
    assert row.status == "new" and row.note == "Focus on robotics" and row.title == rp.report(slug)["title"]
    today = datetime.now(UTC).strftime("%d %b %Y")
    for path in ("/business/reports", f"/business/reports/{slug}"):
        html = client.get(path).text
        assert f'action="/manage/ideas/{slug}/expand"' not in html, path
        assert f"Expansion requested {today}" in html and "Note: Focus on robotics" in html, path
    assert _ask(client, slug).status_code == 409  # double click or an old tab
    assert len(session.scalars(select(IdeaRequest)).all()) == 1
    assert _ask(client, "no-such-report").status_code == 404


def test_request_in_requests_tab_overview_and_inbox(client, session):
    slug = _slug()
    _ask(client, slug)
    page = client.get("/manage/requests").text
    assert "Idea expansion</span>" in page and rp.report(slug)["title"] in page and "Focus on robotics" in page
    idea = client.get("/manage/requests?kind=idea").text
    assert 'class="fchip on" href="/manage/requests?kind=idea"' in idea and "Idea expansions <small>1</small>" in idea
    ov = client.get("/manage/overview").text
    assert 'href="/manage/requests?kind=idea"><b>1</b><span>idea to expand</span>' in ov
    text = inbox.collect(session, date.today())
    assert "## Idea expansion requests" in text
    line = next(x for x in text.splitlines() if f"] {slug}:" in x)
    assert "[new]" in line and "note: Focus on robotics" in line
    # the status select on the Requests tab marks it done
    rid = session.scalar(select(IdeaRequest.id))
    assert client.post(f"/manage/ideas/requests/{rid}", data={"status": "bogus"}).status_code == 400
    r = client.post(f"/manage/ideas/requests/{rid}", data={"status": "done"}, follow_redirects=False)
    assert r.status_code == 303
    assert "idea to expand" not in client.get("/manage/overview").text


def test_done_request_shows_expanded_with_the_link(client, session):
    slug = _slug()
    _ask(client, slug)
    row = session.scalar(select(IdeaRequest))
    ir.set_status(session, row, "done")
    row.done_at = datetime(2026, 10, 26, 18, 0, tzinfo=UTC)
    session.commit()
    for path in ("/business/reports", f"/business/reports/{slug}"):
        html = client.get(path).text
        assert "Expanded 26 Oct 2026 · see section" in html, path
        assert f'href="/business/reports/{slug}#applications-in-depth"' in html, path
        assert f'action="/manage/ideas/{slug}/expand"' not in html and "Expansion requested" not in html, path


def test_expanded_date_in_reports_yaml_marks_the_request_done(client, session, monkeypatch):
    """The daily run marks a request done in the repository: `expanded: <date>` on the report's entry."""
    slug = _slug()
    _ask(client, slug)
    real = rp.reports
    monkeypatch.setattr(rp, "reports", lambda: tuple({**r, "expanded": date(2026, 10, 26)} if r["slug"] == slug
                                                     else r for r in real()))  # fmt: skip
    assert "Expanded 26 Oct 2026" in client.get(f"/business/reports/{slug}").text
    session.expire_all()
    assert session.scalar(select(IdeaRequest)).status == "done"
    assert ir.open_count(session) == 0


# ---- from tests/test_storyline_1024.py -------------------------------------------------------------------------------
# Owner, 24 Oct 2026: one storyline through every research report (decision, answer, needed now, what to say
# externally, next steps), shown as the Bottom line under the title, as next steps at the end and as a thread line at
# the
# end of every main section.

ROOT = Path(__file__).resolve().parents[1]
BODIES = ROOT / "app/web/templates/business/reports"
THREAD = '<p class="rpt-thread"><b>For the decision:</b>'


def test_every_report_has_a_complete_storyline():
    rows = rp.reports()
    assert len(rows) >= 14
    for r in rows:
        assert rp.story_problems(r) == [], r["slug"]
        assert r["story_issues"] == []
        assert r["decision"].endswith("?") and r["answer"]["conf"] in rp.CONFIDENCE
        assert all(len(s["why"]) > 20 for s in r["next_steps"]), r["slug"]


def test_story_check_catches_gaps_and_blocked_words():
    bad = {"decision": "Should we?", "answer": {"text": "Yes", "conf": "sure"}, "needed_now": [],
           "say_externally": "Our roadmap has it, made in our own fab; the margin is fine (est).",
           "next_steps": [{"what": "x", "who": "BU"}]}  # fmt: skip
    probs = " ".join(rp.story_problems(bad))
    assert "conf" in probs and "needed_now" in probs and "three steps" in probs
    assert set(rp.blocked_words(bad["say_externally"])) == {"roadmap", "fab", "margin", "est"}
    assert rp.blocked_words("We are interested in the latest test results and fabric.") == []
    assert rp.story_problems({}) and "no decision" in rp.story_problems({})


def test_say_externally_is_safe_to_say():
    for r in rp.reports():
        text = r["say_externally"]
        assert rp.blocked_words(text) == [], (r["slug"], rp.blocked_words(text))
        assert 2 <= text.count(". ") + 1 <= 4, r["slug"]  # two or three sentences
        assert "$" not in text and "Not enough data" not in text, r["slug"]


def test_report_and_case_pairs_share_or_hand_over_the_decision():
    for r in rp.reports():
        cases = [s for s in r.get("see_also") or [] if (rp.report(s) or {}).get("kind") == "idea"]
        if r["kind"] != "report" or not cases:
            continue
        handed = {s.get("case") for s in r["next_steps"]}
        shared = any(rp.report(c)["decision"] == r["decision"] for c in cases)
        assert shared or handed & set(cases), r["slug"]
        assert all(rp.report(c) for c in handed - {None})


def test_every_body_section_ends_with_a_thread_line():
    for r in rp.reports():
        if r["kind"] == "idea":
            c = prelim.raw(r["slug"])
            th = c.get("thread") or {}
            need = {"position", "market", "outlook", "features", "asp", "risks"}
            need |= {"benefit"} if c.get("customer_benefit") else set()
            need |= {"product"} if c.get("product") else set()
            need |= {"questions"} if c.get("questions") else set()
            assert need <= set(th), (r["slug"], need - set(th))
            assert set(th) <= set(rp.CASE_THREADS), r["slug"]
            assert all(10 < len(v) < 200 for v in th.values()), r["slug"]
            continue
        body = (BODIES / f"{r['slug']}.html").read_text()
        sections = re.split(r"<h2>", body)[1:]
        assert sections, r["slug"]
        for sec in sections:
            if sec.startswith("Sources"):
                assert THREAD not in sec
                continue
            assert THREAD in sec, (r["slug"], sec[:40])


def test_bottom_line_renders_on_every_report_and_the_list(client):
    for r in rp.reports():
        page = html.unescape(client.get(f"/business/reports/{r['slug']}").text)
        assert 'class="rpt-bl"' in page and "Bottom line" in page, r["slug"]
        assert r["decision"] in page and r["answer"]["text"] in page and r["say_externally"] in page
        assert all(s["what"] in page and s["who"] in page for s in r["next_steps"])
        # under the title, above the summary box; the checklist comes after the body and before the sources
        assert page.index("<h1>") < page.index('class="rpt-bl"') < page.index('class="brief"'), r["slug"]
        assert page.index('class="brief"') < page.index('class="rpt-end"'), r["slug"]
        if "<h2>Sources</h2>" in page:
            assert page.index('class="rpt-end"') < page.index("<h2>Sources</h2>")
        assert page.count('class="rpt-thread"') >= 4, r["slug"]
    listing = html.unescape(client.get("/business/reports").text)
    for r in rp.reports():
        assert f"<b>Decision:</b> {r['decision']}" in listing


def test_hot_swap_storyline_is_the_owners_example(client):
    r = rp.report("auto-hv-hot-swap")
    assert "reinforced successor to Si875x" in r["decision"]
    assert any(s.get("case") == "iso-current-sense-charging" for s in r["next_steps"])
    page = client.get("/business/reports/auto-hv-hot-swap").text
    assert 'href="/business/reports/iso-current-sense-charging">→ the case' in page


@pytest.mark.browser
def test_report_pages_fit_390px(client, chromium):
    """Uses the session's shared browser (tests/conftest.py): a second Playwright in one run is refused."""

    def serve(route):
        url = route.request.url.replace("http://bizdev.test", "")
        res = client.get(url)
        route.fulfill(status=res.status_code, body=res.content,
                      headers={"content-type": res.headers.get("content-type", "text/html")})  # fmt: skip

    page = chromium.new_page(viewport={"width": 390, "height": 900})
    try:
        page.route("http://bizdev.test/**", serve)
        for r in rp.reports():
            page.goto(f"http://bizdev.test/business/reports/{r['slug']}")
            box = page.locator(".rpt-bl").bounding_box()
            assert box and box["x"] >= 0 and box["x"] + box["width"] <= 390, r["slug"]
            end = page.locator(".rpt-end").bounding_box()
            assert end and end["x"] + end["width"] <= 390, r["slug"]
            wide = page.evaluate("document.documentElement.scrollWidth")
            assert wide <= 390, (r["slug"], wide)
    finally:
        page.close()


# ---- from tests/test_fb_1025_u.py ------------------------------------------------------------------------------------
# Owner's comments of 24 Oct 2026: the 1–11 GHz filter report explores wideband filters; the eFuse bigger picture
# lists its key applications with library diagrams; the ACT88321 concept item 0 is corrected; SKY5A2105 is reviewed.
BODY = ROOT / "app/web/templates/business/reports/filters-1-11ghz.html"


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
