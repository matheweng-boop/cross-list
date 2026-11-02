"""Products › Cross a list in a real Chromium (shared fixtures in conftest.py): paste, submit, the summary, a red row,
the light filter, and no sideways scrolling on an iPad or a phone."""

import pytest

from tests.conftest import PAGE_TIMEOUT
from tests.test_browser import PHONE, Watch, overflow

expect = pytest.importorskip("playwright.sync_api").expect

pytestmark = pytest.mark.browser

IPAD = {"width": 820, "height": 1180}  # iPad Air held upright


@pytest.mark.parametrize("viewport", [IPAD, PHONE], ids=["ipad", "phone"])
def test_paste_submit_summary_and_red_row(chromium, live_server, viewport):
    watch = Watch(live_server)
    ctx = chromium.new_context(base_url=live_server, viewport=viewport, has_touch=True)
    page = watch.attach(ctx.new_page())
    page.set_default_timeout(PAGE_TIMEOUT)
    page.goto("/cross-list", wait_until="load")
    expect(page.locator(".cx-privacy")).to_contain_text("public part numbers only")
    page.locator("#cx-parts").fill("SC141\t2000\t$0.85\nSD4100, SC142\nZZZ999\nSC141")
    page.get_by_role("button", name="Cross all").click()
    page.wait_for_load_state("load")
    expect(page.locator(".cx-summary")).to_contain_text("4 parts")
    red = page.locator('tr.cx-row[data-light="red"]', has_text="ZZZ999")
    expect(red).to_be_visible()
    expect(red).to_contain_text("Not in our data")
    page.locator('.cx-chips .cx-chip[data-light="red"]').click()
    expect(page.locator('tr.cx-row[data-light="amber"]').first).to_be_hidden()
    expect(red).to_be_visible()
    every = page.evaluate("window.cxTable(false).tsv").strip().split("\n")
    shown = page.evaluate("window.cxTable(true).tsv").strip().split("\n")
    crossed = page.evaluate("window.cxTable(false, true).tsv").strip().split("\n")
    assert len(crossed) == 3 and "ZZZ999" not in "".join(crossed)  # header + SC141, SD4100 (owner, 27 Oct 2026)
    assert page.evaluate("window.cxTable(true, true).tsv").strip().split("\n") == crossed[:1]  # red and crossed
    assert every[0].startswith("#\tYour part") and len(every) == 5 and len(shown) == 3  # header + parts
    assert "<table" in page.evaluate("window.cxTable(false).html")
    page.locator("#cx-only-shown").check()
    assert page.locator("#cx-dl-lights").input_value() == "red"
    page.locator("#cx-only-crossed").check()
    assert page.locator("#cx-dl-crossed").input_value() == "1"
    assert overflow(page) <= 1, f"{overflow(page)} px sideways scroll at {viewport['width']} px"
    ctx.close()
    assert not watch.errors, watch.errors


@pytest.mark.parametrize("viewport", [IPAD, PHONE], ids=["ipad", "phone"])
def test_supply_voltage_input(chromium, live_server, viewport):
    """Owner, 2 Nov 2026: an optional supply voltage; the value stays in the form after crossing and goes with the
    Excel download; no sideways scrolling."""
    watch = Watch(live_server)
    ctx = chromium.new_context(base_url=live_server, viewport=viewport, has_touch=True)
    page = watch.attach(ctx.new_page())
    page.set_default_timeout(PAGE_TIMEOUT)
    page.goto("/cross-list", wait_until="load")
    page.locator("#cx-parts").fill("SC141")
    page.locator("#cx-vdd").fill("3.3")
    page.get_by_role("button", name="Cross all").click()
    page.wait_for_load_state("load")
    expect(page.locator(".cx-summary")).to_contain_text("1 part")
    assert page.locator("#cx-vdd").input_value() == "3.3"
    assert page.locator('.cx-dl input[name="vdd"]').input_value() == "3.3"
    assert overflow(page) <= 1, f"{overflow(page)} px sideways scroll at {viewport['width']} px"
    ctx.close()
    assert not watch.errors, watch.errors


@pytest.mark.parametrize("viewport", [IPAD, PHONE], ids=["ipad", "phone"])
def test_part_page_supply_voltage(chromium, live_server, viewport):
    """The part page's optional supply voltage (owner, 2 Nov 2026) for a digital isolator: kept in the URL and the
    field; no sideways scrolling."""
    watch = Watch(live_server)
    ctx = chromium.new_context(base_url=live_server, viewport=viewport, has_touch=True)
    page = watch.attach(ctx.new_page())
    page.set_default_timeout(PAGE_TIMEOUT)
    page.goto("/find?q=SC141", wait_until="load")
    field = page.locator('.result-filters input[name="vdd"]')
    field.fill("2.5")
    page.locator(".result-filters").get_by_role("button", name="Apply").click()
    page.wait_for_load_state("load")
    assert "vdd=2.5" in page.url and page.locator('.result-filters input[name="vdd"]').input_value() == "2.5"
    assert overflow(page) <= 1, f"{overflow(page)} px sideways scroll at {viewport['width']} px"
    ctx.close()
    assert not watch.errors, watch.errors
