"""Owner's cross verification, 22 Oct 2026 (Verify next › Crosses).

- NSI6602A-DLAR: the 4 V UVLO Si82E29AGC-IS1 is the better stand-in for the 6 V option than the 8 V Si82E29ABC-IS1;
  Novosense CMTI is the datasheet typical (150 kV/µs).
- Rule: typical first, then max (prop delay, CMTI); limits (isolation, creepage, UVLO option) stay as stated.
- 1ED3140MU12FXUMA1: prop delay typ 40 ns; UVLO 9.3 V crosses to the 8 V (B) Skyworks code first.
- Si86: prop delay typ per ordering option (B/E 9 ns, F/H deglitch 36 ns, SLx 11.5 ns).
- MSW2060-206: 8 x 5 mm body, frequency and temperature from the datasheet.
- Dead time and overlap protection count as one capability.
"""

import copy
from functools import lru_cache
from pathlib import Path

import pytest
from sqlalchemy import select

from app import yamlio
from app.matching.engine import compare_param, cross, ranked
from app.matching.rules import ParamDef, get_rules, parse_rules
from app.models import Part
from app.services.queries import crosses_for
from app.services.seed import load_file

DATA = Path(__file__).resolve().parents[1] / "data" / "real"


@lru_cache
def _parts(name: str) -> dict[str, dict]:
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
    nsi = _parts("novosense_isolation")
    a = nsi["NSI6602A-DLAR"]
    assert a["params"]["cmti_kv_us"] == 150 and a["params"]["prop_delay_ns"] == 25
    assert "CMTI typ" in a["param_sources"]["cmti_kv_us"] and "tPD typ" in a["param_sources"]["prop_delay_ns"]
    assert nsi["NSI6602MEB-Q1SWDR"]["params"]["cmti_kv_us"] == 200  # min 150, typ 200
    assert nsi["NSI6602NA-DSPNR"]["params"]["prop_delay_ns"] == 33
    for spec in nsi.values():  # no Novosense gate driver keeps a maximum delay
        assert "tPD max" not in (spec.get("param_sources") or {}).get("prop_delay_ns", "")


def test_si82x_prop_delay_is_typical_per_deglitch_option():
    sky = _parts("skyworks_gate_drivers_more")
    assert sky["SI82E29AGC-IS1"]["params"]["prop_delay_ns"] == 30  # 0 ns deglitch: 20 / 30 / 40
    assert sky["SI82E29BGB-IM3"]["params"]["prop_delay_ns"] == 52.5  # 30 ns deglitch: 45 / 52.5 / 65
    assert sky["SI82B28ABC-IS"]["params"]["prop_delay_ns"] == 26
    assert "typ" in sky["SI82E29AGC-IS1"]["param_sources"]["prop_delay_ns"]
    assert sky["SI82E29AGC-IS1"]["params"]["cmti_kv_us"] == 200  # only a minimum is stated: kept


def test_limits_keep_their_limit_value():
    a = _parts("novosense_isolation")["NSI6602A-DLAR"]["params"]
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
    ifx = _parts("infineon_isolation")
    for mpn in ("1ED3140MU12FXUMA1", "1ED3141MU12FXUMA1", "1ED3145MC12HXUMA1"):
        assert ifx[mpn]["params"]["prop_delay_ns"] == 40, mpn
    assert ifx["1ED3140MU12FXUMA1"]["params"]["uvlo_v"] == 9.3  # the datasheet's 1ED3140 option
    get = load("infineon_isolation", "skyworks_gate_drivers_more")
    best = ranked(crosses_for(session, get("1ED3140MU12FXUMA1")))[0]
    assert best.candidate.param_map()["uvlo_v"] == 8  # the B (8 V) code, not 4 or 12 V


# ---------------------------------------------------------------- Si86


def test_si86_prop_delay_typ_per_option():
    si86 = _parts("skyworks_si86")
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
    m = _parts("macom_switches")["MSW2060-206"]
    assert m["package"] == "Ceramic SMT 8x5x2.5"
    assert m["params"]["freq_range_ghz"] == [0.02, 1.2]  # MSW2060 = the 20-1200 MHz band of MSW206x
    assert m["params"]["temp_range_c"] == [-65, 125]  # +150 °C is storage
    assert _parts("macom_switches")["MSW2062-206"]["params"]["freq_range_ghz"] == [1.5, 6.5]


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
