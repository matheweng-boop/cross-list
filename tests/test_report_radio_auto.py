"""Research report "Car radio: which of our parts fit each block for automotive" (owner, 26 Oct 2026): it loads, answers
the three questions (automotive today, needs improvement, only lacks qualification) plus the gaps, is free of site
names and hands over to the radio-tuner-next case."""

import html

from app.services import autograde, digest, site_guard
from app.services import reports as rp

SLUG, CASE = "radio-auto-fit", "radio-tuner-next"


def test_entry_is_a_complete_car_radio_report():
    r = rp.report(SLUG)
    assert r and r["kind"] == "report" and r["app_type"] == "Car radio" and r["status"] == "draft"
    assert rp.story_problems(r) == [] and rp.has_background(SLUG)
    assert CASE in r["see_also"] and any(s.get("case") == CASE for s in r["next_steps"])
    assert [x["age"] for x in rp.learn(r)] == list(rp.LEARN_AGES)
    assert digest.words(r["gist"]) <= digest.MAX_WORDS and 2 <= len(r["abstract"]) <= 3


def test_page_answers_the_three_questions_in_the_owners_order(client):
    page = html.unescape(client.get(f"/business/reports/{SLUG}").text)
    assert 'class="rpt"' in page and "Bottom line" in page and "Car radio tuner system" in page
    order = ["1. Adjacent products and technologies", "2. (A) Automotive today", "3. (B) Would need improvements",
             "4. (C) Only lacks qualification", "5. Gaps", "6. Where else we see opportunities",
             "7. Market trend"]  # fmt: skip
    assert [page.index(h) for h in order] == sorted(page.index(h) for h in order)
    for t in ("Si47961", "Si46922", "SKYA21001", "QPL6202Q", "ACT4751MQI101", "Si4730", "SKY76206-21", "Si4684",
              "AS183-92LF", "Si510", "TVS / ESD", "PPAP", "Not enough data", "est"):  # fmt: skip
        assert t in page, t
    bg = html.unescape(client.get(f"/business/reports/{SLUG}/background").text)
    assert "Requests made for this report" in bg and "Si4730-31-34-35-D60.pdf" in bg


def test_to_confirm_has_written_gists_and_no_site_names():
    for key in (f"report:{SLUG}", f"background:{SLUG}"):
        item = digest.by_key()[key]
        assert not item["auto"] and digest.words(item["gist"]) <= digest.MAX_WORDS
        assert not site_guard.hits(" ".join([item["gist"], *item["abstract"]]))
    for name in (f"{SLUG}.html", f"{SLUG}.background.html"):
        assert not site_guard.hits((rp.BODIES / name).read_text()), name


def test_groups_match_the_sites_automotive_grade():
    # group A, plus the qualified but 125 kHz buck that sits in group B
    auto = ("Si47961", "Si46922", "Si4624", "SKYA21001", "QPC8010Q", "QPL6202Q", "Si53352A-01AM", "ACT4751MQI101",
            "SKY5A2110", "ACT4529MYH-T0010")  # fmt: skip
    for mpn in auto:
        assert autograde.is_aec(mpn), mpn
    for mpn in ("Si4730", "Si4684", "AS183-92LF", "SKY13374-397LF", "Si510", "SKY76206-21", "QPL7433"):
        assert not autograde.is_aec(mpn), mpn
