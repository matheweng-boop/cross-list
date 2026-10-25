"""Owner feedback 25 Oct 2026 on Engineering knowledge > Interactive visuals: DAB blocks and ensembles drawn better
(Band III raster, 96 ms frame, sub-channels you can click), a step-by-step signal flow for DAB, FM and AM, and an
RDS section (57 kHz in the MPX, groups and blocks, decode example, RBDS)."""

import json
import shutil
import subprocess

import pytest

from app.config import PROJECT_ROOT
from app.services import knowledge, library

STATIC = PROJECT_ROOT / "app" / "web" / "static"
VZ = STATIC / "vz"
NEW = ("flow", "rds")
node = pytest.mark.skipif(not shutil.which("node"), reason="needs node to run the visuals' JavaScript")

# Loads the shared sketch helpers and the three radio visuals with a stand-in for the engine; prints JSON.
HARNESS = """
global.window = {};
for (const f of ["sketch", "dab", "flow", "rds"]) require(%s + "/" + f + ".js");
const V = [], C = {blue: "#1", orange: "#2", green: "#3", purple: "#4", teal: "#5", red: "#6", grey: "#7"};
const num = x => String(+(+x).toPrecision(4)), esc = s => String(s);
const log10 = Math.log10, bandStrip = () => "";
for (const add of window.VZ_ADD) add({V, C, num, esc, log10, bandStrip});
const vis = id => V.find(v => v.id === id);
const run = (id, over) => {
  const v = vis(id);
  return v.compute({...Object.fromEntries(v.controls.map(c => [c.k, c.value])), ...over}, 0);
};
%s
"""


def _node(body: str):
    script = HARNESS % (json.dumps(str(VZ)), body)
    return json.loads(subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True).stdout)


def test_new_visuals_are_registered_included_and_load_before_the_engine(client):
    page = client.get("/visuals").text
    engine = page.index('src="/static/visuals.js"')
    for v in NEW:
        js = (VZ / f"{v}.js").read_text()
        assert "window.VZ_ADD" in js and f'id: "{v}", group: "Broadcast radio"' in js
        assert -1 < page.index(f'src="/static/vz/{v}.js"') < engine
        assert library.VISUALS[v][1] == f"/visuals#{v}"
        assert client.get(f"/static/vz/{v}.js").status_code == 200
    assert page.index("/static/vz/sketch.js") < page.index("/static/vz/dab.js") < page.index("/static/vz/flow.js")
    assert client.get("/static/vz/radio.css").status_code == 200 and "/static/vz/radio.css" in page
    tuners = next(p for p in knowledge.data()["products"] if p["key"] == "tuners")
    assert {"dab", "flow", "rds"} <= set(tuners["visuals"])
    for f in ("sketch", "flow", "rds", "dab"):  # no other site, no library
        src = (VZ / f"{f}.js").read_text()
        assert "http://" not in src and "https://" not in src and "import " not in src


def test_owner_content_is_in_the_sources():
    dab = (VZ / "dab.js").read_text()
    for s in (
        '["5A", 174.928]',
        '["12C", 227.360]',
        '["13F", 239.200]',
        "Blocks and ensembles",
        "FIC",
        "MSC",
        "CIF",
        "data-dab-blk",
        "data-dab-svc",
        "Sub-channel",
        "Start address",
        "Protection",
        "96 ms",
    ):
        assert s in dab, s
    flow = (VZ / "flow.js").read_text()
    for s in (
        "Illustrative",
        "What changed",
        "Next ›",
        "‹ Prev",
        "data-fl-step",
        "19 kHz",
        "MPX",
        "De-emphasis",
        "Envelope",
        "Viterbi",
        "FFT",
        "On our chips",
        "/broadcast",
        "Si469",
        "Si4706",
        "Si4734",
    ):
        assert s in flow, s
    rds = (VZ / "rds.js").read_text()
    for s in ("57 kHz", "1187.5", "PI", "PS", "RadioText", "TP", "TA", "AF", "CT", "RBDS", "IEC 62106", "made up"):
        assert s in rds, s


@node
def test_every_step_renders_for_dab_fm_and_am():
    r = _node("""
      const out = {};
      for (const sys of ["dab", "fm", "am"]) out[sys] = window.VZ_FLOW.CHAINS[sys].map((_, i) => {
        const x = run("flow", {sys, step: i + 1});
        return {title: x.html.match(/Step \\d+ of \\d+: ([^<]+)/)[1], svgs: (x.html.match(/<svg/g) || []).length,
                bad: /NaN|undefined|Infinity/.test(x.html), what: x.html.includes("What changed:")};
      });
      console.log(JSON.stringify(out));""")
    for sys, steps in r.items():
        assert len(steps) == 9, sys
        assert all(s["svgs"] >= 2 and s["what"] and not s["bad"] for s in steps), sys
    titles = {sys: " ".join(s["title"] for s in steps) for sys, steps in r.items()}
    assert (
        "antenna" in titles["dab"]
        and "FFT" in titles["dab"]
        and "Viterbi" in titles["dab"]
        and "Audio out" in titles["dab"]
    )
    assert "MPX" in titles["fm"] and "Stereo" in titles["fm"] and "De-emphasis" in titles["fm"]
    assert "Envelope" in titles["am"] and "Mixer" in titles["am"]


@node
def test_dab_ensemble_highlights_the_block_and_the_service():
    r = _node("""
      const a = run("dab", {}), b = run("dab", {blk: "178.352", svc: "3", eep: "1A"});
      console.log(JSON.stringify({a: a.html, b: b.html, bo: b.outputs}));""")
    a, b = r["a"], r["b"]
    assert (
        'data-dab-blk="227.36" tabindex="0" role="button" aria-label="Block 12C, 227.36 MHz" aria-pressed="true"' in a
    )
    assert a.count("data-dab-blk=") == 38 and "12C · 227.36 MHz · 1.536 MHz wide" in a
    assert 'data-dab-svc="0"' in a and "CU 0–71" in a  # City Pop, 96 kbit/s at EEP-3A = 72 CU from CU 0
    assert "Block 5C" in b and 'aria-label="Block 5C, 178.352 MHz" aria-pressed="true"' in b
    assert "Sport Live" in b and "EEP-1A, code rate 1/4" in b and "does not fit" in b  # 1A needs 1032 CU > 864


@node
def test_rds_groups_decode_with_real_check_words():
    r = _node("""
      const R = window.VZ_RDS;
      const st = {pi: 0xD3C2, ps: "BIZ FM  ", af: [89.1, 94.6, 101.3], rt: "Hello", utc: [2026, 10, 25, 17, 42],
                  offsetHalfHours: 2, ms: 1, stereo: 1, ab: 0, tp: 1, ta: 1, pty: 10};
      const g0 = R.group("0A", 3, st), g2 = R.group("2A", 0, st), g4 = R.group("4A", 0, st);
      const x = run("rds", {}), y = run("rds", {reg: "rbds", grp: "2A", seg: 1});
      console.log(JSON.stringify({c8000: R.check(0x8000), c1: R.check(1),
        pi: R.rbdsPi("WXYZ"), k: R.rbdsPi("KAAA"),
        g0: g0.map(b => b.info), ok: [g0, g2, g4].every(g => g.every(b => R.syndromeOk(b.info, b.cw, b.off))),
        g2: g2.map(b => b.info), mjd: R.mjd(2026, 10, 25), back: R.fromMjd(R.mjd(2026, 10, 25)),
        g4: g4.map(b => b.info),
        af: [R.afCode(89.1), R.afMhz(16)], x: x.html, y: y.html, yo: y.outputs}));""")
    assert r["c8000"] == 0x077 and r["c1"] == 0x1B9  # first and last rows of the RDS parity matrix
    assert r["ok"]
    assert r["g0"] == [0xD3C2, 0x055F, 0x478A, 0x2020]  # TP, PTY 10, TA, music, stereo, segment 3; AF 94.6 / 101.3
    assert r["g2"] == [0xD3C2, 0x2540, 0x4865, 0x6C6C]  # "Hell"
    assert r["back"] == [2026, 10, 25] and r["g4"][2] >> 1 == r["mjd"] & 0x7FFF
    assert r["pi"] == 21672 + 676 * 23 + 26 * 24 + 25 and r["k"] == 4096 and r["af"] == [16, 89.1]
    assert (
        "57 kHz" in r["x"] and "Where RDS sits" in r["x"] and "BIZ FM" in r["x"] and "RBDS in North America" in r["x"]
    )
    assert "Country" in r["y"] and "RadioText characters 5–8" in r["y"]


# --- browser, 390 px phone ------------------------------------------------------------------------------------------
@pytest.mark.browser
def test_radio_visuals_click_through_on_a_phone(chromium, live_server):
    expect = pytest.importorskip("playwright.sync_api").expect
    from tests.test_browser import Watch, overflow

    watch = Watch(live_server)
    ctx = chromium.new_context(
        base_url=live_server, viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True
    )
    page = watch.attach(ctx.new_page())
    page.set_default_timeout(10_000)
    try:
        page.goto("/visuals#dab", wait_until="load")
        panel = page.locator("#vz-panel")
        expect(panel.locator(".dab-ens h3")).to_have_text("Blocks and ensembles")
        panel.locator('[data-dab-blk="178.352"]').click()
        expect(panel.locator('select[data-k="blk"]')).to_have_value("178.352")
        expect(panel.locator(".dab-ens")).to_contain_text("Block 5C")
        panel.locator('tr[data-dab-svc="1"]').click()
        expect(panel.locator('select[data-k="svc"]')).to_have_value("1")
        expect(panel.locator(".dab-detail")).to_contain_text("News 24")
        assert overflow(page) <= 1

        page.goto("/visuals#flow", wait_until="load")
        expect(panel.locator(".fl-now h3")).to_contain_text("Step 1 of 9")
        panel.locator(".fl-nav", has_text="Next").click()
        expect(panel.locator(".fl-now h3")).to_contain_text("Step 2 of 9")
        panel.locator('.fl-blk[data-fl-step="6"]').click()
        expect(panel.locator(".fl-now h3")).to_contain_text("OFDM")
        panel.locator('select[data-k="sys"]').select_option("fm")
        expect(panel.locator(".fl-now h3")).to_contain_text("MPX")
        panel.locator(".fl-nav", has_text="Prev").click()
        expect(panel.locator(".fl-now h3")).to_contain_text("Step 5 of 9")
        panel.locator('select[data-k="sys"]').select_option("am")
        panel.locator('.fl-blk[data-fl-step="6"]').click()
        expect(panel.locator(".fl-now h3")).to_contain_text("Envelope")
        assert overflow(page) <= 1

        page.goto("/visuals#rds", wait_until="load")
        expect(panel.locator(".rd")).to_contain_text("57 kHz")
        expect(panel.locator(".rd-blk")).to_have_count(4)
        expect(panel.locator(".rd-ps")).to_have_text("BI______")
        panel.locator('select[data-k="grp"]').select_option("2A")
        expect(panel.locator(".rd-blk").first).to_contain_text("Block 1")
        panel.locator('select[data-k="reg"]').select_option("rbds")
        expect(panel.locator(".vz-kpis")).to_contain_text("Country")
        assert overflow(page) <= 1
    finally:
        ctx.close()
    assert not watch.errors, watch.errors
