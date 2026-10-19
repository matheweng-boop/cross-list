"""Load per-family matching rules from rules/*.yaml."""

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import get_settings

KINDS = {"number", "range", "category", "set", "ordinal", "bool"}


@dataclass(frozen=True)
class ParamDef:
    key: str
    label: str
    priority: int
    kind: str
    unit: str = ""
    direction: str | None = None
    levels: tuple[str, ...] = ()
    tolerance: float = 0.02
    hard: bool = False  # defines the function: any mismatch means a different part
    must_meet: bool = False  # the candidate must reach the reference's level (worse = not listed)
    exception: bool = False  # worse is listed as an exception, never a deviation that blocks a cross
    exclude: tuple[str, ...] = ()  # set items ignored when comparing (shown, not judged)
    derived_from: str | None = None  # bool derived from another set parameter …
    contains: str | None = None  # … being true when that set contains this item


@dataclass(frozen=True)
class FamilyRules:
    family: str
    title: str
    params: tuple[ParamDef, ...] = field(default_factory=tuple)

    def by_priority(self, *priorities: int) -> list[ParamDef]:
        return [p for p in self.params if p.priority in priorities]

    def get(self, key: str) -> ParamDef | None:
        return next((p for p in self.params if p.key == key), None)

    def values(self, part) -> dict:
        """The part's parameter values, including derived ones."""
        values = part.param_map()
        for p in self.params:
            if p.derived_from:
                src = values.get(p.derived_from)
                values[p.key] = None if src is None else p.contains.upper() in {str(x).upper() for x in src}
        return values


def parse_rules(data: dict) -> FamilyRules:
    params = []
    for raw in data["params"]:
        p = ParamDef(
            key=raw["key"],
            label=raw.get("label", raw["key"]),
            priority=int(raw["priority"]),
            kind=raw["kind"],
            unit=raw.get("unit", ""),
            direction=raw.get("direction"),
            levels=tuple(raw.get("levels", ())),
            tolerance=float(raw.get("tolerance", 0.02)),
            hard=bool(raw.get("hard", False)),
            must_meet=bool(raw.get("must_meet", False)),
            exception=bool(raw.get("exception", False)),
            exclude=tuple(raw.get("exclude", ())),
            derived_from=(raw.get("from") or {}).get("param"),
            contains=(raw.get("from") or {}).get("contains"),
        )
        if p.kind not in KINDS:
            raise ValueError(f"{p.key}: unknown kind {p.kind!r}")
        if p.priority not in (1, 2, 3):
            raise ValueError(f"{p.key}: priority must be 1, 2 or 3")
        if p.kind == "number" and p.direction not in ("higher", "lower"):
            raise ValueError(f"{p.key}: number needs direction higher|lower")
        if p.derived_from and (p.kind != "bool" or not p.contains):
            raise ValueError(f"{p.key}: a derived parameter must be a bool with from.contains")
        if p.kind == "ordinal" and not p.levels:
            raise ValueError(f"{p.key}: ordinal needs levels")
        params.append(p)
    return FamilyRules(family=data["family"], title=data.get("title", data["family"]), params=tuple(params))


@lru_cache
def load_all_rules(rules_dir: Path | None = None) -> dict[str, FamilyRules]:
    rules_dir = rules_dir or get_settings().rules_dir
    out = {}
    for path in sorted(Path(rules_dir).glob("*.yaml")):
        rules = parse_rules(yaml.safe_load(path.read_text()))
        out[rules.family] = rules
    return out


def get_rules(family: str) -> FamilyRules:
    rules = load_all_rules()
    if family not in rules:
        raise KeyError(f"No rules for family {family!r}")
    return rules[family]
