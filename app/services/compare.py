"""Side-by-side comparison of a list of parts on priority 1 & 2 parameters."""

from dataclasses import dataclass

from app.matching.engine import BETTER, EQUAL, UNKNOWN, compare_param, format_value
from app.matching.rules import FamilyRules, ParamDef
from app.models import Part


@dataclass
class Cell:
    display: str
    status: str  # vs baseline: equal / better / worse / different / unknown / baseline
    best: bool = False
    worst: bool = False


@dataclass
class Row:
    param: ParamDef
    cells: list[Cell]


@dataclass
class Comparison:
    parts: list[Part]
    baseline: Part
    rows: list[Row]
    mixed_families: bool


def _rank_value(p: ParamDef, v):
    """Scalar where higher means better, or None when not rankable."""
    if v is None:
        return None
    if p.kind == "number":
        return float(v) if p.direction == "higher" else -float(v)
    if p.kind == "range":
        lo, hi = sorted(map(float, v))
        return hi - lo
    if p.kind == "ordinal":
        levels = [x.lower() for x in p.levels]
        return levels.index(str(v).lower()) if str(v).lower() in levels else None
    if p.kind == "set":
        return len(v)
    return None


def compare_parts(parts: list[Part], baseline: Part, rules: FamilyRules, priorities=(1, 2)) -> Comparison:
    rows = []
    maps = [rules.values(p) for p in parts]
    base_map = rules.values(baseline)
    for pdef in rules.by_priority(*priorities):
        cells = []
        for part, values in zip(parts, maps, strict=True):
            v = values.get(pdef.key)
            if part.id == baseline.id:
                status = "baseline"
            else:
                status, _ = compare_param(pdef, base_map.get(pdef.key), v)
            cells.append(Cell(format_value(pdef, v), status))
        ranks = [_rank_value(pdef, m.get(pdef.key)) for m in maps]
        known = [r for r in ranks if r is not None]
        if len(known) >= 2 and max(known) != min(known):
            for cell, r in zip(cells, ranks, strict=True):
                cell.best = r == max(known)
                cell.worst = r == min(known)
        rows.append(Row(pdef, cells))
    return Comparison(parts, baseline, rows, len({p.family for p in parts}) > 1)


__all__ = ["compare_parts", "Comparison", "Row", "Cell", "BETTER", "EQUAL", "UNKNOWN"]
