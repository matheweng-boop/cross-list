"""Site feedback 2026-10-21 (Verify next › Crosses): gate-driver crosses are variant-aware.

UCC5310MCDR → SI82B41ACE-IS4: the output option (TI UCC53x0 S / M / E, Skyworks Si82B40 / Si82B41) must match.
NSI6602NA-DSPNR → SI82E39ABE-IS3: isolation per package (Novosense LGA13 2.5 kVrms, SOP 3 kVrms, SOW 5.7 kVrms), and
source and sink current compared separately at the same supply.
"""

import copy
import re
from functools import lru_cache
from pathlib import Path

import pytest
from sqlalchemy import select

from app import yamlio
from app.matching.engine import cross, pins_compatible, ranked
from app.matching.rules import curve_value, gate_output_config, get_rules
from app.models import Package, ParamValue, Part
from app.services.queries import crosses_for
from app.services.seed import load_file

DATA = Path(__file__).resolve().parents[1] / "data" / "real"
FILES = ("ti_gate_drivers_more", "novosense_isolation", "skyworks_gate_drivers_more")
SOIC8 = dict(name="", pin_count=8, pitch_mm=1.27, body_length_mm=4.9, body_width_mm=3.9, span_mm=6.0)
M_PINS = ["VCC1", "IN+", "IN-", "GND1", "VCC2", "OUT", "CLAMP", "VEE2"]  # UCC53x0M


@lru_cache
def _parts(name: str) -> dict[str, dict]:
    data = yamlio.load((DATA / f"{name}.yaml").read_text())
    out, pinouts = {}, data.get("pinouts", {})
    for raw in data["parts"]:
        spec = copy.deepcopy(out[raw["like"]]) if "like" in raw else {}
        spec.update({k: v for k, v in raw.items() if k != "like"})
        if isinstance(spec.get("pinout"), str):
            spec["pinout"] = pinouts[spec["pinout"]]
        out[spec["mpn"]] = spec
    return out


def _part(mpn, pins, pkg="P", **params):
    return Part(
        mpn=mpn, family="gate_driver", package=Package(id=1, code=pkg, **SOIC8), pinout=pins, package_locked=False,
        params=[ParamValue(key=k, value=v) for k, v in params.items()],
    )  # fmt: skip


BASE = dict(isolation_rating_kvrms=3.0, isolation_class="basic", creepage_mm=4.0, qualification="industrial",
            cmti_kv_us=100, channel_config="single", input_type="single input", peak_source_a=4.3, peak_sink_a=2.2,
            uvlo_v=12)  # fmt: skip


# ---------------------------------------------------------------- rules


def test_output_option_is_read_from_the_pinout():
    def oc(pins, **values):
        return gate_output_config(Part(pinout=pins), values)

    assert oc(M_PINS) == "Miller clamp"
    assert oc(["VCC1", "IN+", "IN-", "GND1", "VCC2", "OUTH", "OUTL", "VEE2"]) == "split output"  # UCC53x0S
    assert oc(["VCC1", "IN+", "IN-", "GND1", "VCC2", "OUT", "GND2", "VEE2"]) == "UVLO to GND2"  # UCC53x0E
    assert oc(["VDDI", "VI+", "VI-", "GNDI", "VDD", "VO", "MC", "GND"]) == "Miller clamp"  # Si82B41
    assert oc(["VDDI", "VI+", "VI-", "GNDI", "VDD", "VO+", "VO-", "GND"]) == "split output"  # Si82B40
    assert oc(["VDDI", "VI", "DIS", "GNDI", "GND", "NC", "VO", "VDD"]) == "single output"  # Si82B28
    assert oc(["VCC1", "IN+", "IN-", "GND1", "VCC2", "OUT+", "OUT-", "VEE2"]) == "split output"  # NSI6601
    nsi6611 = ["ASC", "DESAT", "GND2", "OUTH", "VCC2", "OUTL", "CLAMP", "VEE2", "GND1", "IN+", "IN-", "RDY", "FLT"]
    assert oc(nsi6611) == "split output + Miller clamp"
    assert oc(["INA", "INB", "VDDI", "GNDI", "EN", "DT", "VDDI", "GNDB", "OUTB", "VDDB", "GNDA", "OUTA", "VDDA"]) == (
        "single output"
    )
    assert oc([], protection=["UVLO", "Miller clamp"]) == "Miller clamp"  # no pinout: the feature list
    assert oc([], protection=["UVLO"]) is None


def test_curve_is_read_between_points_never_beyond():
    curve = [[6, 3.8], [10, 5.4], [15, 6.65], [18, 7.5]]
    assert curve_value(curve, 15) == 6.65 and curve_value(curve, 12) == pytest.approx(5.9)
    assert curve_value(curve, 20) is None and curve_value(None, 15) is None


def test_single_channel_pin_aliases_ti_and_skyworks():
    ti = ["VCC1", "IN+", "IN-", "GND1", "VCC2", "OUT", "CLAMP", "VEE2"]
    sky = ["VDDI", "VI+", "VI-", "GNDI", "VDD", "VO", "MC", "GND"]
    assert all(pins_compatible(a, b, "gate_driver") for a, b in zip(ti, sky, strict=True))
    assert pins_compatible("OUTH", "VO+", "gate_driver") and pins_compatible("OUTL", "VO-", "gate_driver")
    assert not pins_compatible("CLAMP", "VO-", "gate_driver") and not pins_compatible("OUTH", "VO", "gate_driver")
    assert not pins_compatible("VDDI", "VDD1", "digital_isolator")  # gate drivers only


def test_drop_in_turns_into_a_deviation_when_the_output_option_differs():
    rules = get_rules("gate_driver")
    ref = _part("REF", M_PINS, **BASE)
    assert cross(ref, _part("SAME", M_PINS, **BASE), rules).categories == ["fff"]
    other = _part("OTHER", M_PINS, **{**BASE, "output_config": "split output"})
    r = cross(ref, other, rules)
    assert "fff" not in r.categories and [d.key for d in r.deviations] == ["output_config"]
    assert r.deviations[0].summary() == "Output configuration: split output vs Miller clamp (P1, different)"


def test_unknown_output_option_is_shown_not_counted():
    rules = get_rules("gate_driver")
    r = cross(_part("REF", [], **BASE), _part("C", [], pkg="Q", **BASE), rules)
    oc = next(d for d in r.diffs if d.key == "output_config")
    assert oc.status == "unknown" and oc not in r.deviations


def test_source_and_sink_are_judged_separately():
    rules = get_rules("gate_driver")
    ref = _part("REF", M_PINS, **BASE)
    r = cross(ref, _part("C", M_PINS, **{**BASE, "peak_source_a": 6.0, "peak_sink_a": 2.0}), rules)
    assert [d.key for d in r.verdict().better] == ["peak_source_a"]
    assert [d.key for d in r.deviations] == ["peak_sink_a"] and r.verdict().spec == "mixed"


def test_peak_currents_are_compared_at_the_same_supply():
    rules = get_rules("gate_driver")
    ref = _part("REF", M_PINS, **{**BASE, "peak_source_a": 6.0, "peak_sink_a": 8.0, "peak_current_vdd_v": 15})
    curves = dict(
        peak_source_curve=[[10, 5.4], [15, 6.65], [18, 7.5]], peak_sink_curve=[[10, 6.55], [15, 7.4], [18, 7.5]]
    )
    cand = _part("C", M_PINS, **{**BASE, "peak_source_a": 7.5, "peak_sink_a": 7.5, "peak_current_vdd_v": 18, **curves})
    r = cross(ref, cand, rules)
    d = {x.key: x for x in r.diffs}
    assert d["peak_source_a"].status == "better" and d["peak_source_a"].cand_display == "6.65 A at 15 V"
    assert d["peak_sink_a"].status == "worse" and d["peak_sink_a"].summary() == (
        "Peak sink current: 7.4 A at 15 V vs 8 A at 15 V (P1, worse)"
    )
    assert d["peak_current_vdd_v"].status == "equal" and "peak_source_curve" not in d
    # the other way round (our part as the reference) the competitor is compared with our 15 V row as well
    back = {x.key: x for x in cross(cand, ref, rules).diffs}
    assert back["peak_sink_a"].ref_display == "7.4 A at 15 V" and back["peak_sink_a"].status == "better"


# ---------------------------------------------------------------- data, per ordering code


def test_ti_ucc53x0_device_comparison_table():
    """ucc5390.pdf section 4: per option the pin configuration, source / sink current and UVLO; per package
    (D 3 kVrms basic, DWV 5 kVrms reinforced) the isolation rating."""
    table = {"UCC5310MC": ("Miller clamp", 4.3, 2.2, 12), "UCC5320SC": ("split output", 4.3, 4.4, 12),
             "UCC5320EC": ("UVLO to GND2", 4.3, 4.4, 12), "UCC5350MC": ("Miller clamp", 10, 10, 12),
             "UCC5350SB": ("split output", 8.5, 10, 8), "UCC5390SC": ("split output", 17, 17, 12),
             "UCC5390EC": ("UVLO to GND2", 17, 17, 12)}  # fmt: skip
    iso = {"SOIC-8 (D)": (3.0, "basic"), "SOIC-8 (DWV)": (5.0, "reinforced"), "SOIC-8 (DWL)": (5.0, "reinforced")}
    parts = {m: p for m, p in _parts("ti_gate_drivers_more").items() if re.match(r"UCC53[1259]0", m)}
    assert len(parts) == 17
    for mpn, p in parts.items():
        cfg, src, sink, uvlo = table[mpn[:9]]
        q = p["params"]
        got = (q["output_config"], q["peak_source_a"], q["peak_sink_a"], q["uvlo_v"], q["peak_current_vdd_v"])
        assert got == (cfg, src, sink, uvlo, 15), mpn
        assert (q["isolation_rating_kvrms"], q["isolation_class"]) == iso[p["package"]], mpn


def test_novosense_isolation_per_package():
    """NSI66x2x / NSI6602 / NSI6602H datasheets: LGA13 2.5 kVrms, SOP16/SOP14 3 kVrms, SOW16/SOW14 5.7 kVrms (UL 1577,
    1 min); the ordering-code suffix names the package."""
    by_suffix = [(r"-DLAR$", "LGA13 (Novosense 5x5)", 2.5, "basic"), (r"S?WKR$", "SOIC-14W (IS3)", 5.7, "reinforced"),
                 (r"S?WR$", "SOW16", 5.7, "reinforced"), (r"S?PNR$", "SOP16", 3.0, "basic"),
                 (r"S?POR$", "SOP14 (Novosense, 16-position)", 3.0, "basic")]  # fmt: skip
    n = 0
    for mpn, p in _parts("novosense_isolation").items():
        if not re.match(r"NSI66[024]2", mpn) or mpn.startswith("NSI6602M") or mpn.endswith("-DLAMR"):
            continue  # NSI6602M: SOW18 only; NSI6602VD-DLAMR: its own datasheet (1.6 kVrms LGA13 variant)
        rx, pkg, kv, cls = next(s for s in by_suffix if re.search(s[0], mpn))
        q = p["params"]
        assert (p["package"], q["isolation_rating_kvrms"], q["isolation_class"]) == (pkg, kv, cls), mpn
        assert q.get("creepage_mm") in (None, {"LGA13": 3.5, "SOIC-14W": 8.0, "SOW16": 8.0, "SOP16": 4.0,
                                               "SOP14": 4.0}[pkg.split(" ")[0]]), mpn  # fmt: skip
        n += 1
    assert n > 90
    nb = _parts("novosense_isolation")
    assert nb["NSI6602NA-DSPNR"]["params"]["isolation_rating_kvrms"] == 3.0  # SOP16, not the LGA13's 2.5 kVrms
    assert nb["NSI6622VA-DSWKR"]["package"] == "SOIC-14W (IS3)"  # DSWKR is the wide SOW14, not the narrow SOP14


def test_novosense_source_and_sink_from_the_datasheets():
    p = _parts("novosense_isolation")
    q = p["NSI6602NA-DSPNR"]["params"]
    assert (q["peak_source_a"], q["peak_sink_a"], q["peak_current_vdd_v"]) == (6.0, 8.0, 15)
    q = p["NSI6602A-DSPNR"]["params"]  # NSI6602 rev 1.8: 4 / 6 A at VDDA = 12 V for the A and B options
    assert (q["peak_source_a"], q["peak_sink_a"], q["peak_current_vdd_v"]) == (4.0, 6.0, 12)
    q = p["NSI6611ASC-DSWR"]["params"]  # NSI66x1A: IOUTH 11 A, IOUTL 12 A typ
    assert (q["peak_source_a"], q["peak_sink_a"], q["output_config"]) == (11.0, 12.0, "split output + Miller clamp")


def test_skyworks_si82bx_ordering_guide_options():
    """Si82Bx ordering guide: Si82B28 VO, Si82B30/40/43 VO+/VO-, Si82B41/44/47 VO + MC; NB SOIC-8 3.75 kVrms,
    SSO-8 6 kVrms. The clamp variants sink through VO only (3.66 A at VDD = 18 V)."""
    opt = {"28": "single output", "30": "split output", "40": "split output", "43": "split output",
           "41": "Miller clamp", "44": "Miller clamp", "47": "Miller clamp"}  # fmt: skip
    parts = {m: p for m, p in _parts("skyworks_gate_drivers_more").items() if m.startswith("SI82B")}
    assert len(parts) == 82  # industrial and automotive codes
    for mpn, p in parts.items():
        q = p["params"]
        assert q["output_config"] == opt[mpn[5:7]], mpn
        assert q["isolation_rating_kvrms"] == (6.0 if p["package"] == "SSO-8" else 3.75), mpn
        assert q["peak_sink_a"] == (3.66 if opt[mpn[5:7]] == "Miller clamp" else 7.5), mpn
        assert q["peak_current_vdd_v"] == 18 and q["peak_sink_curve"][-1] == [18, q["peak_sink_a"]], mpn


def test_stated_output_option_agrees_with_the_pinout():
    rules = get_rules("gate_driver")
    for name in FILES:
        for mpn, p in _parts(name).items():
            stated = p.get("params", {}).get("output_config")
            if p.get("family") != "gate_driver" or not stated or not p.get("pinout"):
                continue
            derived = gate_output_config(Part(pinout=p["pinout"]), p["params"])
            if mpn.startswith("NSI6601S"):  # OUT and OUTF: compared on the standard OUT as a single output (owner)
                continue
            assert derived == stated, (mpn, stated, derived)
    assert rules.get("output_config").derive == "gate_output_config"


# ---------------------------------------------------------------- the two named crosses


@pytest.fixture
def gate(session):
    for f in FILES:
        load_file(session, DATA / f"{f}.yaml")
    session.commit()

    def get(mpn: str) -> Part:
        return session.scalars(select(Part).where(Part.mpn == mpn)).unique().one()

    return get


def _diffs(r):
    return {d.key: d for d in r.diffs}


def test_ucc5310mcdr_crosses_to_the_miller_clamp_variants(session, gate):
    rules, ref = get_rules("gate_driver"), gate("UCC5310MCDR")
    r = cross(ref, gate("SI82B41ACE-IS4"), rules)
    d = _diffs(r)
    assert d["output_config"].status == "equal" and d["output_config"].ref_display == "Miller clamp"
    assert r.categories == ["functional"] and not r.deviations  # SSO-8: other package, everything equal or better
    assert d["peak_source_a"].cand_display == "6.65 A at 15 V" and d["peak_source_a"].status == "better"
    assert d["peak_sink_a"].cand_display == "3.56 A at 15 V" and d["peak_sink_a"].ref_display == "2.2 A at 15 V"
    assert d["isolation_rating_kvrms"].status == "better" and d["isolation_class"].status == "better"
    # split-output Si82B40: same everything else, but a different output option
    r = cross(ref, gate("SI82B40ACE-IS4"), rules)
    assert [x.key for x in r.deviations] == ["output_config"]
    # the NB SOIC-8 Miller-clamp code is pin-to-pin (VCC1/VDDI, CLAMP/MC, VEE2/GND); only the creepage differs, and
    # creepage is priority 3 (owner, 21 Oct 2026: good to know, not a requirement), so it is the drop-in
    r = cross(ref, gate("SI82B41ACC-IS"), rules)
    assert r.fit.same_package and r.fit.same_pinout and not r.deviations and r.categories == ["fff"]
    assert [x.key for x in r.p3_notes()] == ["creepage_mm"]
    assert ranked(crosses_for(session, ref))[0].candidate.mpn == "SI82B41ACC-IS"  # a drop-in always ranks first
    # the candidates without a deviation are all Miller-clamp parts; the split-output ones carry the deviation
    got = crosses_for(session, ref)["functional"]
    clean = [x for x in got if not x.deviations]
    assert clean and got[0] in clean
    assert {_diffs(x)["output_config"].cand_display for x in clean} == {"Miller clamp"}
    assert all("output_config" in {d.key for d in x.deviations} for x in got if "VO+" in x.candidate.pinout)


def test_nsi6602na_dspnr_compares_source_and_sink_at_15v(gate):
    rules, ref = get_rules("gate_driver"), gate("NSI6602NA-DSPNR")
    r = cross(ref, gate("SI82E39ABE-IS3"), rules)
    d = _diffs(r)
    assert d["isolation_rating_kvrms"].ref_display == "3 kVrms"  # the SOP16 code, not the LGA13's 2.5 kVrms
    assert d["peak_source_a"].summary() == "Peak source current: 6.65 A at 15 V vs 6 A at 15 V (P1, better)"
    assert d["peak_sink_a"].summary() == "Peak sink current: 7.4 A at 15 V vs 8 A at 15 V (P1, worse)"
    assert d["output_config"].status == "equal"
    assert {x.key for x in r.deviations} == {"peak_sink_a", "uvlo_v"} and r.categories == ["functional"]
    # the same Novosense option in other packages is rated differently, and the cross sees it
    wide = cross(gate("NSI6602NB-DSWKR"), gate("SI82E39ABE-IS3"), rules)
    assert _diffs(wide)["isolation_rating_kvrms"].ref_display == "5.7 kVrms"
    assert _diffs(wide)["isolation_rating_kvrms"].status == "better"
