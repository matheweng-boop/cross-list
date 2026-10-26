"""Research report "Wi-Fi 6, 6E and 7 in cars, Wi-Fi and antenna synergies, and the gaps" (owner, 26 Oct 2026):
it loads, has a short written gist for To confirm, is free of site names and builds on the auto-wifi7-fem case."""

import html

from app.services import autograde, digest, site_guard
from app.services import reports as rp

SLUG, CASE = "auto-wifi-antenna", "auto-wifi7-fem"


def test_entry_is_a_complete_report_next_to_the_case():
    r = rp.report(SLUG)
    assert r and r["kind"] == "report" and r["app_type"] == "Automotive" and r["status"] in rp.STATUSES
    assert rp.story_problems(r) == [] and rp.has_background(SLUG)
    assert CASE in r["see_also"] and any(s.get("case") == CASE for s in r["next_steps"])
    assert [x["age"] for x in rp.learn(r)] == list(rp.LEARN_AGES)
    assert digest.words(r["gist"]) <= digest.MAX_WORDS and 2 <= len(r["abstract"]) <= 3


def test_page_renders_the_layout_gaps_and_case_link(client):
    page = html.unescape(client.get(f"/business/reports/{SLUG}").text)
    assert 'class="rpt"' in page and "Bottom line" in page
    order = ["1. Adjacent products and technologies", "2. Gaps and new technology",
             "3. Where else we see opportunities", "4. Future growth topics", "5. Market trend"]  # fmt: skip
    assert [page.index(h) for h in order] == sorted(page.index(h) for h in order)
    for t in ("QPF4239Q", "SKY5A1008", "SKY85929-11", "802.11bn", "802.11bf", "Found in 0 public reference designs",
              "multi-link", "UWB channel 5", "est"):  # fmt: skip
        assert t in page, t
    assert f'href="/business/reports/{CASE}"' in page and "/library/roof_coexistence" in page
    bg = html.unescape(client.get(f"/business/reports/{SLUG}/background").text)
    assert "ieee802.org" in bg and "solution.murata.com" in bg and "Requests made for this report" in bg


def test_to_confirm_has_written_gists_and_no_site_names():
    for key in (f"report:{SLUG}", f"background:{SLUG}"):
        item = digest.by_key()[key]
        assert not item["auto"] and digest.words(item["gist"]) <= digest.MAX_WORDS
        assert not site_guard.hits(" ".join([item["gist"], *item["abstract"]]))
    for name in (f"{SLUG}.html", f"{SLUG}.background.html"):
        assert not site_guard.hits((rp.BODIES / name).read_text()), name


def test_parts_named_as_automotive_are_aec_q_on_the_site():
    for mpn in ("QPF4239Q", "SKYA21040", "SKY5A1006", "SKY5A1008", "SKY5A2108", "QPC8019Q", "QPQ2254Q"):
        assert autograde.is_aec(mpn), mpn
    for mpn in ("SKY85639-11", "SKY85509-11", "QPF4659"):  # consumer Wi-Fi 7 FEMs: the gap
        assert not autograde.is_aec(mpn), mpn
