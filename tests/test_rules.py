import pytest

from app.matching.rules import load_all_rules, parse_rules


def test_all_families_load_with_three_priority_groups():
    rules = load_all_rules()
    assert {"digital_isolator", "gate_driver", "isolated_amplifier", "current_sensor"} <= set(rules)
    for fam in rules.values():
        assert {p.priority for p in fam.params} == {1, 2, 3}, fam.family
        assert len({p.key for p in fam.params}) == len(fam.params), "duplicate keys"


def test_uvlo_is_priority_1_for_gate_drivers():
    assert load_all_rules()["gate_driver"].get("uvlo_v").priority == 1


@pytest.mark.parametrize(
    "param,error",
    [
        ({"key": "x", "priority": 1, "kind": "weird"}, "unknown kind"),
        ({"key": "x", "priority": 4, "kind": "category"}, "priority"),
        ({"key": "x", "priority": 1, "kind": "number"}, "direction"),
        ({"key": "x", "priority": 1, "kind": "ordinal"}, "levels"),
    ],
)
def test_invalid_rules_are_rejected(param, error):
    with pytest.raises(ValueError, match=error):
        parse_rules({"family": "f", "params": [param]})
