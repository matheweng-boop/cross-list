"""Data management › Data flow in a real Chromium at iPad size (owner, 26 Oct 2026; the owner uses an iPad): the three
columns (27 Oct 2026), handover labels always shown and other labels only on tap, the research inputs as one bundle;
drag a box, connect two boxes with the handle, tap for details, save, reload keeps it, Undo; no console errors, no
sideways scroll."""

import os
import re

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
        # three columns: inputs, then each process as a framed panel; two input brackets; one bundled research arrow
        expect(page.locator("#df-svg .lane")).to_have_count(3)
        expect(page.locator("#df-svg .lane-crosses .lane-title")).to_have_text("2 · Cross process")
        sub = "sources and comments → reports you confirm"
        expect(page.locator("#df-svg .lane-research .lane-sub")).to_have_text(sub)
        expect(page.locator("#df-svg .bracket.g-cross")).to_have_count(1)
        expect(page.locator("#df-svg .bracket.g-research")).to_have_count(1)
        expect(page.locator("#df-svg .bundle")).to_have_count(1)
        expect(page.locator("#df-svg .row-band")).to_have_count(0)
        data = page.evaluate("JSON.parse(document.querySelector('#df-data').textContent)")
        n_nodes = len(data["state"]["nodes"])
        expect(page.locator("#df-svg .node")).to_have_count(n_nodes)
        group = {n["id"]: n.get("group") for n in data["state"]["nodes"]}
        bundled = [e for e in data["state"]["edges"] if group.get(e["from"]) == "research" and not e.get("handover")]
        assert len(bundled) >= 5
        n_edges = page.locator("#df-svg .edge").count()
        assert n_edges == len(data["state"]["edges"]) - len(bundled)  # the research inputs ride in the bundle
        assert page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth") <= 1

        # labels: the four handovers always, every other line none until tapped
        expect(page.locator("#df-svg .edge.handover text")).to_have_count(4)
        for t in ("crossed parts", "gaps", "volumes", "parts in designs (planned)"):
            expect(page.locator("#df-svg .edge.handover text", has_text=t).first).to_be_visible()
        expect(page.locator("#df-svg .edge:not(.handover) text")).to_have_count(0)

        page.locator("#df-frame").scroll_into_view_if_needed()
        # tap a research input: its own lines show (highlighted, labelled), routed below the cross panel
        page.locator('#df-svg [data-node="market_sources"] rect.box').click()
        expect(page.locator("#df-info")).to_contain_text("Analyst press releases")
        expect(page.locator("#df-info")).to_contain_text("Kept in:")
        hl = page.locator("#df-svg .edge.hl")
        expect(hl).to_have_count(2)
        expect(page.locator("#df-svg .edge.hl text", has_text="market figures")).to_have_count(1)
        cross = data["lanes"][1]
        panel_bottom = float(page.locator("#df-svg .lane-crosses rect").get_attribute("height"))
        for k in range(2):
            pts = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", hl.nth(k).locator("path.line").get_attribute("d"))]
            for px, py in zip(pts[::2], pts[1::2], strict=True):
                if cross["x"] < px < cross["x"] + cross["w"]:
                    assert py > panel_bottom, (px, py)  # never through the cross column

        # tap a cross box: where its data is kept shows below the chart; its own line labels appear
        page.locator('#df-svg [data-node="importers"] rect.box').click()
        expect(page.locator("#df-info")).to_contain_text("Kept in: data/real/")
        expect(page.locator("#df-svg .edge.hl text", has_text="checked values")).to_have_count(1)

        # drag a box
        node = page.locator('#df-svg [data-node="gists"]')
        before = node.get_attribute("transform")
        x, y = _center(node.locator("rect.box"))
        _drag(page, (x, y), (x + 40, y))
        moved = node.get_attribute("transform")
        assert moved != before
        expect(page.locator("#df-status")).to_contain_text("Not saved yet")

        # connect two boxes: drag the handle of one onto the other
        hx, hy = _center(page.locator('#df-svg [data-handle="tam_check"]'))
        tx, ty = _center(page.locator('#df-svg [data-node="shareable"] rect.box'))
        _drag(page, (hx, hy), (tx, ty))
        expect(page.locator("#df-status")).to_contain_text("Connected")
        expect(page.locator("#df-svg .edge")).to_have_count(n_edges + 1)

        page.get_by_role("button", name="Save").click()
        expect(page.locator("#df-status")).to_contain_text("Saved")
        expect(page.locator("#df-changes")).to_contain_text("new edge Market size→Shareables")
        expect(page.locator("#df-changes")).to_contain_text("moved 'Summaries'")
        if os.environ.get("DATA_FLOW_SHOT"):
            page.screenshot(path=os.environ["DATA_FLOW_SHOT"], full_page=False)

        page.reload()
        expect(page.locator("#df-svg .edge")).to_have_count(n_edges + 1)
        assert page.locator('#df-svg [data-node="gists"]').get_attribute("transform") == moved
        expect(page.locator("#df-changes")).to_contain_text("new edge Market size→Shareables")

        # Undo goes back to the file version
        page.get_by_role("button", name="Undo last save").click()
        expect(page.locator("#df-status")).to_contain_text("Undone")
        expect(page.locator("#df-svg .edge")).to_have_count(n_edges)
        assert page.locator('#df-svg [data-node="gists"]').get_attribute("transform") == before
        assert not errors, errors
    finally:
        ctx.close()
