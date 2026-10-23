"""Owner verification 23 Oct 2026: MSW2030-203 (MACOM) -> SKY12212-478LF. The values come from MACOM's product page
(the linked datasheet covers MSW2031 / MSW2032 only), and RF switch values are compared over the same frequencies."""

from pathlib import Path

import pytest
from sqlalchemy import select

from app import yamlio
from app.matching import engine
from app.matching.rules import BAND_SUFFIX, curve_worst, get_rules, parse_rules
from app.models import Part
from app.services.seed import load_file

ROOT = Path(__file__).resolve().parent.parent


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
