"""Research report "Charging in and around the car" (owner, 28 Oct 2026: full charging solutions with Qorvo power ICs,
DC-DC with USB-C for cars, our own PD controller): it loads in the standard layout, answers the three questions with
a confidence, runs the depth check per block with the path data, links the related reports and Part knowledge, is
free of site names and keeps automotive claims in line with the site's AEC-Q rule."""

import html

from app.services import autograde, digest, site_guard
from app.services import reports as rp

SLUG, CASE = "auto-charging-power", "iso-current-sense-charging"


def test_entry_is_a_complete_automotive_report():
    r = rp.report(SLUG)
    assert r and r["kind"] == "report" and r["app_type"] == "Automotive" and r["status"] == "draft"
    assert rp.story_problems(r) == [] and rp.has_background(SLUG) and r["answer"]["conf"] in rp.CONFIDENCE
    assert {"auto-hv-hot-swap", CASE, "hv-extra-wide-isolation"} <= set(r["see_also"])
    assert any(s.get("case") == CASE for s in r["next_steps"])
    assert all(t in r["answer"]["text"] for t in ("(a)", "(b)", "(c)"))
    assert digest.words(r["gist"]) <= digest.MAX_WORDS and 2 <= len(r["abstract"]) <= 3


def test_page_answers_the_three_questions_with_depth_check_and_links(client):
    page = html.unescape(client.get(f"/business/reports/{SLUG}").text)
    order = ["1. Adjacent products and technologies", "Depth check", "2. Gaps and new technology",
             "3. Where else we see opportunities", "4. Market trend", "Answers to the three questions",
             "Risks"]  # fmt: skip
    assert [page.index(h) for h in order] == sorted(page.index(h) for h in order)
    assert "<svg" in page and "Car USB-C charging port" in page
    for t in ("ACT4751M", "ACT4752", "ACT4529M", "ACT5101", "ACT2861", "PAC25140", "Si8239x", "Si828x", "Si875",
              "TPS25772-Q1", "CCG7D", "RTQ7880", "Weltrend", "usb_pd_controller", "pre_regulator", "power_fets",
              "onsemi", "Not Enough Data", "est"):  # fmt: skip
        assert t in page, t
    for href in ("/reviews/how/gatedriver", "/reviews/how/currentsense", "/business/reports/auto-hv-hot-swap",
                 f"/business/reports/{CASE}", "/business/reports/hv-extra-wide-isolation"):  # fmt: skip
        assert f'href="{href}"' in page, href
        assert client.get(href).status_code == 200, href
    bg = html.unescape(client.get(f"/business/reports/{SLUG}/background").text)
    assert "Requests made for this report" in bg and "TPS25762-Q1" in bg and "usb.org" in bg


def test_no_site_names_and_no_qorvo_links():
    for key in (f"report:{SLUG}", f"background:{SLUG}"):
        item = digest.by_key()[key]
        assert not item["auto"] and not site_guard.hits(" ".join([item["gist"], *item["abstract"]]))
    for name in (f"{SLUG}.html", f"{SLUG}.background.html"):
        text = (rp.BODIES / name).read_text()
        assert not site_guard.hits(text), name
        assert "qorvo.com/" not in text


def test_part_grades_match_the_sites_rule():
    for mpn in ("ACT4751MQI101", "ACT4529MYH-T0010", "Si8751AB-AS"):
        assert autograde.is_aec(mpn), mpn
    for mpn in ("ACT4752QI101-T", "ACT5101QI102-T", "ACT2861QI501", "PAC25140", "ACT4910QW121-T"):
        assert not autograde.is_aec(mpn), mpn
