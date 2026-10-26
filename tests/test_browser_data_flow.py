"""Data management › Data flow in a real Chromium at iPad size (owner, 26 Oct 2026; the owner uses an iPad): drag a
box, connect two boxes with the handle, tap for details, save, reload keeps it, Undo; no console errors, no sideways
scroll."""

import os

import pytest

expect = pytest.importorskip("playwright.sync_api").expect

pytestmark = pytest.mark.browser

IPAD = {"width": 820, "height": 1180}


def _center(loc):
    b = loc.bounding_box()
    return b["x"] + b["width"] / 2, b["y"] + b["height"] / 2


def _drag(page, start, end):
    page.mouse.move(*start)
    page.mouse.down()
    for k in range(1, 9):
        page.mouse.move(start[0] + (end[0] - start[0]) * k / 8, start[1] + (end[1] - start[1]) * k / 8)
    page.mouse.up()


def test_drag_connect_save_reload_at_ipad_size(chromium, live_server):
    ctx = chromium.new_context(base_url=live_server, viewport=IPAD, is_mobile=True, has_touch=True)
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.set_default_timeout(10_000)
    try:
        page.goto("/manage/data-flow")
        expect(page.locator("#df-svg .lane")).to_have_count(4)
        n_nodes = page.locator("#df-svg .node").count()
        assert n_nodes >= 25
        n_edges = page.locator("#df-svg .edge").count()
        assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 1

        # tap a source category: its plain list shows below the chart
        page.locator('#df-svg [data-node="mfr_docs"] rect.box').click()
        expect(page.locator("#df-info")).to_contain_text("Datasheets")

        page.locator("#df-frame").scroll_into_view_if_needed()
        # drag a box
        node = page.locator('#df-svg [data-node="gists"]')
        before = node.get_attribute("transform")
        x, y = _center(node.locator("rect.box"))
        _drag(page, (x, y), (x + 50, y))
        moved = node.get_attribute("transform")
        assert moved != before
        expect(page.locator("#df-status")).to_contain_text("Not saved yet")

        # connect two boxes: drag the handle of one onto the other
        hx, hy = _center(page.locator('#df-svg [data-handle="research"]'))
        tx, ty = _center(page.locator('#df-svg [data-node="cases"] rect.box'))
        _drag(page, (hx, hy), (tx, ty))
        expect(page.locator("#df-status")).to_contain_text("Connected")
        expect(page.locator("#df-svg .edge")).to_have_count(n_edges + 1)

        page.get_by_role("button", name="Save").click()
        expect(page.locator("#df-status")).to_contain_text("Saved")
        expect(page.locator("#df-changes")).to_contain_text("new edge Research & ideas→Business cases")
        expect(page.locator("#df-changes")).to_contain_text("moved 'Gists and abstracts'")
        if os.environ.get("DATA_FLOW_SHOT"):
            page.screenshot(path=os.environ["DATA_FLOW_SHOT"], full_page=False)

        page.reload()
        expect(page.locator("#df-svg .edge")).to_have_count(n_edges + 1)
        assert page.locator('#df-svg [data-node="gists"]').get_attribute("transform") == moved
        expect(page.locator("#df-changes")).to_contain_text("new edge Research & ideas→Business cases")

        # Undo goes back to the file version
        page.get_by_role("button", name="Undo last save").click()
        expect(page.locator("#df-status")).to_contain_text("Undone")
        expect(page.locator("#df-svg .edge")).to_have_count(n_edges)
        assert page.locator('#df-svg [data-node="gists"]').get_attribute("transform") == before
        assert not errors, errors
    finally:
        ctx.close()
