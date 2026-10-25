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
    pg.set_default_timeout(10_000)
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
    name = system.inner_text().rsplit(" ", 1)[0].strip()
    system.click()
    page.wait_for_load_state("load")
    assert "system=" in page.url
    assert page.locator(".sys-pick a.fchip.on").inner_text().startswith(name)
    sub = page.locator(".sys-sub-title").first
    sub_name = sub.inner_text().strip()
    sub.click()
    page.wait_for_load_state("load")
    assert "sub=" in page.url
    heading = page.locator("h3.tpl-cat").first
    assert heading.is_visible() and heading.inner_text().startswith(sub_name)


def test_cross_sell_by_system(page):
    go(page, "/blocks/cross-sell")
    sel = page.locator("select[name=sel]")
    option = sel.locator("option").nth(2)  # the first sub-system of the first system
    with page.expect_navigation():
        sel.select_option(option.get_attribute("value"))
    assert "sel=" in page.url
    assert page.locator("main h2").first.is_visible()
    assert page.get_by_role("heading", name=re.compile("Our parts that go together")).is_visible()


def test_cross_sell_automotive_together_here_then_portfolio_tab(page):
    """Owner, 25 Oct 2026: pick Automotive on Cross-sell, see the Skyworks + Qorvo pairs there, open the portfolio tab
    with the system kept and its pairs marked, and come back to By system."""
    go(page, "/blocks/cross-sell")
    with page.expect_navigation():
        page.locator("select[name=sel]").select_option("automotive")
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


def test_every_visual_moves_without_errors(page):
    go(page, "/visuals")
    links = page.locator("#vz-nav a[data-id]")
    ids = [links.nth(i).get_attribute("data-id") for i in range(links.count())]
    assert len(ids) > 10
    stuck, total = [], 0
    for vid in ids:
        page.locator(f"#vz-nav a[data-id='{vid}']").click()
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
    page.locator("#vz-nav a[data-id='fmim']").click()
    for label in ("Japan", "most countries", "OIRT"):
        expect(page.locator("#vz-panel .vz-chart text.vz-bl", has_text=label).first).to_be_attached()
    page.locator("#vz-nav a[data-id='nf']").click()
    expect(page.locator("#vz-panel .vz-strip .vz-sbar").first).to_be_attached()


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
    show, Save as PDF calls the print dialog, the print view hides the site's frame, and the A4 PDF has 4 pages at most
    (owner, 24 Oct 2026)."""
    go(page, "/")
    page.locator("nav.main-nav a", has_text="Shareable").click()
    expect(page).to_have_url(re.compile(r"/shareable$"))
    expect(page.locator("main h1")).to_have_text("Shareable")
    page.locator(".sh-card", has_text="Technology overview").click()
    expect(page).to_have_url(re.compile(r"/shareable/technology-overview$"))
    for sid, heading in (("at-a-glance", "technology overview"), ("platforms", "Technology platforms"),
                         ("markets", "End markets"), ("families", "Product families")):  # fmt: skip
        expect(page.locator(f"section#{sid} :is(h1, h2)").first).to_contain_text(heading)
    expect(page.locator(".to-matrix .to-dot").first).to_be_visible()
    page.evaluate("() => { window.__printed = 0; window.print = () => { window.__printed += 1; }; }")  # the dialog
    page.get_by_role("button", name="Save as PDF").click()
    assert page.evaluate("window.__printed") == 1
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


def test_technology_overview_market_focus_and_watermark(page, tmp_path):
    """Owner, 24 Oct 2026: the focus dropdown adds a page 5 for Automotive, Data center or Drones (the address keeps
    the choice); the watermark prints on every page and changes no page count; unknown values are ignored."""
    go(page, TO)
    page.select_option("select[name='focus']", "automotive")
    expect(page).to_have_url(re.compile(r"focus=automotive"))
    expect(page.locator("#market-focus h2")).to_have_text("Automotive")
    expect(page.locator("#market-focus")).to_contain_text("Car radio")
    pdf = a4(page)
    assert pdf_pages(pdf) <= 5
    page.select_option("select[name='wm']", "draft")
    expect(page).to_have_url(re.compile(r"wm=draft"))
    expect(page.locator(".to-wm")).to_have_text("Draft")
    pdf = a4(page)
    assert pdf_pages(pdf) <= 5
    for n in range(1, pdf_pages(pdf) + 1):
        text = pdf_text(pdf, tmp_path, n)
        if text is not None:
            assert "draft" in text.lower(), f"no watermark on page {n}"
    page.select_option("select[name='wm']", "none")
    expect(page.locator(".to-wm")).to_have_count(0)
    page.locator("input[type='checkbox'][name='include']").uncheck()
    expect(page.locator("#market-focus")).to_have_count(0)
    assert pdf_pages(a4(page)) <= 4
    for market, title, sub in (("datacenter", "Data center", "Rack power"), ("drones", "Drones", "Radio links")):
        go(page, f"{TO}?focus={market}")
        expect(page.locator("#market-focus")).to_contain_text(title)
        expect(page.locator("#market-focus")).to_contain_text(sub)
        assert pdf_pages(a4(page)) <= 5
    go(page, f"{TO}?focus=bogus&wm=bogus")
    expect(page.locator("#market-focus")).to_have_count(0)
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
    """The length limits keep the PDF at 4 A4 pages (5 with the focus page), even with every text and number at its
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
        for market in te.to.focus_markets():
            go(page, f"{TO}?focus={market}&wm=draft")
            assert pdf_pages(a4(page)) <= 5, market
    finally:
        reset_overview(page)


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
