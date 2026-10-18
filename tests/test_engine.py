"""Classification of the synthetic demo parts. Each candidate was designed to
exercise one rule; see data/synthetic/demo.yaml."""

import pytest

from app.matching.engine import cross, find_crosses
from app.matching.rules import get_rules
from app.services.queries import candidates_for


def crosses(session, part, mpn):
    ref = part(mpn)
    return find_crosses(ref, candidates_for(session, ref), get_rules(ref.family))


def names(results):
    return [r.candidate.mpn for r in results]


EXPECTED = {
    "SR8641": {
        # SC141 is only worse in priority 2, SD8641A is automotive (P1 better): both still FFF
        "fff": ["SC141", "SD8641A", "SA7741", "SA7741X"],
        "functional": ["SB8641N"],  # same package, other pinout
        "package": ["SB8441"],  # same package, other default output (SC142: other channels, not listed)
    },
    "SR8640N": {
        "fff": ["SA7740N"],
        "upgrade": ["SB8140Q"],  # smaller package, better
        "functional": ["SD4100", "SC141", "SD8641A", "SA7741", "SB8641N", "SA7741X"],  # wide body
        "package": ["SD140N"],
        "downgrade": ["SC140N"],
    },
    "SR8233": {"fff": ["SA21520", "SA21521"], "package": ["SB6602", "SC4223"]},  # pin-to-pin first
    "SR8286": {"fff": ["SC4135", "SA5870"], "functional": ["SB6601"]},  # package-locked: no upgrade
    "SR8920": {"fff": ["SA1300", "SB1300", "SA1301"]},  # gain is priority 3 (sensitivity)
    "SR8501": {"fff": ["SA1100", "SB2011"], "functional": ["SC712"]},
}


@pytest.mark.parametrize("ref", EXPECTED)
def test_expected_categories(session, part, ref):
    got = crosses(session, part, ref)
    for cat, expected in EXPECTED[ref].items():
        assert names(got[cat]) == expected, f"{ref} {cat}"
    for cat in set(got) - set(EXPECTED[ref]):
        assert got[cat] == [], f"{ref} {cat}"


def test_fff_requires_same_pinout(part):
    r = cross(part("SR8641"), part("SB8641N"), get_rules("digital_isolator"))
    assert r.fit.same_package and not r.fit.same_pinout and r.categories == ["functional"]
    assert not r.verdict().p2p


def test_package_equivalent_is_same_package_other_features(part):
    # Different default output: same package and pins, but not the same function.
    r = cross(part("SR8641"), part("SB8441"), get_rules("digital_isolator"))
    assert r.categories == ["package"] and r.verdict().p2p


def test_priority_2_never_blocks_fff(part):
    r = cross(part("SR8641"), part("SC141"), get_rules("digital_isolator"))
    assert r.categories == ["fff"] and r.fff_status == "auto"
    v = r.verdict()
    assert v.spec == "exact" and {d.key for d in v.info_worse} >= {"data_rate_mbps", "prop_delay_ns"}


def test_better_priority_1_marked_on_fff(part):
    v = cross(part("SR8641"), part("SD8641A"), get_rules("digital_isolator")).verdict()
    assert v.category == "fff" and v.spec == "over" and [d.key for d in v.better] == ["qualification"]


def test_rejected_fff_becomes_package_equivalent(part):
    from types import SimpleNamespace

    from app.models import FeedbackVerdict

    rules = get_rules("digital_isolator")
    rejected = cross(part("SR8641"), part("SC141"), rules, SimpleNamespace(verdict=FeedbackVerdict.reject))
    assert rejected.fff_status == "rejected" and rejected.categories == ["package"]


def test_downgrade_only_pin_to_pin_with_lower_priority_1(part):
    rules = get_rules("digital_isolator")
    down = cross(part("SR8640N"), part("SC140N"), rules)
    assert down.categories == ["downgrade"] and down.fit.fits
    assert any(d.status == "worse" for d in down.diffs if d.priority == 1)


def test_same_package_ignores_pin_count_but_not_dimensions():
    from app.matching.engine import same_package
    from app.models import Package

    wide16 = Package(
        code="A", name="", pin_count=16, pitch_mm=1.27, body_length_mm=10.3, body_width_mm=7.5, span_mm=10.3
    )
    wide12 = Package(
        code="B", name="", pin_count=12, pitch_mm=1.27, body_length_mm=10.3, body_width_mm=7.5, span_mm=10.3
    )
    ssop = Package(code="C", name="", pin_count=16, pitch_mm=0.635, body_length_mm=5.4, body_width_mm=3.9, span_mm=6.0)
    qsop = Package(code="D", name="", pin_count=16, pitch_mm=0.635, body_length_mm=4.9, body_width_mm=3.9, span_mm=6.0)
    assert same_package(wide16, wide12)
    assert not same_package(ssop, qsop)  # 5.4 mm vs 4.9 mm body


def test_missing_pin_positions_match_nc():
    from app.matching.engine import check_fit
    from app.models import Package, Part

    full = Package(code="F", name="", pin_count=8, pitch_mm=1.27, body_length_mm=4.9, body_width_mm=3.9, span_mm=6.0)
    gaps = Package(
        code="G", name="", pin_count=6, pitch_mm=1.27, body_length_mm=4.9, body_width_mm=3.9, span_mm=6.0,
        positions_total=8, pin_positions=[1, 2, 4, 5, 7, 8],
    )  # fmt: skip
    ref = Part(mpn="R", package=full, pinout=["VDD1", "INA", "NC", "GND1", "GND2", "NC", "OUTA", "VDD2"])
    cand = Part(mpn="C", package=gaps, pinout=["VDD1", "INA", "GND1", "GND2", "OUTA", "VDD2"])
    fit = check_fit(ref, cand)
    assert fit.same_package and fit.same_pinout
    unknown = Package(code="U", name="", pin_count=6, pitch_mm=1.27, body_length_mm=4.9, body_width_mm=3.9, span_mm=6.0)
    fit = check_fit(ref, Part(mpn="U", package=unknown, pinout=cand.pinout))
    assert fit.same_package and not fit.same_pinout and fit.positions_unknown


def test_hard_mismatch_is_not_listed(part):
    r = cross(part("SR8641"), part("SC142"), get_rules("digital_isolator"))
    assert r.hard_fail and r.fit.same_package and r.categories == []  # other channels
    r = cross(part("SR8261"), part("SA5350"), get_rules("gate_driver"))
    assert r.hard_fail and r.fit.fits and r.categories == []  # same pins, CMOS vs opto input


def test_smaller_package_upgrade_allowed(part):
    r = cross(part("SR8640N"), part("SB8140Q"), get_rules("digital_isolator"))
    assert r.fit.package_relation == "smaller" and "upgrade" in r.categories


def test_larger_package_is_functional_not_upgrade(part):
    r = cross(part("SR8640N"), part("SA7741"), get_rules("digital_isolator"))
    assert r.fit.package_relation == "larger" and r.categories == ["functional"]


def test_package_lock_blocks_smaller_package_upgrade(part):
    ref, cand = part("SR8286"), part("SB6601")
    assert ref.package_locked
    r = cross(ref, cand, get_rules("gate_driver"))
    assert r.fit.package_relation == "smaller" and "upgrade" not in r.categories


def test_other_packages_with_worse_priority_1_are_not_listed(session, part):
    got = crosses(session, part, "SR8233")
    listed = {r.candidate.mpn for rs in got.values() for r in rs}
    assert "SD6602N" not in listed  # narrow body and worse


def test_lifecycle_risk_parts_sorted_last(session, part):
    got = crosses(session, part, "SR8641")
    assert got["fff"][-1].candidate.mpn == "SA7741X" and got["fff"][-1].lifecycle_risk


def test_top_five_differences(part):
    r = cross(part("SR8640N"), part("SA7741"), get_rules("digital_isolator"))
    assert len([d for d in r.all_diffs if d.status != "equal"]) > 5
    top = r.top_differences()
    assert len(top) == 5
    assert all(d.priority == 1 for d in top)  # P1 differences outrank P2/P3
    assert [d.score for d in top] == sorted((d.score for d in top), reverse=True)
    assert "Isolation" in r.comment() and r.comment().startswith("1) ")


def test_fewer_than_five_differences(part):
    r = cross(part("SR8641"), part("SD4100"), get_rules("digital_isolator"))
    keys = [d.key for d in r.top_differences()]
    # On equal scores a worse value (creepage) ranks above a better one (smaller package).
    assert keys == ["isolation_class", "creepage_mm", "package", "isolation_rating_kvrms"]


def test_identical_part_has_no_differences(part):
    r = cross(part("SR8641"), part("SR8641"), get_rules("digital_isolator"))
    assert r.top_differences() == []
    assert r.comment().startswith("No differences")


def test_pin_alternatives_are_compatible():
    from app.matching.engine import pins_compatible

    assert pins_compatible("VDD1/NC", "NC") and pins_compatible("GND2/NC", "GND2")
    assert pins_compatible("INA", "ina")
    assert not pins_compatible("EN1", "NC") and not pins_compatible("GND1", "NC")


def test_isolator_priorities(part):
    rules = get_rules("digital_isolator")
    p1 = {p.key for p in rules.by_priority(1)}
    assert {"isolation_rating_kvrms", "isolation_class", "creepage_mm", "default_output", "qualification"} <= p1
    assert "cmti_kv_us" in p1
    assert {p.key for p in rules.by_priority(2)} >= {"vdd_range_v", "viorm_vpk", "prop_delay_ns"}
    r = cross(part("SR8641"), part("SB8641N"), rules)
    by_key = {d.key: d for d in r.diffs}
    assert by_key["certifications"].status == "equal"  # TUV is not judged in the certification set
    assert by_key["tuv_certified"].priority == 3 and by_key["tuv_certified"].status == "better"


def test_priority_3_differences_are_noted_in_the_comment(part):
    rules = get_rules("digital_isolator")
    r = cross(part("SB8641N"), part("SR8641"), rules)  # SR8641 lacks TUV
    assert [d.key for d in r.p3_notes()] == ["tuv_certified"]
    assert "TÜV certification: no vs yes (P3, worse)" in r.comment()  # already in the top 5
    r.top_differences = lambda n=5: []  # when it is not in the top 5 it gets its own note
    assert "Also note (priority 3): TÜV certification no vs yes" in r.comment()
    assert "Also note" not in cross(part("SR8641"), part("SA7741"), rules).comment()
