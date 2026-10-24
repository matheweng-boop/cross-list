"""Shareable > Technology overview (owner, 24 Oct 2026): a public brief on the Skyworks + Qorvo portfolio, meant to be
shared outside the company and saved as PDF. The page must stay share-safe (no internal words, no competitors), take
its numbers from the site's data, and be readable by guests. The printed page count is checked in
tests/test_browser.py (Chromium)."""

import re
from html import unescape

from app.services import opportunity as op
from app.services import portfolio as pf
from app.services import tech_overview as to
from app.web import nav

URL = "/shareable/technology-overview"

# never on a page meant for outside readers; whole words, any case, plural too ("interest" does not trip "est")
BLOCKLIST = ("gap", "risk", "weakness", "weaknesses", "roadmap", "internal", "confidential", "business case", "TAM",
             "est", "estimate", "margin", "our price", "fab", "foundry", "wafer", "secret", "proprietary data",
             "not public", "divested", "competitor", "versus", "vs", "beats", "lags", "behind")  # fmt: skip


def content_text(html: str) -> str:
    """The brief itself: what prints, without the site's menus, banners and footer."""
    body = html.split('id="tech-overview"', 1)[1].split("</main>", 1)[0]
    body = re.sub(r"<(script|style)\b.*?</\1>", " ", body, flags=re.S)
    return unescape(re.sub(r"<[^>]+>", " ", body))


def competitor_names() -> set[str]:
    from app.services import competitors

    names = set()
    for c in pf.curated().get("competitors") or []:
        names |= {c["vendor"], *(c.get("aliases") or [])}
    names |= {p["name"] for p in competitors.all_profiles() if p.get("name")}
    return {n for n in names if len(n) >= 3}


def blocked(text: str) -> list[str]:
    hits = [w for w in BLOCKLIST if re.search(rf"\b{re.escape(w)}s?\b", text, re.I)]
    hits += [n for n in competitor_names() if re.search(rf"\b{re.escape(n)}\b", text)]
    return hits


def test_the_blocklist_matches_whole_words_only():
    assert blocked("Our interest is the best estimate") == ["estimate"]
    assert blocked("Gaps and risks") == ["gap", "risk"]
    assert not blocked("fabless, foundational, gapless, tamper, estate, marginalia")


def test_menu_has_a_shareable_section_after_engineering_knowledge():
    keys = [s[0] for s in nav.NAV]
    assert keys[-2:] == ["knowledge", "shareable"]
    items = next(s for s in nav.NAV if s[0] == "shareable")[2]
    assert items[0] == ("Technology overview", URL, "Public, ready to share or save as PDF")
    assert nav.HOMES["shareable"] == "/shareable"
    assert nav.place(URL) == ("shareable", URL) and nav.place("/shareable") == ("shareable", "/shareable")
    assert nav.page_title(URL) == "Technology overview – Shareable – BizDev"
    assert nav.page_title("/shareable") == "Shareable – BizDev"
    assert "shareable" in nav.ICONS


def test_landing_page_lists_the_shareable_pages(client):
    html = client.get("/shareable").text
    assert "Everything here is public information" in html
    assert f'class="sh-card" href="{URL}"' in html
    assert 'href="/shareable"' in html  # the section row opens the landing page
    assert 'aria-current="page" class="on">Technology overview<' in client.get(URL).text


def test_the_page_is_share_safe(client):
    r = client.get(URL)
    assert r.status_code == 200
    text = content_text(r.text)
    assert blocked(text) == [], blocked(text)
    for words in ("Public information", "Save as PDF", "Learn more", "Sources."):
        assert words in r.text, words


def test_guests_read_the_whole_section(make_guest, owner):
    g, _ = make_guest()
    for url in ("/shareable", URL):
        r = g.get(url, follow_redirects=False)
        assert r.status_code == 200, url
    assert blocked(content_text(g.get(URL).text)) == []


def test_four_sections_with_the_numbers_from_the_catalogue(client):
    html = client.get(URL).text
    for sid in ("at-a-glance", "platforms", "markets", "families"):
        assert f'class="to-page" id="{sid}"' in html, sid
    assert html.count('class="to-pfoot"') == 4
    b = to.build()
    cats = pf.product_categories()  # the same counts as Products > Skyworks + Qorvo
    total = cats["totals"]["Skyworks"] + cats["totals"]["Qorvo"]
    assert b["facts"][0]["num"] == f"{total:,}" and f"{total:,}" in html
    assert int(b["facts"][1]["num"]) == len([r for r in cats["rows"] if r["label"] != pf.OTHER_CATEGORY])
    assert int(b["facts"][2]["num"]) == len(b["platforms"]) == len(b["matrix"])
    assert int(b["facts"][3]["num"]) == len(b["markets"]) == 6
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
