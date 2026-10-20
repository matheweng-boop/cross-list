import pytest

from app.matching.engine import BETTER, DIFFERENT, EQUAL, UNKNOWN, WORSE, compare_param, format_value
from app.matching.rules import ParamDef


def P(kind, **kw):
    return ParamDef(key="k", label="K", priority=1, kind=kind, **kw)


@pytest.mark.parametrize(
    "direction,ref,cand,status",
    [
        ("higher", 5.0, 5.0, EQUAL),
        ("higher", 5.0, 5.05, EQUAL),  # within 2 % tolerance
        ("higher", 5.0, 5.7, BETTER),
        ("higher", 5.0, 3.75, WORSE),
        ("lower", 13, 25, WORSE),
        ("lower", 60, 25, BETTER),
        ("higher", None, 5, UNKNOWN),
    ],
)
def test_number(direction, ref, cand, status):
    assert compare_param(P("number", direction=direction), ref, cand)[0] == status


def test_number_severity_is_capped():
    status, sev = compare_param(P("number", direction="higher"), 1.0, 10.0)
    assert status == BETTER and sev == 1.0


@pytest.mark.parametrize(
    "ref,cand,status",
    [
        ([-40, 125], [-40, 125], EQUAL),
        ([-40, 125], [-40, 150], BETTER),
        ([-40, 125], [-40, 105], WORSE),
        ([2.5, 5.5], [3.0, 5.5], WORSE),
        ([2.5, 5.5], [1.7, 5.5], BETTER),
    ],
)
def test_range(ref, cand, status):
    assert compare_param(P("range"), ref, cand)[0] == status


def test_category_is_case_insensitive():
    assert compare_param(P("category"), "High", "high")[0] == EQUAL
    assert compare_param(P("category"), "high", "low") == (DIFFERENT, 1.0)


def test_set_superset_is_better():
    p = P("set")
    assert compare_param(p, ["UL1577", "CQC"], ["CQC", "UL1577"])[0] == EQUAL
    assert compare_param(p, ["UL1577"], ["UL1577", "CSA"])[0] == BETTER
    assert compare_param(p, ["UL1577", "CSA"], ["UL1577"]) == (WORSE, 0.5)


def test_ordinal():
    p = P("ordinal", levels=("commercial", "industrial", "automotive"))
    assert compare_param(p, "industrial", "automotive")[0] == BETTER
    assert compare_param(p, "automotive", "commercial") == (WORSE, 1.0)
    assert compare_param(p, "industrial", "space")[0] == UNKNOWN


def test_bool():
    assert compare_param(P("bool", direction="true_better"), False, True)[0] == BETTER
    assert compare_param(P("bool", direction="match"), False, True)[0] == DIFFERENT


def test_format_value():
    assert format_value(P("number", direction="higher", unit="kVrms"), 5.0) == "5 kVrms"
    assert format_value(P("range", unit="V"), [2.5, 5.5]) == "2.5 to 5.5 V"
    assert format_value(P("set"), ["b", "a"]) == "a, b"
    assert format_value(P("number", direction="higher"), None) == "—"


@pytest.mark.parametrize(
    "ref,cand,status", [(12, 12.5, EQUAL), (13, 13.6, EQUAL), (12, 13, DIFFERENT), (12, 8, DIFFERENT)]
)
def test_number_match_direction(ref, cand, status):
    # a UVLO threshold: neither higher nor lower is better, so outside the tolerance the value only differs
    assert compare_param(P("number", direction="match", tolerance=0.06), ref, cand)[0] == status
