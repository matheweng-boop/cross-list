"""Site checks: old names, internal links, dates, page titles, counts that must agree, guest pages, and the owner's
answers to the 24 Oct 2026 check."""

import re
from pathlib import Path

import pytest
import yaml

# ---- from tests/test_site_check_1024.py ------------------------------------------------------------------------------
# Site check, 24 Oct 2026: old names from the menu restructure, internal link targets, dates, page titles, part
# counts that must agree, and owner-only links for guests.

ROOT = Path(__file__).resolve().parents[1]
OLD_NAMES = ("Opportunity explorer", "Cross-sell & gaps", "Cross-sell &amp; gaps", "Radio & audio", "Radio &amp; audio",
             "Requests & reviews", "Requests &amp; reviews", "Data centre", "data centre")  # fmt: skip
PAGES = ("/", "/parts", "/portfolio", "/library", "/blocks", "/blocks/cross-sell", "/business/opportunities",
         "/business/explorer/table", "/business/risks", "/business/reports", "/business/shortlist", "/business/tam",
         "/business/quality", "/business/validation", "/business/method", "/business/markets", "/manage/schedule",
         "/manage/overview", "/shareable/technology-overview", "/reviews/qorvo-dw3000-uwb", "/rf-notes")  # fmt: skip


@pytest.mark.parametrize("path", PAGES)
def test_no_old_names_after_the_restructure(client, path):
    page = client.get(path)
    assert page.status_code == 200
    html = re.sub(r"<script.*?</script>", "", page.text, flags=re.S)
    assert not [n for n in OLD_NAMES if n in html], path


def test_review_sources_link_to_web_or_site_pages():
    """A source link must be a web address or a page of this site, never a file path in the repository."""
    for f in sorted((ROOT / "data" / "reviews").glob("[!_]*.yaml")):  # _format.yaml is the template
        for s in yaml.safe_load(f.read_text()).get("sources") or []:
            url = s.get("url") or ""
            assert not url or url.startswith(("http://", "https://", "/")), (f.name, s.get("id"), url)


def test_internal_links_on_a_review_resolve(client):
    html = client.get("/reviews/qorvo-dw3000-uwb").text
    hrefs = {h for h in re.findall(r'href="(/[^"#]*)', html) if not h.startswith("/static")}
    bad = [h for h in sorted(hrefs) if client.get(h).status_code >= 400]
    assert not bad


def test_detailed_table_links_to_tam_not_the_old_market_data_page(client):
    html = client.get("/business/explorer/table?scope=all").text
    assert "/business/data?focus=" not in html
    assert "<h1>Gaps &amp; new technology: detailed table</h1>" in html


def test_dates_read_as_day_month_year(client):
    for path in ("/reviews", "/reviews/qorvo-dw3000-uwb", "/business/reports"):
        meta = " ".join(re.findall(r'class="rp-meta small">(.*?)</', client.get(path).text, flags=re.S))
        assert meta and not re.search(r"\b20\d\d-\d\d-\d\d\b", meta), path


def test_competitor_overlap_never_shows_none(client):
    html = client.get("/business/competitors/sitime").text
    assert "<b>Qorvo:</b> None<" not in html and "No product here" in html


def test_portfolio_headline_counts_each_part_once(client):
    from app.services import portfolio as pf

    html = client.get("/portfolio").text
    totals = pf.product_categories()["totals"]
    for m in ("Skyworks", "Qorvo"):
        assert f'<span class="pf-num">{totals[m]:,}</span>' in html


def test_titles_name_the_page(client):
    assert "<title>Car radio – Application library" in client.get("/broadcast").text
    assert "<title>Library sources – " in client.get("/library/sources").text
    assert "<h1>New radio configuration</h1>" in client.get("/broadcast/configurations/new").text


def test_guest_css_covers_every_owner_page():
    """Guests see links to owner-only pages as plain text: the CSS rule lists every owner-only page prefix."""
    from app.auth.access import OWNER_PAGES

    css = (ROOT / "app" / "web" / "static" / "app.css").read_text()
    rule = css[css.index("body.guest main :is(") :]
    rule = rule[: rule.index("}")]
    missing = [p for p in OWNER_PAGES if not p.startswith("/api/") and not p.endswith(".txt")
               and f'a[href^="{p}"]' not in rule]  # fmt: skip
    assert not missing


def test_guest_pages_are_marked(make_guest, owner):
    g, _ = make_guest()
    assert '<body class="shell guest">' in g.get("/business/method").text
    assert '<body class="shell">' in owner.get("/business/method").text


# ---- from tests/test_site_check_answers_1024.py ----------------------------------------------------------------------
# The owner's answers to the 24 Oct 2026 site check: Browse products width, the Overview tile, touch targets, the
# "Shortlist & cases" menu item, TAM hidden from guests, numbers right-aligned, RF band label contrast, and an Overview
# that no longer waits for a new Verify next batch.
CSS = (ROOT / "app" / "web" / "static" / "app.css").read_text()


def test_browse_products_hides_package_on_desktops_below_1400px():
    block = CSS[CSS.index("@media (min-width: 601px) and (max-width: 1399px)") :]
    assert ".browse-table :is(th, td):nth-child(4) { display: none; }" in block[: block.index("}\n}")]


def test_touch_screens_get_40px_buttons_only():
    block = CSS[CSS.index("@media (pointer: coarse)") :]
    block = block[: block.index("}\n}")]
    assert ".small-btn" in block and ".rv-b" in block and "min-height: 40px" in block


def test_overview_tile_names_parts_with_full_data(client):
    assert "Skyworks and Qorvo parts with full data" in client.get("/manage/overview").text


def test_menu_item_is_shortlist_and_cases(client):
    from app.web import nav

    growth = next(items for key, _, items in nav.NAV if key == "growth")
    assert ("Shortlist & cases", "/business/shortlist") in [(label, href) for label, href, _ in growth]
    html = client.get("/business/shortlist").text
    assert "<title>Shortlist &amp; cases – Future growth – BizDev</title>" in html
    assert "<h1>Shortlist &amp; cases</h1>" in html
    assert client.get("/business/cases").status_code == 200  # old URLs unchanged


def test_guests_never_see_tam_numbers(make_guest, owner):
    from app.web import nav

    assert nav.owner_page("/business/tam")  # the owner-only list in app/auth/access.py decides
    g, _ = make_guest()
    url = "/business/explorer/table?scope=all&sort=tam"
    assert "TAM / year" in owner.get(url).text
    assert "TAM / year" not in g.get(url).text
    assert "Content (priced)" in owner.get("/business/applications").text
    assert "Content (priced)" not in g.get("/business/applications").text


def test_numbers_right_aligned(client):
    assert 'class="n">Priority</th>' in client.get("/rules").text
    method = client.get("/business/method").text
    assert '<th class="n">Weight</th>' in method and '<th class="n">Points</th>' in method
    assert 'class="num-table"' in client.get("/engineering/creepage_mm").text
    assert "td.n, th.n, th[data-n] { text-align: right; font-variant-numeric: tabular-nums; }" in CSS


def test_rf_band_labels_reach_4_5_to_1():
    def lum(h):
        c = [int(h[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]

    page = (ROOT / "app" / "web" / "templates" / "engineering" / "rf_bands.html").read_text()
    pal = page[page.index("const PAL = [") : page.index("];", page.index("const PAL = ["))]
    dark = page[page.index("const DARK = {") : page.index("};", page.index("const DARK = {"))]

    darker = dict(re.findall(r'"(#[0-9a-f]{6})": "(#[0-9a-f]{6})"', dark))
    bg = lum("#f8f6fb")
    for c in re.findall(r"#[0-9a-f]{6}", pal):
        text = darker.get(c, c)
        assert (bg + 0.05) / (lum(text) + 0.05) >= 4.5, (c, text)


def test_overview_does_not_wait_for_a_new_verify_batch(client, monkeypatch):
    import app.services.verify as sv
    import app.web.verify as wv

    calls = []

    def slow_assign(session):
        raise AssertionError("the Overview must not pick a batch while the owner waits")

    monkeypatch.setattr(sv, "assign", slow_assign)
    monkeypatch.setattr(wv, "_assign_later", lambda: calls.append(1))
    assert client.get("/manage/overview").status_code == 200
    assert calls == [1]  # prepared after the page was sent
