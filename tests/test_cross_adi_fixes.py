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

