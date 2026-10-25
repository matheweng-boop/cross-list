"""Shareable > Technology overview (owner, 24 Oct 2026): a public brief on the Skyworks + Qorvo portfolio, meant to be
shared outside the company and saved as PDF; editable by the owner (texts, numbers, paragraphs, comments, header and
logo), with a watermark (the market focus page was removed, owner 25 Oct 2026). The page must stay share-safe, take
its numbers from the site's data unless the owner overrides them, and be readable by guests. Printed page counts are
checked in tests/test_browser.py (Chromium)."""

import re
import struct
import zlib
from datetime import UTC, datetime, timedelta
from html import unescape

from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import PageComment, PageTextVersion
from app.services import opportunity as op
from app.services import portfolio as pf
from app.services import tech_overview as to
from app.services import tech_overview_edit as te
from app.services.text import round_count
from app.web import nav

URL = "/shareable/technology-overview"
EDIT = URL + "/edit"
blocked = to.blocked_words


def content_text(html: str) -> str:
    """The brief itself: what prints, without the site's menus, banners and footer (and without the edit tools)."""
    body = html.split('id="tech-overview"', 1)[1].split("</main>", 1)[0]
    body = re.sub(r"<(script|style|template)\b.*?</\1>", " ", body, flags=re.S)
    body = re.sub(r'<span class="to-wm-tag">.*?</span>', " ", body)  # the watermark word: the owner's choice
    return unescape(re.sub(r"<[^>]+>", " ", body))


def png(w: int = 4, h: int = 2) -> bytes:
    """A tiny valid PNG (a grey rectangle)."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\x80" * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))  # fmt: skip


def test_the_blocklist_matches_whole_words_only():
    assert blocked("Our interest is the best estimate") == ["estimate"]
    assert blocked("Gaps and risks") == ["gap", "risk"]
    assert not blocked("fabless, foundational, gapless, tamper, estate, marginalia")
    assert "Texas Instruments" in blocked("Texas Instruments parts")
    assert to.share_problems("our roadmap") == ["“roadmap” looks internal; this page is public."]
    assert not to.share_problems("Confidential", allow=("confidential",))


def test_menu_has_a_shareable_section_after_engineering_knowledge():
    keys = [s[0] for s in nav.NAV]
    assert keys[-2:] == ["knowledge", "shareable"]
    items = next(s for s in nav.NAV if s[0] == "shareable")[2]
    assert [i[1] for i in items] == ["/shareable"]  # owner, 25 Oct 2026: one page, the reports open from there
    assert nav.HOMES["shareable"] == "/shareable"
    assert nav.place(URL) == ("shareable", "/shareable") and nav.place("/shareable") == ("shareable", "/shareable")
    assert nav.page_title(URL) == "Technology overview – Shareable – BizDev"
    assert nav.page_title("/shareable") == "Shareable – BizDev"
    assert "shareable" in nav.ICONS


def test_landing_page_lists_the_shareable_pages(client):
    html = client.get("/shareable").text
    assert "Public information, ready to share" in html
    assert f'class="sh-preview" role="button" href="{URL}" data-lightbox="Technology overview"' in html
    assert 'href="/shareable"' in html  # the section row opens the landing page
    assert 'aria-current="page" class="on">Reports<' in client.get(URL).text  # the menu highlights the one entry


def test_the_page_is_share_safe(client):
    r = client.get(URL)
    assert r.status_code == 200
    text = content_text(r.text)
    assert blocked(text) == [], blocked(text)
    for words in ("Public information", "Save as PDF", "Learn more", "Sources."):
        assert words in r.text, words


def test_the_overview_is_four_pages_and_old_focus_links_still_open_it(client):
    """Owner, 25 Oct 2026: "Remove the Market focus page, as I can now separately select it." The page has no
    market focus page or controls; an old link with ?focus= / ?include= opens the same 4-page overview."""
    html = client.get(URL).text
    assert html.count('class="to-page') == 4 and "/ 4<" in html and "/ 5<" not in html
    assert 'id="market-focus"' not in html and 'name="focus"' not in html and 'name="include"' not in html
    assert "Market focus" not in html
    for q in ("focus=automotive", "focus=drones&include=1", "focus=bogus&include=x", "focus=none"):
        r = client.get(f"{URL}?{q}")
        assert r.status_code == 200, q
        assert r.text.count('class="to-page') == 4 and "/ 4<" in r.text and 'id="market-focus"' not in r.text, q
    assert "focus" not in te.view_options({}, {"focus": "automotive"})
    assert te.view_options({}, {"focus": "automotive"})["pages"] == 4
    assert not any(fid.startswith("focus.") for fid in te.specs()) and te.sections() == te.MAIN_SECTIONS
    assert not hasattr(to, "focus_markets") and "focus" not in to.curated()


def test_no_watermark_by_default_and_unknown_values_are_ignored(client):
    html = client.get(URL).text
    assert 'class="to-wm"' not in html
    r = client.get(f"{URL}?wm=bogus")
    assert r.status_code == 200 and 'class="to-wm"' not in r.text


def test_watermark_choices_and_custom_text(client):
    assert 'class="to-wm"' not in client.get(f"{URL}?wm=none").text
    html = client.get(f"{URL}?wm=draft").text
    assert '<div class="to-wm" aria-hidden="true"><span>Draft</span>' in html and 'class="to-wm-tag">Draft<' in html
    assert "<span>Confidential</span>" in client.get(f"{URL}?wm=confidential").text
    assert "<span>Confidential copy</span>" in client.get(f"{URL}?wm=custom&wmt=Confidential+copy").text
    bad = client.get(f"{URL}?wm=custom&wmt=Our+roadmap").text
    assert 'class="to-wm"' not in bad and "No watermark: “roadmap” looks internal" in bad
    # the watermark sits outside the brief, so the brief's word check is unchanged
    assert blocked(content_text(client.get(f"{URL}?wm=confidential").text)) == []


def test_guests_read_the_whole_section_but_never_edit(make_guest, owner):
    g, _ = make_guest()
    for url in ("/shareable", URL, f"{URL}?wm=draft"):
        assert g.get(url, follow_redirects=False).status_code == 200, url
    html = g.get(URL).text
    assert blocked(content_text(html)) == [] and f'href="{EDIT}' not in html
    assert g.get(EDIT, follow_redirects=False).status_code == 403
    for path in ("", "/undo", "/reset", "/comment", "/resolve", "/logo", "/logo/remove"):
        r = g.post(EDIT + path, data={"title": "x", "all": "1", "block": "title", "cid": "1"}, follow_redirects=False)
        assert r.status_code == 403, path
    assert g.post(EDIT + "/logo", files={"logo": ("l.png", png(), "image/png")}).status_code == 403
    assert f'href="{EDIT}' in owner.get(URL).text  # the owner sees the Edit button


def test_four_sections_with_the_numbers_from_the_catalogue(client):
    html = client.get(URL).text
    for sid in ("at-a-glance", "platforms", "markets", "families"):
        assert f'class="to-page" id="{sid}"' in html, sid
    assert html.count('class="to-pfoot"') == 4 and html.count('<div class="to-band') == 4
    b = to.build()
    cats = pf.product_categories()  # the same counts as Cross-sell > Skyworks + Qorvo portfolio
    total = cats["totals"]["Skyworks"] + cats["totals"]["Qorvo"]
    nums = {f["key"]: f["num"] for f in b["facts"]}
    assert nums["parts"] == f"{total:,}" and f">{round_count(total)}<" in html  # shown rounded (owner, 25 Oct 2026)
    assert int(nums["families"]) == len([r for r in cats["rows"] if r["label"] != pf.OTHER_CATEGORY])
    assert int(nums["platforms"]) == len(b["platforms"]) == len(b["matrix"])
    assert int(nums["markets"]) == len(b["markets"]) == 6
    fams = {f["label"]: f for f in b["families"]}
    for r in cats["rows"]:
        if r["label"] != pf.OTHER_CATEGORY:
            assert (fams[r["label"]]["Skyworks"], fams[r["label"]]["Qorvo"]) == (r["Skyworks"], r["Qorvo"])


def test_curated_words_point_at_real_data():
    cur = to.curated()
    caps = op.capabilities()
    labels = {label for label, _ in pf.CATEGORY_RULES}
    keys = {p["key"] for p in cur["platforms"]}
    for p in cur["platforms"]:
        assert p["caps"] and all(k in caps for k in p["caps"]), p["key"]
        assert set(p["families"]) <= labels, p["key"]
        assert to.owner_of(p["caps"]) in ("Skyworks", "Qorvo", "Both"), p["key"]
    for m in cur["markets"]:
        assert set(m["platforms"]) <= keys, m["key"]
        assert 3 <= len(m["parts"]) <= 4, m["key"]
        for _name, series in m["parts"]:
            assert to.series_parts(series), f"{series} matches no active catalogue part"
    assert set(cur["families"]) <= labels
    for label, f in cur["families"].items():
        for fig in f.get("figures") or []:
            got = to.figure(label, fig)
            assert got and got["mpn"], (label, fig["spec"])


def test_every_default_passes_its_own_checks():
    """The defaults fit their length limits and the word check, so the unedited page always saves."""
    vals = te.values({})
    bad = {fid: te.check(fid, vals[fid]) for fid in te.specs() if te.check(fid, vals[fid])}
    bad |= {
        s: te.check(f"paras.{s}", vals[f"paras.{s}"])
        for s in te.sections()
        if te.check(f"paras.{s}", vals[f"paras.{s}"])
    }
    assert bad == {}


def test_the_daily_runs_answers_pass_the_same_checks():
    """data/business/tech_overview_answers.yaml: every answer is public-safe and fits its block."""
    vals = te.values({})
    for a in te.answers():
        assert a.get("comment") and a.get("reply") and str(a.get("text") or "").strip(), a
        new: dict = {}
        fid = te.set_block(new, vals, str(a["block"]), str(a["text"]))
        assert fid and te.check(fid, new[fid]) == "", a


def test_owner_follows_the_capabilities_file():
    assert to.owner_of(["gan_on_sic"]) == "Qorvo"
    assert to.owner_of(["digital_isolation_capacitive"]) == "Skyworks"
    assert to.owner_of(["pmic_configurable_power", "power_management_skyworks"]) == "Both"
    assert to.owner_of(["sic_jfet_divested"]) == ""  # divested: nobody holds it


def test_print_styles_hide_the_frame_and_break_pages():
    from app.config import PROJECT_ROOT

    css = (PROJECT_ROOT / "app" / "web" / "static" / "shareable.css").read_text()
    printing = css.split("@media print", 1)[1]
    assert "size: A4" in css and "print-color-adjust: exact" in printing and "break-before: page" in printing
    for frame in (".site-head", ".site-foot", ".fb", ".to-actions", ".banner"):
        assert frame in printing, frame
    assert ".to-controls { display: none" in css


# ---- editing ---------------------------------------------------------------------------------------------------------
def _versions() -> list[PageTextVersion]:
    with Session(get_engine()) as s:
        return list(s.query(PageTextVersion).order_by(PageTextVersion.id))


def test_owner_edits_a_text_and_a_number_and_undoes(client):
    edit = client.get(EDIT).text
    assert "automatic: 4,500+ (exact 4,621) from the catalogue" in edit or "automatic: " in edit
    assert 'name="fact.parts.num"' in edit and 'name="paras.glance"' in edit
    r = client.post(EDIT, data={"fact.parts.num": "5,000", "plat.gan.what": "Wide-bandgap transistors for power.",
                                "dot.gan.mobile": "Qorvo"}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"].endswith("done=saved")
    html = client.get(URL).text
    assert ">5,000<" in html and "Wide-bandgap transistors for power." in html
    gan = re.search(r'<tr><th scope="row">GaN on SiC</th>(.*?)</tr>', html).group(1)
    assert gan.startswith('<td><span class="to-dot to-qorvo"')  # the owner's dot in the Mobile column
    edit = client.get(EDIT).text
    assert "overridden" in edit and "Back to automatic" in edit and "automatic: 4,500+ (exact 4,621)" in edit
    v = _versions()[-1]
    assert v.fields["fact.parts.num"] == "5,000" and v.auto["fact.parts.num"] == "4,500+"
    client.post(EDIT + "/undo")
    assert ">5,000<" not in client.get(URL).text and ">4,500+<" in client.get(URL).text


def test_a_blocked_word_is_not_saved_and_says_why(client):
    r = client.post(EDIT, data={"plat.baw.what": "Part of our roadmap", "title": "New title"})
    assert r.status_code == 400 and "“roadmap” looks internal; this page is public." in r.text
    assert 'value="New title"' in r.text  # the typed text stays in the form
    assert _versions() == [] and "New title" not in client.get(URL).text
    r = client.post(EDIT, data={"plat.baw.what": "x" * 200})
    assert r.status_code == 400 and "at most 100 here" in r.text


def test_reset_one_field_and_reset_all(client):
    client.post(EDIT, data={"title": "Title one", "fam.diodes.skyworks": "140"})
    assert "Title one" in client.get(URL).text
    client.post(EDIT + "/reset", data={"field": "title"})
    html = client.get(URL).text
    assert "Title one" not in html and ">140<" in html
    client.post(EDIT + "/reset", data={"all": "1"})
    assert ">140<" not in client.get(URL).text
    client.post(EDIT + "/undo")  # undo brings the reset-all back
    assert ">140<" in client.get(URL).text


def test_paragraphs_add_move_delete_and_limits(client):
    form = {"paras.glance": ["First paragraph.", "Second paragraph."], "pid.glance": ["glance-1", ""]}
    assert client.post(EDIT, data=form, follow_redirects=False).status_code == 303
    paras = te.values(_versions()[-1].fields)["paras.glance"]
    assert [p["text"] for p in paras] == ["First paragraph.", "Second paragraph."] and paras[0]["id"] == "glance-1"
    second = paras[1]["id"]
    client.post(EDIT, data={**form, "pid.glance": ["glance-1", second], "op": f"up:glance:{second}"})
    assert [p["text"] for p in _versions()[-1].fields["paras.glance"]] == ["Second paragraph.", "First paragraph."]
    order = {"paras.glance": ["Second paragraph.", "First paragraph."], "pid.glance": [second, "glance-1"]}
    client.post(EDIT, data={**order, "op": "del:glance:glance-1"})
    assert [p["text"] for p in _versions()[-1].fields["paras.glance"]] == ["Second paragraph."]
    r = client.post(EDIT, data={"paras.glance": ["a", "b", "c"], "pid.glance": ["", "", ""]})
    assert r.status_code == 400 and "At most 2 paragraphs" in r.text


def test_comments_go_to_the_inbox_and_answers_close_them(client, monkeypatch, tmp_path):
    from app.services import inbox

    r = client.post(EDIT + "/comment", data={"block": "para.glance-1", "ctext.para.glance-1": "make this shorter"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    assert "Open comment" in client.get(EDIT).text and "make this shorter" in client.get(EDIT).text
    with Session(get_engine()) as s:
        c = s.query(PageComment).one()
        text = inbox.collect(s, (datetime.now(UTC) - timedelta(days=1)).date())
    assert "## Technology overview (Shareable)" in text
    assert f"Comment #{c.id} on para.glance-1" in text and "make this shorter" in text and "Skyworks and Qorvo" in text
    # the daily run answers in the repo; the site applies it (word check first) and closes the comment
    answers = tmp_path / "answers.yaml"
    answers.write_text(f"answers:\n  - {{comment: {c.id}, block: para.glance-1, text: 'Our roadmap.', reply: x}}\n")
    monkeypatch.setattr(te, "ANSWERS", answers)
    client.get(URL)
    with Session(get_engine()) as s:
        assert s.get(PageComment, c.id).status == "open" and "not applied" in s.get(PageComment, c.id).reply
    answers.write_text(f"answers:\n  - {{comment: {c.id}, block: para.glance-1, text: 'A shorter intro.', "
                       "reply: 'Cut to one sentence.'}\n")  # fmt: skip
    assert "A shorter intro." in client.get(URL).text
    with Session(get_engine()) as s:
        c2 = s.get(PageComment, c.id)
        assert c2.status == "done" and c2.reply == "Cut to one sentence."
    assert _versions()[-1].author == "Daily run"
    # the owner can resolve a comment too
    client.post(EDIT + "/comment", data={"block": "plat.baw.what", "ctext.plat.baw.what": "mention Wi-Fi 7"})
    with Session(get_engine()) as s:
        cid = s.query(PageComment).filter_by(status="open").one().id
    client.post(EDIT + "/resolve", data={"cid": str(cid), f"reply.{cid}": "Done by hand"})
    assert te.comments(Session(get_engine())) == []


def test_inbox_flags_edits_and_numbers_whose_automatic_value_changed(client):
    from app.services import inbox

    client.post(EDIT, data={"fact.parts.num": "5,000", "title": "Edited title"})
    with Session(get_engine()) as s:
        v = s.query(PageTextVersion).one()
        v.auto = {"fact.parts.num": "4,000"}  # as if the catalogue had 4,000 parts when the owner saved
        s.commit()
        text = inbox.collect(s, (datetime.now(UTC) - timedelta(days=1)).date())
    assert "Technology overview: 2 texts edited by the owner" in text
    assert "fact.parts.num: overridden value differs from the new automatic value" in text


def test_logo_upload_checks_the_content_and_cleans_svg(client):
    r = client.post(EDIT + "/logo", files={"logo": ("logo.png", b"<html>not a picture</html>", "image/png")})
    assert r.status_code == 400 and "Only PNG, JPG or SVG files" in r.text
    svg = (b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" onload="alert(1)">'
           b'<script>alert(2)</script><rect width="10" height="5" style="fill:url(http://x/y)"/>'
           b'<a xlink:href="javascript:alert(3)"><text>Hi</text></a><image href="https://x/p.png"/></svg>')  # fmt: skip
    assert client.post(EDIT + "/logo", files={"logo": ("l.svg", svg, "image/svg+xml")},
                       follow_redirects=False).status_code == 303  # fmt: skip
    html = client.get(URL).text
    src = re.search(r'src="(/shareable/logo/\d+)"', html).group(1)
    assert html.count(src) == 4  # on every page's header band
    r = client.get(src)
    assert r.headers["content-type"].startswith("image/svg+xml") and "sandbox" in r.headers["content-security-policy"]
    for bad in (b"script", b"onload", b"javascript", b"http://x", b"https://x"):
        assert bad not in r.content, bad
    assert b"<rect" in r.content and b"Hi" in r.content
    doctype = b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x "y">]><svg xmlns="http://www.w3.org/2000/svg"/>'
    assert client.post(EDIT + "/logo", files={"logo": ("x.svg", doctype, "image/svg+xml")}).status_code == 400
    # a PNG replaces it; removing takes it out; undo brings it back (it is part of the version history)
    client.post(EDIT + "/logo", files={"logo": ("l.png", png(), "image/png")})
    assert client.get(re.search(r'src="(/shareable/logo/\d+)"', client.get(URL).text).group(1)).content == png()
    client.post(EDIT + "/logo/remove")
    assert "/shareable/logo/" not in client.get(URL).text
    client.post(EDIT + "/undo")
    assert "/shareable/logo/" in client.get(URL).text


def test_without_a_logo_the_band_has_only_text(client):
    html = client.get(URL).text
    assert 'class="to-logo' not in html and "Skyworks + Qorvo · Technology overview" in html
    client.post(EDIT, data={"hdr.subtitle": "Prepared for the board"})
    assert html.count("to-band") == client.get(URL).text.count("to-band")
    assert client.get(URL).text.count("Prepared for the board") == 4


def test_owner_saves_a_default_watermark(client):
    assert 'name="focus.default"' not in client.get(EDIT).text  # the default focus setting is gone
    client.post(EDIT, data={"wm.default": "draft"})
    assert "<span>Draft</span>" in client.get(URL).text
    assert 'class="to-wm"' not in client.get(f"{URL}?wm=none").text  # the address wins
    r = client.post(EDIT, data={"wm.default": "custom", "wm.custom": "Our TAM"})
    assert r.status_code == 400 and "“TAM” is our own estimate" in r.text
    assert client.post(EDIT, data={"wm.default": "custom", "wm.custom": "Confidential"},
                       follow_redirects=False).status_code == 303  # fmt: skip
    assert "<span>Confidential</span>" in client.get(URL).text


def test_stored_focus_edits_are_ignored_and_other_edits_kept(client, session):
    """A version saved while the focus page existed (focus.default, focus texts, focus paragraphs) still loads: the
    focus values are ignored, every other edit stays, and saving again keeps it."""
    old = {"focus.default": "automotive", "focus.automotive.title": "Cars", "paras.focus-automotive": [
        {"id": "p-1", "text": "Old focus words."}], "hdr.subtitle": "Prepared for the board"}
    session.add(PageTextVersion(page=te.PAGE, fields=old, auto={"focus.automotive.fact.parts.num": "1,000"},
                                note="Changed: focus.default", author="Owner"))  # fmt: skip
    session.commit()
    html = client.get(URL).text
    assert html.count("Prepared for the board") == 4 and "Old focus words." not in html and "Cars" not in html
    assert html.count('class="to-page') == 4 and 'id="market-focus"' not in html
    assert client.get(EDIT).status_code == 200
    r = client.post(EDIT, data={"hdr.title": "Skyworks + Qorvo · Portfolio brief"}, follow_redirects=False)
    assert r.status_code == 303
    html = client.get(URL).text
    assert "Portfolio brief" in html and html.count("Prepared for the board") == 4
