"""Interactive visuals in a real Chromium (owner, 26 Oct 2026: "explanations below all graphs"): opening a chart
visual or a diagram visual puts its "How to read this visual" box in the panel, below the graph or diagram."""

import pytest

pytest.importorskip("playwright.sync_api")

pytestmark = pytest.mark.browser


def test_box_shows_below_the_graph(chromium, live_server):
    ctx = chromium.new_context(base_url=live_server, viewport={"width": 820, "height": 1180})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.set_default_timeout(10_000)
    try:
        for vid, below in (("link", ".vz-chartwrap"), ("dab", ".vz-more"), ("hex", ".vz-more")):
            page.goto(f"/visuals#{vid}")
            page.reload()  # a hash change alone keeps the page; reload so each visual opens from scratch
            box = page.locator(f'#vz-panel .vz-explain[data-for="{vid}"]')
            box.wait_for(state="visible")
            assert box.locator("p").count() == 4
            assert box.bounding_box()["y"] > page.locator(f"#vz-panel {below}").bounding_box()["y"], vid
        assert not errors, errors
    finally:
        ctx.close()
