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
