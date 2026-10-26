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
    assert ">Create PDF<" in r.text and "window.print()" not in r.text and f'href="{url}/edit"' not in r.text
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
    assert "woburn" in sr.site_names() and "mexicali" in sr.site_names()
    # and on save: the owner cannot put a site name on the page
    vals = te.values({}, sr.SYNERGIES)
    assert te.check("mfg.0.skyworks", vals["mfg.0.skyworks"], sr.SYNERGIES) == ""
    assert "where or how parts are made" in te.check("mfg.0.skyworks", "Woburn", sr.SYNERGIES)


def test_automotive_names_only_aec_q_series_and_opens_as_an_extension(client):
    html = client.get(AUTO).text
    assert "Extension of: Skyworks + Qorvo synergies" in html  # named, not linked: no reference to the site
    b = sr.build_automotive()
    assert [s["key"] for s in b["subsystems"]][:3] == ["car-access", "car-radio", "telematics-v2x"]
    named = [x for s in b["subsystems"] for x in s["series"]]
    assert named and all(sr.qualified_series(x) for x in named)
    for x in re.findall(r"<code>([^<]+)</code>", html):
        rows = sr.series_rows(x)
        assert any(sr._qualified(r) for r in rows), f"{x} is not AEC-Q qualified"  # the one site-wide AEC-Q test
    for p in b["pairs"]:
        for mpn in (p["s_ex"], p["q_ex"]):
            if mpn:
                assert any(r["mpn"] == mpn and sr._qualified(r) for r in to.active_rows()), mpn
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


def test_old_pack_links_now_download_the_pdf(client):
    """Owner, 26 Oct 2026: no browser printing; the old combined print view's links download the server PDF of the
    same reports (pack order: overview first), with the watermark; an old &focus= is ignored."""
    r = client.get(f"{PACK}?r=automotive,overview,synergies&wm=draft", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/shareable/pdf?r=overview,synergies,automotive&wm=draft"
    for q in ("", "?r=overview&focus=automotive", "?r=synergies&r=automotive", "?wm=custom&wmt=For%20Anna"):
        got = client.get(PACK + q)
        assert got.status_code == 200 and got.headers["content-type"] == "application/pdf", q
        assert got.content.startswith(b"%PDF"), q
    assert client.get(PACK, follow_redirects=False).headers["location"].startswith(
        "/shareable/pdf?r=overview,synergies,automotive")  # fmt: skip
    landing = client.get("/shareable").text
    assert 'id="build-pdf"' in landing and 'value="synergies"' in landing and ">Create PDF<" in landing
    form = landing[landing.index('id="build-pdf"'):landing.index("</form>", landing.index('id="build-pdf"'))]
    assert 'name="focus"' not in form and "Market focus" not in form and "4 pages" in form  # no focus option


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


# ---- owner, 25 Oct 2026 comments on the Technology overview (and the same elements on the two reports) -------------
AEC_COUNT = re.compile(r"\d[\d,]*\+?\s*(?:AEC-Q|automotive-grade)[\w -]{0,12}?\b(?:parts|qualified)\b|"
                       r"\bAEC-Q qualified parts\b|\bautomotive-grade parts\b", re.I)  # fmt: skip


def test_no_aec_q_part_counts_but_the_designations_stay(client):
    """ "I just want AEC-Q part counts out, filters and designations should remain." """
    over = body_text(client.get("/shareable/technology-overview").text, 'id="tech-overview"')
    syn = body_text(client.get(SYN).text, 'id="share-report"')
    auto = body_text(client.get(AUTO).text, 'id="share-report"')
    for text in (over, syn, auto):
        assert not AEC_COUNT.search(text), AEC_COUNT.search(text)
    assert AEC_COUNT.search("Car radio (12 AEC-Q parts)") and AEC_COUNT.search("1,500+ AEC-Q qualified")
    for facts in (to.build()["facts"], sr.build_synergies()["facts"], sr.build_automotive()["facts"]):
        assert all(f["key"] != "automotive" for f in facts)
    assert all("n" not in s for s in sr.build_automotive()["subsystems"])
    # the designations remain: which series are AEC-Q qualified, the AEC-Q examples, the standards
    assert "Series listed are AEC-Q qualified" in auto and "AEC-Q example" in auto and "AEC-Q100" in auto
    assert sr.build_automotive()["subsystems"][0]["series"]


def test_every_synergy_states_one_benefit_from_the_fixed_set(client):
    """ "How are these synergies useful? Better manufacturing capability, shared tech, new tech, cost savings
    assumed?" One tag from a fixed set per pair and per overlap column; cost savings always say "assumed". """
    labels = sr.benefit_labels()
    assert set(labels) == {"manufacturing", "shared_tech", "new_tech", "cost", "market"}
    assert "assumed" in labels["cost"].lower()
    words = sr.curated()["synergies"]
    assert set(words["benefits"].values()) <= set(labels) and words["benefit_default"] in labels
    syn, auto = sr.build_synergies(), sr.build_automotive()
    assert syn["pairs"] and auto["pairs"]
    for p in syn["pairs"] + auto["pairs"]:
        assert p["benefit"] in labels.values() and p["line"], p
    assert {o["benefit"] for o in syn["overlap"].values()} <= set(labels.values())
    assert all(o["line"] for o in syn["overlap"].values())
    for url, b, extra in ((SYN, syn, 3), (AUTO, auto, 0)):
        tags = [unescape(x) for x in re.findall(r'<span class="sr-ben">([^<]+)</span>', client.get(url).text)]
        assert len(tags) == len(b["pairs"]) + extra and set(tags) <= set(labels.values()), (url, tags)
    edit = client.get(SYN + "/edit").text
    assert f'name="pair.{syn["pairs"][0]["key"]}.benefit"' in edit  # the owner can change the tag


def test_the_little_markers_are_right_aligned(client):
    """ "Right align the little markers for both etc": each Skyworks / Qorvo / Both, IP and benefit marker sits in a
    row with the to-marks-right class (flex; the marker is pushed right and never wraps), on screen and in print. """
    from app.config import PROJECT_ROOT

    css =(PROJECT_ROOT / "app" / "web" / "static" / "shareable.css").read_text()
    rule = css[css.index(".to-marks-right > :not(:first-child)"):]
    assert "margin-left: auto" in rule.split("}")[0] and "white-space: nowrap" in rule.split("}")[0]
    over = client.get("/shareable/technology-overview").text
    assert over.count('class="to-plat-name to-marks-right"') == len(to.build()["platforms"])
    closers = ("</li>", "</b>", "</p>", "</div>")
    for url in (SYN, AUTO):
        html = client.get(url).text.split('id="share-report"', 1)[1]
        marks = [m.start() for m in re.finditer(r'<span class="(?:sr-ip|sr-ben)">', html)]
        marks += [m.start() for m in re.finditer(r'<span class="to-marks">', html)]
        assert marks, url
        for at in marks:
            row = html.rfind("to-marks-right", 0, at)
            assert row > 0 and not any(c in html[row:at] for c in closers), (url, html[max(0, at - 200):at + 40])


# ---- one Shareable page (owner, 25 Oct 2026): no sub-tabs; the reports in one list -----------------------------------
def test_menu_has_one_shareable_entry_and_no_report_items():
    from app.web import nav

    labels = [i[0] for _, _, items in nav.NAV for i in items]
    hrefs = [i[1] for _, _, items in nav.NAV for i in items]
    assert not {"Skyworks + Qorvo synergies", "Automotive", "Technology overview", "Presentation builder"} & set(labels)
    assert not [h for h in hrefs if h.startswith("/shareable/")]
    assert next(s for s in nav.NAV if s[0] == "shareable")[2] == (
        ("Reports", "/shareable", "Pick reports, preview them and save one PDF"),)
    for path in ("/shareable/technology-overview", SYN, AUTO, PACK, "/shareable/presentation",
                 "/shareable/presentation/preview", f"{SYN}/edit"):  # fmt: skip
        assert nav.place(path) == ("shareable", "/shareable"), path
    assert nav.page_title(SYN) == "Skyworks + Qorvo synergies – Shareable – BizDev"  # still named in the title


def test_shareable_lists_the_three_reports_with_previews_and_two_actions(client):
    html = client.get("/shareable").text
    rows = re.findall(r'<li class="sh-row">.*?</li>', html, re.S)
    assert len(rows) == 3
    # the synergies report first, its automotive extension next (owner, 25 Oct 2026)
    want = (("synergies", "Skyworks + Qorvo synergies", 3, SYN), ("automotive", "Automotive", 3, AUTO),
            ("overview", "Technology overview", 4, "/shareable/technology-overview"))  # fmt: skip
    for row, (key, label, pages, href) in zip(rows, want, strict=True):
        assert f'name="r" value="{key}"' in row and ' checked' not in row  # nothing ticked by default
        assert f"<b>{label}</b>" in unescape(row) and f"{pages} pages" in row
        assert f'href="{href}" data-lightbox="{label}">Preview</a>' in unescape(row)
        assert f'class="sh-open" href="{href}" data-lightbox="{label}"' in unescape(row)  # tapping the report opens it
        assert ">Include</label>" in row
    form = html[html.index('id="build-pdf"'):html.index("</form>", html.index('id="build-pdf"'))]
    assert form.count('type="submit"') == 1 and ">Create PDF</button>" in form  # one combine button
    assert ">Create PowerPoint</button>" in form and 'action="/shareable/pdf"' in form
    assert 'class="sh-ppt" role="button" href="/shareable/presentation">Build a presentation</a>' in html
    assert "Pick at least one report." in html and 'class="sh-cards"' not in html
    again = client.get("/shareable?r=automotive,synergies&wm=draft").text  # the last choice from the address
    assert 'value="synergies" checked' in again and 'value="automotive" checked' in again
    assert 'value="overview" checked' not in again and 'value="draft" selected' in again


def test_owner_sees_edit_links_guest_does_not(owner, make_guest):
    html = owner.get("/shareable").text
    for href in ("/shareable/technology-overview", SYN, AUTO):
        assert f'class="sh-edit small" href="{href}/edit"' in html
    g, _ = make_guest()
    assert 'class="sh-edit' not in g.get("/shareable").text


def test_shareable_documents_carry_no_reference_to_the_site(client):
    """Owner, 26 Oct 2026: "Leave all references to the site out of the shareable documentation" - no site footer,
    no site name in the title (browsers print it in a PDF's header), no links from one report to another."""
    for url in (SYN, AUTO, "/shareable/technology-overview", "/shareable/presentation/preview?s=title"):
        html = client.get(url).text
        title = re.search(r"<title>(.*?)</title>", html, re.S).group(1)
        assert "BizDev" not in title and "Shareable" not in title, (url, title)
        assert 'class="site-foot"' not in html and "Cross lists loaded" not in html, url
        if 'id="share-report"' in html:
            doc = html.split('id="share-report"', 1)[1]
            assert 'href="/shareable/synergies"' not in doc and 'href="/shareable/automotive"' not in doc, url
    assert 'class="site-foot"' in client.get("/shareable").text  # the site's own pages keep their footer
