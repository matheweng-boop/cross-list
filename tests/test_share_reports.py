"""Shareable > Skyworks + Qorvo synergies and Automotive (owner, 25 Oct 2026): two management reports that reuse the
Technology overview's editing, storage, word check, header, watermark and print CSS; counts shown rounded; a combined
PDF of the selected reports. Printed page counts are checked in tests/test_browser.py (Chromium)."""

import re
from html import unescape

import pytest

from app.services import share_reports as sr
from app.services import tech_overview as to
from app.services import tech_overview_edit as te
from app.services.text import round_count, rounded_count_text

SYN, AUTO, PACK = "/shareable/synergies", "/shareable/automotive", "/shareable/pack"


def body_text(html: str, marker: str) -> str:
    body = html.split(marker, 1)[1].split("</main>", 1)[0]
    body = re.sub(r"<(script|style|template)\b.*?</\1>", " ", body, flags=re.S)
    body = re.sub(r'<span class="to-wm-tag">.*?</span>', " ", body)
    return unescape(re.sub(r"<[^>]+>", " ", body))


@pytest.mark.parametrize("n, shown", [(4132, "4,000+"), (1955, "1,500+"), (523, "500+"), (47, "40+"), (12, "12"),
                                      (1000, "1,000+"), (100, "100+"), (20, "20+"), (19, "19"), (0, "0")])  # fmt: skip
def test_round_count(n, shown):
    assert round_count(n) == shown
    assert rounded_count_text(f"{n:,}") == shown


def test_specs_are_never_rounded():
    for spec in ("up to 5 kVrms", "to 40 GHz", "up to 1,000 W", "jitter from 69 fs", "–", "SKY5A5003", "4.5"):
        assert rounded_count_text(spec) == spec


@pytest.mark.parametrize("url, marker", [(SYN, 'id="share-report"'), (AUTO, 'id="share-report"')])
def test_each_report_renders_for_a_guest_and_is_share_safe(make_guest, url, marker):
    g, _ = make_guest()
    r = g.get(url, follow_redirects=False)
    assert r.status_code == 200
    text = body_text(r.text, marker)
    assert to.blocked_words(text) == [] or url == SYN and all(w == "foundry" for w in to.blocked_words(text))
    problems = (sr.synergy_problems if url == SYN else to.share_problems)(text)
    assert problems == [], problems
    assert "Save as PDF" in r.text and f'href="{url}/edit"' not in r.text
    assert g.get(url + "/edit", follow_redirects=False).status_code == 403
    assert g.post(url + "/edit", data={"title": "x"}, follow_redirects=False).status_code == 403


def test_synergies_has_the_sections_and_rounded_numbers(client):
    html = client.get(SYN).text
    for sid in ("syn-glance", "syn-tech", "syn-combine"):
        assert f'class="to-page" id="{sid}"' in html, sid
    assert html.count('class="to-pfoot"') == 3 and "/ 3<" in html
    b = sr.build_synergies()
    parts = next(f for f in b["facts"] if f["key"] == "parts")["num"]
    assert f">{rounded_count_text(parts)}<" in html and f">{parts}<" not in html
    for words in ("Manufacturing capabilities", "Key technologies per company", "Product overlap",
                  "Where the two combine",
                  "Foundry partners", "Skyworks only", "Qorvo only", "Both offer"):  # fmt: skip
        assert words in html, words
    assert b["both"] and b["sky"] and b["qor"] and 3 <= len(b["pairs"]) <= 6


def test_the_manufacturing_guard_blocks_fabs_sites_and_named_partners():
    ok = "Silicon comes from foundry partners; GaAs HBT in-house."
    assert sr.synergy_problems(ok) == []
    for bad in ("Made in our wafer fab", "Our fab runs GaAs", "Built at TSMC", "Assembly in Mexicali",
                "GaAs from the Newbury Park site", "a foundry in Asia"):  # fmt: skip
        assert sr.synergy_problems(bad), bad
    assert "Woburn" in sr.site_names() and "Mexicali" in sr.site_names()
    # and on save: the owner cannot put a site name on the page
    vals = te.values({}, sr.SYNERGIES)
    assert te.check("mfg.0.skyworks", vals["mfg.0.skyworks"], sr.SYNERGIES) == ""
    assert "where or how parts are made" in te.check("mfg.0.skyworks", "Woburn", sr.SYNERGIES)


def test_automotive_names_only_aec_q_series_and_opens_as_an_extension(client):
    html = client.get(AUTO).text
    assert "Extension of:" in html and 'href="/shareable/synergies"' in html
    b = sr.build_automotive()
    assert [s["key"] for s in b["subsystems"]][:3] == ["car-access", "car-radio", "telematics-v2x"]
    named = [x for s in b["subsystems"] for x in s["series"]]
    assert named and all(sr.qualified_series(x) for x in named)
    for x in re.findall(r"<code>([^<]+)</code>", html):
        rows = sr.series_rows(x)
        assert any(r["automotive"] is True for r in rows), f"{x} is not AEC-Q qualified"
    for p in b["pairs"]:
        for mpn in (p["s_ex"], p["q_ex"]):
            if mpn:
                assert any(r["mpn"] == mpn and r["automotive"] is True for r in to.active_rows()), mpn
    assert "AEC-Q100" in html and "ISO 26262" in html


def test_every_default_passes_its_checks():
    for rep in sr.REPORTS.values():
        vals = te.values({}, rep)
        bad = {fid: te.check(fid, vals[fid], rep) for fid in rep.specs() if te.check(fid, vals[fid], rep)}
        bad |= {s: why for s in rep.sections() if (why := te.check(f"paras.{s}", vals[f"paras.{s}"], rep))}
        assert bad == {}, (rep.key, bad)


def test_overview_counts_are_rounded_with_the_exact_value_in_edit_mode(client):
    html = client.get("/shareable/technology-overview").text
    parts = f"{len(to.active_rows()):,}"
    assert f">{rounded_count_text(parts)}<" in html
    edit = client.get("/shareable/technology-overview/edit").text
    assert f"automatic: {rounded_count_text(parts)} (exact {parts}) from the catalogue" in edit


def test_owner_edits_a_new_report_comments_and_undoes(client):
    edit = client.get(SYN + "/edit").text
    assert 'name="fact.parts.num"' in edit and 'name="paras.glance"' in edit and "(exact " in edit
    r = client.post(SYN + "/edit", data={"fact.parts.num": "4,621", "paras.glance": ["A shorter intro."],
                                         "pid.glance": ["syn-glance-1"]}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"].endswith("done=saved")
    html = client.get(SYN).text
    assert ">4,621<" in html and "A shorter intro." in html  # the owner's number shows as typed
    assert "A shorter intro." not in client.get("/shareable/technology-overview").text  # its own storage key
    r = client.post(SYN + "/edit", data={"mfg.0.qorvo": "Hillsboro"})
    assert r.status_code == 400 and "where or how parts are made" in r.text
    r = client.post(SYN + "/edit/comment", data={"block": "para.syn-glance-1", "ctext.para.syn-glance-1": "shorter"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and "Open comment" in client.get(SYN + "/edit").text
    client.post(SYN + "/edit/undo")
    assert ">4,621<" not in client.get(SYN).text
    client.post(AUTO + "/edit", data={"title": "Automotive at a glance"})
    assert "Automotive at a glance" in client.get(AUTO).text
    client.post(AUTO + "/edit/reset", data={"all": "1"})
    assert "Automotive at a glance" not in client.get(AUTO).text


def test_the_pack_combines_the_selected_reports_in_order(client):
    html = client.get(f"{PACK}?r=automotive,overview,synergies&wm=draft").text
    ids = re.findall(r'class="to-page[^"]*" id="([^"]+)"', html)
    assert ids == ["at-a-glance", "platforms", "markets", "families", "syn-glance", "syn-tech", "syn-combine",
                   "auto-offer", "auto-apps", "auto-pairs"]  # fmt: skip
    assert html.count('class="to-pfoot"') == 10 and "1 / 10<" in html and "10 / 10<" in html
    assert html.count("<b>Sources.</b>") == 1  # one list, at the end
    assert "<span>Draft</span>" in html
    two = client.get(f"{PACK}?r=synergies&r=automotive").text
    assert re.findall(r'class="to-page[^"]*" id="([^"]+)"', two)[0] == "syn-glance" and "6 / 6<" in two
    focus = client.get(f"{PACK}?r=overview&focus=automotive").text
    assert 'id="market-focus"' in focus and "5 / 5<" in focus
    from app.config import PROJECT_ROOT

    css = (PROJECT_ROOT / "app" / "web" / "static" / "shareable.css").read_text()
    assert ".sr-pack-part .to-page { break-before: page; }" in css  # each report from a new page
    landing = client.get("/shareable").text
    assert 'id="build-pdf"' in landing and 'value="synergies"' in landing and "Create PDF" in landing


def test_patent_tags_come_from_a_fixture_and_are_quiet_without_data(monkeypatch, tmp_path):
    """W's patent summary (merged later): one tag per platform row; nothing at all when the data is missing."""
    monkeypatch.setattr(sr, "_patent_source", lambda: None)
    assert sr.patent_marks() == {}
    fixture = tmp_path / "patents_platforms.yaml"
    fixture.write_text("platforms:\n  gan_on_sic: {leader: Qorvo, us_families: 412, automotive: false}\n"
                       "  digital_isolation_capacitive: {leader: Skyworks, us_families: 233, automotive: true}\n"
                       "  baw: {leader: both, automotive: true}\n  odd: {leader: nobody}\n")  # fmt: skip
    monkeypatch.setattr(sr, "PATENTS_FILE", fixture)
    monkeypatch.setattr(sr, "_patent_source", lambda: __import__("app.yamlio", fromlist=["load"]).load(
        fixture.read_text()))  # fmt: skip
    marks = sr.patent_marks()
    assert set(marks) == {"gan_on_sic", "digital_isolation_capacitive", "baw"}
    gan = {"key": "gan", "caps": ["gan_on_sic"]}
    iso = {"key": "isolation", "caps": ["digital_isolation_capacitive"]}
    assert sr.patent_tag(gan, marks) == "IP: Qorvo-led" and sr.patent_tag({"key": "baw"}, marks) == "IP: both"
    assert sr.patent_tag(gan, marks, automotive_only=True) == ""
    assert sr.patent_tag(iso, marks, True) == "IP: Skyworks-led"
    assert sr.patent_tag({"key": "x"}, marks) == ""
