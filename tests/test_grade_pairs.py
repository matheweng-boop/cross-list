"""Industrial and automotive codes of the same Skyworks part carry the same datasheet values (owner, 26 Oct 2026: "the
Automotive Grade parts usually carry the same values as the regular parts"). Only the grade and temperature differ.
E.g. Si8641AB-IS1 and Si8641AB-AS1 share one ordering-guide row (si86xx-1Mbps-datasheet.pdf p.2)."""

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


def test_industrial_and_automotive_codes_have_the_same_values():
    pairs = _pairs()
    assert len(pairs) > 900
    bad = []
    for ind, auto in pairs:
        a, b = ind.get("params") or {}, auto.get("params") or {}
        for k in (set(a) | set(b)) - GRADE_ONLY:
            if a.get(k) != b.get(k):
                bad.append((ind["mpn"], auto["mpn"], k, a.get(k), b.get(k)))
    assert not bad, bad[:10]


def test_fixed_pairs_26_oct():
    by = {i["mpn"]: (i, a) for i, a in _pairs()}
    ind, auto = by["SI8660BA-IS1"]
    assert ind["params"]["isolation_rating_kvrms"] == auto["params"]["isolation_rating_kvrms"] == 1.0  # si866x p.2
    ind, auto = by["SI8620EB-IS"]
    assert ind["params"]["prop_delay_ns"] == auto["params"]["prop_delay_ns"] == 8.0
    ind, auto = by["SI8641AB-IS1"]
    assert ind["params"]["data_rate_mbps"] == auto["params"]["data_rate_mbps"] == 1.0  # speed grade A
