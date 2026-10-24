"""Browser flow tests (24 Oct 2026): the pages the owner uses, clicked in a real Chromium against the app on a real
port.

The other tests read the server's HTML; these catch what only happens in the browser (a script that does not fill a
field, a button that does nothing, a console error, a page wider than a phone). Every test also fails on any console
error or uncaught page error, and when a page it visited scrolls sideways at 390 px. Select them with
``-m browser``, leave them out with ``-m "not browser"``; they skip when the image has no Chromium.
"""

import re

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
