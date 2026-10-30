"""The cross-list data files agree with each other and with the matching rules."""

import copy
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import pytest

from app import yamlio
from app.matching.rules import load_all_rules

DATA = Path(__file__).resolve().parents[1] / "data" / "real"
pytestmark = pytest.mark.smoke  # part of the quick check (tests/test_smoke.py)


@lru_cache
def _files() -> dict[str, dict]:
    return {f.name: yamlio.load(f.read_text()) for f in sorted(DATA.glob("*.yaml"))}


def _parts():
    """Every part with ``like`` resolved, as the loader sees it."""
    for name, data in _files().items():
        resolved = {}
        for raw in data.get("parts", []):
            spec = copy.deepcopy(resolved[raw["like"]]) if "like" in raw else {}
            params = {**spec.get("params", {}), **raw.get("params", {})}
            spec.update({k: v for k, v in raw.items() if k not in ("like", "params")})
            spec["params"] = params
            resolved[spec["mpn"]] = spec
            yield name, spec


def test_package_defined_the_same_everywhere():
    # the loader updates a package from each file in turn, so two different definitions would make the last file win
    defs = defaultdict(dict)
    for name, data in _files().items():
        for p in data.get("packages", []):
            defs[p["code"]][name] = p
    differ = {code: sorted(by) for code, by in defs.items() if len({repr(sorted(p.items())) for p in by.values()}) > 1}
    assert not differ, f"packages defined differently in several files: {differ}"


def test_manufacturer_defined_the_same_everywhere():
    defs = defaultdict(set)
    for data in _files().values():
        for m in data.get("manufacturers", []):
            defs[m["name"]].add((m["role"], m.get("website")))
    assert not {n: v for n, v in defs.items() if len(v) > 1}


def test_ordinal_values_are_known_levels():
    # a value outside the levels compares as unknown, which counts as a deviation against every reference.
    # Known exception: a space-grade (QML Level V) part is "space" on purpose; against it every candidate is unknown
    # and fails the must-meet qualification, so it is never offered an automotive or industrial part as equivalent.
    rules = load_all_rules()
    allowed = {("qualification", "space")}
    bad = []
    for name, spec in _parts():
        for p in rules[spec["family"]].params:
            v = spec["params"].get(p.key)
            if p.key == "qualification" and (p.key, v) in allowed:
                continue
            if p.kind == "ordinal" and v is not None and str(v).lower() not in {x.lower() for x in p.levels}:
                bad.append((name, spec["mpn"], p.key, v))
    assert not bad, bad[:10]


def test_number_parameters_are_numbers():
    rules = load_all_rules()
    bad = []
    for name, spec in _parts():
        for p in rules[spec["family"]].params:
            v = spec["params"].get(p.key)
            if p.kind == "number" and v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
                bad.append((name, spec["mpn"], p.key, v))
    assert not bad, bad[:10]
