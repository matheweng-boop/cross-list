"""Load per-family matching rules from rules/*.yaml."""

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from app import yamlio
from app.config import get_settings

KINDS = {"number", "range", "category", "set", "ordinal", "bool", "curve"}


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
    unknown_ok: bool = False  # an unknown value (not stated, not derivable) is shown but not counted as a deviation
    exclude: tuple[str, ...] = ()  # set items ignored when comparing (shown, not judged)
    derived_from: str | None = None  # bool derived from another set parameter …
    contains: str | None = None  # … being true when that set contains this item
    default: object = None  # value assumed when a part states none (e.g. the usual CMOS input)
    derive: str | None = None  # name of a DERIVE function giving the value when the data file states none
    at: str | None = None  # parameter holding the test condition of this value (the supply of a peak current)
    curve: str | None = None  # a ``curve`` parameter giving this value at other test conditions
    x_unit: str = ""  # curve: unit of the test condition
    # range parameter (an RF part's frequency band): a candidate that covers a wider band than the reference is read
    # off its ``curve`` at its worst over the reference's band, so both values cover the same frequencies
    band: str | None = None
    # direction "match": the side that is the safer stand-in when no variant matches (a UVLO threshold: a lower one
    # still starts up at every supply the reference starts at; owner, 22 Oct 2026). Still a deviation, ranked closer.
    prefer: str | None = None


@dataclass(frozen=True)
class FamilyRules:
    family: str
    title: str
    params: tuple[ParamDef, ...] = field(default_factory=tuple)
    # functional_focus (owner, 22 Oct 2026, timing): judge a cross by function and specs only; package and pinout do
    # not decide the cross type or the order, and a functional match without priority 1 deviations counts as crossed
    functional_focus: bool = False

    def by_priority(self, *priorities: int) -> list[ParamDef]:
        return [p for p in self.params if p.priority in priorities]

    def get(self, key: str) -> ParamDef | None:
        return next((p for p in self.params if p.key == key), None)

    def values(self, part) -> dict:
        """The part's parameter values, including derived ones."""
        values = part.param_map()
        for p in self.params:
            if p.derive and values.get(p.key) in (None, "", []):
                values[p.key] = DERIVE[p.derive](part, values)
            if p.default is not None and values.get(p.key) in (None, "", []):
                values[p.key] = p.default
            if p.derived_from:
                src = values.get(p.derived_from)
                values[p.key] = None if src is None else p.contains.upper() in {str(x).upper() for x in src}
        return values

    def at_same_conditions(self, ref: dict, cand: dict) -> tuple[dict, dict]:
        """Values stated at different test conditions (a voltage-mode driver's peak current at VDD = 18 V against a
        competitor's at 15 V) are compared at the same condition: a part whose ``curve`` covers the other part's
        condition is read off its curve there (linear between the stated points, never extrapolated)."""
        ref, cand = dict(ref), dict(cand)
        moved: list[tuple[dict, str, float]] = []
        for p in self.params:
            if not (p.at and p.curve):
                continue
            rc, cc = ref.get(p.at), cand.get(p.at)
            if rc is None or cc is None or abs(float(rc) - float(cc)) < 1e-9:
                continue
            for mine, cond in ((cand, float(rc)), (ref, float(cc))):
                v = curve_value(mine.get(p.curve), cond)
                if v is not None:
                    mine[p.key] = v
                    moved.append((mine, p.at, cond))
                    break
        for side, key, cond in moved:  # the condition shown is the one the compared value was read at
            side[key] = cond
        for p in self.params:  # owner, 23 Oct 2026: compare RF values over the same frequencies
            if not (p.band and p.curve):
                continue
            rb, cb = ref.get(p.band), cand.get(p.band)
            if not (rb and cb) or (float(cb[0]) >= float(rb[0]) and float(cb[1]) <= float(rb[1])):
                continue
            v = curve_worst(cand.get(p.curve), float(rb[0]), float(rb[1]), p.direction)
            if v is not None:
                cand[p.key], cand[p.key + BAND_SUFFIX] = v, (float(rb[0]), float(rb[1]))
        return ref, cand


BAND_SUFFIX = "@band"  # values key: the band a value was read over (shown next to it)


def curve_worst(curve, lo: float, hi: float, direction: str | None) -> float | None:
    """The curve's worst value between ``lo`` and ``hi`` (highest for a lower-is-better value, lowest otherwise): the
    stated points inside and the values read at both edges; None when the curve does not cover the whole span."""
    pts = sorted((float(a), float(b)) for a, b in curve or [])
    if not pts or pts[0][0] > lo + 1e-9 or pts[-1][0] < hi - 1e-9:
        return None
    ys = [y for x, y in pts if lo <= x <= hi] + [v for v in (curve_value(pts, lo), curve_value(pts, hi)) if v is not None]
    return (max if direction == "lower" else min)(ys) if ys else None


def curve_value(curve, x: float) -> float | None:
    """The curve's value at ``x``: [[x, y], ...] read linearly between the two nearest points; None outside."""
    pts = sorted((float(a), float(b)) for a, b in curve or [])
    if len(pts) == 1 and abs(pts[0][0] - x) < 1e-9:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:], strict=False):
        if x0 <= x <= x1:
            return round(y0 + (y1 - y0) * (x - x0) / (x1 - x0), 3)
    return None


# Gate drivers: the output option vendors sell as separate variants (TI UCC53x0 S / M / E, Skyworks Si82B40 / Si82B41,
# Novosense NSI6601 / NSI6601M), read from the datasheet pinout when the data file states none.
_CLAMP_PINS = {"CLAMP", "CLAMPA", "CLAMPB", "MC", "CLMP", "CLMPI", "CLMPE"}
_SPLIT_PAIRS = (("OUTH", "OUTL"), ("OUT+", "OUT-"), ("VO+", "VO-"), ("VH", "VL"), ("OUTH1", "OUTL1"))
_OUT_PINS = {"OUT", "VO", "OUTA", "OUTB", "VOA", "VOB", "VOUT"}


def gate_output_config(part, values: dict) -> str | None:
    pins = {str(x).upper() for x in part.pinout or []}
    split = any(a in pins and b in pins for a, b in _SPLIT_PAIRS)
    clamp = bool(pins & _CLAMP_PINS)
    if split:
        return "split output + Miller clamp" if clamp else "split output"
    if clamp:
        return "Miller clamp"
    if pins & _OUT_PINS:
        # TI UCC53x0E: one output plus a GND2 (emitter) pin that the output UVLO is referred to
        if {"GND2", "VEE2"} <= pins and not pins & {"DESAT", "DSAT", "OC"}:
            return "UVLO to GND2"
        return "single output"
    if not pins and "Miller clamp" in (values.get("protection") or []):
        return "Miller clamp"  # no pinout read: the vendor's feature list names the clamp variant
    return None


DERIVE = {"gate_output_config": gate_output_config}


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
            unknown_ok=bool(raw.get("unknown_ok", False)),
            exclude=tuple(raw.get("exclude", ())),
            derived_from=(raw.get("from") or {}).get("param"),
            contains=(raw.get("from") or {}).get("contains"),
            default=raw.get("default"),
            derive=raw.get("derive"),
            at=raw.get("at"),
            curve=raw.get("curve"),
            x_unit=raw.get("x_unit", ""),
            band=raw.get("band"),
            prefer=raw.get("prefer"),
        )
        if p.kind not in KINDS:
            raise ValueError(f"{p.key}: unknown kind {p.kind!r}")
        if p.priority not in (1, 2, 3):
            raise ValueError(f"{p.key}: priority must be 1, 2 or 3")
        if p.kind == "number" and p.direction not in ("higher", "lower", "match"):
            raise ValueError(f"{p.key}: number needs direction higher|lower|match")
        if p.prefer not in (None, "lower", "higher") or (p.prefer and p.direction != "match"):
            raise ValueError(f"{p.key}: prefer (lower|higher) goes with direction match")
        if p.derived_from and (p.kind != "bool" or not p.contains):
            raise ValueError(f"{p.key}: a derived parameter must be a bool with from.contains")
        if p.kind == "ordinal" and not p.levels:
            raise ValueError(f"{p.key}: ordinal needs levels")
        if p.derive and p.derive not in DERIVE:
            raise ValueError(f"{p.key}: unknown derive {p.derive!r}")
        if p.kind != "curve" and (bool(p.at) or bool(p.band)) != bool(p.curve):
            raise ValueError(f"{p.key}: a curve goes with at (a test condition) or band (a frequency band)")
        params.append(p)
    return FamilyRules(family=data["family"], title=data.get("title", data["family"]), params=tuple(params),
                       functional_focus=bool(data.get("functional_focus")))


@lru_cache
def load_all_rules(rules_dir: Path | None = None) -> dict[str, FamilyRules]:
    rules_dir = rules_dir or get_settings().rules_dir
    out = {}
    for path in sorted(Path(rules_dir).glob("*.yaml")):
        rules = parse_rules(yamlio.load(path.read_text()))
        out[rules.family] = rules
    return out


def get_rules(family: str) -> FamilyRules:
    rules = load_all_rules()
    if family not in rules:
        raise KeyError(f"No rules for family {family!r}")
    return rules[family]
