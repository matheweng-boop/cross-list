"""Research report "Wireless audio in the car" (owner, 28 Oct 2026): it loads in the standard layout, answers the
decision with a confidence, draws the hub-radio-node diagram, runs the depth check per block, is free of site names
and keeps automotive claims in line with the site's AEC-Q rule."""

import html

from app.services import autograde, digest, site_guard
from app.services import reports as rp

SLUG, CASE = "auto-wireless-audio", "auto-clock-tree"


def test_entry_is_a_complete_automotive_report():
    r = rp.report(SLUG)
    assert r and r["kind"] == "report" and r["app_type"] == "Automotive" and r["status"] == "draft"
    assert rp.story_problems(r) == [] and rp.has_background(SLUG) and r["answer"]["conf"] == "low"
    assert CASE in r["see_also"] and any(s.get("case") == CASE for s in r["next_steps"])
    assert [x["age"] for x in rp.learn(r)] == list(rp.LEARN_AGES) and r["learn_links"]
    assert digest.words(r["gist"]) <= digest.MAX_WORDS and 2 <= len(r["abstract"]) <= 3


def test_page_follows_the_owners_order_with_diagram_and_depth_check(client):
    page = html.unescape(client.get(f"/business/reports/{SLUG}").text)
    assert 'class="rpt"' in page and "Bottom line" in page
    order = ["1. Adjacent products and technologies", "Depth check", "2. Gaps and new technology",
             "3. Where else we see opportunities", "4. Market trend and who is doing it", "Risks"]  # fmt: skip
    assert [page.index(h) for h in order] == sorted(page.index(h) for h in order)
    assert "<svg" in page and "Wireless audio link in the car" in page
    for t in ("QPF4239Q", "SKYA21040", "QPQ2254Q", "SKY76360", "SKY76361", "SKY76303", "SKY76206", "Si5332-AM",
              "ACT4751", "LE Audio", "Auracast", "LC3", "A2B", "nothing that fits", "Not enough data",
              "Not Enough Data", "est"):  # fmt: skip
        assert t in page, t
    bg = html.unescape(client.get(f"/business/reports/{SLUG}/background").text)
    assert "Requests made for this report" in bg and "SKY76303-21_PS-206442A.pdf" in bg and "bluetooth.com" in bg


def test_to_confirm_has_written_gists_and_no_site_names():
    for key in (f"report:{SLUG}", f"background:{SLUG}"):
        item = digest.by_key()[key]
        assert not item["auto"] and digest.words(item["gist"]) <= digest.MAX_WORDS
        assert not site_guard.hits(" ".join([item["gist"], *item["abstract"]]))
    for name in (f"{SLUG}.html", f"{SLUG}.background.html"):
        text = (rp.BODIES / name).read_text()
        assert not site_guard.hits(text), name
        assert "qorvo.com/" not in text.replace("store.qorvo.com", "")  # never a qorvo.com source link


def test_automotive_and_consumer_parts_match_the_sites_grade():
    for mpn in ("QPF4239Q", "SKYA21040", "QPQ2254Q", "SKY5A2108", "QPC8019Q", "Si5332A-AM1", "ACT4751MQI101"):
        assert autograde.is_aec(mpn), mpn
    for mpn in ("SKY76303-21", "SKY76360-22", "SKY76361-32", "SKY76206-21", "SKY66407-11", "QM42655", "ACT2861QI501"):
        assert not autograde.is_aec(mpn), mpn
