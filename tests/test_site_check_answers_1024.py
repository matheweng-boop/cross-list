"""The owner's answers to the 24 Oct 2026 site check: Browse products width, the Overview tile, touch targets, the
"Shortlist & cases" menu item, TAM hidden from guests, numbers right-aligned, RF band label contrast, and an Overview
that no longer waits for a new Verify next batch."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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
    assert "td.n, th.n { text-align: right; font-variant-numeric: tabular-nums; }" in CSS


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
