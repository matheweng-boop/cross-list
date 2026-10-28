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


def test_bldc_shows_back_emf_zero_crossing_and_speed():
    """Owner, 28 Oct 2026 ("BLDC Motor Functionality - including Back EMF for circuits in Motion"): the BLDC visual
    draws each phase's back-EMF (trapezoidal in 6-step, sine in FOC), marks the floating phase's zero crossings and the
    commutations 30 degrees later, and has a speed slider: the current falls as the back-EMF nears the bus voltage."""
    js = JS.read_text()
    bldc = js[js.index('id: "bldc", group') : js.index("3 · buck converter")]
    for t in ('k: "spd"', "emfTrap", "emfSine", "floating(", "cf-zc", "cf-cm", "+30° → commutate", "VBUS - e",
              "limited by the back-EMF", "commutation = zero crossing + 30°"):  # fmt: skip
        assert t in bldc or t in js[: js.index('id: "bldc", group')], t
    assert "vlines" in js and ".cf-zc" in CSS.read_text() and ".cf-cm" in CSS.read_text()
    assert library.VISUALS["bldc"][0] == "BLDC motor: 6-step commutation, FOC and back-EMF"
    read = dict(visuals.explanations()["bldc"])["How to read it"]
    assert "SPRABQ7A" in read and "AN1946" in read and "AP16173" in read and "30 degrees" in read
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    # the waveform maths: the floating phase's trapezoidal back-EMF crosses zero mid-step, the driven ones are flat
    probe = """
const AX = {A: 90, B: 210, C: 330};
const wrap180 = a => ((((a + 180) % 360) + 360) % 360) - 180;
const trap = a => { const p = Math.abs(wrap180(a)); return p <= 60 ? 1 : p >= 120 ? -1 : 1 - (p - 60) / 30; };
const emfTrap = (th, k) => trap(th + 90 - AX[k]);
const v = [emfTrap(30, "B"), emfTrap(15, "A"), emfTrap(15, "C"), emfTrap(90, "A"), emfTrap(150, "C")];
console.log(JSON.stringify(v));
"""
    for name in ("wrap180", "trap", "emfTrap"):  # the probe copies the real definitions
        line = next(ln.strip() for ln in js.splitlines() if ln.strip().startswith(f"const {name} ="))
        assert line in probe, name
    out = subprocess.run([node, "-e", probe], check=True, capture_output=True, text=True).stdout
    b30, a15, c15, a90, c150 = (round(x, 6) for x in __import__("json").loads(out))
    assert b30 == 0 and a15 == 1 and c15 == -1 and a90 == 0 and c150 == 0


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
            # back-EMF: zero-crossing ticks in the waveform; the speed slider raises the back-EMF and cuts the current
            page.locator(".cf-play").tap()
            assert page.locator(".cf-wave .cf-zc").count() >= 6
            page.locator('.cf-x[data-b="foc"]').tap()  # back to 6-step
            assert page.locator(".cf-wave .cf-cm").count() >= 6 and "floats" in page.locator(".cf-bemf").text_content()
            page.locator('input[data-k="spd"]').fill("100")
            page.locator('input[data-k="spd"]').dispatch_event("input")
            page.wait_for_timeout(100)
            assert "limited by back-EMF" in page.locator(".cf-head").text_content()

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
