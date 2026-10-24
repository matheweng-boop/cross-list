"""Site check, 24 Oct 2026: old names from the menu restructure, internal link targets, dates, page titles, part
counts that must agree, and owner-only links for guests."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
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
    rule = css[css.index("body.guest main :is("):]
    rule = rule[: rule.index("}")]
    missing = [p for p in OWNER_PAGES if not p.startswith("/api/") and not p.endswith(".txt")
               and f'a[href^="{p}"]' not in rule]  # fmt: skip
    assert not missing


def test_guest_pages_are_marked(make_guest, owner):
    g, _ = make_guest()
    assert '<body class="shell guest">' in g.get("/business/method").text
    assert '<body class="shell">' in owner.get("/business/method").text
