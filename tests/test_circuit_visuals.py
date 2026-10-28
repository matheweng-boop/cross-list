"""Animated circuit visuals (owner, 28 Oct 2026: "diagrams that move like in a circuit diagram the way current flows";
"Build the six examples you mentioned ... Put it in the engineering knowledge"): six visuals in static/vz/circuit.js,
registered, explained, linked from Part knowledge, and moving in a real browser at iPad size."""

import re
import shutil
import subprocess

import pytest

from app.config import PROJECT_ROOT
from app.services import library, visuals

CIRCUITS = ("bootstrap", "bldc", "buck", "efuse", "isosense", "ook")
JS = PROJECT_ROOT / "app" / "web" / "static" / "vz" / "circuit.js"
CSS = PROJECT_ROOT / "app" / "web" / "static" / "vz" / "circuit.css"


def test_six_circuits_are_registered_with_explanation_boxes():
    ex = visuals.explanations()
    js = JS.read_text()
    for vid in CIRCUITS:
        assert library.VISUALS[vid][1] == f"/visuals#{vid}"
        assert f'id: "{vid}", group: "Circuits in motion"' in js, vid
        assert {label for label, _ in ex[vid]} == {"What it shows", "How to read it", "What to try", "Why it matters"}
    # numbers shown name their source in the box
    read = dict(ex["isosense"])["How to read it"]
    assert "AN1270" in read and "-0.530 / +0.484" in read
    assert "AN1359" in dict(ex["ook"])["How to read it"] and "SLUA887A" in dict(ex["bootstrap"])["Why it matters"]


def test_js_and_css_exist_and_parse():
    assert JS.exists() and CSS.exists()
    css = CSS.read_text()
    assert "prefers-color-scheme: dark" in css and ':root[data-theme="dark"] .cf' in css  # light and dark tokens
    js = JS.read_text()
    assert "prefers-reduced-motion" in js and "stroke-dashoffset" in js
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    subprocess.run([node, "--check", str(JS)], check=True, capture_output=True)


def test_visuals_page_loads_the_circuits_with_their_boxes(client):
    html = client.get("/visuals").text
    assert "/static/vz/circuit.js" in html and "/static/vz/circuit.css" in html
    for vid in CIRCUITS:
        assert f'class="vz-explain" data-for="{vid}"' in html, vid
    assert client.get("/static/vz/circuit.js").status_code == 200
    assert client.get("/static/vz/circuit.css").status_code == 200


def test_part_knowledge_and_other_pages_link_the_circuits(client):
    want = {"motor": ("bootstrap", "bldc"), "gatedriver": ("bootstrap",), "isolator": ("ook",),
            "currentsense": ("isosense",)}
    for group, vids in want.items():
        page = client.get(f"/reviews/how/{group}")
        assert page.status_code == 200
        for vid in vids:
            assert f'href="/visuals#{vid}"' in page.text, (group, vid)
    report = client.get("/business/reports/auto-hv-hot-swap").text
    assert 'href="/visuals#efuse"' in report and 'href="/visuals#buck"' in report
    cards = client.get("/knowledge").text  # Engineering knowledge, By product
    for vid in CIRCUITS:
        assert f'href="/visuals#{vid}"' in cards, vid
    # every /visuals#id link in the Part knowledge data points at a registered visual
    from app.services import how_it_works as hw

    for vid in re.findall(r"/visuals#([a-z0-9-]+)", hw.FILE.read_text()):
        assert vid in library.VISUALS, vid


# ---- in a real Chromium at iPad size ---------------------------------------------------------------------------------
def _offsets(page):
    return page.eval_on_selector_all(".cf-flow", "els => els.map(e => e.dataset.k + ':' + e.style.strokeDashoffset)")


@pytest.mark.browser
def test_ipad_play_and_step_move_the_current(chromium, live_server):
    pytest.importorskip("playwright.sync_api")
    from tests.conftest import PAGE_TIMEOUT

    for reduced in ("no-preference", "reduce"):
        ctx = chromium.new_context(base_url=live_server, viewport={"width": 820, "height": 1180}, has_touch=True,
                                   is_mobile=True, reduced_motion=reduced)  # fmt: skip
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda e, errs=errors: errs.append(str(e)))
        page.set_default_timeout(PAGE_TIMEOUT)
        try:
            # 1 · bootstrap: plays by default; the dots move along the wires; Pause stops them, Step changes the phase
            page.goto("/visuals#bootstrap")
            page.wait_for_selector(".cf-svg .cf-flow")
            play = page.locator(".cf-play")
            if reduced == "reduce":
                assert "Play" in play.inner_text()  # starts paused
                before = _offsets(page)
                page.wait_for_timeout(400)
                assert _offsets(page) == before
                play.tap()
            assert "Pause" in play.inner_text()
            first = _offsets(page)
            page.wait_for_timeout(500)
            assert _offsets(page) != first, "the current dots did not move"
            play.tap()
            phase = page.locator(".cf-ph").inner_text()
            page.locator(".cf-step").tap()
            assert page.locator(".cf-ph").inner_text() != phase

            # 2 · BLDC: Step turns the rotor to the next 60° state; the FOC toggle switches the drive
            page.goto("/visuals#bldc")
            page.reload()
            page.wait_for_selector(".cf-rotor")
            if "Pause" in page.locator(".cf-play").inner_text():
                page.locator(".cf-play").tap()
            angle = page.locator(".cf-rotor").get_attribute("data-angle")
            phase = page.locator(".cf-ph").inner_text()
            page.locator(".cf-step").tap()
            assert page.locator(".cf-rotor").get_attribute("data-angle") != angle
            new = page.locator(".cf-ph").inner_text()
            assert new != phase and new.startswith("Step ")
            page.locator('.cf-x[data-b="foc"]').tap()
            assert page.locator(".cf-ph").inner_text().startswith("FOC")
            page.locator(".cf-play").tap()
            angle = page.locator(".cf-rotor").get_attribute("data-angle")
            page.wait_for_timeout(400)
            assert page.locator(".cf-rotor").get_attribute("data-angle") != angle

            # no sideways scroll at iPad width, on any of the six
            for vid in CIRCUITS:
                page.goto(f"/visuals#{vid}")
                page.reload()
                page.wait_for_selector(".cf-svg")
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), vid
                assert page.locator(f'#vz-panel .vz-explain[data-for="{vid}"]').count() == 1
            assert not errors, errors
        finally:
            ctx.close()
