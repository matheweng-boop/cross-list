"""Cross engine fixes from the Analog Devices import (owner, 2 Nov 2026), checked on datasheet facts:

1. pin names: ADI VIA..VID are our INA..IND; VOUT is OUT (it used to read "outut");
2. control pins 7 and 10 compared by what they do (data/pin_roles.yaml);
3. gate drivers: short-circuit protection steers the pick;
4. isolated amplifiers: ADI numbers the input side 2, we call it side A (1).
"""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.matching.engine import check_fit, pin_name, pins_compatible
from app.models import Part
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
