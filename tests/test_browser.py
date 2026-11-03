"""Browser flow tests (24 Oct 2026): the pages the owner uses, clicked in a real Chromium against the app on a real
port.

The other tests read the server's HTML; these catch what only happens in the browser (a script that does not fill a
field, a button that does nothing, a console error, a page wider than a phone). Every test also fails on any console
error or uncaught page error, and when a page it visited scrolls sideways at 390 px. Select them with
``-m browser``, leave them out with ``-m "not browser"``; they skip when the image has no Chromium.
"""

import re
from urllib.parse import quote

import pytest

from tests.conftest import PAGE_TIMEOUT

expect = pytest.importorskip("playwright.sync_api").expect

pytestmark = pytest.mark.browser

PHONE = {"width": 390, "height": 844}
WIDE = {"width": 1180, "height": 900}  # the iPad held sideways, a small Windows window


class Watch:
    """Console errors, uncaught page errors and the pages visited by one test."""

    def __init__(self, base: str):
        self.base, self.errors, self.visited = base, [], []

    def attach(self, page):
        page.on("console", lambda m: m.type == "error" and self.errors.append(f"console: {m.text} ({page.url})"))
        page.on("pageerror", lambda e: self.errors.append(f"page error: {e} ({page.url})"))
        page.on("framenavigated", lambda f: f == page.main_frame and self._visit(f.url))
        return page

    def _visit(self, url: str):
        url = url.split("#")[0]
        if url.startswith(self.base) and url not in self.visited:
            self.visited.append(url)


def overflow(page) -> int:
    """How many pixels the page is wider than the window (0: no sideways scrolling)."""
    return page.evaluate("Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth)")


@pytest.fixture
def page(chromium, live_server):
    """A fresh browser tab on the live app; afterwards every visited page is opened again at 390 px wide."""
    watch = Watch(live_server)
    ctx = chromium.new_context(base_url=live_server, viewport=WIDE)
    pg = watch.attach(ctx.new_page())
    pg.set_default_timeout(PAGE_TIMEOUT)
    yield pg
    ctx.close()
    phone = chromium.new_context(viewport=PHONE, is_mobile=True, has_touch=True)
    tab = watch.attach(phone.new_page())
    wide = []
    for url in list(watch.visited):
        tab.goto(url, wait_until="load")
        if (px := overflow(tab)) > 1:
            wide.append(f"{url} is {px} px wider than a 390 px phone")
    phone.close()
    problems = watch.errors + wide
    if problems:
        pytest.fail("\n".join(problems), pytrace=False)


def test_the_checks_themselves_catch_errors_and_overflow(chromium, live_server):
    """The watcher sees a console error and an uncaught error, and a page wider than a phone is measured as such."""
    watch = Watch(live_server)
    ctx = chromium.new_context(viewport=PHONE)
    tab = watch.attach(ctx.new_page())
    tab.goto(live_server + "/healthz")
    tab.evaluate("""() => { console.error("boom"); setTimeout(() => { throw new Error("bang"); });
                            const d = document.createElement("div"); d.style.width = "900px"; d.textContent = "x";
                            document.body.append(d); }""")
    tab.wait_for_timeout(100)
    assert overflow(tab) > 400
    ctx.close()
    assert any("boom" in e for e in watch.errors) and any("bang" in e for e in watch.errors)
    assert watch.visited == [live_server + "/healthz"]


def go(page, path: str):
    r = page.goto(path, wait_until="load")
    assert r is not None and r.status == 200, (path, r and r.status)
    return r


def test_every_menu_page_opens_without_errors(page):
    """Every page in the menus and tabs: no console error, and (checked after the test) none wider than a phone."""
    from tests.test_blank_forms import menu_pages

    for path in menu_pages():
        go(page, path)
        assert page.locator("main h1").count() >= 1, path


# --- Products ---------------------------------------------------------------------------------------------------------
def test_price_estimate_picks_a_part_override_and_estimate(page):
    go(page, "/pricing/estimate")
    form = page.locator("form.pe-form")
    form.locator("input[name=name]").fill("Si47962")
    form.locator("input[name=name]").press("Tab")  # leaving the box, as after picking from the list
    pins = form.locator("input[name=pins]")
    pins.wait_for()
    expect(pins).to_have_value("56")  # filled at once, before any submit
    assert form.locator("select[name=family]").input_value() == "am_fm_tuner"
    assert form.locator("input[name=package]").input_value() == "QFN-56"
    for name in ("family", "package", "pins"):  # locked: the part data fills them, "Override" is the second option
        assert "pe-locked" in (form.locator(f"[name={name}]").get_attribute("class") or ""), name
    assert form.locator("input[name=package]").evaluate("e => e.readOnly")
    assert form.locator("input[name=pins]").evaluate("e => e.readOnly")
    assert page.locator(".pe-from[data-for=pins]").inner_text() == "(from the part data)"

    page.get_by_role("button", name="Override").click()
    assert not form.locator("input[name=package]").evaluate("e => e.readOnly")
    assert "pe-locked" not in (form.locator("select[name=family]").get_attribute("class") or "")
    other = form.locator("select[name=family] option").nth(0)
    value, label = other.get_attribute("value"), other.inner_text().split(" · ")[0].strip()
    assert value != "am_fm_tuner"
    form.locator("select[name=family]").select_option(value)
    form.locator("input[name=bq]").first.fill("1000")
    form.locator("input[name=bp]").first.fill("2.64")
    with page.expect_navigation():
        form.get_by_role("button", name="Estimate").click()
    result = page.locator("#price-model.pe-result h2")
    result.wait_for()
    assert label in result.inner_text()  # the family I picked, not the part data's
    assert "override=true" in page.url and f"family={value}" in page.url
    assert page.locator("form.pe-form select[name=family]").input_value() == value


def test_price_estimate_with_every_number_blank(page):
    go(page, "/pricing/estimate")
    form = page.locator("form.pe-form")
    for name in ("pins", "sop", "released"):
        form.locator(f"input[name={name}]").fill("")
    with page.expect_navigation():
        form.get_by_role("button", name="Estimate").click()
    assert page.locator("main h1").inner_text() == "Price estimate"
    assert "released=" in page.url
    assert "cannot use" not in page.content()


def test_search_lists_matches_as_you_type_and_on_find(page):
    go(page, "/")
    box = page.locator("#finder-search")
    box.press_sequentially("SA77", delay=30)
    page.locator("#suggestions .suggest-list li").first.wait_for()
    assert "SA77" in page.locator("#suggestions").inner_text()
    with page.expect_navigation():
        box.press("Enter")
    assert "/find" in page.url
    assert page.locator("main").get_by_role("link", name=re.compile("SA77")).count() >= 2


def test_part_walk_through_next_step(page):
    go(page, "/find?q=SA7741")
    part_url = page.url.split("?")[0]
    assert re.search(r"/parts/\d+$", part_url)
    go(page, part_url + "/walk")
    assert page.locator("#step-2").count() == 1 and page.locator("#step-3").count() == 0
    for n in (3, 4, 5):
        nxt = page.locator(".walk-next a")
        assert nxt.count() == 1 and nxt.inner_text().startswith(f"Next: {n}")
        with page.expect_navigation():
            nxt.click()
        assert f"upto={n}" in page.url
        expect(page.locator(f"#step-{n}")).to_be_visible()
        expect(page.locator(f"#step-{n}")).to_be_in_viewport()  # the page scrolls to the new step
    assert page.locator(".walk-next a").count() == 0  # the last step has no "Next"


def test_feedback_button_sends_and_confirms(page):
    go(page, "/parts")
    page.locator(".fb-open").click()
    panel = page.locator("#fb-panel")
    assert panel.is_visible()
    expect(panel.locator(".fb-where")).not_to_have_text(re.compile(r"^(…)?$"))
    panel.locator("textarea[name=text]").fill("Browser test: the filter row could be shorter.")
    panel.get_by_role("button", name=re.compile("^Send")).click()
    expect(panel.locator(".fb-msg")).to_contain_text("Thank you")


# --- Systems & applications -------------------------------------------------------------------------------------------
def test_application_library_system_then_sub_system(page):
    go(page, "/blocks")
    system = page.locator(".sys-pick a.fchip").nth(1)
    key = system.get_attribute("href").removeprefix("#area-")
    system.click()  # owner, 2 Nov 2026: jumps to the system and opens it, no reload
    expect(page.locator(f"details#area-{key}[open]")).to_have_count(1)
    card = page.locator(f"details#area-{key} .sys-sub", has=page.locator('a.sys-btn-dg[href^="/blocks?"]')).first
    sub_name = card.locator(".sys-sub-title").inner_text().strip()
    with page.expect_navigation():
        card.locator("a.sys-btn-dg").click()  # "▦ See the N block diagrams"
    assert f"system={key}" in page.url and "sub=" in page.url
    assert page.locator(".sys-pick a.fchip.on").get_attribute("href") == f"#area-{key}"
    heading = page.locator(f"details#area-{key}[open] h3.tpl-cat").first
    assert heading.is_visible() and heading.inner_text().startswith(sub_name)


def test_systems_library_systems_open_and_close(page):
    """Owner, 2 Nov 2026: each system is one closed line; a click opens its sub-systems and deep dives, a second click
    closes it; the buttons jump to a system and open it; /library#sys-<key> opens with that system expanded."""
    go(page, "/library")
    expect(page.locator("details.sys-block")).not_to_have_count(0)
    expect(page.locator("details.sys-block[open]")).to_have_count(0)  # all start closed
    auto = page.locator("details#sys-automotive")
    card = auto.locator(".sys-sub").first
    expect(card).to_be_hidden()
    auto.locator("summary").click()
    expect(card).to_be_visible()
    expect(auto.locator(".lib-card").first).to_be_visible()  # its deep dives
    auto.locator("summary").click()
    expect(card).to_be_hidden()
    button = page.locator('.sys-pick a[href="#sys-drones"]')
    button.click()
    drones = page.locator("details#sys-drones")
    expect(page.locator("details#sys-drones[open]")).to_have_count(1)
    expect(drones.locator("summary")).to_be_in_viewport()
    drones.locator("summary").click()  # closed again, then the same button (same hash) opens it once more
    expect(page.locator("details#sys-drones[open]")).to_have_count(0)
    button.click()
    expect(page.locator("details#sys-drones[open]")).to_have_count(1)
    go(page, "/blocks")
    go(page, "/library#sys-medical")  # an old link: opens with that system expanded
    expect(page.locator("details#sys-medical[open]")).to_have_count(1)
    expect(page.locator("details#sys-medical .sys-sub").first).to_be_visible()
    expect(page.locator("details.sys-block[open]")).to_have_count(1)


def test_block_diagram_library_opens_a_system_by_button_hash_and_query(page):
    """Owner, 2 Nov 2026: the Block diagram library opens and closes its systems like the Systems library; #area-,
    #sub- and ?system= open the right one."""
    go(page, "/blocks")
    expect(page.locator("details.sys-block[open]")).to_have_count(0)
    page.locator('.sys-pick a[href="#area-cellular"]').click()
    expect(page.locator("details#area-cellular[open]")).to_have_count(1)
    expect(page.locator("details#area-cellular .sys-sub").first).to_be_visible()
    page.locator("details#area-cellular > summary").click()
    expect(page.locator("details#area-cellular[open]")).to_have_count(0)
    go(page, "/library")
    go(page, "/blocks#sub-car-radio")  # a sub-system whose diagrams are not listed: its card, system open
    expect(page.locator("details#area-automotive[open]")).to_have_count(1)
    expect(page.locator("#card-automotive-car-radio")).to_be_in_viewport()
    go(page, "/blocks?system=drones")
    expect(page.locator("details#area-drones[open]")).to_have_count(1)
    expect(page.locator("#diagrams-drones")).to_be_visible()
    expect(page.locator("details.sys-block[open]")).to_have_count(1)
    go(page, "/blocks?system=automotive&sub=car-radio#sub-car-radio")
    expect(page.locator("#sub-car-radio")).to_be_in_viewport()


def test_cross_sell_by_system(page):
    """Owner, 2 Nov 2026: a grid of system buttons; the sub-systems appear as chips once a system is picked."""
    go(page, "/blocks/cross-sell")
    expect(page.locator(".xs-subs")).to_have_count(0)
    with page.expect_navigation():
        page.locator(".xs-sys").first.click()
    assert "system=" in page.url
    expect(page.locator(".xs-sys.on")).to_have_count(1)
    chip = page.locator(".xs-subs a.fchip").nth(1)  # the first sub-system (the first chip is "All of …")
    with page.expect_navigation():
        chip.click()
    assert "sub=" in page.url
    assert page.locator("main h2").first.is_visible()
    assert page.get_by_role("heading", name=re.compile("Our parts that go together")).is_visible()


def test_cross_sell_start_from_a_part(page):
    """Owner, 2 Nov 2026: By part is gone; type one of our part numbers in By system's box, see the systems that use
    its function, pick one and find the part highlighted there. An old By part link lands on the same list."""
    go(page, "/blocks/cross-sell")
    expect(page.locator("nav.page-tabs a", has_text="By part")).to_have_count(0)
    page.locator("#xs-part").fill("Si8641")
    with page.expect_navigation():
        page.locator("#part-box button[type=submit]").click()
    assert "part=Si8641" in page.url
    expect(page.locator(".xs-places .xs-sys-list li").first).to_be_visible()
    with page.expect_navigation():
        page.locator(".xs-sys-list li a").nth(1).click()  # the first sub-system of the first system
    assert "sub=" in page.url and "part=" in page.url
    expect(page.locator(".xs-note")).to_contain_text("highlighted")
    expect(page.locator("#parts-here tr.xs-hl .xs-you").first).to_be_visible()
    go(page, "/business/attach?fn=digital_isolator")
    assert "/blocks/cross-sell?fn=digital_isolator" in page.url
    expect(page.locator(".xs-sys-list")).to_be_visible()


def test_cross_sell_system_buttons_fit_side_by_side(page, chromium, live_server):
    """The system buttons sit side by side: at 390 px three per row in three short rows, nothing sideways, the
    sub-system chips right under them."""
    ctx = chromium.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    tab = ctx.new_page()
    tab.goto(live_server + "/blocks/cross-sell?system=automotive", wait_until="load")
    tops = tab.locator(".xs-sys").evaluate_all("bs => bs.map(b => Math.round(b.getBoundingClientRect().top))")
    assert len(tops) >= 9 and len(tops) / len(set(tops)) >= 3  # three or more per row
    grid = tab.locator(".xs-sys-grid").bounding_box()
    assert grid["x"] >= 0 and grid["x"] + grid["width"] <= 391 and grid["height"] < 200  # three short rows
    subs = tab.locator(".xs-subs").bounding_box()
    assert 0 <= subs["y"] - (grid["y"] + grid["height"]) < 30  # the sub-system chips right under the buttons
    assert overflow(tab) <= 1
    ctx.close()


def test_cross_sell_compact_parts_table(page, chromium, live_server):
    """Owner, 2 Nov 2026: one row per function (Function | Skyworks | Qorvo | Used in), three chips, the rest under
    "+N more" (opens on a tap, no script). At 390 px the function and "Used in" share a line and the two line cells sit
    side by side under it; no sideways scrolling."""
    go(page, "/blocks/cross-sell?system=cellular&aec=0")
    table = page.locator("#parts-here table")
    expect(table.locator("thead th")).to_have_count(4)
    row = page.locator("#parts-here tr.xs-row", has=page.locator("details.xs-more")).first
    more = row.locator("details.xs-more").first
    expect(more.locator(".aec-chip").first).to_be_hidden()
    more.locator("summary").click()
    expect(more).to_have_attribute("open", "")
    expect(more.locator(".aec-chip").first).to_be_visible()
    rows = table.locator("tbody tr").count()
    heights = table.locator("tbody tr").evaluate_all("rs => rs.map(r => r.getBoundingClientRect().height)")
    assert rows >= 20 and sorted(heights)[len(heights) // 2] < 70  # compact: most rows one line of chips
    ctx = chromium.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    tab = ctx.new_page()
    tab.goto(live_server + "/blocks/cross-sell?system=cellular&aec=0", wait_until="load")
    first = tab.locator("#parts-here tbody tr").first
    fn = first.locator("th").bounding_box()
    used = first.locator("td.xs-used").bounding_box()
    sky, qor = (first.locator(f"td.ln-{k}").bounding_box() for k in ("skyworks", "qorvo"))
    assert abs(fn["y"] - used["y"]) < 4 and used["x"] > fn["x"]  # one line: function, then "Used in"
    assert abs(sky["y"] - qor["y"]) < 4 and qor["x"] > sky["x"] >= 0 and sky["y"] > fn["y"]  # the lines side by side
    assert qor["x"] + qor["width"] <= 391
    box = tab.locator("#parts-here table").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 391
    assert overflow(tab) <= 1
    ctx.close()


def test_new_systems_in_the_libraries_and_cross_sell(page):
    """Owner, 25 Oct 2026: the diagrams under Other became new systems. The pages are opened again at 390 px by the
    fixture (no sideways scrolling)."""
    go(page, "/library")
    assert page.locator("#sys-aerospace").is_visible()
    go(page, "/blocks?system=aerospace")
    assert page.locator(".sys-pick a.fchip.on").inner_text().startswith("Aerospace")
    go(page, "/blocks?system=consumer&sub=connectivity")
    assert page.locator("#sub-connectivity").is_visible()
    go(page, "/blocks/cross-sell?sel=aerospace:satcom")
    assert page.get_by_role("heading", name=re.compile("Our parts that go together")).is_visible()
    go(page, "/blocks/cross-sell?sel=industrial")
    assert page.locator("main h2").first.is_visible()


def test_sub_system_card_buttons_open_the_deep_dive_and_the_diagrams(page):
    """Owner, 2 Nov 2026: a sub-system card has two clear buttons, "📖 Read the deep dive" and "▦ See the N block
    diagrams" (the editor is visited last: leaving a library diagram asks before unload)."""
    go(page, "/library#sys-automotive")
    card = page.locator("#card-automotive-car-access")
    expect(card.locator("a.sys-btn")).to_have_count(2)
    with page.expect_navigation():
        card.get_by_role("link", name="📖 Read the deep dive").click()
    assert page.url.endswith("/library/auto_uwb")
    go(page, "/blocks")
    expect(page.locator("#diagrams")).to_be_in_viewport()  # the summary sits at the top
    page.locator(".sys-pick a.fchip").first.click()  # opens the first system
    card = page.locator("details.sys-block[open] .sys-sub", has=page.locator('a.sys-btn-dg[href^="/blocks?"]')).first
    expect(card.locator("a.sys-btn-dg")).to_have_text(re.compile(r"^▦ See the \d+ block diagrams$"))
    with page.expect_navigation():
        card.locator("a.sys-btn-dg").click()
    sub = re.search(r"sub=([a-z0-9-]+)", page.url).group(1)
    expect(page.locator(f"#sub-{sub}")).to_be_in_viewport()
    with page.expect_navigation():
        page.locator(f"#sub-{sub} + .tpl-grid a.tpl-card").first.click()
    assert "/blocks/new?template=" in page.url


def test_where_am_i_strip_and_breadcrumbs(page):
    """Owner, 2 Nov 2026: a strip on the four pages highlights where you are, with one line on what the page shows; a
    deep dive and a diagram show "Automotive › UWB in the car" and link to the other view of the same sub-system."""
    page.on("dialog", lambda d: d.accept())  # a library diagram opens as an unsaved copy: leaving it asks first
    here = page.locator('nav.where [aria-current="page"]')
    what = page.locator("nav.where .where-what")
    go(page, "/library")
    expect(here).to_have_text("1 Systems library")
    expect(what).to_have_text("The map of systems and the sub-systems they are made of.")
    with page.expect_navigation():
        page.locator("nav.where").get_by_role("link", name="3 Block diagrams").click()
    expect(here).to_have_text("3 Block diagrams")
    expect(what).to_contain_text("Real block diagrams from public sources")
    go(page, "/library/auto_uwb")
    expect(here).to_have_text("2 Deep dive")
    expect(what).to_contain_text("A written explainer for one sub-system")
    crumbs = page.locator("nav.crumbs")
    expect(crumbs).to_contain_text("Automotive")
    expect(crumbs).to_contain_text("UWB in the car")
    with page.expect_navigation():
        crumbs.get_by_role("link", name=re.compile(r"See its block diagrams \(\d+\)")).click()
    assert "system=automotive" in page.url and "sub=car-access" in page.url
    expect(page.locator("details#area-automotive[open]")).to_have_count(1)
    expect(page.locator("#sub-car-access")).to_be_in_viewport()
    with page.expect_navigation():
        page.locator("#sub-car-access + .tpl-grid a.tpl-card").first.click()
    expect(here).to_have_text("3 Block diagrams")
    expect(page.locator("nav.crumbs")).to_contain_text("UWB in the car")
    with page.expect_navigation():
        page.locator("nav.crumbs").get_by_role("link", name="📖 Read the deep dive").click()
    assert page.url.endswith("/library/auto_uwb")
    with page.expect_navigation():
        page.locator("nav.where").get_by_role("link", name="4 Your workspace").click()
    assert page.url.endswith("/blocks/new")
    expect(here).to_have_text("4 Your workspace")
    expect(what).to_have_text("Your own diagrams, to build, edit and save.")
    expect(page.locator("nav.crumbs")).to_have_count(0)


def test_efuse_key_applications_table_fits_desktop_and_phone(page, chromium, live_server):
    """Owner, 25 Oct 2026: the eFuse key-applications table: short cells without wrapping at 1280 px, cards at 390 px
    (no sideways scrolling of the page); "More" opens the details and the diagram count opens them too."""
    path = "/business/evidence/efuse_hotswap"
    page.set_viewport_size({"width": 1280, "height": 900})
    go(page, path)
    table = page.locator("table.ka-table")
    assert table.evaluate("t => t.scrollWidth <= t.parentElement.clientWidth + 1")
    heights = table.locator("tr.ka-main").evaluate_all("rows => rows.map(r => r.getBoundingClientRect().height)")
    assert max(heights) < 80, heights  # one or two lines per row, not a wall of wrapped text
    page.locator("a.ka-n").first.click()
    expect(page.locator(".ka-more details").first).to_have_attribute("open", "")
    ctx = chromium.new_context(viewport={"width": 390, "height": 844}, is_mobile=True)
    tab = ctx.new_page()
    tab.goto(live_server + path, wait_until="load")
    assert overflow(tab) <= 1
    box = tab.locator("table.ka-table").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 391
    assert tab.locator("tr.ka-main th").first.evaluate("e => getComputedStyle(e).display") == "block"
    ctx.close()


def test_cross_sell_automotive_together_here_then_portfolio_tab(page):
    """Owner, 25 Oct 2026: pick Automotive on Cross-sell, see the Skyworks + Qorvo pairs there, open the portfolio tab
    with the system kept and its pairs marked, and come back to By system."""
    go(page, "/blocks/cross-sell")
    with page.expect_navigation():
        page.locator(".xs-sys", has_text="Automotive").click()
    block = page.locator("#together")
    assert block.get_by_role("heading", name=re.compile("Skyworks \\+ Qorvo together here")).is_visible()
    assert block.locator(".pf-syn-card").count() >= 5
    tab = page.locator("nav.page-tabs a", has_text="Skyworks + Qorvo portfolio")
    assert "system=automotive" in tab.get_attribute("href")
    with page.expect_navigation():
        tab.click()
    assert "/portfolio?system=automotive" in page.url
    assert page.locator(".pf-from").is_visible() and page.locator(".pf-syn-card.pf-here").count() >= 1
    with page.expect_navigation():
        page.locator("nav.page-tabs a", has_text="By system").click()
    assert "system=automotive" in page.url and page.locator("#together").is_visible()


def test_cross_sell_parts_table_and_automotive_filter(page):
    """Owner, 24-25 Oct 2026: the Skyworks and Qorvo parts table tops the selection; on Automotive the
    "Automotive-qualified only" filter is on (AEC-Q chips only, the hidden count shown), one click shows every part
    with its "not automotive" mark, and a pair link jumps to its card. Both views are checked at 390 px too."""
    go(page, "/blocks/cross-sell?system=automotive&sub=powertrain")
    table = page.locator("#parts-here")
    expect(table.get_by_role("heading", name=re.compile("Skyworks and Qorvo parts here"))).to_be_visible()
    toggle = page.get_by_role("button", name="Automotive-qualified only")
    expect(toggle).to_have_attribute("aria-pressed", "true")
    expect(table.locator(".aec-no")).to_have_count(0)
    with page.expect_navigation():
        toggle.click()
    assert "aec=0" in page.url
    expect(page.get_by_role("button", name="Automotive-qualified only")).to_have_attribute("aria-pressed", "false")
    expect(page.locator("#parts-here .aec-yes").first).to_be_visible()
    link = page.locator("#parts-here a.xs-pair").first
    if link.count():
        target = link.get_attribute("href")
        link.click()
        expect(page.locator(target)).to_be_in_viewport()


def go_built_on_first_use(page, path: str):
    """A page whose data (the Automotive map) is built on first use: on a fresh test server, next to the start-up
    warm-up, that can take longer than the page timeout."""
    r = page.goto(path, wait_until="load", timeout=90_000)
    assert r is not None and r.status == 200, (path, r and r.status)


def test_automotive_map_letter_column(page):
    """Item 10 (owner, 2 Nov 2026): in By application each letter sits in its own left column with its meaning, the
    function chips wrap only in the right column, and a PC shows about two cards per row (the 390 px check follows)."""
    go_built_on_first_use(page, "/business/automotive")
    rows = page.locator(".am-app .am-row")
    assert rows.count() > 5
    tabs = page.locator(".lv-tabs button")
    expect(tabs).to_have_count(5)  # owner, 2 Nov 2026: one letter at a time, A (Sell now) first where there is one
    first = page.locator('.lv-tabs button[aria-pressed="true"]')
    expect(first).to_have_count(1)
    lv = first.get_attribute("data-lv")
    expect(page.locator(f'.am-app .am-row[data-lv]:not([data-lv="{lv}"])').first).to_be_hidden()
    page.locator('.lv-tabs button[data-lv="gap"]').click()
    expect(page.locator('.lv-tabs button[data-lv="gap"]')).to_have_attribute("aria-pressed", "true")
    expect(page.locator(".am-app .am-lv", has_text="Gap").first).to_be_visible()
    expect(page.locator('.am-app .am-row[data-lv="gap"]').first).to_be_visible()
    gaps = page.evaluate("""() => [...document.querySelectorAll('.am-app .am-row:not([hidden])')].map(r => {
        const lv = r.querySelector('.am-lv').getBoundingClientRect();
        return Math.min(...[...r.querySelectorAll('.am-fnchip')].map(c => c.getBoundingClientRect().left)) - lv.right;
    })""")
    assert min(gaps) > 0  # no chip ever wraps under the letter
    tops = page.evaluate("[...document.querySelectorAll('.am-app')].slice(0, 2).map(e => e.offsetTop)")
    assert tops[0] == tops[1]  # two cards side by side on a PC
    page.goto("/business/automotive?view=apps#app-bms", wait_until="load")
    expect(page.locator("#app-bms")).to_be_in_viewport()


def test_car_explorer_area_button_opens_its_list(page):
    """Item 11 (owner, 2 Nov 2026): the Car explorer loads (the 3D car where the browser has WebGL, else a short note);
    on the car a click on an area flies in and opens its list, "← Whole car" closes it; an area button below the car
    opens its list with letters, "+N more" and links (the 390 px check follows)."""
    go_built_on_first_use(page, "/business/car-explorer")
    if page.evaluate("!!document.createElement('canvas').getContext('webgl')"):
        expect(page.locator("#ce-stage")).to_have_attribute("data-ready", "1")
        x, y = page.evaluate("carExplorer.where('roof')")
        page.mouse.click(x, y)
        expect(page.locator("#ce-area-roof")).to_be_visible()
        expect(page.locator("#ce-area-roof").get_by_role("heading", name="V2X")).to_be_visible()
        page.get_by_role("button", name="← Whole car").click()
        expect(page.locator("#ce-area-roof")).to_be_hidden()
        expect(page.locator("#ce-back")).to_be_hidden()
    else:
        expect(page.locator("#ce-no3d")).to_be_visible()
    page.get_by_role("link", name="High-voltage battery").click()
    panel = page.locator("#ce-area-battery")
    expect(panel).to_be_visible()
    expect(panel.get_by_role("heading", name=re.compile("Battery systems"))).to_be_visible()
    expect(panel.locator(".am-row .am-lv").first).to_be_visible()
    blocks_link = panel.get_by_role("link", name=re.compile("^Block diagrams"))
    expect(blocks_link).to_have_attribute("href", "/blocks?system=automotive&sub=battery-power")
    expect(panel.locator(".lv-tabs button")).to_have_count(5)
    panel.locator('.lv-tabs button[data-lv="gap"]').click()  # the gaps: the longest list
    expect(panel.locator('.am-row[data-lv="gap"]').first).to_be_visible()
    more = panel.locator('.am-row[data-lv="gap"] details.ce-more').first
    hidden = more.locator(".am-fnchip").first
    expect(hidden).to_be_hidden()
    more.locator("summary").click()
    expect(hidden).to_be_visible()
    assert "area=battery" in page.url


def test_car_explorer_without_webgl(page):
    """Without WebGL (old devices, some headless browsers): no 3D car and no three.js download, a short note instead,
    and the area buttons still open their lists, without a console error."""
    page.add_init_script("""(() => { const get = HTMLCanvasElement.prototype.getContext;
        HTMLCanvasElement.prototype.getContext = function (type, ...rest) {
            return /webgl/i.test(type) ? null : get.call(this, type, ...rest); }; })();""")
    asked = []
    page.on("request", lambda r: asked.append(r.url))
    go_built_on_first_use(page, "/business/car-explorer")
    expect(page.locator("#ce-no3d")).to_be_visible()
    expect(page.locator("#ce-stage")).to_be_hidden()
    page.get_by_role("link", name="Doors, mirrors and access").click()
    expect(page.locator("#ce-area-doors").get_by_role("heading", name="Digital key & car access")).to_be_visible()
    assert not [u for u in asked if "/vendor/three/" in u or "car_explorer.js" in u]


def test_automotive_focus_goals_folds_and_links(page):
    """Automotive focus (owner, 3 Nov 2026): from the Future growth menu, six goal cards (two or more per row on an
    iPad held sideways), "Parts and diagrams" and "How these were picked" open on a tap, a "why" link leads to its
    page (the 390 px check follows)."""
    go(page, "/business/reports")
    page.locator("nav").get_by_role("link", name="Automotive focus").first.click()
    page.wait_for_url("**/business/automotive-focus", timeout=90_000)
    cards = page.locator(".af-card")
    expect(cards).to_have_count(6)
    tops = page.evaluate("[...document.querySelectorAll('.af-card')].slice(0, 2).map(e => e.offsetTop)")
    assert tops[0] == tops[1]  # side by side
    how = page.locator("#af-how")
    expect(how.locator("li").first).to_be_hidden()
    how.locator("summary").click()
    expect(how.locator("li").first).to_be_visible()
    more = cards.first.locator("details.af-more")
    if more.count():
        more.locator("summary").click()
        expect(more.locator("a").first).to_be_visible()
    link = cards.first.locator(".af-why a").first
    href = link.get_attribute("href")
    link.click()
    page.wait_for_load_state("load")
    assert href.split("?")[0].split("#")[0] in page.url


def test_rf_coverage_why_it_could_matter(page, chromium, live_server):
    """Owner, 2 Nov 2026: each gap row says why it could matter, with the applications linked; on a phone the sentence
    is a second line under the row and the table is not wider than the screen."""
    go(page, "/business/rf-coverage")
    # owner, 3 Nov 2026: one row per function; its bands (each with its own sentence) open under it
    page.locator("details.vg-subs > summary").first.click()
    why = page.locator("table.vg-table td.rf-why").first
    expect(why).to_contain_text("Needed by")
    link = why.locator("a").first
    with page.expect_navigation():
        link.click()
    assert "/business/applications/" in page.url
    ctx = chromium.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    tab = ctx.new_page()
    tab.goto(live_server + "/business/rf-coverage", wait_until="load")
    row = tab.locator("table.rf-gaps tbody tr").first
    first, sentence = row.locator("td").first.bounding_box(), row.locator("td.rf-why").bounding_box()
    assert sentence["y"] > first["y"] + 5 and sentence["x"] < 40  # its own line, from the left edge
    box = tab.locator("table.rf-gaps").first.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= 391
    assert overflow(tab) <= 1
    ctx.close()


# --- Engineering knowledge --------------------------------------------------------------------------------------------
def test_rf_bands_type_and_application_chips_change_the_chart(page):
    go(page, "/rf-bands")
    chart = page.locator("#rbt-chart")
    chart.locator("g").first.wait_for(state="attached")
    before = chart.inner_html()
    chip = page.locator(".rbt-chip").first
    pressed = chip.get_attribute("aria-pressed")
    chip.click()
    assert chip.get_attribute("aria-pressed") != pressed
    after_type = chart.inner_html()
    assert after_type != before
    app = page.locator(".rbt-apps [data-app]").nth(1)
    app.click()
    assert app.get_attribute("aria-pressed") == "true"
    assert chart.inner_html() != after_type
    assert page.locator(".rbt-list").inner_text().strip()


def pick_visual(page, vid: str):
    """Open a visual the way a person does (owner, 2 Nov 2026): its tab, its drop-down line, then its title."""
    link, inner = page.locator(f"#vz-nav a[data-id='{vid}']"), page.locator(f"a[data-id='{vid}']")
    tab = page.locator("#vz-nav .vz-tp", has=inner).get_attribute("aria-labelledby")
    page.locator(f"#{tab}").click()
    line = page.locator("#vz-nav details.vz-sub", has=inner)
    if line.get_attribute("open") is None:
        line.locator("summary").click()
    link.click()


def test_every_visual_moves_without_errors(page):
    go(page, "/visuals")
    links = page.locator("#vz-nav a[data-id]")
    ids = [links.nth(i).get_attribute("data-id") for i in range(links.count())]
    assert len(ids) > 10
    stuck, total = [], 0
    for vid in ids:
        pick_visual(page, vid)
        expect(page.locator("#vz-nav a.on")).to_have_attribute("data-id", vid)
        panel = page.locator("#vz-panel")
        before = panel.inner_html()
        moved = panel.evaluate("""p => {
          let n = 0;
          p.querySelectorAll('input[type=range]').forEach(r => {
            r.value = r.value === r.max ? r.min : r.max; r.dispatchEvent(new Event('input', {bubbles: true}));
            r.dispatchEvent(new Event('change', {bubbles: true})); n++;
          });
          p.querySelectorAll('select').forEach(s => {
            if (s.options.length < 2) return;
            s.selectedIndex = (s.selectedIndex + 1) % s.options.length;
            s.dispatchEvent(new Event('change', {bubbles: true})); s.dispatchEvent(new Event('input', {bubbles: true}));
            n++;
          });
          return n;
        }""")
        total += moved
        if moved and panel.inner_html() == before:
            stuck.append(vid)
    assert not stuck, f"controls moved but nothing changed in: {stuck}"
    assert total > len(ids)  # most visuals have several controls


def test_hex_visual_converts_flips_bits_and_follows_the_word_size(page):
    """Owner 24 Oct 2026: the hex / binary visual. Typing in one box fills the others, a clicked bit flips, the word
    size changes the signed reading, and a value too big for the word is refused."""
    go(page, "/visuals#hex")
    panel = page.locator("#vz-panel")
    expect(panel.locator("h2")).to_have_text("Hex, binary and registers")
    box = {k: panel.locator(f'[data-hx="{k}"]') for k in ("16", "2", "u", "s", "8")}
    box["16"].fill("0xFF")
    expect(box["u"]).to_have_value("255")
    expect(box["2"]).to_have_value("1111 1111")
    expect(box["s"]).to_have_value("-1")
    expect(panel.locator(".vz-kpis")).to_contain_text("0xFF")
    bit7 = panel.locator('.hx-bit[data-bit="7"]')
    expect(bit7).to_have_attribute("aria-pressed", "true")
    bit7.click()
    expect(panel.locator('.hx-bit[data-bit="7"]')).to_have_attribute("aria-pressed", "false")
    expect(box["16"]).to_have_value("0x7F")
    panel.locator('select[data-k="w"]').select_option("16")
    box["s"].fill("-1")
    expect(box["16"]).to_have_value("0xFFFF")
    expect(panel.locator(".hx-reg .hx-bit")).to_have_count(16)
    expect(panel.locator(".vz-more")).to_contain_text("0xFFFF")
    box["u"].fill("70000")
    expect(box["u"]).to_have_attribute("aria-invalid", "true")
    expect(panel.locator(".hx-msg")).to_contain_text("Does not fit in 16 bits")
    panel.locator(".hx-fields").fill("[15:8] HIGH, [3:0] LOW")
    expect(panel.locator(".hx-t").first).to_contain_text("HIGH")
    slider = panel.locator('input[data-k="bit"]')
    slider.evaluate("r => { r.value = 5; r.dispatchEvent(new Event('input', {bubbles: true})); }")
    expect(panel.locator(".vz-more")).to_contain_text("Worked example, bit 5")


def test_frequency_visuals_draw_the_bands_as_ranges(page):
    """Owner 24 Oct 2026: "FM is not only at 100 MHz". The wavelength chart shades AM, FM and DAB as ranges, the FM
    intermodulation chart shades the FM band by region, and the noise-figure visual shows the band strip."""
    go(page, "/visuals#wave")
    chart = page.locator("#vz-panel .vz-chart")
    for label in ("AM", "FM", "DAB", "GNSS", "UWB"):
        expect(chart.locator("text.vz-bl", has_text=label).first).to_be_attached()
    expect(page.locator("#vz-panel .vz-more")).to_contain_text("76–108 MHz")
    pick_visual(page, "fmim")
    for label in ("Japan", "most countries", "OIRT"):
        expect(page.locator("#vz-panel .vz-chart text.vz-bl", has_text=label).first).to_be_attached()
    pick_visual(page, "nf")
    expect(page.locator("#vz-panel .vz-strip .vz-sbar").first).to_be_attached()


def test_dbm_ladder_bands_explain_what_moves_them(page):
    """Owner 2 Nov 2026 ("BLE sensitivity is a range, not a dotted line at one value"): the ladder draws each rung as a
    band; a tap, a hover or the keyboard shows its range, what moves it and the source; the slider picks the nearest."""
    go(page, "/visuals#dbm")
    panel = page.locator("#vz-panel")
    bands = panel.locator(".dl-b")
    expect(bands).to_have_count(14)
    expect(panel.locator(".dl-ln")).to_have_count(4)  # noise in 1 MHz, 1 mW, 1 W and the slider
    expect(panel.locator(".vz-chartwrap")).to_be_hidden()
    ble = panel.locator('.dl-b[data-dl="BLE sensitivity"]')
    ble.click()
    expect(ble).to_have_attribute("aria-pressed", "true")
    info = panel.locator(".dl-info")
    expect(info.locator("h4")).to_have_text("BLE sensitivity")
    expect(info).to_contain_text("−105 dBm to −70 dBm, typical −97 dBm")
    expect(info).to_contain_text("What moves it")
    expect(info.locator('a[href*="bluetooth.com"]')).to_have_count(1)
    panel.locator('.dl-b[data-dl="Radar transmitter (peak)"]').hover()
    expect(info.locator("h4")).to_have_text("Radar transmitter (peak)")
    expect(info).to_contain_text("BizDev estimate (est)")
    panel.locator('.dl-b[data-dl="Wi-Fi client transmitter"]').focus()
    page.keyboard.press("Tab")  # the keyboard moves on to the next band, which explains itself
    expect(info.locator("h4")).to_have_text("Phone transmitter (LTE / 5G)")
    expect(panel.locator('.dl-b[data-dl="Phone transmitter (LTE / 5G)"]')).to_be_focused()
    slider = panel.locator('input[data-k="p"]')
    slider.evaluate("r => { r.value = -128; r.dispatchEvent(new Event('input', {bubbles: true})); }")
    expect(info.locator("h4")).to_have_text("GNSS signal at the antenna")
    expect(panel.locator(".vz-kpis")).to_contain_text("GNSS signal at the antenna")
    panel.locator('select[data-k="mode"]').select_option("blocker")
    expect(panel.locator(".vz-chartwrap")).to_be_visible()
    expect(panel.locator(".dl-b")).to_have_count(0)


def test_fm_intermod_answers_yes_or_no_and_shows_the_fixes(page):
    """Owner 2 Nov 2026: "here's the tuned station, here's strong station A and strong station B; is this an intermod
    product of that?" The verdict gives the arithmetic; A and B move by keyboard and by dragging; a fix is tried."""
    go(page, "/visuals#fmim")
    panel = page.locator("#vz-panel")
    verdict = panel.locator(".fm-verdict")
    expect(verdict).to_contain_text("Yes, this is an intermod product: 2 × 91.0 − 89.5 = 92.5 MHz, exactly your")
    expect(verdict).to_contain_text("6 dB louder than your station")
    expect(panel.locator(".fm-svg .fm-gh.hit")).to_have_count(1)
    expect(panel.locator(".fm-pairs")).to_contain_text("2 × 91.0 − 89.5 = 92.5 MHz")
    a = panel.locator('.fm-svg [data-fk="f1"]')
    expect(a).to_have_attribute("role", "slider")
    a.focus()
    page.keyboard.press("ArrowRight")  # A to 91.1 MHz: the ghost moves to the next channel
    expect(verdict).to_contain_text("Next door: 2 × 91.1 − 89.5 = 92.7 MHz")
    expect(panel.locator('input[data-k="f1"]')).to_have_value("91.1")
    expect(panel.locator('.fm-svg [data-fk="f1"]')).to_be_focused()  # the keyboard keeps its place
    page.keyboard.press("ArrowLeft")
    expect(verdict).to_contain_text("exactly your station")
    b = panel.locator('.fm-svg [data-fk="f2"] .fm-st')
    box, svg = b.bounding_box(), panel.locator(".fm-svg").bounding_box()
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
    page.mouse.down()
    page.mouse.move(svg["x"] + svg["width"] * 0.8, box["y"] + box["height"] / 2, steps=5)
    page.mouse.up()
    expect(verdict).to_contain_text("No: the products land on")
    assert float(panel.locator('input[data-k="f2"]').input_value()) > 100
    panel.locator(".vz-pre", has_text="A ghost on your station").click()
    expect(verdict).to_contain_text("exactly your station")
    lin = panel.locator('[data-fix="lin"]')
    lin.click()
    expect(panel.locator('[data-fix="lin"]')).to_have_attribute("aria-pressed", "true")
    expect(panel.locator('[data-fix="lin"]')).to_be_focused()
    expect(verdict).to_contain_text("14 dB below your station")
    panel.locator('[data-fix="att"]').click()
    expect(verdict).to_contain_text("34 dB below your station → harmless")
    expect(panel.locator(".fx-card.on")).to_have_count(2)
    expect(panel.locator(".fm-fix")).to_contain_text("not close neighbours")
    panel.locator(".vz-fmlist").fill("90.0, 91.0, 92.0")
    expect(panel.locator(".fm-pairs")).to_contain_text("2 × 91.0 − 89.5 = 92.5 MHz")
    fold = panel.locator("details.vz-fold")
    expect(fold.locator("summary")).to_have_text(
        "Show the whole picture: every product, the image and the FM band by region")
    fold.locator("summary").click()
    expect(fold.locator(".vz-chart")).to_be_visible()
    expect(panel.locator(".vz-im")).to_contain_text("Half-IF spur")


def test_ip3_trade_off_meter_scenarios_and_textbook_chart(page):
    """Owner 2 Nov 2026: "what am I actually trading off with linearity?" More gain: the signal turns red (drowned by
    distortion); more IP3 brings it back and costs current; ready-made scenarios; the textbook chart folded."""
    go(page, "/visuals#ip3")
    panel = page.locator("#vz-panel")
    verdict = panel.locator(".ip-verdict")
    expect(verdict).to_contain_text("Your signal is heard")
    expect(panel.locator(".tm-row")).to_have_count(3)
    expect(panel.locator(".ip-try")).to_contain_text("raise the gain until the red appears")

    def move(k, value):
        panel.locator(f'input[data-k="{k}"]').evaluate(
            f"r => {{ r.value = {value}; r.dispatchEvent(new Event('input', {{bubbles: true}})); }}")

    move("g", 40)
    expect(verdict).to_contain_text("Your signal is lost: drowned by distortion")
    expect(panel.locator(".ip-svg .ip-w.lost")).to_have_count(1)
    expect(panel.locator(".ip-svg")).to_contain_text("your signal is lost")
    move("oip3", 45)
    expect(verdict).to_contain_text("Your signal is heard")
    expect(panel.locator(".tm-row.t-cur")).to_contain_text("56.6 mA")  # 10 mA × 2^((45 − 20) / 10), est
    panel.locator(".vz-pre", has_text="Car FM next to a strong local station").click()
    expect(panel.locator(".ip-cap")).to_contain_text("Car FM next to a strong local station")
    expect(verdict).to_contain_text("Your signal is lost")
    expect(panel.locator(".vz-pre-note")).to_contain_text("Si4734/35")
    panel.locator(".vz-pre", has_text="5G phone near a base station").click()
    expect(verdict).to_contain_text("Your signal is heard")
    fold = panel.locator("details.vz-fold")
    expect(fold.locator(".vz-chart")).to_be_hidden()
    fold.locator("summary", has_text="Show the textbook IP3 chart").click()
    expect(fold.locator(".vz-chart polyline")).to_have_count(2)


def test_uwb_positioning_page_visuals_follow_sliders_drags_taps_and_keys(page):
    """Owner 2 Nov 2026: two-way ranging, TDoA, lightweight TDoA and PDoA on one page, each with a live visual that
    works with a mouse, a finger (tap) and the keyboard; the same visuals are on Interactive visuals under UWB."""
    go(page, "/engineering/uwb_positioning")
    slide = "(r, v) => { r.value = v; r.dispatchEvent(new Event('input', {bubbles: true})); }"
    kpi = lambda box, label: box.locator(".vz-kpi", has_text=re.compile(label)).locator("b")  # noqa: E731
    for vid in ("uwbtwr", "uwbtdoa", "uwbltdoa", "uwbpdoa"):
        expect(page.locator(f'[data-uwp="{vid}"] .vz-kpi').first).to_be_visible()

    twr = page.locator('[data-uwp="uwbtwr"]')  # longer reply: single-sided error grows, double-sided stays tiny
    ss = kpi(twr, "^Single-sided error")
    before = ss.inner_text()
    twr.locator('input[data-k="r1"]').evaluate(slide, 1000)
    expect(ss).not_to_have_text(before)
    expect(kpi(twr, "^Double-sided error")).to_contain_text("µm")
    twr.locator(".uwp-play").click()
    expect(twr.locator(".uwp-play")).to_have_text("▶ Play again", timeout=15000)
    expect(twr.locator(".uwp-ladder text", has_text="t6")).to_be_attached()

    tdoa = page.locator('[data-uwp="uwbtdoa"]')
    where = kpi(tdoa, "^Tag")
    start = where.inner_text()
    tdoa.locator('[data-h="tag"]').focus()
    page.keyboard.press("ArrowRight")
    expect(where).not_to_have_text(start)
    expect(tdoa.locator('[data-h="tag"]')).to_be_focused()  # the redraw keeps the keyboard focus
    after_key = where.inner_text()
    plan = tdoa.locator(".uwp-plan").bounding_box()
    page.mouse.click(plan["x"] + plan["width"] * 0.75, plan["y"] + plan["height"] * 0.55)  # a tap places the tag
    expect(where).not_to_have_text(after_key)
    pair = kpi(tdoa, "^Anchor 2 − anchor 1")
    first = pair.inner_text()
    a2 = tdoa.locator('[data-h="a1"] rect').bounding_box()
    page.mouse.move(a2["x"] + a2["width"] / 2, a2["y"] + a2["height"] / 2)
    page.mouse.down()
    page.mouse.move(a2["x"] - 60, a2["y"] + 40, steps=6)
    page.mouse.up()
    expect(pair).not_to_have_text(first)
    spread = kpi(tdoa, "^Position spread")
    s0 = spread.inner_text()
    tdoa.locator('input[data-k="sync"]').evaluate(slide, 2)
    expect(spread).not_to_have_text(s0)
    tdoa.locator('select[data-k="mode"]').select_option("dl")
    expect(kpi(tdoa, "^Computes the position")).to_have_text("the tag itself")

    light = page.locator('[data-uwp="uwbltdoa"]')
    got = kpi(light, "^Blinks that get through")
    g0 = got.inner_text()
    light.locator('input[data-k="tags"]').evaluate(slide, 1000)
    expect(got).not_to_have_text(g0)
    expect(light.locator(".uwp-light text", has_text="slots full")).to_be_attached()

    pd = page.locator('[data-uwp="uwbpdoa"]')
    pd.locator('input[data-k="d"]').evaluate(slide, 40)
    expect(kpi(pd, "^Spacing d / λ")).to_contain_text("ambiguous")
    expect(pd.locator(".uwp-pdoa text", has_text="also fits").first).to_be_attached()
    pd.locator('[data-h="tag"]').focus()
    page.keyboard.press("ArrowRight")
    expect(pd.locator('input[data-k="th"]')).to_have_value("31")
    expect(kpi(pd, "^Angle read back")).to_be_visible()

    go(page, "/visuals#uwbpdoa")  # the same visual inside the engine on /visuals
    expect(page.locator("#vz-panel h2")).to_contain_text("phase difference of arrival")
    expect(page.locator("#vz-panel .uwp-pdoa")).to_be_attached()
    page.locator('#vz-panel input[data-k="th"]').evaluate(slide, 70)
    expect(page.locator("#vz-panel .vz-kpi", has_text="Angle read back")).to_contain_text("70")


def test_visuals_tabs_drop_downs_one_visual_deep_links_and_search(page):
    """Owner, 2 Nov 2026: three tabs; under the chosen tab each sub-group is one closed line with a count; opening it
    lists only the titles; a title shows only that visual; #id deep links open the right tab, line and visual; a
    search box finds a visual by its title or a word."""
    go(page, "/visuals")
    tabs = page.locator("#vz-tabbar [role=tab]")
    expect(tabs).to_have_count(3)
    for i, label in enumerate(("RF & wireless", "Power & isolation", "Basics")):
        expect(tabs.nth(i)).to_contain_text(label)
    expect(tabs.nth(0)).to_have_attribute("aria-selected", "true")
    rf = page.locator("#vz-tp-rf")
    lines = ("RF links", "Receivers", "Matching and filters", "Broadcast radio", "GNSS", "UWB", "Timing")
    expect(rf.locator("details.vz-sub > summary")).to_have_text([re.compile(rf"^{s} · \d+$") for s in lines])
    expect(rf.locator("details.vz-sub[open]")).to_have_count(0)  # every line starts closed
    expect(page.locator("#vz-panel .vz-hint")).to_be_visible()  # no visual until one is picked
    radio = rf.locator("details.vz-sub").filter(has=page.locator("summary", has_text="Broadcast radio"))
    radio.locator("summary").click()
    titles = radio.locator(".vz-titles > *")
    expect(titles.first).to_be_visible()
    assert titles.count() == radio.locator(".vz-titles > a[data-id]").count()  # only titles in the list
    radio.locator(".vz-titles a", has_text="AM vs FM").click()
    expect(page.locator("#vz-panel h2")).to_have_count(1)  # only that visual
    expect(page.locator("#vz-panel h2")).to_have_text("AM vs FM modulation")
    assert page.url.endswith("#mod")
    tabs.nth(1).click()
    power = page.locator("#vz-tp-power")
    expect(power).to_be_visible()
    expect(rf).to_be_hidden()
    expect(power.locator("details.vz-sub > summary")).to_have_text(
        [re.compile(rf"^{s} · \d+$") for s in ("Isolation", "Power switching", "Circuits in motion")])  # fmt: skip
    ids = power.locator("details.vz-sub").evaluate_all(
        "ds => ds.map(d => [...d.querySelectorAll('a[data-id]')].map(a => a.dataset.id))")  # fmt: skip
    assert ids[0] == ["cmti", "creep", "emc"] and ids[1][:4] == ["gate", "thermal", "swloss", "turnon"]
    assert len(ids[2]) == 6
    tabs.nth(2).click()
    expect(page.locator("#vz-tp-basics details.vz-sub > summary")).to_have_text([re.compile(r"^Digital basics · \d+$")])
    # deep links from other pages open the right tab, line and visual
    for vid, tab, line in (("ip3", "rf", "Receivers"), ("creep", "power", "Isolation"),
                           ("turnon", "power", "Power switching"), ("hex", "basics", "Digital basics")):  # fmt: skip
        page.goto("about:blank")
        go(page, f"/visuals#{vid}")
        expect(page.locator(f"#vz-tab-{tab}")).to_have_attribute("aria-selected", "true")
        expect(page.locator(f"#vz-tp-{tab} details.vz-sub[open] > summary")).to_have_text(re.compile(rf"^{line} · "))
        expect(page.locator("#vz-nav a.on")).to_have_attribute("data-id", vid)
        expect(page.locator("#vz-panel h2")).to_have_count(1)
    page.evaluate("location.hash = 'nf'")  # a link inside a visual to another one switches the tab too
    expect(page.locator("#vz-tab-rf")).to_have_attribute("aria-selected", "true")
    expect(page.locator("#vz-nav a.on")).to_have_attribute("data-id", "nf")
    # search by title or word
    q, hits = page.locator("#vz-q"), page.locator("#vz-hits a[data-hit]")
    q.fill("jitter")
    expect(hits.first).to_have_attribute("data-hit", "jitter")
    q.fill("VSWR")
    expect(hits.first).to_have_attribute("data-hit", "vswr")
    hits.first.click()
    expect(page.locator("#vz-panel h2")).to_contain_text("VSWR")
    expect(page.locator("#vz-tp-rf details.vz-sub[open] > summary")).to_contain_text(["Matching and filters"])
    q.fill("clearance")  # a word from the visual's keywords, not its title; Enter opens the first hit
    expect(hits.first).to_have_attribute("data-hit", "creep")
    q.press("Enter")
    expect(page.locator("#vz-panel h2")).to_have_text("Creepage against working voltage")
    expect(page.locator("#vz-tab-power")).to_have_attribute("aria-selected", "true")
    q.fill("zzzz")
    expect(page.locator("#vz-hits")).to_contain_text("No visual matches")
    q.fill("")
    expect(page.locator("#vz-hits")).to_be_hidden()


# --- Data management --------------------------------------------------------------------------------------------------
def test_verify_next_answer_one_with_a_comment(page):
    go(page, "/manage/verify")
    assert page.title().startswith("Verify next") and "<" not in page.title()
    task = page.locator("article.vf-task").first
    title = task.locator("h3").inner_text()
    form = task.locator("form.vf-form").last
    form.locator("textarea[name=note]").fill("Checked in the browser test.")
    with page.expect_navigation():
        form.get_by_role("button", name="Correct").click()
    done = page.locator("details", has_text="Done").first
    done.locator("summary").click()
    assert page.locator("li", has_text=title).filter(has_text="Checked in the browser test.").count() >= 1


def test_overview_waiting_line_opens_the_filtered_requests(page):
    """Owner, 24 Oct 2026: a "Waiting for you" line goes straight to the place to act, here Requests > Part requests."""
    go(page, "/manage/requests")
    page.locator("details.rq-add summary").click()
    page.locator("textarea[name=mpns]").fill("ZQ4242")
    with page.expect_navigation():
        page.get_by_role("button", name="Add requests").click()
    go(page, "/manage/overview")
    line = page.locator("#ov-todo a", has_text="part request")
    with page.expect_navigation():
        line.click()
    assert page.url.endswith("/manage/requests?kind=part")
    expect(page.locator("a.fchip.on", has_text="Part requests")).to_be_visible()
    expect(page.locator("nav.page-tabs a.on", has_text="Requests")).to_be_visible()
    item = page.locator("li.rq-item", has_text="ZQ4242")
    expect(item).to_contain_text("Part request")
    with page.expect_navigation():
        item.locator("select[name=status]").select_option("in_progress")
    expect(page.locator("li.rq-item", has_text="ZQ4242").locator("select[name=status]")).to_have_value("in_progress")


# --- Shareable --------------------------------------------------------------------------------------------------------
def test_shareable_technology_overview_prints_to_four_a4_pages(page):
    """Shareable > Technology overview: the section row opens the landing page, its card the brief; the four sections
    show, the preview has no print button (owner, 26 Oct 2026: Create PDF makes the file instead), the page links to
    Create PDF, the print view still hides the site's frame, and the A4 print has 4 pages at most."""
    go(page, "/")
    page.locator("nav.main-nav a", has_text="Shareable").click()
    expect(page).to_have_url(re.compile(r"/shareable$"))
    expect(page.locator("main h1")).to_have_text("Shareable")
    # owner, 25 Oct 2026: one list; Preview opens the report in the lightbox, then check it as a page of its own
    page.locator(".sh-row", has_text="Technology overview").get_by_role("button", name="Preview").click()
    frame = page.locator("dialog.lb iframe.lb-frame")
    expect(frame).to_have_attribute("src", re.compile(r"/shareable/technology-overview\?embed=1$"))
    expect(page.frame_locator("dialog.lb iframe.lb-frame").locator("section#platforms")).to_be_attached()
    inner = page.frame_locator("dialog.lb iframe.lb-frame")
    expect(inner.locator("#tech-overview")).to_be_visible()
    for chrome in (".site-head", ".site-foot", ".to-actions"):  # only the report shows, like a document
        expect(inner.locator(chrome).first).to_be_hidden()
    expect(page.locator("dialog.lb").get_by_role("button", name=re.compile("Print"))).to_have_count(0)
    expect(page.locator("dialog.lb").get_by_role("link", name="Open in a new tab")).to_be_visible()
    page.get_by_role("button", name="Close preview").click()
    expect(page.locator("dialog.lb")).to_be_hidden()
    # tapping the report itself opens it too; ticking "Add to PDF" is separate (owner, 25 Oct 2026)
    page.locator(".sh-open", has_text="Skyworks + Qorvo synergies").click()
    expect(page.locator("dialog.lb")).to_be_visible()
    expect(frame).to_have_attribute("src", re.compile(r"/shareable/synergies\?embed=1$"))
    expect(page.locator('input[name="r"][value="synergies"]')).not_to_be_checked()
    page.get_by_role("button", name="Close preview").click()
    go(page, "/shareable/technology-overview")
    for sid, heading in (("at-a-glance", "technology overview"), ("platforms", "Technology platforms"),
                         ("markets", "End markets"), ("families", "Product families")):  # fmt: skip
        expect(page.locator(f"section#{sid} :is(h1, h2)").first).to_contain_text(heading)
    expect(page.locator(".to-matrix .to-dot").first).to_be_visible()
    expect(page.get_by_role("button", name="Create PDF")).to_have_attribute("href", "/shareable/pdf?r=overview&wm=none")
    expect(page.get_by_role("button", name="Save as PDF")).to_have_count(0)
    page.emulate_media(media="print")
    for frame in (".site-head", ".site-foot", ".fb", ".to-actions"):
        expect(page.locator(frame).first).to_be_hidden()
    expect(page.locator(".to-pfoot").first).to_contain_text("Public information")
    pdf = page.pdf(format="A4", print_background=True)
    pages = len(re.findall(rb"/Type\s*/Page\b(?!s)", pdf))
    assert 1 <= pages <= 4, f"{pages} A4 pages"


TO = "/shareable/technology-overview"


def pdf_pages(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page\b(?!s)", pdf))


def pdf_text(pdf: bytes, tmp_path, page_no: int | None = None) -> str | None:
    """The PDF's text (pdftotext from poppler), or None when the image has no pdftotext."""
    import shutil
    import subprocess

    if not shutil.which("pdftotext"):
        return None
    f = tmp_path / "page.pdf"
    f.write_bytes(pdf)
    pages = ["-f", str(page_no), "-l", str(page_no)] if page_no else []
    return subprocess.run(["pdftotext", *pages, str(f), "-"], capture_output=True, text=True, check=True).stdout


def a4(page) -> bytes:
    page.emulate_media(media="print")
    pdf = page.pdf(format="A4", print_background=True)
    page.emulate_media(media="screen")
    return pdf


def reset_overview(page):
    """The live server is shared by the browser tests: put the overview back to its defaults."""
    page.request.post(TO + "/edit/reset", form={"all": "1"})


def test_technology_overview_edit_number_paragraph_comment_resolve_undo(page, tmp_path):
    """Owner, 24 Oct 2026: edit a number, edit a paragraph, Save and see both (also in the PDF); comment on the
    paragraph, resolve the comment; Undo brings the page back."""
    page.on("dialog", lambda d: d.accept())
    try:
        go(page, TO)
        page.get_by_role("button", name="Edit", exact=True).click()
        expect(page).to_have_url(re.compile(r"/edit$"))
        expect(page.locator("#f-fact\\.parts\\.num .te-auto")).to_contain_text("from the catalogue")
        page.fill("input[name='fact.parts.num']", "5,000")
        page.locator("textarea[name='paras.glance']").first.fill("A new intro, written on the iPad.")
        page.get_by_role("button", name="Save").first.click()
        expect(page.locator(".te-status")).to_contain_text("Saved")
        expect(page.locator("#f-fact\\.parts\\.num .te-tag")).to_have_text("overridden")
        para = page.locator(".te-para").first
        para.locator("summary", has_text="Comment").click()
        para.locator("textarea[name^='ctext.']").fill("make this shorter")
        para.get_by_role("button", name="Send comment").click()
        expect(page.locator(".te-open").first).to_contain_text("make this shorter")
        page.locator(".te-open").first.get_by_role("button", name="Resolve").click()
        expect(page.locator(".te-status")).to_contain_text("Comment resolved")
        expect(page.locator(".te-open")).to_have_count(0)
        go(page, TO)
        expect(page.locator("#at-a-glance .to-lead")).to_have_text("A new intro, written on the iPad.")
        expect(page.locator(".to-fact b").first).to_have_text("5,000")
        text = pdf_text(a4(page), tmp_path)
        if text is not None:
            assert "A new intro, written on the iPad." in text and "5,000" in text
        go(page, TO + "/edit")
        page.get_by_role("button", name="Undo last change").click()
        go(page, TO)
        expect(page.locator(".to-fact b").first).not_to_have_text("5,000")
        expect(page.locator("#at-a-glance .to-lead")).not_to_contain_text("iPad")
    finally:
        reset_overview(page)


def test_technology_overview_is_four_pages_with_a_watermark(page, tmp_path):
    """Owner, 25 Oct 2026: the market focus page is gone, so the overview PDF is 4 A4 pages; an old ?focus= link opens
    the same 4 pages without error. The watermark prints on every page and changes no page count."""
    go(page, TO)
    expect(page.locator("select[name='focus']")).to_have_count(0)
    expect(page.locator("input[name='include']")).to_have_count(0)
    expect(page.locator(".to-page")).to_have_count(4)
    assert pdf_pages(a4(page)) == 4
    page.select_option("select[name='wm']", "draft")
    expect(page).to_have_url(re.compile(r"wm=draft"))
    expect(page.locator(".to-wm")).to_have_text("Draft")
    pdf = a4(page)
    assert pdf_pages(pdf) == 4
    for n in range(1, pdf_pages(pdf) + 1):
        text = pdf_text(pdf, tmp_path, n)
        if text is not None:
            assert "draft" in text.lower(), f"no watermark on page {n}"
    page.select_option("select[name='wm']", "none")
    expect(page.locator(".to-wm")).to_have_count(0)
    go(page, f"{TO}?focus=automotive")  # an old link: status 200, no error
    expect(page.locator("#market-focus")).to_have_count(0)
    expect(page.locator(".to-page")).to_have_count(4)
    assert pdf_pages(a4(page)) == 4
    go(page, f"{TO}?focus=bogus&wm=bogus")
    expect(page.locator(".to-wm")).to_have_count(0)


def test_technology_overview_logo_upload_and_remove(page):
    """Owner, 24 Oct 2026: add a logo (only with permission), see it on every page band, remove it."""
    from tests.test_tech_overview import png

    page.on("dialog", lambda d: d.accept())
    try:
        go(page, TO + "/edit")
        expect(page.locator(".te-logo")).to_contain_text("Use a logo only with permission from its owner.")
        page.set_input_files("input[name='logo']", files=[{"name": "logo.png", "mimeType": "image/png",
                                                           "buffer": png(40, 16)}])  # fmt: skip
        page.get_by_role("button", name="Add logo").click()
        expect(page.locator(".te-status")).to_contain_text("Logo added")
        go(page, TO)
        expect(page.locator(".to-band img.to-logo")).to_have_count(4)
        assert pdf_pages(a4(page)) <= 4
        go(page, TO + "/edit")
        page.get_by_role("button", name="Remove logo").click()
        expect(page.locator(".te-status")).to_contain_text("Logo removed")
        go(page, TO)
        expect(page.locator(".to-band img")).to_have_count(0)
    finally:
        reset_overview(page)


def _filler(n: int) -> str:
    words = "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike november oscar papa".split()
    out, i = "", 0
    while len(out) < n:
        out += ("" if not out else " ") + words[i % len(words)]
        i += 1
    return out[:n].rstrip()


def test_technology_overview_every_field_at_its_limit_still_fits(page):
    """The length limits keep the PDF at 4 A4 pages, even with every text and number at its
    limit, every dot set, two paragraphs per section and a medium logo."""
    from app.services import tech_overview_edit as te
    from tests.test_tech_overview import png

    form: dict = {}
    for fid, f in te.specs().items():
        if f.kind in ("line", "text", "data") and f.max and not fid.endswith(".url") and fid != "wm.custom":
            form[fid] = _filler(f.max)
        elif f.kind == "chips":
            form[fid] = "\n".join(_filler(te.CHIP_MAX) for _ in range(f.options[0] if f.options else te.CHIPS))
        elif f.kind in ("owner", "dot"):
            form[fid] = "Both"
    form["hdr.logo_size"] = "medium"
    multi = [(k, v) for k, v in form.items()]
    for s in te.sections():
        most, total = te.para_limits(s)
        multi += [(f"paras.{s}", _filler(total // most - 1)) for _ in range(most)] + [(f"pid.{s}", "")] * most
    try:
        r = page.request.post(TO + "/edit/logo", multipart={"logo": {"name": "l.png", "mimeType": "image/png",
                                                                      "buffer": png(40, 16)}})  # fmt: skip
        assert r.ok
        body = "&".join(f"{quote(k)}={quote(str(v))}" for k, v in multi)
        r = page.request.post(TO + "/edit", data=body, headers={"content-type": "application/x-www-form-urlencoded"})
        assert r.ok and "Not saved" not in r.text(), re.findall(r'role="alert">([^<]*)', r.text())[:5]
        go(page, TO)
        assert pdf_pages(a4(page)) <= 4
    finally:
        reset_overview(page)


def test_shareable_pack_of_all_three_and_each_report_alone(page):
    """Owner, 25 Oct 2026: the Synergies and Automotive reports are at most 3 A4 pages each; the combined PDF of all
    three reports at most 10 pages, numbered through. Owner, 26 Oct 2026: the PDF is made on the server; an old link
    to the combined print view downloads it."""
    for path in ("/shareable/synergies", "/shareable/automotive"):
        go(page, path)
        expect(page.locator(".to-page")).to_have_count(3)
        r = page.request.get(path.replace("/shareable/", "/shareable/pdf?r="))
        assert r.ok and r.headers["content-type"] == "application/pdf" and pdf_pages(r.body()) <= 3, path
    r = page.request.get("/shareable/pack?r=overview,synergies,automotive&wm=none")
    assert r.ok and r.headers["content-type"] == "application/pdf"
    assert pdf_pages(r.body()) <= 10


def test_shareable_create_pdf_with_two_reports(page, tmp_path):
    """The one Shareable page (owner, 26 Oct 2026): nothing ticked asks to pick a report; tick Synergies and
    Automotive, Create PDF downloads one A4 PDF (application/pdf) with Synergies then Automotive, made on the server;
    the page stays and the address keeps the choice."""
    go(page, "/shareable")
    box = page.locator("#build-pdf")
    expect(box.locator("input[name=r]:checked")).to_have_count(0)
    box.get_by_role("button", name="Create PDF").click()
    expect(page.locator("#sh-err")).to_have_text("Pick at least one report.")
    expect(page.locator("dialog.lb[open]")).to_have_count(0)
    box.locator("input[value='synergies']").check()
    box.locator("input[value='automotive']").check()
    expect(page.locator("#sh-err")).to_be_hidden()
    with page.expect_download() as dl:
        box.get_by_role("button", name="Create PDF").click()
    d = dl.value
    assert d.suggested_filename == "skyworks-qorvo-synergies-automotive.pdf"
    path = tmp_path / d.suggested_filename
    d.save_as(path)
    pdf = path.read_bytes()
    assert pdf.startswith(b"%PDF") and 2 <= pdf_pages(pdf) <= 6
    r = page.request.get("/shareable/pdf?r=synergies,automotive&wm=none")
    assert r.headers["content-type"] == "application/pdf"
    text = pdf_text(pdf, tmp_path)
    if text is not None:
        assert text.index("Skyworks + Qorvo synergies") < text.index("Extension of: Skyworks + Qorvo synergies")
        assert "Sources" in text and "BizDev" not in text
    expect(page).to_have_url(re.compile(r"/shareable\?r=synergies,automotive&wm=none$"))  # the page stays


def test_shareable_build_a_presentation_button(page):
    """Owner, 25 Oct 2026: Build a presentation sits next to Create PDF and opens the topic builder."""
    go(page, "/shareable")
    page.locator("#build-pdf").get_by_role("button", name="Build a presentation").click()
    expect(page).to_have_url(re.compile(r"/shareable/presentation$"), timeout=90_000)
    expect(page.locator("nav.sub-nav a.on")).to_have_text("Reports")


def test_shareable_create_powerpoint_with_two_reports(page, tmp_path):
    """Owner, 25 and 26 Oct 2026: Create PowerPoint sits with Create PDF; nothing ticked asks to pick a report; two
    ticked download one .pptx with both reports (iPad-size window)."""
    from pptx import Presentation

    go(page, "/shareable")
    box = page.locator("#build-pdf")
    box.get_by_role("button", name="Create PowerPoint").click()
    expect(page.locator("#sh-err")).to_have_text("Pick at least one report.")
    box.locator("input[value='synergies']").check()
    box.locator("input[value='automotive']").check()
    with page.expect_download() as dl:
        box.get_by_role("button", name="Create PowerPoint").click()
    d = dl.value
    assert d.suggested_filename == "skyworks-qorvo-synergies-automotive.pptx"
    path = tmp_path / d.suggested_filename
    d.save_as(path)
    heads = {sh.text_frame.text for s in Presentation(path).slides for sh in s.shapes
             if sh.has_text_frame and sh.text_frame.text.startswith("Skyworks + Qorvo · ")}  # fmt: skip
    assert heads == {"Skyworks + Qorvo · Synergies", "Skyworks + Qorvo · Automotive"}
    expect(page).to_have_url(re.compile(r"/shareable\?r=synergies,automotive&wm=none$"))  # the page stays


def test_shareable_explanation_opens_in_the_lightbox_at_ipad_size(page):
    """Owner, 27 Oct 2026: "another button next to the shareable pages where I can click preview or I can read the
    explanation": Explanation sits next to Preview and opens the same lightbox (?embed=1) with the block table, both
    companies' columns; it fits an iPad held sideways and upright (390 px checked after the test)."""
    go(page, "/shareable")
    page.locator(".sh-row", has_text="Car radio").get_by_role("button", name="Explanation").click()
    frame = page.locator("dialog.lb iframe.lb-frame")
    expect(frame).to_have_attribute("src", re.compile(r"/shareable/radio/explain\?embed=1$"))
    inner = page.frame_locator("dialog.lb iframe.lb-frame")
    expect(inner.locator("h1")).to_contain_text("Explanation: Car radio", timeout=PAGE_TIMEOUT)  # built on first use
    for who in ("Skyworks", "Qorvo"):
        expect(inner.locator(".sx-table thead")).to_contain_text(who)
    for chrome in (".site-head", ".site-foot"):  # only the explanation shows inside the window
        expect(inner.locator(chrome).first).to_be_hidden()
    page.get_by_role("button", name="Close preview").click()
    expect(page.locator("dialog.lb")).to_be_hidden()
    for size in ({"width": 1180, "height": 900}, {"width": 820, "height": 1180}):
        page.set_viewport_size(size)
        for path in ("/shareable", "/shareable/radio/explain", "/shareable/uwb/explain"):
            go(page, path)
            assert overflow(page) <= 1, (size, path)


def test_shareable_synergies_owner_edit_and_undo(page):
    """The new reports edit like the overview: a number (the exact automatic value is shown), Save, Undo."""
    try:
        go(page, "/shareable/synergies")
        page.get_by_role("button", name="Edit", exact=True).click()
        expect(page.locator("#f-fact\\.parts\\.num .te-auto")).to_contain_text("(exact ")
        page.fill("input[name='fact.parts.num']", "4,600")
        page.get_by_role("button", name="Save").first.click()
        expect(page.locator(".te-status")).to_contain_text("Saved")
        go(page, "/shareable/synergies")
        expect(page.locator(".to-fact b").first).to_have_text("4,600")
        go(page, "/shareable/synergies/edit")
        page.get_by_role("button", name="Undo last change").click()
        go(page, "/shareable/synergies")
        expect(page.locator(".to-fact b").first).not_to_have_text("4,600")
    finally:
        page.request.post("/shareable/synergies/edit/reset", form={"all": "1"})


@pytest.mark.parametrize("slug", ["synergies", "automotive"])
def test_shareable_report_every_field_at_its_limit_still_fits(page, slug):
    """The length limits keep each management report at 3 A4 pages, with every text at its limit."""
    from app.services import share_reports as sr
    from app.services import tech_overview_edit as te

    rep = sr.REPORTS[slug]
    multi = []
    for fid, f in rep.specs().items():
        if f.kind in ("line", "text", "data") and f.max:
            multi.append((fid, _filler(f.max)))
        elif f.kind == "chips":
            multi += [(fid, "\n".join(_filler(te.CHIP_MAX) for _ in range(f.options[0] if f.options else te.CHIPS)))]
    for s in rep.sections():
        most, total = rep.para_limits(s)
        multi += [(f"paras.{s}", _filler(total // most - 1)) for _ in range(most)] + [(f"pid.{s}", "")] * most
    try:
        body = "&".join(f"{quote(k)}={quote(str(v))}" for k, v in multi)
        r = page.request.post(f"/shareable/{slug}/edit", data=body,
                              headers={"content-type": "application/x-www-form-urlencoded"})  # fmt: skip
        assert r.ok and "Not saved" not in r.text(), re.findall(r'role="alert">([^<]*)', r.text())[:5]
        go(page, f"/shareable/{slug}?wm=draft")
        assert pdf_pages(a4(page)) <= 3, slug
    finally:
        page.request.post(f"/shareable/{slug}/edit/reset", form={"all": "1"})


# --- Signing in -------------------------------------------------------------------------------------------------------
STUB = """
window.__calls = [];
addEventListener('click', () => { window.__inClick = true; }, true);
addEventListener('click', () => { window.__inClick = false; });
if (!window.PublicKeyCredential) window.PublicKeyCredential = function () {};
Object.defineProperty(navigator, 'credentials', {configurable: true, value: {
  get(o) { window.__calls.push({kind: 'get', inClick: !!window.__inClick,
                                challenge: !!(o && o.publicKey && o.publicKey.challenge)});
           return Promise.reject(new DOMException('cancelled in the test', 'NotAllowedError')); },
  create(o) { window.__calls.push({kind: 'create', inClick: !!window.__inClick});
              return Promise.reject(new DOMException('cancelled in the test', 'NotAllowedError')); },
}});
"""


def test_sign_in_passkey_button_calls_credentials_inside_the_tap(page):
    page.add_init_script(STUB)
    with page.expect_response(lambda r: r.url.endswith("/passkey/login/options")) as opts:
        go(page, "/login")
    assert opts.value.ok
    page.wait_for_timeout(50)  # the options are stored once the response is read
    page.locator("#passkey-login").click()
    calls = page.evaluate("window.__calls")
    assert calls == [{"kind": "get", "inClick": True, "challenge": True}]
    expect(page.locator("#auth-msg")).to_contain_text("cancelled")
    assert page.locator("#passkey-login").is_enabled()


# --- Research & ideas -------------------------------------------------------------------------------------------------
def test_expand_this_idea_asks_once_and_shows_the_request(page):
    """Owner, 25 Oct 2026: "Expand this idea" under a card opens a note field; sent, the button is gone on the list
    and on the report page, replaced by "Expansion requested" and the note (390 px checked after the test)."""
    go(page, "/business/reports")
    box = page.locator("details.rp-exp").first
    slug = box.get_attribute("id").removeprefix("exp-")
    expect(box.locator("summary")).to_contain_text("a deeper look at the applications before a business case")
    box.locator("summary").click()
    box.locator("textarea[name=note]").fill("Robot joints first")
    with page.expect_navigation():
        box.get_by_role("button", name="Ask for the expansion").click()
    done = page.locator(f"#exp-{slug}")
    expect(done).to_contain_text("Expansion requested")
    expect(done).to_contain_text("Robot joints first")
    assert page.locator(f"details#exp-{slug}").count() == 0
    go(page, f"/business/reports/{slug}")
    expect(page.locator(f"p#exp-{slug}")).to_contain_text("Robot joints first")
    assert page.locator("details.rp-exp").count() == 0


def test_answer_a_question_to_ask_switch_edit_and_find_it_in_answers(page):
    """Owner, 2 Nov 2026 (item 15): under a research report's question, write a two-line answer and who answered;
    it saves as Internal only, the switch makes it Can be shared, an edit keeps the earlier version (shown on a tap),
    and Data management › Answers lists it with a link back to its question (iPad upright; 390 px checked after)."""
    page.set_viewport_size({"width": 820, "height": 1180})
    go(page, "/business/reports/filters-1-11ghz")
    box = page.locator("#i-q-bu-standalone")
    form = box.locator("form.aq-form")
    expect(form.locator(".aq-warn")).to_have_text("Don't record confidential figures or plans; summarise instead")
    expect(form.locator("input[name=sharing][value=internal]")).to_be_checked()
    form.locator("textarea[name=text]").fill("They keep standalone filters.\nLow volume stays for now.")
    form.locator("input[name=who]").fill("Filter BU product line")
    with page.expect_navigation():
        form.get_by_role("button", name="Save answer").click()
    card = page.locator("#i-q-bu-standalone article.aq-a").first
    expect(card).to_contain_text("Low volume stays for now.")
    expect(card).to_contain_text("Filter BU product line")
    expect(card.get_by_role("button", name="🔒 Internal only")).to_have_attribute("aria-pressed", "true")
    with page.expect_navigation():
        card.get_by_role("button", name="✅ Can be shared").click()
    card = page.locator("#i-q-bu-standalone article.aq-a").first
    expect(card.get_by_role("button", name="✅ Can be shared")).to_have_attribute("aria-pressed", "true")
    card.locator("details.aq-more summary", has_text="Edit").click()
    card.locator("textarea[name=text]").fill("They keep standalone filters for defense and test.")
    with page.expect_navigation():
        card.get_by_role("button", name="Save changes").click()
    card = page.locator("#i-q-bu-standalone article.aq-a").first
    expect(card.locator(".aq-text")).to_have_text("They keep standalone filters for defense and test.")
    expect(card.locator(".aq-edited")).to_be_visible()
    old = card.locator("details.aq-more", has_text="Earlier versions")
    expect(old.locator(".aq-vers")).to_be_hidden()
    old.locator("summary").click()
    expect(old.locator(".aq-vers")).to_contain_text("Low volume stays for now.")
    assert overflow(page) <= 1
    go(page, "/manage/answers?sharing=shared")
    item = page.locator(".aq-list > li", has_text="for defense and test").first
    expect(item.locator(".aq-q")).to_contain_text("standalone filters")
    with page.expect_navigation():
        item.locator(".aq-where a").click()
    assert page.url.endswith("/business/reports/filters-1-11ghz#i-q-bu-standalone")
    go(page, "/manage/answers?sharing=internal")
    expect(page.locator(".aq-list > li", has_text="for defense and test")).to_have_count(0)
    expect(page.locator("#open-questions")).to_contain_text("Still open")
    go(page, "/business/reports/auto-uwb-15-4ab#questions-to-ask")  # a case's section 8 (390 px checked after)
    expect(page.locator("#i-q-bu-ab form.aq-form .aq-warn")).to_be_visible()


# --- Block editor: "Describe your system" (owner, 27 Oct 2026) --------------------------------------------------------
def test_describe_your_system_builds_blocks_at_ipad_size(page):
    """Type a sentence, Build: the 48 V input, protection, buck, LDO and MCU frames appear, linked left to right, with
    the understood words as chips (iPad held upright; 390 px checked after the test)."""
    page.set_viewport_size({"width": 820, "height": 1180})
    go(page, "/blocks/new")
    box = page.locator("#bk-words")
    expect(box).to_have_attribute("open", "")
    box.locator("textarea[name=text]").fill("I have a 48 V input and an MCU with isolated CAN")
    with page.expect_navigation():
        box.get_by_role("button", name="Build").click()
    expect(page.locator("#bk-svg .grp")).to_have_count(6)
    for label in ("48 V input", "Input protection", "Step-down 48 V → 5 V", "LDO 5 V → 3.3 V", "Microcontroller",
                  "Isolated CAN transceiver"):
        expect(page.locator("#bk-svg .grp-title", has_text=label).first).to_be_visible()
    expect(page.locator("#bk-svg .link")).to_have_count(5)
    expect(page.locator("#bk-words-echo .wchip").first).to_have_text("48 V input")
    expect(page.locator("#bk-words-echo")).to_contain_text("MCU → Microcontroller")
    expect(page.locator("#bk-status")).to_contain_text("built from your description")
    assert overflow(page) <= 1


# --- Research: our own PD controller (worker G, 2 Nov 2026) -----------------------------------------------------------
def test_charging_report_own_pd_controller_section_on_a_phone(page):
    """Owner, 2 Nov 2026 ("Look into own pd controller"): the summary links to the closer look; its five parts show
    and their tables scroll inside their own box on a 390 px phone, not the page."""
    page.set_viewport_size(PHONE)
    go(page, "/business/reports/auto-charging-power")
    page.locator('.brief a[href="#own-pd-controller"]').click()
    sec = page.locator("#own-pd-controller")
    expect(sec).to_be_in_viewport()
    for h in ("What we could reuse (est)", "What it takes", "Who sells it today", "Effort and feasibility",
              "Build, partner or license"):  # fmt: skip
        expect(sec.locator("h3", has_text=h)).to_have_count(1)
    assert overflow(page) <= 1


# --- Research: isolated current sensing case, In depth (worker G, 2 Nov 2026) -----------------------------------------
def test_current_sense_case_in_depth_reads_on_a_phone(page):
    """Owner, 27 Oct 2026 ("Look more into it"): the case's In depth tables; on a 390 px phone each row is a block and
    each cell shows its column name, nothing scrolls sideways; a link in the table list jumps to its table."""
    page.set_viewport_size(PHONE)
    page.request.get("/business/reports/iso-current-sense-charging", timeout=90_000)  # a case's first render is slow
    go(page, "/business/reports/iso-current-sense-charging")
    sec = page.locator("#in-depth")
    expect(sec.locator("h3")).to_have_count(7)  # six tables and "Next step"
    cell = sec.locator("#depth-where + .table-wrap td[data-label='How it is done']").first
    expect(cell).to_be_visible()
    label = cell.evaluate("e => getComputedStyle(e, '::before').content")
    assert "How it is done" in label, label
    sec.locator("a[href='#depth-needs']").click()
    expect(page.locator("#depth-needs")).to_be_in_viewport()
    assert overflow(page) <= 1


# --- Products > Clock planner (owner, 2 Nov 2026, item 18) ------------------------------------------------------------
def test_clock_planner_preset_parts_plan_save_reopen(page):
    """Preset → the parts that fit → plan with another part → add an output row → save → the link reopens the plan
    (iPad held upright; 390 px checked after the test)."""
    page.set_viewport_size({"width": 820, "height": 1180})
    go(page, "/clocks")
    expect(page.locator("#cp-cbpro a")).to_have_attribute("href", re.compile("Clockbuilder-Pro-Software"))
    with page.expect_navigation():
        page.get_by_role("link", name="Mixed with fractional outputs").click()
    expect(page.locator("#cp-parts")).to_contain_text("Si5332A-GM1")
    expect(page.locator("#cp-plan h2")).to_contain_text("Frequency plan for")
    expect(page.locator("#cp-plan")).to_contain_text("fractional divider")
    with page.expect_navigation():
        page.locator("#cp-parts tr", has_text="Si5332A-GM1").get_by_role("link", name="Plan with this part").click()
    expect(page.locator("#cp-plan h2")).to_contain_text("Si5332A-GM1")
    expect(page.locator("#cp-plan")).to_contain_text("All outputs come from one VCO with integer dividers")
    expect(page.locator(".cp-diagram svg .cp-out")).to_have_count(3)
    rows = page.locator("#cp-rows .cp-row:not(.cp-row-head)")
    before = rows.count()
    page.locator("#cp-add").click()
    expect(rows).to_have_count(before + 1)
    page.locator("#cp-name").fill("Browser clock plan")
    page.locator("#cp-save-btn").click()
    expect(page.locator("#cp-status")).to_contain_text("Saved. Link:")
    assert re.search(r"/clocks/plans/\d+$", page.url)
    go(page, page.url)
    expect(page.locator("main h1")).to_have_text("Browser clock plan")
    expect(page.locator("#cp-plan h2")).to_contain_text("Si5332A-GM1")
    go(page, "/clocks/plans")
    expect(page.locator("main")).to_contain_text("Browser clock plan")


def test_data_center_shows_timing_sub_system_deep_dive_and_diagrams(page):
    """Owner, 2 Nov 2026: timing solutions in the data center: the Data center system has a "Timing and
    synchronization" sub-system with its deep dive (which links the Clock planner) and its block diagrams."""
    go(page, "/library#sys-datacenter")
    card = page.locator("#card-datacenter-timing")
    expect(card).to_be_visible()
    expect(card).to_contain_text("Timing and synchronization")
    with page.expect_navigation():
        card.locator("a.sys-btn-deep").click()
    assert page.url.endswith("/library/dc_timing")
    expect(page.locator("main h1")).to_contain_text("Timing in the AI data center")
    expect(page.locator('main a[href="/clocks"]').first).to_be_visible()
    go(page, "/blocks?system=datacenter&sub=timing#sub-timing")
    expect(page.locator("details#area-datacenter[open]")).to_have_count(1)
    expect(page.locator("main")).to_contain_text("AI / GPU server clock tree")


def test_data_center_shows_cooling_and_hvac(page):
    """Owner, 2 Nov 2026 ("Also add cooling and HVAC to data centers"): Data center opens with a Cooling and HVAC card
    whose buttons lead to the deep dive and to its block diagrams."""
    go(page, "/library#sys-datacenter")
    card = page.locator("#card-datacenter-cooling")
    expect(card).to_be_visible()
    expect(card).to_contain_text("Cooling and HVAC")
    expect(card.locator("a.sys-btn")).to_have_count(2)
    with page.expect_navigation():
        card.get_by_role("link", name="📖 Read the deep dive").click()
    assert page.url.endswith("/library/dc_cooling")
    expect(page.locator("main h1")).to_contain_text("Data-center cooling")
    go(page, "/library#sys-datacenter")
    with page.expect_navigation():
        page.locator("#card-datacenter-cooling a.sys-btn-dg").click()
    expect(page.locator("#sub-cooling")).to_be_in_viewport()
    expect(page.locator("#sub-cooling + .tpl-grid a.tpl-card")).to_have_count(5)


def test_drones_show_satellite_navigation_and_anti_jamming(page):
    """Owner, 2 Nov 2026 (worker P): Drones gets "Satellite link (NTN / direct-to-cell)", "Navigation" and
    "Anti-jamming and anti-spoofing", each with diagrams and a deep dive; the radio-links deep dive shows "Which link
    when"."""
    go(page, "/blocks?system=drones")
    for sub in ("satellite-link", "navigation", "anti-jamming"):
        card = page.locator(f"#card-drones-{sub}")
        expect(card).to_have_count(1)
        expect(card.locator(".sys-btn-deep")).to_have_count(1)
    go(page, "/library/drone_satellite_link")
    expect(page.locator("h1")).to_contain_text("satellite link")
    go(page, "/library/drone_radio_links")
    expect(page.locator("#k-drone_link_choice table")).to_be_visible()
    go(page, "/library/drone_antijam")
    expect(page.locator('a[href="/library/drone_navigation"]').first).to_be_visible()


# --- Systems library > Industrial > Robotics (European view) (owner, 3 Nov 2026, worker Q) ---------------------------
def test_industrial_shows_robotics_and_its_deep_dive_opens(page):
    """Owner, 3 Nov 2026 ("something for robotics ... a Euro-centric view"): Industrial & energy opens with the
    Robotics (European view) card; its deep dive opens and links back to the factory-automation diagrams."""
    go(page, "/library#sys-industrial")
    expect(page.locator("details#sys-industrial[open]")).to_have_count(1)
    card = page.locator("#card-industrial-robotics")
    expect(card).to_be_visible()
    expect(card).to_contain_text("Robotics (European view)")
    with page.expect_navigation():
        card.get_by_role("link", name="📖 Read the deep dive").click()
    assert page.url.endswith("/library/robotics_europe")
    expect(page.locator("main h1")).to_contain_text("Robotics in Europe")
    with page.expect_navigation():
        page.locator(".lib-see-also a", has_text="Factory automation").click()
    expect(page.locator("#sub-factory-automation")).to_be_in_viewport()
    go(page, "/blocks?system=industrial&sub=robotics#sub-robotics")
    expect(page.locator("#sub-robotics")).to_be_in_viewport()


def test_one_function_in_many_bands_is_one_row_that_opens(page):
    """Owner, 3 Nov 2026 ("group all of these together"): Frequency multiplier is one card on Gaps & new technology and
    one row in its detailed table and on RF coverage; a tap opens its bands; setting the group aside and restoring it
    works from the table (the 390 px check follows)."""
    go_built_on_first_use(page, "/business/opportunities?show=all")
    card = page.locator('.vg-card[data-fn="frequency_multiplier"]')
    expect(card).to_have_count(1)
    expect(card).to_contain_text("6 bands · L–Ka (1–40 GHz)")
    bands = card.locator(".vg-subs li")
    expect(bands.first).to_be_hidden()
    card.locator(".vg-subs summary").click()
    expect(bands).to_have_count(6)
    expect(bands.first).to_be_visible()

    go(page, "/business/explorer/table")
    head = page.locator('tr.vg-head[data-fn="frequency_multiplier"]')
    expect(head).to_have_count(1)
    subs = head.locator("xpath=following-sibling::tr[1]")
    expect(subs.locator(".vg-table tbody tr").first).to_be_hidden()
    subs.locator(".vg-subs > summary").click()
    expect(subs.locator(".vg-table tbody tr")).to_have_count(6)
    expect(subs.locator(".vg-table tbody tr").first).to_be_visible()
    head.locator(".aside-form summary").click()
    head.locator('.aside-form input[name="note"]').fill("not this year")
    with page.expect_navigation():
        head.locator(".aside-form button").click()
    expect(page.locator('tr.vg-head[data-fn="frequency_multiplier"]')).to_have_count(0)
    aside = page.locator("table.explorer tr", has_text="not this year")
    expect(aside).to_contain_text("6 bands")
    with page.expect_navigation():
        aside.get_by_role("button", name="Restore all").click()
    expect(page.locator('tr.vg-head[data-fn="frequency_multiplier"]')).to_have_count(1)

    go(page, "/business/rf-coverage")
    row = page.locator('.rf-gaps tr.vg-head[data-fn="rf_synthesizer"]')
    expect(row).to_have_count(1)
    more = row.locator("xpath=following-sibling::tr[1]")
    more.locator("summary").click()
    expect(more.locator(".vg-table tbody tr")).to_have_count(7)
