"""Owner's cross verification from the live site, 26 Oct 2026 (docs/worked_2026-10-26.md).

1. CA-IS3720HG-Q1: the 10 Mbps deglitch code (Si86S620HE) no longer comes first; the data rate is priority 1.
2. LMK3H0102-Q1: 105 fs typ. differential jitter (not the 0.5 ps LVCMOS max), so Si5332A-AM1 shows a jitter deviation.
3. NSI8240S0-Q1SSR: the SSOP16 parts are basic insulation, VIORM 565 Vpk, creepage 3.9 mm.
4. NSI8320N0-Q1SPR: crosses to the Si86S620BC-AS (CMTI 100) before the Si8620BC-AS (CMTI 50).
5. NSI6801B-DSPR -> SI8261BBC-C-IS: 1.8 A source / 4.0 A sink typ. confirmed (Si826x.pdf p.5).
6. LMK03328 -> Si5341A: jitter compared at the same output frequency; the Si5341 needs two core rails.
7. ISOW7841AQDWERQ1: the Si86P matches on integrated power but is industrial only, so no cross is shown
   (owner, 26 Oct 2026: "No industrial fallback. Automotive needs automotive").
8. ISO7761: CMTI typ. 100 kV/us (min 85).
"""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.matching.engine import cross
from app.matching.rules import get_rules
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
    assert row(session, "NSI8320N0-Q1SPR").functional.result.candidate.mpn == "SI86S620BC-AS"
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
