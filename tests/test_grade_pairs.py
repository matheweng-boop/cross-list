"""Industrial and automotive codes of the same Skyworks part (owner, 26 Oct 2026: "the Automotive Grade parts usually
carry the same values as the regular parts" and "the test shouldn't blindly assume values").

The test does not copy one code's values to the other. It only flags a pair whose values differ without a datasheet
page behind both sides: that difference must be read in the datasheet, never filled in from the twin. A value the
datasheet does not give is marked as an estimate ("est ... check datasheet")."""

import re
from collections import defaultdict
from pathlib import Path

from app import yamlio

ROOT = Path(__file__).resolve().parents[1]
GRADE_ONLY = {"qualification", "temp_range_c", "temperature_max_c", "temperature_min_c", "aec_q100", "grade"}


def _pairs():
    parts = {}
    for f in sorted((ROOT / "data" / "real").glob("skyworks*.yaml")):
        for p in yamlio.load(f.read_text()).get("parts") or []:
            parts[p["mpn"].upper()] = p
    groups = defaultdict(dict)
    for mpn, p in parts.items():
        m = re.sub(r"-[A-Z]-(?=[IA][SMU])", "-", mpn)  # the die revision (-B-) is not part of the pairing
        g = re.search(r"-([IA])([SMU]\d*)$", m)
        if g:
            groups[m[: g.start()] + g.group(2)][g.group(1)] = p
    return [(d["I"], d["A"]) for d in groups.values() if "I" in d and "A" in d]


def test_a_difference_between_the_two_grades_is_read_from_the_datasheet():
    from app.matching.engine import from_datasheet, is_estimate_source

    pairs = _pairs()
    assert len(pairs) > 900
    unchecked = []
    for ind, auto in pairs:
        a, b = ind.get("params") or {}, auto.get("params") or {}
        sa, sb = ind.get("param_sources") or {}, auto.get("param_sources") or {}
        for k in (set(a) | set(b)) - GRADE_ONLY:
            if a.get(k) == b.get(k):
                continue
            documented = all(from_datasheet(src) or is_estimate_source(src) for src in (sa.get(k), sb.get(k)))
            if not documented:
                unchecked.append((ind["mpn"], auto["mpn"], k, a.get(k), b.get(k)))
    assert not unchecked, unchecked[:10]


def test_no_value_is_copied_from_the_other_grade():
    for ind, auto in _pairs():
        for p in (ind, auto):
            for k, src in (p.get("param_sources") or {}).items():
                assert "same as" not in str(src).lower(), (p["mpn"], k, src)


def test_pairs_read_26_oct():
    by = {i["mpn"]: (i, a) for i, a in _pairs()}
    ind, auto = by["SI8660BA-IS1"]  # one ordering-guide row for both codes, si866x.pdf p.2
    assert ind["params"]["isolation_rating_kvrms"] == auto["params"]["isolation_rating_kvrms"] == 1.0
    assert "row Si8660BA-B-IS1 / Si8660BA-AS1" in ind["param_sources"]["isolation_rating_kvrms"]
    ind, auto = by["SI8641AB-IS1"]  # speed grade A, si86xx-1Mbps-datasheet.pdf p.2
    assert ind["params"]["data_rate_mbps"] == auto["params"]["data_rate_mbps"] == 1.0
    ind, auto = by["SI8650BC-IS1"]  # not in the ordering guide: an estimate, shown "check datasheet"
    assert all(s.startswith("est:") for s in (ind["param_sources"]["isolation_rating_kvrms"],
                                              auto["param_sources"]["isolation_rating_kvrms"]))
