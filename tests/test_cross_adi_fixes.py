"""Cross engine fixes from the Analog Devices import (owner, 2 Nov 2026), checked on datasheet facts:

1. pin names: ADI VIA..VID are our INA..IND; VOUT is OUT (it used to read "outut");
2. control pins 7 and 10 compared by what they do (data/pin_roles.yaml);
3. gate drivers: short-circuit protection steers the pick;
4. isolated amplifiers: ADI numbers the input side 2, we call it side A (1).
"""

import re
from pathlib import Path

import pytest
from sqlalchemy import select

from app.matching import pinroles
from app.matching.engine import check_fit, pin_name, pins_compatible
from app.models import Part
from app.services import crosslist as cl
from app.services.seed import load_file

DATA = Path(__file__).resolve().parents[1] / "data" / "real"


@pytest.fixture
def load(session):
    def go(*files):
        for f in files:
            load_file(session, DATA / f"{f}.yaml")
        session.commit()
        return lambda mpn: session.scalars(select(Part).where(Part.mpn == mpn)).unique().one()

    return go


# ---------------------------------------------------------------- 1. pin names


def test_vout_reads_as_out_and_adi_inputs_as_in():
    assert pin_name("VOUT") == pin_name("OUT") == "out"  # VO<x> used to turn VOUT into "outut"
    assert pin_name("VOUT", "gate_driver") == pin_name("VO", "gate_driver") == "out"
    assert pin_name("VOUTP") == "outp" and pin_name("VOA") == "outa"
    # ADI logic inputs VIA..VID against our INA..IND; outputs VOA..VOD against OUTA..OUTD (adum1410_1411_1412.pdf
    # p.15, Table 11; si864x-datasheet.pdf p.29)
    assert all(pins_compatible(f"VI{x}", f"IN{x}", "digital_isolator") for x in "ABCD")
    assert all(pins_compatible(f"VO{x}", f"OUT{x}", "digital_isolator") for x in "ABCD")
    assert not pins_compatible("VIA", "INB", "digital_isolator")
    assert not pins_compatible("VI", "INA", "digital_isolator")  # a lone VI is the Si86Px dc-dc input
    assert not pins_compatible("VIA", "INA")  # the input alias is for digital isolators only


def test_adum4121_matches_si82b47_pin_for_pin_in_another_package(load):
    """ADuM4121 (ADuM4121_4121-1.pdf pin table: VDD1, VI+, VI-, GND1, GND2, CLAMP, VOUT, VDD2) against Si82B47 (VDDI,
    VI+, VI-, GNDI, GND, MC, VO, VDD): the same function on every pin. The packages still differ: ADI RI-8-1 spans
    10.31 mm, our SSO-8 11.5 mm."""
    get = load("adi_gate_drivers", "skyworks_gate_drivers_more")
    fit = check_fit(get("ADuM4121ARIZ"), get("SI82B47AGE-IS4"))
    assert fit.same_pinout and not fit.pin_diffs
    assert not fit.same_package and not fit.fits


# ---------------------------------------------------------------- 2. control pins 7 and 10, by role


@pytest.fixture
def iso(load):
    return load("adi_digital_isolators", "skyworks_si86")


def test_pin_roles_have_datasheet_pages():
    d = pinroles.data()
    assert set(d["roles"]) == {"nc", "output_enable", "default_output_control", "refresh_enable", "input_disable"}
    for sheet, pins in d["pins"].items():
        for name, entry in pins.items():
            assert entry["role"] in d["roles"], (sheet, name)
            assert re.search(r"\.pdf p\.\d", entry["source"]) and entry["source"].lower().startswith(sheet), (
                sheet, name)


def test_nc_takes_any_wiring_of_their_control_pin(iso):
    """Si86SS41 pins 7 and 10 are NC, not connected (si86s6xx-datasheet.pdf p.5, Table 2): whatever the board does with
    the ADuM1411 CTRL1 / CTRL2 pins (adum1410_1411_1412.pdf p.15-16), our part does not see it. No pin deviation;
    their default output follows the board, ours the ordering code, so both variants are offered."""
    fit = check_fit(iso("ADuM1411BRWZ"), iso("SI86SS41EE-IS2"))
    assert fit.fits and not fit.pin_diffs and not fit.conditions
    assert fit.board_default == [7, 10]


def test_our_enable_against_their_ctrl_is_a_conditional_fit(iso):
    """Si86S641 / Si8641 pins 7 and 10 are EN1 / EN2: active high, pulled up, tied low = outputs high impedance
    (si86s6xx-datasheet.pdf p.4, p.8; si864x-datasheet.pdf p.9, p.29). ADuM1411 CTRL1 / CTRL2 only set the default
    output while the other side is unpowered and act as high when open: a fit only if they are high or open."""
    for ours in ("SI86S641HE-IS2", "SI8641ET-IS"):
        fit = check_fit(iso("ADuM1411BRWZ"), iso(ours))
        assert fit.same_package and fit.same_pinout and not fit.fits, ours
        assert [c[0] for c in fit.conditions] == [7, 10]
        assert fit.condition_note == ("Works if pins 7 and 10 are tied high or left open on the board; tied low, "
                                      "our outputs switch off")


def test_refresh_enable_against_our_output_enable_is_a_mismatch(iso):
    """ADuM1441 EN1 / EN2 are refresh / watchdog enables, tied to ground in normal use (adum1440...pdf p.16): the same
    name as our output enables, a different job. Tied low, ours would switch the outputs off: never a drop-in."""
    fit = check_fit(iso("ADuM1441ARQZ"), iso("SI86S641EB-IU"))
    assert fit.same_package and not fit.same_pinout and [p[0] for p in fit.pin_diffs] == [7, 10]
    assert fit.role_diffs == [(7, "refresh_enable", "output_enable"), (10, "refresh_enable", "output_enable")]


def test_disable_against_our_enable_is_a_mismatch(iso):
    """ADuM141D DISABLE1 / DISABLE2: input disable, active high, outputs to the fail-safe state, low or open in normal
    use (adum140d...pdf p.19, p.21). Our EN: active high output enable, low = high impedance. Opposite polarity and
    another effect: a pin-function mismatch, not just a priority 2 note."""
    ref = iso("ADuM141D1BRZ")
    fit = check_fit(ref, iso("SI86S641EC-IS1"))
    assert fit.same_package and [p[0] for p in fit.pin_diffs] == [7, 10]
    assert {r[1:] for r in fit.role_diffs} == {("input_disable", "output_enable")}
    assert check_fit(ref, iso("SI86SS41EC-IS1")).fits  # our NC takes it (si86s6xx p.5)


def test_their_enable_against_ours_matches(iso):
    """ADuM141E VE1 / VE2 and our EN1 / EN2: both active high output enables, high or open = on, low = high-Z
    (adum140d...pdf p.19, p.21; si864x-datasheet.pdf p.9, p.29)."""
    assert check_fit(iso("ADuM141E1BRWZ"), iso("SI8641ET-IS")).fits


def test_adum1411_crosses_to_si86ss41_with_both_default_outputs(session, iso):
    """Owner, 2 Nov 2026, for both ADuM1411 grades: Si86SS41 is the drop-in, in both default-output variants (B = low
    for CTRL tied low, E = high for CTRL high or open); Si86S641 and Si8641 are shown with the deciding note; for the
    10 Mbps B grade the closest Si86S641 is the 10 Mbps deglitch, default-high HE code."""
    rows = {r.text: r for r in cl.cross_list(session, cl.parse("ADuM1411BRWZ\nADuM1411ARWZ")[0])}
    note = "Works if pins 7 and 10 are tied high or left open on the board; tied low, our outputs switch off"
    for mpn, row in rows.items():
        assert row.drop_in.part.mpn == "SI86SS41EE-IS2" and row.drop_in.type == "Direct package equivalent", mpn
        assert "SI86SS41BE-IS2 (default low) when tied low" in row.drop_in.comment
        assert row.functional.part.mpn.startswith("SI86S641") and row.functional.type.startswith(cl.CONDITIONAL_TYPE)
        assert row.functional.comment.startswith(note)
        assert row.other.part.mpn.startswith("SI8641") and note in row.other.comment
        assert row.light == "green"
    assert rows["ADuM1411BRWZ"].functional.part.mpn == "SI86S641HE-IS2"


def test_a_conditional_fit_is_never_the_drop_in(session, iso):
    """ADuM1412 pins 7 and 10 are CTRL1 / CTRL2 (adum1410_1411_1412.pdf p.16); our 2/2 parts Si86S642 and Si8642 have
    EN1 / EN2 there and we have no 2/2 part with NC pins: no drop-in, the conditional fit with its note."""
    row = cl.cross_list(session, cl.parse("ADuM1412BRWZ")[0])[0]
    assert row.drop_in is None and row.light == "amber"
    assert row.functional.type.startswith(cl.CONDITIONAL_TYPE) and row.functional.comment.startswith("Works if pins 7")


# ---------------------------------------------------------------- 3. gate drivers: protection steers the pick


@pytest.fixture
def gd(load):
    return load("adi_gate_drivers", "skyworks_gate_drivers_more")


def test_desat_reference_ranks_unprotected_candidates_last(session, gd):
    """ADuM4136 detects desaturation, with soft shutdown (ADuM4136.pdf p.1, p.7: DESAT pin 14). Si8286 has DESAT and
    soft shutdown too; Si82B28 has neither. Every candidate without DESAT, overcurrent or short-circuit protection
    ranks below every candidate with one, so Si8286 is the pick."""
    ref = gd("ADuM4136BRWZ")
    pool = cl._pool(ref, cl.Crosser(session).crosses(ref))
    misses = [r.steer_miss for r in sorted(pool, key=cl.functional_key)]
    assert misses == sorted(misses) and not misses[0] and any(misses)
    row = cl.cross_list(session, cl.parse("ADuM4136BRWZ")[0])[0]
    assert (row.drop_in or row.functional).part.mpn.startswith("SI8286")
    plain = next(r for r in pool if r.candidate.mpn.startswith("SI82B28"))
    assert plain.steer_miss and "ours has no desaturation protection" in cl.comment(plain, 2)


# ---------------------------------------------------------------- 4. isolated amplifiers: input side


def test_adum4195_1_sides_compare_by_function(load):
    """ADuM4195-1 has its input on side 2 (adum4195-1.pdf p.8: VDD2, VIN, SHTD, GND2 | GND1, NC, VOUT, VDD1); Si8932D
    calls the input side A (VDDA, VIN, NC, GNDA | GNDB, GNDB, AO, VDDB). With the sides normalised only pin 3 (their
    shutdown input, our NC) and pin 6 (their NC, to be tied to GND1 or VDD1; our GNDB) differ: it was 7 of 8."""
    get = load("adi_isolated_amplifiers", "skyworks_isolated_amplifiers")
    ref = get("ADUM4195-1BRIZ")
    assert [p[0] for p in check_fit(ref, get("SI8932D-IS4")).pin_diffs] == [3, 6]
    assert pinroles.by_side(ref, ["VDD2", "GND1", "VIN", "VOUT"]) == ["VDD1", "GND2", "VIN", "VOUT"]
    assert pinroles.by_side(get("SI8932D-IS4"), ["VDDA", "GNDB"]) == ["VDDA", "GNDB"]  # ours: side A is the input


# ---------------------------------------------------------------- rule 5: unstated values are info, not deviations


def test_unstated_values_are_info_not_deviations(gd):
    """ADuM4137 states no CMTI (ADuM4137.pdf has no CMTI row). Owner, 2 Nov 2026: a value the competitor does not state
    no longer counts against our candidates; it is shown as "not stated by" the maker. Si8285 (DESAT, automotive) is
    then a functional fit with its two real deviations: peak source 2.7 A and sink 5.5 A against ADI's 6 A."""
    from app.matching.engine import cross
    from app.matching.rules import get_rules

    r = cross(gd("ADuM4137WBRNZ"), gd("SI8285CD-AS"), get_rules("gate_driver"))
    assert {d.key for d in r.deviations} == {"peak_source_a", "peak_sink_a"} and r.category == "functional"
    assert "CMTI not stated by Analog Devices (info)" in cl.comment(r, 2)


# ---------------------------------------------------------------- rule 6: isolation below theirs ranks last


def test_isolation_shortfall_ranks_below_an_output_option_difference(session, gd):
    """ADuM4122 is a 5 kVrms reinforced driver (ADuM4122.pdf p.1). Si82B28 (3.75 kVrms) falls short of it; Si82B47
    (6 kVrms) differs in the output option. Owner, 2 Nov 2026: the 6 kVrms part with another output option ranks above
    the 3.75 kVrms part, and every candidate below their isolation rating ranks below every candidate that is not."""
    ref = gd("ADuM4122ARIZ")
    pool = cl._pool(ref, cl.Crosser(session).crosses(ref))
    order = sorted(pool, key=cl.functional_key)
    downs = [r.downgrade for r in order]
    assert downs == sorted(downs) and any(downs)
    assert order[0].candidate.mpn.startswith("SI82B47") and not order[0].downgrade
    assert all(r.downgrade for r in pool if r.candidate.mpn.startswith("SI82B28"))


# ---------------------------------------------------------------- rule 10: space grade says why


def test_space_grade_red_row_says_why(session, iso):
    """ADuM141ES is QML Level V space grade (adum141es.pdf p.1): we have no space-grade part; the red row says so."""
    row = cl.cross_list(session, cl.parse("ADuM141E1L703F")[0])[0]
    assert row.light == "red" and row.reason == "No space-grade (QML) part in our portfolio."


# ---------------------------------------------------------------- rule 8: input ranges as numbers


def test_input_range_text_reads_as_numbers():
    from app.matching.rules import input_range_v

    def v(text):
        return input_range_v(None, {"input_range": text})

    assert v("±250 mV") == [-0.25, 0.25] and v("0.25 to 4.3 V") == [0.25, 4.3] and v("8 to 68.5 mV") == [0.008, 0.0685]
    assert v("-0.1 to 2 V") == [-0.1, 2.0] and v("±1.2 V") == [-1.2, 1.2] and v("1 V/V") is None


def test_a_narrower_input_range_names_the_part_not_covered(load):
    """ADuM4195-1 takes 0.25 to 4.3 V (adum3195_adum4195.pdf p.4 / adum4195-1.pdf), Si8932D 0.25 to 2.25 V
    (si8931-32-datasheet.pdf p.7-9): a deviation that names 2.25 to 4.3 V as not covered."""
    from app.matching.engine import cross
    from app.matching.rules import get_rules

    get = load("adi_isolated_amplifiers", "skyworks_isolated_amplifiers")
    r = cross(get("ADUM4195-1BRIZ"), get("SI8932D-IS4"), get_rules("isolated_amplifier"))
    d = next(d for d in r.diffs if d.key == "input_range_v")
    assert d.status == "worse" and d in r.deviations
    assert "Linear input range 0.25 to 4.3 V vs 0.25 to 2.25 V (ours worse; partial: not covered 2.25 to 4.3 V)" in (
        cl.comment(r, 2))


# ---------------------------------------------------------------- rule 11: RF partial band


def test_rf_partial_band_names_dc_and_the_uncovered_band(load):
    """ADGM1121 works from DC to 18 GHz (adgm1121.pdf p.1); SKY13355 covers 0.1 to 6 GHz: a priority 1 partial-band
    deviation that names DC to 0.1 GHz and 6 to 18 GHz."""
    from app.matching.engine import cross
    from app.matching.rules import get_rules

    get = load("adi_switches", "skyworks_switches")
    r = cross(get("ADGM1121BCCZ-RL7"), get("SKY13355-374LF"), get_rules("rf_switch"))
    assert any(d.key == "freq_range_ghz" for d in r.deviations)
    assert "partial: not covered DC to 0.1, 6 to 18 GHz" in cl.comment(r, 2)
