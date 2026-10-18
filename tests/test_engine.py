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
        "fff": ["SD8641A", "SA7741", "SA7741X"],
        "p2p": ["SD8641A", "SC141", "SA7741", "SB8441", "SA7741X"],
        "upgrade": ["SB8641N", "SA7741"],
        "downgrade": ["SB8441"],
    },
    "SR8640N": {
        "fff": ["SA7740N"],
        "upgrade": ["SB8140Q", "SD4100"],
        "downgrade": ["SC140N", "SD140N"],
    },
    "SR8233": {"fff": ["SA21520", "SA21521"], "upgrade": ["SA21520"], "downgrade": ["SB6602", "SC4223"]},
    "SR8286": {"fff": ["SA5870"], "upgrade": ["SA5870"], "downgrade": ["SC4135"]},
    "SR8920": {"fff": ["SB1300", "SA1301"], "upgrade": ["SA1301"], "downgrade": ["SA1300"]},
    "SR8501": {"fff": ["SA1100"], "upgrade": ["SA1100"], "downgrade": ["SB2011"]},
}


@pytest.mark.parametrize("ref", EXPECTED)
def test_expected_categories(session, part, ref):
    got = crosses(session, part, ref)
    for cat, expected in EXPECTED[ref].items():
        assert names(got[cat]) == expected, f"{ref} {cat}"


def test_fff_requires_same_pinout(session, part):
    got = crosses(session, part, "SR8641")
    assert "SB8641N" not in names(got["fff"]) + names(got["p2p"])  # pinout differs


def test_p2p_ignores_function(part):
    # Different default output: not FFF, but still pin-to-pin.
    r = cross(part("SR8641"), part("SB8441"), get_rules("digital_isolator"))
    assert r.categories == ["p2p", "downgrade"]


def test_p2p_only_when_p2_worse(part):
    r = cross(part("SR8641"), part("SC141"), get_rules("digital_isolator"))
    assert r.categories == ["p2p"]


def test_hard_mismatch_excludes_functional_categories(part):
    r = cross(part("SR8641"), part("SC142"), get_rules("digital_isolator"))
    assert r.hard_fail and r.categories == []
    r = cross(part("SR8261"), part("SA5350"), get_rules("gate_driver"))
    assert r.hard_fail and r.categories == ["p2p"]  # same pins, CMOS vs opto input


def test_smaller_package_upgrade_allowed(part):
    r = cross(part("SR8640N"), part("SB8140Q"), get_rules("digital_isolator"))
    assert r.fit.package_relation == "smaller" and "upgrade" in r.categories


def test_larger_package_never_upgrade(part):
    r = cross(part("SR8640N"), part("SA7741"), get_rules("digital_isolator"))
    assert r.fit.package_relation == "larger" and r.categories == []


def test_package_lock_blocks_smaller_package_upgrade(part):
    ref, cand = part("SR8286"), part("SB6601")
    assert ref.package_locked
    r = cross(ref, cand, get_rules("gate_driver"))
    assert r.fit.package_relation == "smaller" and "upgrade" not in r.categories


def test_downgrade_requires_same_package_and_prefers_same_pinout(session, part):
    got = crosses(session, part, "SR8233")
    assert "SD6602N" not in names(got["downgrade"])  # narrow body
    assert names(got["downgrade"]) == ["SB6602", "SC4223"]  # pinout match ranked first


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
