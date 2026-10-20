from pathlib import Path
from types import SimpleNamespace

import yaml

from app.services.mechanical import compare, load_mechanical, outline, svg

ROOT = Path(__file__).resolve().parents[1]


def pkg(code, pins=16, pitch=1.27, length=10.3, width=7.5, span=10.3, height=2.65, **kw):
    return SimpleNamespace(
        code=code,
        pin_count=pins,
        pitch_mm=pitch,
        body_length_mm=length,
        body_width_mm=width,
        span_mm=span,
        height_mm=height,
        positions_total=kw.get("positions_total"),
        pin_positions=kw.get("pin_positions"),
    )


def statuses(ov):
    return {c.label: c.status for c in ov.checks}


# Files whose datasheets give land patterns for every package. Later imports (many RF switch and competitor
# packages) often have no published pad drawing; their outlines must still draw, without pads.
FULLY_DRAWN = {"skyworks_si86.yaml", "skyworks_si823x.yaml", "ti_digital_isolators.yaml", "ti_gate_drivers.yaml",
               "novosense_digital_isolators.yaml", "skyworks_switches.yaml",
               "skyworks_gate_drivers_more.yaml"}  # fmt: skip


def test_every_real_package_has_lead_data():
    mech = load_mechanical()
    for path in (ROOT / "data" / "real").glob("*.yaml"):
        for p in yaml.safe_load(path.read_text()).get("packages", []):
            if path.name in FULLY_DRAWN:
                assert p["code"] in mech, f"{p['code']} ({path.name}) missing from data/mechanical.yaml"
            else:
                pk = SimpleNamespace(**{"positions_total": None, "pin_positions": None, "height_mm": None, **p})
                assert outline(pk).code == p["code"]


def test_pins_run_down_the_left_and_up_the_right():
    o = outline(pkg("SOIC-16W"))
    by_pin = {n: (y, side) for n, y, side in o.pins}
    assert by_pin[1][1] == -1 and by_pin[8][1] == -1 and by_pin[9][1] == 1
    assert by_pin[1][0] < by_pin[8][0]  # pin 1 at the top
    assert by_pin[16][0] == by_pin[1][0] and by_pin[9][0] == by_pin[8][0]


def test_same_outline_fits_reference_pads():
    ov = compare(outline(pkg("SOIC-16 (DW)"), "TI"), outline(pkg("SOIC-16W"), "Skyworks"))
    st = statuses(ov)
    assert st["Pitch"] == "ok" and st["Toe"] == "ok" and st["Lead width"] == "ok"
    assert ("Pad row spacing", "9.3 mm", "9.4 mm", "+0.1 mm") in ov.dims


def test_extended_creepage_pads_flag_long_feet():
    # Skyworks -IS2 pads start 4.1 mm out: a 1.27 mm foot on a 10.3 mm span runs past them
    ov = compare(outline(pkg("SOIC-16W"), "ref", land_index=1), outline(pkg("SOIC-16 (DW)"), "cand"))
    assert statuses(ov)["Heel"] == "warn"


def test_lead_tip_beyond_the_pads_fails():
    ov = compare(outline(pkg("SOIC-16N", width=3.9, length=9.9, span=6.0)), outline(pkg("SOIC-16W")))
    assert statuses(ov)["Toe"] == "bad"


def test_different_pitch_stops_the_checks():
    ov = compare(outline(pkg("SOIC-16W")), outline(pkg("QSOP-16", pitch=0.635, length=4.9, width=3.9, span=6.0)))
    assert [c.status for c in ov.checks] == ["bad"]


def test_missing_data_is_reported_not_guessed():
    ov = compare(outline(pkg("NO-SUCH-PKG")), outline(pkg("SOIC-16W")))
    assert statuses(ov)["Leads on pads"] == "unknown"
    assert "<svg" in svg(ov)


def test_svg_draws_one_pad_per_pin_and_both_parts():
    drawing = svg(compare(outline(pkg("SOIC-16W"), "SI8641"), outline(pkg("SOW16"), "NSI8241")), standalone=True)
    assert drawing.count('class="pad layer-pads"') == 32  # 16 reference + 16 candidate pads
    assert "SI8641 (reference)" in drawing and "NSI8241 (candidate)" in drawing
    assert 'width="' in drawing.split(">")[0]


def test_overlay_pages(client):
    parts = {p["mpn"]: p for p in client.get("/api/parts").json()}
    ref, cand = parts["SR8641"], parts["SA7741"]
    r = client.get(f"/overlay/{ref['id']}/{cand['id']}")
    assert r.status_code == 200
    assert "Fit checks" in r.text and "<svg" in r.text
    r = client.get(f"/overlay/{ref['id']}/{cand['id']}.svg")
    assert r.headers["content-type"].startswith("image/svg+xml")
    r = client.get(f"/packages/{ref['package_id']}/overlay/{cand['package_id']}")
    assert r.status_code == 200
    assert f'href="/overlay/{ref["id"]}/{cand["id"]}"' in client.get(f"/parts/{ref['id']}").text


def test_quad_package_pins_run_counter_clockwise(monkeypatch):
    import app.services.mechanical as mechanical

    qfn = mechanical.Mechanical((0.2, 0.3), (0.3, 0.4), sides=4)
    monkeypatch.setattr(mechanical, "load_mechanical", lambda: {"QFN-12 2x2": qfn})
    o = outline(pkg("QFN-12 2x2", pins=12, pitch=0.5, length=2, width=2, span=2, height=0.55))
    side = {n: s for n, _, s in o.pins}
    assert [side[n] for n in (1, 3, 4, 6, 7, 9, 10, 12)] == [-1, -1, 2, 2, 1, 1, -2, -2]
    pos = {n: t for n, t, _ in o.pins}
    assert pos[1] < pos[3]  # left side: top to bottom
    assert pos[4] < pos[6]  # bottom: left to right
    assert pos[7] > pos[9]  # right side: bottom to top
    assert pos[10] > pos[12]  # top: right to left
    assert o.quad and "<svg" in svg(compare(o, o))
