"""Owner feedback 2 Nov 2026 on Engineering knowledge > Interactive visuals (worker E): the dBm ladder's rungs as ranges
with sources (item 12), and the IP3 and FM intermodulation visuals redesigned around the trade-off (item 13)."""

import json
import re
import shutil
import subprocess

import pytest

from app.config import PROJECT_ROOT
from app.services import visuals

STATIC = PROJECT_ROOT / "app" / "web" / "static"
JS = (STATIC / "visuals.js").read_text()
CSS = (STATIC / "rf_visuals.css").read_text()
node = pytest.mark.skipif(not shutil.which("node"), reason="needs node to run the visuals' JavaScript")


def _block(start: str, end: str) -> str:
    """The source between two markers of visuals.js (the start marker included, the end marker not)."""
    a = JS.index(start)
    return JS[a : JS.index(end, a)]


def _run(code: str):
    return json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)


# ---- item 12: the dBm ladder as ranges -------------------------------------------------------------------------------
def _ladder():
    rungs = _block("  const DBM_RUNGS = [", "\n  // owner, 2 Nov 2026")
    ranges = _block("  const SRC = {", "\n  const dlRange =")
    out = "console.log(JSON.stringify({rungs: DBM_RUNGS, ranges: DBM_RANGES}));"
    return _run(f"const NOTE = id => '/rf-notes#' + id;\n{rungs}\n{ranges}\n{out}")


@node
def test_every_range_has_low_typical_high_and_a_source_or_est():
    d = _ladder()
    names = [r["name"] for r in d["rungs"]]
    assert len(names) == len(set(names))
    labels = [g["label"] for g in d["ranges"]]
    assert set(labels) <= set(names) and len(labels) >= 12
    for g in d["ranges"]:
        assert g["lo"] <= g["typ"] <= g["hi"] and g["lo"] < g["hi"], g["label"]
        assert g["moves"] and g["pts"], g["label"]
        assert all(g["lo"] - 2 <= x <= g["hi"] + 2 for _, x in g["pts"]), g["label"]
        assert g["src"] or g.get("est"), g["label"]  # no source: marked est
        for text, url in g["src"]:
            assert text and (not url or url.startswith(("https://", "/"))), g["label"]
            assert "qorvo.com" not in url and "analog.com" not in url
    # fixed definitions stay lines: 1 mW, 1 W and the thermal noise in 1 MHz have no band
    lines = {r["name"]: r["p"] for r in d["rungs"] if r["name"] not in labels}
    assert lines == {"Thermal noise in 1 MHz": -114, "1 mW: the reference": 0, "1 W": 30}
    # the rungs climb the ladder: each one's typical value (or line) is at least the one before
    typ = {g["label"]: g["typ"] for g in d["ranges"]}
    order = [typ.get(r["name"], r["p"]) for r in d["rungs"]]
    assert order == sorted(order)
    assert all(typ[n] == r["p"] for n in typ for r in d["rungs"] if r["name"] == n)  # p is the typical value


@node
def test_owner_example_ble_sensitivity_and_the_sourced_ranges():
    g = {x["label"]: x for x in _ladder()["ranges"]}
    ble = g["BLE sensitivity"]
    assert (ble["lo"], ble["typ"], ble["hi"]) == (-105, -97, -70)  # LE Coded chip, LE 1M chip, specification
    pts = dict((round(x, 1), t) for t, x in ble["pts"])
    assert "specification" in pts[-70] and "LE Coded" in pts[-105] and "CC2652R" in pts[-97]
    srcs = " ".join(t + " " + u for t, u in ble["src"])
    assert "bluetooth.com" in srcs and "cc2652r.pdf" in srcs and "AN1451" in srcs
    for word in ("PHY", "chip", "temperature", "supply", "matching", "switch"):  # what moves it, as the owner listed
        assert word in ble["moves"], word
    lte = g["LTE / 5G phone sensitivity"]
    assert lte["hi"] == -94 and lte["typ"] == -97 and "36.101" in lte["src"][0][0] and "38.101-1" in lte["src"][1][0]
    wifi = g["Wi-Fi sensitivity (by data rate)"]
    assert wifi["lo"] == -96 and wifi["hi"] == -64 and "cc3235s.pdf" in wifi["src"][0][1]
    assert g["Phone transmitter (LTE / 5G)"]["lo"] == -40 and g["Phone transmitter (LTE / 5G)"]["hi"] == 26
    fm, gnss = g["FM tuner sensitivity"], g["GNSS signal at the antenna"]
    assert fm["typ"] == -112 and "Si4734-35-short.pdf" in fm["src"][0][1]
    assert gnss["typ"] == -128.5 and "IS-GPS-200" in gnss["src"][0][0]
    est_only = ("Macro base station, 40 W", "Radar transmitter (peak)", "FM broadcast transmitter",
                "GNSS receiver sensitivity")
    for est in est_only:
        assert g[est].get("est") and not g[est]["src"], est


def test_lna_iip3_band_matches_the_catalogue():
    """The IIP3 band is the 10th to 90th percentile of our LNAs' IIP3 (Skyworks and Qorvo key specs)."""
    vals = sorted(p["iip3"] for p in visuals.rf_parts() if p["stage"] == "lna" and p.get("iip3") is not None)
    assert len(vals) >= 50
    lo, hi = vals[len(vals) // 10], vals[9 * len(vals) // 10]
    m = re.search(r'label: "IIP3 of a good LNA", lo: (-?[\d.]+), typ: (-?[\d.]+), hi: (-?[\d.]+)', JS)
    assert m and abs(float(m[1]) - lo) <= 3 and abs(float(m[3]) - hi) <= 3, (lo, hi, m and m.groups())


def test_ladder_draws_bands_ticks_lines_and_an_info_box():
    for s in ("dl-b", "data-dl=", "aria-pressed", "dl-info", "aria-live", "dl-ln", "Tap or hover a band",
              "nochart: true", "pointerover", "focusin"):  # fmt: skip
        assert s in JS, s
    for s in (".dl-b.est", ".dl-b i", ".dl-ln", ".dl-info", "@media (pointer: coarse)"):
        assert s in CSS, s
    assert '{k: "p", label: "Power", min: -170, max: 90' in JS


# ---- item 13: IP3 and FM intermodulation -----------------------------------------------------------------------------
def _imx(body: str):
    maths = _block("  // ---- intermodulation maths", "  // ---- end of the intermodulation maths")
    return _run(f"{maths}\n{body}")


@node
def test_third_order_products_frequencies_and_levels():
    r = _imx("""console.log(JSON.stringify({
      eq: IMX.im3(91.0, -30, 89.5, -30, -8), uneq: IMX.im3(100, -20, 101, -30, 0),
      up: IMX.im3(91.0, -29, 89.5, -29, -8)[0].p - IMX.im3(91.0, -30, 89.5, -30, -8)[0].p,
      lin: IMX.fm({ft: 92.5, pt: -80, fa: 91, pa: -30, fb: 89.5, pb: -30, iip3: -8}, {lin: 10}),
      att: IMX.fm({ft: 92.5, pt: -80, fa: 91, pa: -30, fb: 89.5, pb: -30, iip3: -8}, {att: 10}),
      base: IMX.fm({ft: 92.5, pt: -80, fa: 91, pa: -30, fb: 89.5, pb: -30, iip3: -8}),
      filt: IMX.fm({ft: 92.5, pt: -80, fa: 91, pa: -30, fb: 89.5, pb: -30, iip3: -8}, {bw: 4}),
      tr: [IMX.tracking(1.5, 4), IMX.tracking(0, 4), IMX.tracking(20, 4), IMX.tracking(3, 0)],
      near: [IMX.near(92.5, 92.5), IMX.near(2 * 91 - 89.4, 92.5), IMX.near(92.7, 92.5), IMX.near(93, 92.5)]}));""")
    (a, b), (c, d) = r["eq"], r["uneq"]
    assert (a["k"], a["f"], b["k"], b["f"]) == ("2A − B", 92.5, "2B − A", 88.0)  # 2f1 − f2 and 2f2 − f1
    assert a["p"] == b["p"] == 3 * -30 - 2 * -8 == -74  # equal tones: 3·P − 2·IIP3
    assert (c["f"], c["p"], d["f"], d["p"]) == (99, 2 * -20 - 30, 102, 2 * -30 - 20)  # the doubled tone counts twice
    assert r["up"] == 3  # 1 dB more of both stations: 3 dB more ghost
    g0, gl, ga = r["base"]["ghosts"][0], r["lin"]["ghosts"][0], r["att"]["ghosts"][0]
    assert g0["at"] == "on" and g0["over"] == 6  # the default: the ghost 6 dB above the station
    assert gl["p"] - g0["p"] == -20 and r["lin"]["pt"] == -80  # +10 dB IIP3: ghost -20 dB, station unchanged
    assert ga["p"] - g0["p"] == -30 and r["att"]["pt"] == -90 and ga["over"] - g0["over"] == -20  # 10 dB attenuator
    ra, rb = r["filt"]["ra"], r["filt"]["rb"]
    assert round(ra, 2) == 1.94 and round(rb, 2) == 5.12  # close neighbours pass a 4 MHz tracking filter
    assert abs((r["filt"]["ghosts"][0]["p"] - g0["p"]) + (2 * ra + rb)) < 1e-9
    assert r["tr"][1] == 0 and r["tr"][2] > 20 and r["tr"][3] == 0  # far-away stations are removed, none: no filter
    assert r["near"] == ["on", "near", "adjacent", ""]


@node
def test_fm_verdict_in_plain_words_with_the_arithmetic():
    r = _imx("""
      const s = (ft, fa, fb, o = {}) => ({ft, pt: -80, fa, pa: -30, fb, pb: -30, iip3: -8, ...o});
      const v = (x, fx) => IMX.verdict(x, IMX.fm(x, fx), 50, -112);
      console.log(JSON.stringify([v(s(92.5, 91, 89.5)), v(s(94.3, 91, 89.5)), v(s(92.5, 91.1, 89.5, {pa: -25})),
        v(s(92.5, 91, 89.4)), v(s(91, 91, 89.5)), v(s(92.5, 91, 89.5), {lin: 10, att: 10}),
        v(s(94.3, 91, 89.5, {pt: -105}), {att: 10})]));""")
    on, clear, adj, near, own, fixed, weak = r
    assert on["text"] == ("Yes, this is an intermod product: 2 × 91.0 − 89.5 = 92.5 MHz, exactly your station. "
                          "The ghost is 6 dB louder than your station → you'll hear stations A and B mixed in, "
                          "or a whistle.") and on["tone"] == "bad"  # fmt: skip
    assert clear["text"] == "No: the products land on 88.0 and 92.5 MHz; your 94.3 MHz is clear."
    assert clear["tone"] == "ok"
    assert adj["text"].startswith("Next door: 2 × 91.1 − 89.5 = 92.7 MHz, on the adjacent channel 200 kHz")
    assert "50 dB" in adj["text"]
    assert near["text"].startswith("Yes, close: 2 × 91.0 − 89.4 = 92.6 MHz, 100 kHz from your 92.5 MHz")
    assert near["tone"] == "bad"
    assert "tuned to station A itself" in own["text"]
    assert "34 dB below your station → harmless" in fixed["text"] and fixed["tone"] == "ok"  # -74 - 20 - 30 vs -90
    assert "too weak to hear" in weak["text"] and weak["tone"] == "warn"  # the attenuator took the station below −112


@node
def test_ip3_trade_off_gain_against_linearity():
    r = _imx("""
      const c = {pw: -90, bw: 1, snr: 10, nf1: 2, nf2: 15}, rx = o => IMX.rx({...c, g: 15, oip3: 20, pn: -40, ...o});
      console.log(JSON.stringify({d: rx({}), g0: rx({g: 0}), g32: rx({g: 32}), g32ip: rx({g: 32, oip3: 30}),
        loud: rx({pn: -39}), friis: IMX.friis(2, 15, 15), n: IMX.noise(0, 1e6), sum: IMX.sum(-100, -100)}));""")
    d, g0, g32, fix = r["d"], r["g0"], r["g32"], r["g32ip"]
    assert d["iip3"] == 5 and d["im"] == 3 * -40 - 2 * 5 == -130 and not d["lost"]  # IIP3 = OIP3 − gain
    assert round(r["friis"], 2) == 4.07 and round(r["n"], 1) == -114.0 and round(r["sum"], 2) == -96.99
    assert round(d["mNoise"], 1) == 9.9 and d["mIm"] == 30
    assert g0["mNoise"] < 0 and g0["lost"]  # no gain: too weak to hear (the stages behind are noisy)
    assert g32["mIm"] < 0 and g32["lost"] and g32["mNoise"] > d["mNoise"]  # much gain: drowned by distortion
    assert not fix["lost"] and fix["im"] - g32["im"] == -20 and fix["ma"] == 2 * g32["ma"] == 20  # +10 dB IP3: 2x mA
    assert r["loud"]["im"] - d["im"] == 3  # 1 dB more neighbours: 3 dB more false tone


def test_fm_and_ip3_visuals_are_built_as_the_owner_asked():
    fm = _block("  // FM intermodulation (owner 23 Oct 2026", '    id: "vswr", group:')
    for s in ('role="slider"', "ArrowLeft", "PageUp", "setPointerCapture", "How to fix it",
              "Better linearity: +10 dB IIP3", "Turn the input down: AGC or a 10 dB attenuator",
              "Filter before the amplifier", "about twice the front-end current (est)",
              "not close neighbours", "My local stations", "aria-pressed", "Half-IF spur", "Image (LO + IF)",
              "Show the whole picture"):  # fmt: skip
        assert s in fm, s
    ip3 = _block('    id: "ip3", group:', '  // FM intermodulation (owner 23 Oct 2026')
    for s in ("BLE next to Wi-Fi", "Car FM next to a strong local station", "5G phone near a base station",
              "loudspeaker turned up too far",
              "raise the gain until the red appears, then raise IP3 and see what it costs",
              "Show the textbook IP3 chart", "Too weak to hear", "Drowned by distortion", "your signal is lost",
              "(est)"):  # fmt: skip
        assert s in ip3 or s in JS, s
    for s in (".fm-gh.hit", ".fx-card", ".tm-tr", ".vz-fold", "touch-action: pan-y", ".fm-drag:focus-visible"):
        assert s in CSS, s
