"""The owner's verified crosses (Verify next > Crosses and the live site): named pairs and the rules they fixed."""

import copy
import re
from functools import lru_cache
from pathlib import Path

import pytest
from sqlalchemy import select

from app import yamlio
from app.matching import engine
from app.matching.engine import compare_param, cross, pins_compatible, ranked
from app.matching.rules import (
    BAND_SUFFIX,
    ParamDef,
    curve_value,
    curve_worst,
    gate_output_config,
    get_rules,
    parse_rules,
)
from app.models import Package, ParamValue, Part
from app.services import crosslist as cl
from app.services.queries import crosses_for
from app.services.seed import load_file

# ---- from tests/test_fb_1021_crosses.py ------------------------------------------------------------------------------
# Site feedback 2026-10-21 (Verify next › Crosses): gate-driver crosses are variant-aware.
#
# UCC5310MCDR → SI82B41ACE-IS4: the output option (TI UCC53x0 S / M / E, Skyworks Si82B40 / Si82B41) must match.
# NSI6602NA-DSPNR → SI82E39ABE-IS3: isolation per package (Novosense LGA13 2.5 kVrms, SOP 3 kVrms, SOW 5.7 kVrms), and
# source and sink current compared separately at the same supply.

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


PRELOAD = {"gate": (FILES, None)}  # loaded into the test database through tests/conftest.py


@pytest.fixture
def gate(session):
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


# ---- from tests/test_fb_1022_crosses.py ------------------------------------------------------------------------------
# Owner's cross verification, 22 Oct 2026 (Verify next › Crosses).
#
# - NSI6602A-DLAR: the 4 V UVLO Si82E29AGC-IS1 is the better stand-in for the 6 V option than the 8 V Si82E29ABC-IS1;
# Novosense CMTI is the datasheet typical (150 kV/µs).
# - Rule: typical first, then max (prop delay, CMTI); limits (isolation, creepage, UVLO option) stay as stated.
# - 1ED3140MU12FXUMA1: prop delay typ 40 ns; UVLO 9.3 V crosses to the 8 V (B) Skyworks code first.
# - Si86: prop delay typ per ordering option (B/E 9 ns, F/H deglitch 36 ns, SLx 11.5 ns).
# - MSW2060-206: 8 x 5 mm body, frequency and temperature from the datasheet.
# - Dead time and overlap protection count as one capability.


@lru_cache
def _parts_unresolved_pinouts(name: str) -> dict[str, dict]:
    data = yamlio.load((DATA / f"{name}.yaml").read_text())
    out = {}
    for raw in data["parts"]:
        spec = copy.deepcopy(out[raw["like"]]) if "like" in raw else {}
        spec.update({k: v for k, v in raw.items() if k != "like"})
        out[spec["mpn"]] = spec
    return out


@pytest.fixture
def load(session):
    def go(*files):
        for f in files:
            load_file(session, DATA / f"{f}.yaml")
        session.commit()
        return lambda mpn: session.scalars(select(Part).where(Part.mpn == mpn)).unique().one()

    return go


# ---------------------------------------------------------------- UVLO: the lower variant is the safer stand-in


def test_uvlo_prefers_the_lower_threshold_when_no_variant_matches():
    p = get_rules("gate_driver").get("uvlo_v")
    assert p.direction == "match" and p.prefer == "lower"
    lower, higher = compare_param(p, 6.5, 4), compare_param(p, 6.5, 8)
    assert lower[0] == higher[0] == "different"  # still a deviation either way
    assert lower[1] < higher[1]
    assert compare_param(p, 12, 12.5)[0] == "equal"  # within 6 %: the same variant


def test_prefer_needs_direction_match():
    with pytest.raises(ValueError):
        parse_rules({"family": "x", "params": [
            {"key": "a", "priority": 1, "kind": "number", "direction": "higher", "prefer": "lower"}]})  # fmt: skip
    assert ParamDef("a", "a", 1, "number").prefer is None


def test_nsi6602a_dlar_crosses_to_the_4v_si82e29agc(session, load):
    get = load("novosense_isolation", "skyworks_gate_drivers_more")
    ref = get("NSI6602A-DLAR")
    best = ranked(crosses_for(session, ref))[0]
    assert best.candidate.mpn in ("SI82E29AGC-IS1", "SI82E39AGC-IS1")  # Si82E29 and E39 differ only in DIS / EN
    rules = get_rules("gate_driver")
    agc, abc = cross(ref, get("SI82E29AGC-IS1"), rules), cross(ref, get("SI82E29ABC-IS1"), rules)
    assert [d.key for d in agc.deviations] == [d.key for d in abc.deviations] == ["uvlo_v"]
    assert agc.closeness < abc.closeness


# ---------------------------------------------------------------- typical first


def test_novosense_cmti_and_prop_delay_are_typical():
    nsi = _parts_unresolved_pinouts("novosense_isolation")
    a = nsi["NSI6602A-DLAR"]
    assert a["params"]["cmti_kv_us"] == 150 and a["params"]["prop_delay_ns"] == 25
    assert "CMTI typ" in a["param_sources"]["cmti_kv_us"] and "tPD typ" in a["param_sources"]["prop_delay_ns"]
    assert nsi["NSI6602MEB-Q1SWDR"]["params"]["cmti_kv_us"] == 200  # min 150, typ 200
    assert nsi["NSI6602NA-DSPNR"]["params"]["prop_delay_ns"] == 33
    for spec in nsi.values():  # no Novosense gate driver keeps a maximum delay
        assert "tPD max" not in (spec.get("param_sources") or {}).get("prop_delay_ns", "")


def test_si82x_prop_delay_is_typical_per_deglitch_option():
    sky = _parts_unresolved_pinouts("skyworks_gate_drivers_more")
    assert sky["SI82E29AGC-IS1"]["params"]["prop_delay_ns"] == 30  # 0 ns deglitch: 20 / 30 / 40
    assert sky["SI82E29BGB-IM3"]["params"]["prop_delay_ns"] == 52.5  # 30 ns deglitch: 45 / 52.5 / 65
    assert sky["SI82B28ABC-IS"]["params"]["prop_delay_ns"] == 26
    assert "typ" in sky["SI82E29AGC-IS1"]["param_sources"]["prop_delay_ns"]
    assert sky["SI82E29AGC-IS1"]["params"]["cmti_kv_us"] == 200  # only a minimum is stated: kept


def test_limits_keep_their_limit_value():
    a = _parts_unresolved_pinouts("novosense_isolation")["NSI6602A-DLAR"]["params"]
    assert a["isolation_rating_kvrms"] == 2.5 and a["creepage_mm"] == 3.5 and a["uvlo_v"] == 6.5


def test_rule_labels_say_typ_first():
    for fam in ("gate_driver", "digital_isolator"):
        rules = get_rules(fam)
        assert rules.get("prop_delay_ns").label == "Propagation delay (typ, else max)"
        assert rules.get("cmti_kv_us").label == "CMTI (typ, else min)"


def test_rules_page_explains_the_value_choice(client):
    html = client.get("/rules").text
    assert "Typical first, then maximum" in html and "Limits stay limits" in html
    assert 'href="/engineering/deadtime"' in html


# ---------------------------------------------------------------- Infineon 1ED3140


def test_1ed3140_prop_delay_and_uvlo_cross(session, load):
    ifx = _parts_unresolved_pinouts("infineon_isolation")
    for mpn in ("1ED3140MU12FXUMA1", "1ED3141MU12FXUMA1", "1ED3145MC12HXUMA1"):
        assert ifx[mpn]["params"]["prop_delay_ns"] == 40, mpn
    assert ifx["1ED3140MU12FXUMA1"]["params"]["uvlo_v"] == 9.3  # the datasheet's 1ED3140 option
    get = load("infineon_isolation", "skyworks_gate_drivers_more")
    best = ranked(crosses_for(session, get("1ED3140MU12FXUMA1")))[0]
    assert best.candidate.param_map()["uvlo_v"] == 8  # the B (8 V) code, not 4 or 12 V


# ---------------------------------------------------------------- Si86


def test_si86_prop_delay_typ_per_option():
    si86 = _parts_unresolved_pinouts("skyworks_si86")
    p = {m: s["params"] for m, s in si86.items()}
    assert p["SI86S640EE-IS2"]["prop_delay_ns"] == 9  # B/E: 6.5 / 9 / 14 ns
    assert p["SI86S640HE-IS2"]["prop_delay_ns"] == 36  # H = default high, 36 ns deglitch: 31.5 / 36 / 42 ns
    assert p["SI86S640HE-IS2"]["data_rate_mbps"] == 10
    assert p["SI86SL40EC-IS1"]["prop_delay_ns"] == 11.5  # low-power Si86SLx, slightly slower than Si86S6x
    assert p["SI86S621HC-IS"]["prop_delay_ns"] == 36 and p["SI86S621EC-IS"]["prop_delay_ns"] == 9
    assert p["SI8640BB-IS1"]["prop_delay_ns"] == 8  # Si864x: 5 / 8 / 13 ns
    assert p["SI8640AB-IS"]["prop_delay_ns"] == 35  # 1 Mbps: only a maximum is stated
    assert p["SI8640BB-IS1"]["cmti_kv_us"] == 50  # 35 min / 50 typ


# ---------------------------------------------------------------- MACOM MSW2060-206


def test_msw2060_from_the_datasheet():
    m = _parts_unresolved_pinouts("macom_switches")["MSW2060-206"]
    assert m["package"] == "Ceramic SMT 8x5x2.5"
    assert m["params"]["freq_range_ghz"] == [0.02, 1.2]  # MSW2060 = the 20-1200 MHz band of MSW206x
    assert m["params"]["temp_range_c"] == [-65, 125]  # +150 °C is storage
    assert _parts_unresolved_pinouts("macom_switches")["MSW2062-206"]["params"]["freq_range_ghz"] == [1.5, 6.5]


# ---------------------------------------------------------------- dead time and overlap protection


def test_dead_time_and_overlap_protection_are_one_capability():
    rules = get_rules("gate_driver")
    prot = rules.get("protection")
    assert {"programmable dead time", "overlap protection"} <= set(prot.exclude)
    sky = ["UVLO", "overlap protection", "disable", "programmable dead time"]
    nsi = ["UVLO", "programmable dead time", "disable"]
    assert compare_param(prot, sky, nsi)[0] == "equal"
    assert "overlap" in rules.get("deadtime").label


def test_deadtime_note_page(client):
    html = client.get("/engineering/deadtime").text
    assert "Overlap protection" in html and "one</b> capability" in html


# ---- from tests/test_fb_1023_msw2030.py ------------------------------------------------------------------------------
# Owner verification 23 Oct 2026: MSW2030-203 (MACOM) -> SKY12212-478LF. The values come from MACOM's product page
# (the linked datasheet covers MSW2031 / MSW2032 only), and RF switch values are compared over the same frequencies.

ROOT = Path(__file__).resolve().parents[1]


def _spec(file: str, mpn: str) -> dict:
    return next(p for p in yamlio.load((ROOT / "data" / "real" / file).read_text())["parts"] if p["mpn"] == mpn)


def test_msw2030_values_and_sources():
    p = _spec("macom_switches.yaml", "MSW2030-203")
    v = p["params"]
    assert v["freq_range_ghz"] == [0.05, 1.0] and v["insertion_loss_db"] == 0.3 and v["isolation_db"] == 52
    assert v["iip3_dbm"] == 65
    assert "product page" in p["param_sources"]["insertion_loss_db"]
    assert "no longer lists the MSW2030" in p["notes"] and "MSW2031-203" in p["notes"]
    m31 = _spec("macom_switches.yaml", "MSW2031-203")["params"]
    assert m31["freq_range_ghz"] == [0.4, 4.0] and m31["isolation_db"] == 35 and m31["insertion_loss_db"] == 0.5


def test_sky12212_curves_from_the_datasheet():
    v = _spec("skyworks_switches.yaml", "SKY12212-478LF")["params"]
    assert v["insertion_loss_curve"][-1] == [2.7, 0.55] and v["insertion_loss_db"] == 0.55  # TX-ANT, worst path
    assert v["isolation_curve"][-1] == [2.7, 28] and v["isolation_db"] == 28
    assert [x for x, _ in v["isolation_curve"]] == [0.05, 0.6, 1.2, 2.0, 2.7]


def test_curve_worst():
    c = [[0.05, 47], [0.6, 39], [1.2, 34]]
    assert curve_worst(c, 0.05, 1.0, "higher") == pytest.approx(35.667, abs=1e-3)  # read between 0.6 and 1.2 GHz
    assert curve_worst([[0.05, 0.47], [0.6, 0.29], [1.2, 0.33]], 0.05, 1.0, "lower") == 0.47
    assert curve_worst(c, 0.01, 1.0, "higher") is None  # never extrapolated
    with pytest.raises(ValueError):
        parse_rules({"family": "x", "params": [{"key": "a", "priority": 2, "kind": "number", "direction": "lower",
                                                "curve": "a_curve"}]})  # fmt: skip


def test_cross_compares_over_the_reference_band(session):
    for f in ("macom_switches", "skyworks_switches"):
        load_file(session, ROOT / "data" / "real" / f"{f}.yaml")
    session.commit()

    def part(mpn):
        return session.scalars(select(Part).where(Part.mpn == mpn)).unique().one()

    rules = get_rules("rf_switch")
    ref, cand = part("MSW2030-203"), part("SKY12212-478LF")
    rv, cv = rules.at_same_conditions(rules.values(ref), rules.values(cand))
    assert cv["insertion_loss_db"] == 0.47 and cv["isolation_db"] == pytest.approx(35.667, abs=1e-3)
    assert cv["isolation_db" + BAND_SUFFIX] == (0.05, 1.0) and rv["isolation_db"] == 52
    r = engine.cross(ref, cand, rules)
    d = {x.key: x for x in r.diffs}
    assert d["isolation_db"].cand_display.endswith("over 0.05–1 GHz") and "35.6" in d["isolation_db"].cand_display
    assert d["insertion_loss_db"].cand_display.startswith("0.47") and d["insertion_loss_db"].is_negative
    # a candidate whose band does not reach past the reference's keeps its own worst-in-band value
    rv2, cv2 = rules.at_same_conditions(rules.values(cand), rules.values(ref))
    assert cv2["isolation_db"] == 52 and "isolation_db" + BAND_SUFFIX not in cv2


# ---- from tests/test_fb_1026_verify.py -------------------------------------------------------------------------------
# Owner's cross verification from the live site, 26 Oct 2026 (docs/worked_2026-10-26.md).
#
# 1. CA-IS3720HG-Q1: the 10 Mbps deglitch code (Si86S620HE) no longer comes first; the data rate is priority 1.
# 2. LMK3H0102-Q1: 105 fs typ. differential jitter (not the 0.5 ps LVCMOS max), so Si5332A-AM1 shows a jitter deviation.
# 3. NSI8240S0-Q1SSR: the SSOP16 parts are basic insulation, VIORM 565 Vpk, creepage 3.9 mm.
# 4. NSI8320N0-Q1SPR: crosses to the Si86S620BC-AS (CMTI 100) before the Si8620BC-AS (CMTI 50).
# 5. NSI6801B-DSPR -> SI8261BBC-C-IS: 1.8 A source / 4.0 A sink typ. confirmed (Si826x.pdf p.5).
# 6. LMK03328 -> Si5341A: jitter compared at the same output frequency; the Si5341 needs two core rails.
# 7. ISOW7841AQDWERQ1: the Si86P matches on integrated power but is industrial only, so no cross is shown
# (owner, 26 Oct 2026: "No industrial fallback. Automotive needs automotive").
# 8. ISO7761: CMTI typ. 100 kV/us (min 85).


def row(session, mpn):
    entries, _ = cl.parse(mpn)
    return cl.cross_list(session, entries)[0]


def diffs(r):
    return {d.key: d for d in r.diffs}


# ---------------------------------------------------------------- 1. data rate is priority 1


def test_data_rate_is_priority_1():
    p = get_rules("digital_isolator").get("data_rate_mbps")
    assert p.priority == 1 and p.direction == "higher" and p.unknown_ok


def test_ca_is3720hg_q1_crosses_to_the_150_mbps_si86s620ee(session, load):
    get = load("chipanalog_isolation", "skyworks_si86")
    r = row(session, "CA-IS3720HG-Q1")
    assert r.functional.result.candidate.mpn in ("SI86S620EE-AS4", "SI86SO20EE-AS4")
    deglitch = cross(get("CA-IS3720HG-Q1"), get("SI86S620HE-AS4"), get_rules("digital_isolator"))
    assert "data_rate_mbps" in [d.key for d in deglitch.deviations]  # 10 Mbps (36 ns deglitch) for 150 Mbps
    # AV, 26 Oct 2026 (owner: "better researched from the datasheet"): AW's 10 Mbps holds, now from datasheet pages
    # on both sides (si86s61x_2x_Ox-datasheet.pdf p.9, CAIS372xQ1 datasheet p.6), so it may decide the cross
    srcs = {pv.key: pv.source for pv in get("SI86S620HE-AS4").params}
    assert srcs["data_rate_mbps"].startswith("si86s61x_2x_Ox-datasheet.pdf p.9 (max 10 Mbps")


# ---------------------------------------------------------------- 2. LMK3H0102-Q1 jitter


def test_lmk3h0102_q1_jitter_is_the_differential_typical(session, load):
    get = load("ti_timing", "skyworks_timing")
    ref = get("LMK3H0102-Q1")
    assert ref.param_map()["jitter_fs"] == 105 and ref.param_map()["jitter_fout_mhz"] == 156.25
    r = cross(ref, get("Si5332A-AM1"), get_rules("timing"))
    assert diffs(r)["jitter_fs"].status == "worse"  # 190 fs typ.
    assert diffs(r)["jitter_fs"].ref_display == "105 fs at 156.25 MHz"
    assert {"jitter_fs", "freq_range_mhz"} <= {d.key for d in r.deviations}
    assert "29.6 fs" in ref.notes  # PCIe Gen 7 Common Clock, max with SSC


# ---------------------------------------------------------------- 3. Novosense SSOP16 insulation


def test_nsi8240s0_q1ssr_is_basic_565_vpk(session, load):
    get = load("novosense_digital_isolators", "skyworks_si86")
    v = get("NSI8240S0-Q1SSR").param_map()
    assert v["isolation_class"] == "basic" and v["viorm_vpk"] == 565 and v["creepage_mm"] == 3.9
    best = row(session, "NSI8240S0-Q1SSR").functional.result
    assert best.candidate.param_map()["data_rate_mbps"] >= 150  # no 10 Mbps deglitch code (Si86S640FC)
    assert diffs(best)["isolation_class"].status == "better"


# ---------------------------------------------------------------- 4. NSI8320N0-Q1SPR


def test_nsi8320n0_q1spr_prefers_the_higher_cmti(session, load):
    get = load("novosense_digital_isolators", "skyworks_si86")
    r = row(session, "NSI8320N0-Q1SPR")
    assert r.functional.result.candidate.mpn == "SI86S620BC-AS"
    # its 150 Mbps is from Novosense's product table (the datasheet is served encrypted): amber, check datasheet
    assert "Data rate not from their datasheet: check datasheet" in r.functional.comment
    si8620 = get("SI8620BC-AS").param_map()  # every priority 1 value as in si861x-2x-datasheet.pdf
    assert (si8620["isolation_class"], si8620["isolation_rating_kvrms"], si8620["cmti_kv_us"]) == ("basic", 3.75, 50)
    assert (si8620["default_output"], si8620["data_rate_mbps"], si8620["channel_config"]) == ("low", 150, "2/0")


# ---------------------------------------------------------------- 5. Si8261BBC peak currents


def test_si8261bbc_peak_currents_confirmed(session, load):
    get = load("novosense_isolation", "skyworks_gate_drivers_more")
    cand = get("SI8261BBC-C-IS")
    assert (cand.param_map()["peak_source_a"], cand.param_map()["peak_sink_a"]) == (1.8, 4.0)
    src = {pv.key: pv.source for pv in cand.params}["peak_source_a"]
    assert "p.5" in src and "VDD - VO = 7.5 V" in src
    r = cross(get("NSI6801B-DSPR"), cand, get_rules("gate_driver"))
    assert {"peak_source_a", "peak_sink_a"} <= {d.key for d in r.deviations}


# ---------------------------------------------------------------- 6. LMK03328 vs Si5341A


def test_lmk03328_si5341a_supply_rails_and_jitter(session, load):
    get = load("ti_timing", "skyworks_timing")
    r = cross(get("LMK03328"), get("Si5341A"), get_rules("timing"))
    d = diffs(r)
    assert d["jitter_fs"].status == "equal"  # 100 fs vs 90 fs, both at 156.25 MHz, within 10 %
    assert d["core_rails"].status == "worse" and d["vdd_range_v"].status == "worse"  # 3.3 V only vs 1.8 V + 3.3 V
    assert get("LMK03328").param_map()["vdd_range_v"] == [3.135, 3.465]


def test_jitter_read_at_the_other_parts_output_frequency():
    rules = get_rules("timing")
    ref = {"jitter_fs": 150, "jitter_fout_mhz": 50}
    cand = {"jitter_fs": 100, "jitter_fout_mhz": 156.25, "jitter_curve": [[25, 160], [156.25, 100]]}
    rv, cv = rules.at_same_conditions(ref, cand)
    assert cv["jitter_fout_mhz"] == 50 and 140 < cv["jitter_fs"] < 160


# ---------------------------------------------------------------- 7. ISOW7841A-Q1 and the Si86P


def test_si86p_family_and_integrated_power(session, load):
    get = load("ti_digital_isolators", "skyworks_si86", "skyworks_isolators_more")
    si86p = session.scalars(select(Part).where(Part.mpn.like("SI86P%"))).unique().all()
    assert len(si86p) == 30 and {p.param_map()["integrated_power"] for p in si86p} == {"isolated dc-dc"}
    rules = get_rules("digital_isolator")
    ref = get("ISOW7841AQDWEQ1")
    assert diffs(cross(ref, get("SI86P341EC-IS"), rules))["integrated_power"].status == "equal"
    ctrl = next(p for p in session.scalars(select(Part)).unique()
                if str(p.param_map().get("integrated_power")).startswith("isolated dc-dc controller"))  # fmt: skip
    assert cross(ref, ctrl, rules).hard_fail  # a DC-DC controller needs an external transformer: not the same
    for mpn in ("ISOW7841AQDWERQ1", "ISOW7741QDFMRQ1"):  # automotive needs automotive: no industrial fallback
        r = row(session, mpn)
        assert r.drop_in is None and r.functional is None and r.light == "red"


# ---------------------------------------------------------------- 8. ISO7761 CMTI


def test_iso7761_cmti_is_typical(session, load):
    get = load("ti_digital_isolators", "skyworks_si86")
    assert get("ISO7761QDWRQ1").param_map()["cmti_kv_us"] == 100  # typ (min 85), iso7761-q1.pdf p.13
    assert get("SI86S661EE-AS2").param_map()["cmti_kv_us"] == 100  # min; the datasheet states no typical
    assert get("SI8661ED-AS").param_map()["cmti_kv_us"] == 50  # typ (min 35)
    r = cross(get("ISO7761QDWRQ1"), get("SI86S661EE-AS2"), get_rules("digital_isolator"))
    assert diffs(r)["cmti_kv_us"].status == "equal"
