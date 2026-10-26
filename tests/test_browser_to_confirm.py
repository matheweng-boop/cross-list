"""Data management › To confirm in a real Chromium at iPad and phone size (owner, 25 Oct 2026: the owner uses an
iPad): Read opens the abstract, Confirm takes the card off the feed with an Undo, no sideways scrolling."""

import pytest

from tests.conftest import PAGE_TIMEOUT

expect = pytest.importorskip("playwright.sync_api").expect

pytestmark = pytest.mark.browser

IPAD = {"width": 820, "height": 1180}  # iPad held upright
PHONE = {"width": 390, "height": 844}


def _overflow(page) -> int:
    return page.evaluate("Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth)")


def _tab(chromium, live_server, viewport):
    ctx = chromium.new_context(base_url=live_server, viewport=viewport, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.set_default_timeout(PAGE_TIMEOUT)
    return ctx, page, errors


def test_read_expands_and_confirm_removes_at_ipad_size(chromium, live_server):
    ctx, page, errors = _tab(chromium, live_server, IPAD)
    try:
        page.goto("/manage/to-confirm?type=risk")
        card = page.locator(".tc-card").first
        key = card.get_attribute("data-key")
        count = page.locator('.tc-tabs [data-count="open"]')
        before = int(count.inner_text())
        expect(card.locator(".tc-abstract")).to_be_hidden()
        card.locator(".tc-read summary").click()  # Read
        expect(card.locator(".tc-abstract")).to_be_visible()
        expect(card.get_by_role("link", name="Full text →")).to_be_visible()
        box = card.get_by_role("button", name="Confirm").bounding_box()
        assert box["height"] >= 44 and box["width"] >= 88  # a big tap target
        card.get_by_role("button", name="Confirm").click()
        expect(card).to_be_hidden()
        expect(count).to_have_text(str(before - 1))
        expect(page.locator("#tc-status")).to_contain_text("Confirmed")
        assert _overflow(page) <= 1
        page.reload()
        assert page.locator(f'.tc-card[data-key="{key}"]').count() == 0  # stored, not only hidden
        page.goto("/manage/to-confirm?tab=confirmed&type=risk")
        expect(page.locator(f'.tc-card[data-key="{key}"]')).to_be_visible()
        page.locator(f'.tc-card[data-key="{key}"]').get_by_role("button", name="Undo").click()
        expect(page.locator("#tc-status")).to_contain_text("Back in the feed")
        page.goto("/manage/to-confirm?type=risk")
        expect(page.locator(f'.tc-card[data-key="{key}"]')).to_be_visible()  # back in the feed
        assert not errors, errors
    finally:
        ctx.close()


def test_feed_fits_a_phone(chromium, live_server):
    ctx, page, errors = _tab(chromium, live_server, PHONE)
    try:
        for url in ("/manage/to-confirm", "/manage/to-confirm?tab=ignored", "/business/reports/auto-uwb-cpd",
                    "/business/risks"):
            page.goto(url)
            assert _overflow(page) <= 1, url
        page.goto("/manage/to-confirm")
        expect(page.locator(".tc-card").first.locator(".tc-gist")).to_be_visible()
        assert not errors, errors
    finally:
        ctx.close()
