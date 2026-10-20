"""Cross-reference matching engine.

Given a reference part (the part being crossed) and a candidate, decide which cross
type the candidate is. Priority 1 parameters decide function; priority 2 and 3 are
shown for information and never block a cross. In order of preference:

* Drop-in (FFF)         – same package, pin-to-pin, every priority 1 parameter equal or
                          better (better ones are marked).
* Functional equivalent – another package or pinout; priority 1 equal or better except
                          for at most ``max_deviations`` parameters (worse, different or
                          unknown). Better ones are marked, deviations listed. A
                          package-locked reference (thermal / technical reasons) only
                          accepts other pinouts in its own package.
* Package equivalent    – same package and basic function, other technical specs (more
                          deviations, or a pin-to-pin part with a lower priority 1 value);
                          marked pin-to-pin or not.

Anything else is not listed. "Hard" parameters (e.g. channel configuration) define what
the part does: they never count as a deviation, a mismatch is not listed at all.
"Must meet" parameters (automotive grade) work one way: a candidate below the reference
(an industrial part for an AEC-Q100 reference) is not listed; a better one is fine.
An engineer can reject a drop-in; it is then listed as a package equivalent.
"""

import re
from dataclasses import dataclass, field

from app.matching.rules import FamilyRules, ParamDef
from app.models import FeedbackVerdict, LifecycleStatus, Package, Part

EQUAL, BETTER, WORSE, DIFFERENT, UNKNOWN = "equal", "better", "worse", "different", "unknown"
PRIORITY_WEIGHT = {1: 100.0, 2: 10.0, 3: 1.0}
UNKNOWN_SEVERITY = 0.25
CATEGORY_ORDER = ("fff", "functional", "package")
CATEGORY_LABELS = {
    "fff": "Drop-in (FFF)",
    "functional": "Functional equivalent (different package)",
    "package": "Package equivalent (different technical spec)",
}
DEFAULT_MAX_DEVIATIONS = 2  # priority 1 deviations accepted for a functional equivalent
LIFECYCLE_RISK = {LifecycleStatus.nrnd, LifecycleStatus.last_time_buy, LifecycleStatus.obsolete}
# Short names for the result table on phones
CATEGORY_SHORT = {"fff": "Drop-in", "functional": "Functional", "package": "Package eq."}
# FFF status: an engineer may reject an FFF cross
FFF_AUTO, FFF_REJECTED = "auto", "rejected"
FFF_STATUS_LABELS = {FFF_AUTO: "FFF", FFF_REJECTED: "FFF – rejected"}


@dataclass
class Diff:
    key: str
    label: str
    priority: int
    status: str
    ref_display: str
    cand_display: str
    severity: float = 0.0
    hard: bool = False
    must_meet: bool = False
    exception: bool = False  # worse = an exception to list, not a deviation

    @property
    def score(self) -> float:
        if self.status == EQUAL:
            return 0.0
        sev = UNKNOWN_SEVERITY if self.status == UNKNOWN else self.severity
        return PRIORITY_WEIGHT[self.priority] * max(sev, 0.01)

    @property
    def is_negative(self) -> bool:
        return self.status in (WORSE, DIFFERENT)

    def summary(self) -> str:
        return f"{self.label}: {self.cand_display} vs {self.ref_display} (P{self.priority}, {self.status})"


@dataclass
class Fit:
    same_package: bool
    package_relation: str  # same | smaller | larger | similar
    same_pinout: bool
    pin_diffs: list[tuple[int, str, str]] = field(default_factory=list)
    positions_unknown: bool = False  # same body, different pin counts, pin positions not known

    @property
    def fits(self) -> bool:
        return self.same_package and self.same_pinout


SPEC_LABELS = {"exact": "Exact", "over": "Better", "under": "Worse", "mixed": "Mixed"}


@dataclass
class Verdict:
    """Cross type, pin-to-pin flag and how priority 1 compares (better list, deviations).

    Priority 2/3 differences are counted separately, for information only.
    """

    category: str
    p2p: bool
    spec: str  # priority 1: exact | over | under | mixed
    better: list[Diff]
    worse: list[Diff]
    info_better: list[Diff]
    info_worse: list[Diff]
    exceptions: list[Diff] = field(default_factory=list)  # e.g. basic for a reinforced reference

    @property
    def label(self) -> str:
        return CATEGORY_LABELS[self.category]

    @property
    def short(self) -> str:
        return CATEGORY_SHORT[self.category]

    @property
    def spec_label(self) -> str:
        return SPEC_LABELS[self.spec]


@dataclass
class CrossResult:
    reference: Part
    candidate: Part
    fit: Fit
    diffs: list[Diff]  # parameter diffs, in rules order
    fit_diffs: list[Diff]  # package / pinout pseudo-rows
    categories: list[str]
    hard_fail: bool
    incomplete: bool
    fff_status: str | None = None
    feedback: object | None = None  # CrossFeedback row, if any

    @property
    def all_diffs(self) -> list[Diff]:
        return self.fit_diffs + self.diffs

    @property
    def closeness(self) -> float:
        """Lower is closer to the reference."""
        return sum(d.score for d in self.all_diffs)

    def top_differences(self, n: int = 5) -> list[Diff]:
        ranked = sorted(
            (d for d in self.all_diffs if d.status != EQUAL),
            key=lambda d: (-d.score, d.priority, not d.is_negative),
        )
        return ranked[:n]

    @property
    def deviations(self) -> list[Diff]:
        """Priority 1 parameters that are worse, different or unknown (exceptions excluded)."""
        return _deviations(self.diffs)

    @property
    def exceptions(self) -> list[Diff]:
        """Parameters marked ``exception`` where the candidate is worse: listed, never blocking."""
        return [d for d in self.diffs if d.exception and d.is_negative]

    @property
    def category(self) -> str | None:
        return self.categories[0] if self.categories else None

    def verdict(self) -> Verdict:
        p1 = [d for d in self.diffs if d.priority == 1]
        info = [d for d in self.diffs if d.priority in (2, 3)]
        better = [d for d in p1 if d.status == BETTER]
        worse = self.deviations
        spec = ("mixed" if better else "under") if worse else ("over" if better else "exact")
        return Verdict(
            self.category or "package",
            self.fit.fits,
            spec,
            better,
            worse,
            [d for d in info if d.status == BETTER],
            [d for d in info if d.is_negative],
            self.exceptions,
        )

    def p3_notes(self) -> list[Diff]:
        """Priority 3 parameters where the candidate is worse or different. They never
        decide a category but are always worth noting in the comment."""
        return [d for d in self.diffs if d.priority == 3 and d.is_negative]

    def comment(self, n: int = 5) -> str:
        top = self.top_differences(n)
        text = (
            " · ".join(f"{i}) {d.summary()}" for i, d in enumerate(top, 1))
            if top
            else "No differences found in the compared parameters."
        )
        extra = [d for d in self.p3_notes() if d not in top]
        if extra:
            text += " · Also note (priority 3): " + "; ".join(
                f"{d.label} {d.cand_display} vs {d.ref_display}" for d in extra
            )
        return text

    @property
    def lifecycle_risk(self) -> bool:
        return self.candidate.lifecycle_status in LIFECYCLE_RISK


# ---------------------------------------------------------------- formatting


def _fmt_num(v: float) -> str:
    return f"{v:g}"


def format_value(p: ParamDef, value) -> str:
    if value is None or value == [] or value == "":
        return "—"
    unit = f" {p.unit}" if p.unit else ""
    if p.kind == "number":
        return f"{_fmt_num(float(value))}{unit}"
    if p.kind == "range":
        lo, hi = value
        return f"{_fmt_num(lo)} to {_fmt_num(hi)}{unit}"
    if p.kind == "set":
        return ", ".join(sorted(value)) if value else "none"
    if p.kind == "bool":
        return "yes" if value else "no"
    return f"{value}{unit}" if p.kind == "category" and p.unit else str(value)


# ---------------------------------------------------------------- parameters


def _norm(s) -> str:
    return str(s).strip().lower()


def compare_param(p: ParamDef, ref, cand) -> tuple[str, float]:
    """Return (status, severity 0..1) of ``cand`` relative to ``ref``."""
    if ref is None or cand is None:
        return UNKNOWN, 0.0

    if p.kind == "number":
        r, c = float(ref), float(cand)
        rel = abs(c - r) / max(abs(r), 1e-12)
        if rel <= p.tolerance:
            return EQUAL, 0.0
        if p.direction == "match":  # neither way is better (a UVLO threshold): outside the tolerance it differs
            return DIFFERENT, min(rel, 1.0)
        better = c > r if p.direction == "higher" else c < r
        return (BETTER if better else WORSE), min(rel, 1.0)

    if p.kind == "range":
        (a, b), (c, d) = sorted(map(float, ref)), sorted(map(float, cand))
        width = max(b - a, abs(a), abs(b), 1e-12) if b == a else b - a
        tol = p.tolerance * width
        if abs(a - c) <= tol and abs(b - d) <= tol:
            return EQUAL, 0.0
        if c <= a + tol and d >= b - tol:
            return BETTER, min((max(0, a - c) + max(0, d - b)) / width, 1.0)
        return WORSE, min((max(0, c - a) + max(0, b - d)) / width, 1.0)

    if p.kind == "category":
        return (EQUAL, 0.0) if _norm(ref) == _norm(cand) else (DIFFERENT, 1.0)

    if p.kind == "set":
        skip = {_norm(x) for x in p.exclude}
        r, c = {_norm(x) for x in ref} - skip, {_norm(x) for x in cand} - skip
        if r == c:
            return EQUAL, 0.0
        if c >= r:
            return BETTER, len(c - r) / max(len(r), 1)
        return WORSE, len(r - c) / max(len(r), 1)

    if p.kind == "ordinal":
        levels = [_norm(x) for x in p.levels]
        if _norm(ref) not in levels or _norm(cand) not in levels:
            return UNKNOWN, 0.0
        ri, ci = levels.index(_norm(ref)), levels.index(_norm(cand))
        if ri == ci:
            return EQUAL, 0.0
        sev = abs(ci - ri) / max(len(levels) - 1, 1)
        return (BETTER if ci > ri else WORSE), sev

    if p.kind == "bool":
        if bool(ref) == bool(cand):
            return EQUAL, 0.0
        if p.direction == "true_better":
            return (BETTER if cand else WORSE), 1.0
        return DIFFERENT, 1.0

    raise ValueError(p.kind)


# ---------------------------------------------------------------- fit


# Vendors name the same pin differently: VCCI / VDDI (input supply), VSSA / GNDA (output ground),
# OUTA / VOA (driver output). Pin names are mapped to one spelling before comparing.
_PIN_ALIASES = ((r"^vcc", "vdd"), (r"^vss", "gnd"), (r"^vo([a-z0-9]+)$", r"out\1"))
# Family-specific names for the same pin. Only within the family: gate drivers use VDDA/VDDB for the two output
# channels, not for the input and output sides. Gate drivers: Skyworks VIA/VIB against INA/INB, and DISABLE against
# DIS (EN is left alone: it has the opposite polarity). Isolated amplifiers: Skyworks side A/B names and TI's
# AVDD/DVDD, AINP/AINN against TI's VDD1/VDD2, INP/INN. ACLK is left out: it is a clock input on some Skyworks parts
# and an output on others.
_FAMILY_PIN_ALIASES = {
    "gate_driver": ((r"^vi([ab])$", r"in\1"), (r"^disable$", "dis")),
    "isolated_amplifier": (
        (r"^(vdda|avdd)$", "vdd1"), (r"^(vddb|dvdd)$", "vdd2"), (r"^(gnda|agnd)$", "gnd1"), (r"^(gndb|dgnd)$", "gnd2"),
        (r"^(aip|ainp)$", "inp"), (r"^(ain|ainn)$", "inn"), (r"^aop$", "outp"), (r"^aon$", "outn"), (r"^ao$", "out"),
        (r"^(adat|data)$", "dout"),
    ),
}  # fmt: skip


def pin_name(name: str, family: str | None = None) -> str:
    n = _norm(name)
    for pattern, repl in _PIN_ALIASES + _FAMILY_PIN_ALIASES.get(family or "", ()):
        n = re.sub(pattern, repl, n)
    return n


def pins_compatible(ref: str, cand: str, family: str | None = None) -> bool:
    """Pins match when equal (after vendor aliases), or when a datasheet allows alternatives
    ("VDD1/NC") and the other part's function is one of them. A plain "GND" matches a ground with a
    side suffix (GNDI, GND1): the position already fixes which side it is on."""
    r, c = {pin_name(x, family) for x in ref.split("/")}, {pin_name(x, family) for x in cand.split("/")}
    if r & c:
        return True
    return ("gnd" in r and any(x.startswith("gnd") for x in c)) or ("gnd" in c and any(x.startswith("gnd") for x in r))


def same_package(a: Package, b: Package) -> bool:
    if a.id is not None and a.id == b.id:
        return True
    if not a.pitch_mm or not b.pitch_mm:  # pitch not published (stored as 0): only the very same package matches
        return False
    # Pin count may differ: one package can leave positions empty where another
    # has a no-connect pin. Pinouts are compared by position in check_fit. Body sizes allow 0.15 mm: some vendors
    # state the nominal JEDEC body (SOIC-8 4.9 x 3.9 mm), others a rounded one (Infineon PG-DSO-8 5.0 x 4.0 mm).
    return (
        abs(a.pitch_mm - b.pitch_mm) <= 0.01
        and abs(a.body_length_mm - b.body_length_mm) <= 0.15
        and abs(a.body_width_mm - b.body_width_mm) <= 0.15
        and abs(a.span_mm - b.span_mm) <= 0.1
        and a.exposed_pad == b.exposed_pad
    )


def check_fit(ref: Part, cand: Part) -> Fit:
    same_pkg = same_package(ref.package, cand.package)
    if same_pkg:
        relation = "same"
    else:
        ra, ca = ref.package.footprint_mm2, cand.package.footprint_mm2
        relation = "smaller" if ca < ra * 0.98 else "larger" if ca > ra * 1.02 else "similar"

    pin_diffs = []
    ref_pos, cand_pos = pin_positions(ref), pin_positions(cand)
    if not ref.pinout or not cand.pinout:
        return Fit(same_pkg, relation, False, pin_diffs)
    if ref_pos is None or cand_pos is None or (same_pkg and len(ref_pos) != len(cand_pos)):
        return Fit(same_pkg, relation, False, pin_diffs, positions_unknown=same_pkg)
    if len(ref_pos) != len(cand_pos):
        return Fit(same_pkg, relation, False, pin_diffs)
    for i, (r, c) in enumerate(zip(ref_pos, cand_pos, strict=True), 1):
        if not pins_compatible(r, c, ref.family if ref.family == cand.family else None):
            pin_diffs.append((i, r, c))
    return Fit(same_pkg, relation, not pin_diffs, pin_diffs)


def pin_positions(part: Part) -> list[str] | None:
    """Pin functions by physical position. Positions without a pin count as NC.
    Returns None when a package leaves positions out but does not say which."""
    pkg = part.package
    total = pkg.positions_total or pkg.pin_count
    if len(part.pinout) == total:
        return list(part.pinout)
    if pkg.pin_positions and len(pkg.pin_positions) == len(part.pinout):
        slots = ["NC"] * total
        for pos, fn in zip(pkg.pin_positions, part.pinout, strict=True):
            slots[pos - 1] = fn
        return slots
    return None


def _fit_diffs(ref: Part, cand: Part, fit: Fit) -> list[Diff]:
    rp, cp = ref.package, cand.package
    pkg_status = {
        "same": EQUAL,
        "smaller": DIFFERENT if ref.package_locked else BETTER,
        "larger": WORSE,
        "similar": DIFFERENT,
    }[fit.package_relation]
    pkg = Diff(
        key="package",
        label="Package",
        priority=1,
        status=pkg_status,
        ref_display=f"{rp.code} ({rp.body_length_mm:g}×{rp.span_mm:g} mm)",
        cand_display=f"{cp.code} ({cp.body_length_mm:g}×{cp.span_mm:g} mm)",
        severity=0.0 if pkg_status == EQUAL else 0.5 if pkg_status == BETTER else 1.0,
    )
    if fit.same_pinout:
        pin = Diff("pinout", "Pinout", 1, EQUAL, "matches", "matches")
    elif not ref.pinout or not cand.pinout:
        pin = Diff(
            "pinout",
            "Pinout",
            1,
            UNKNOWN,
            "known" if ref.pinout else "not read",
            "not read" if not cand.pinout else "known",
        )
    elif fit.positions_unknown:
        pin = Diff(
            "pinout", "Pinout", 1, UNKNOWN, f"{len(ref.pinout)} pins", f"{len(cand.pinout)} pins (positions not known)"
        )
    elif len(ref.pinout) != len(cand.pinout) and not fit.pin_diffs:
        pin = Diff("pinout", "Pinout", 1, DIFFERENT, f"{len(ref.pinout)} pins", f"{len(cand.pinout)} pins", 1.0)
    else:
        listed = ", ".join(f"{i}" for i, _, _ in fit.pin_diffs[:6])
        more = "…" if len(fit.pin_diffs) > 6 else ""
        pin = Diff(
            "pinout",
            "Pinout",
            1,
            DIFFERENT,
            "reference pinout",
            f"differs on pin {listed}{more}",
            min(1.0, 0.4 + 0.1 * len(fit.pin_diffs)),
        )
    return [pkg, pin]


# ---------------------------------------------------------------- classify


def _deviations(diffs: list[Diff]) -> list[Diff]:
    """Priority 1 parameters that are worse, different or unknown; an ``exception`` parameter that is worse is
    listed separately and does not count (an unknown value still does: it cannot be checked)."""
    return [d for d in diffs if d.priority == 1 and ((d.is_negative and not d.exception) or d.status == UNKNOWN)]


def cross(
    ref: Part, cand: Part, rules: FamilyRules, feedback=None, max_deviations: int = DEFAULT_MAX_DEVIATIONS
) -> CrossResult:
    fit = check_fit(ref, cand)
    rv, cv = rules.values(ref), rules.values(cand)
    diffs = []
    for p in rules.params:
        status, sev = compare_param(p, rv.get(p.key), cv.get(p.key))
        diffs.append(
            Diff(
                p.key,
                p.label,
                p.priority,
                status,
                format_value(p, rv.get(p.key)),
                format_value(p, cv.get(p.key)),
                sev,
                p.hard,
                p.must_meet,
                p.exception,
            )
        )

    # hard: any mismatch; must_meet: the candidate falls below the reference (e.g. an industrial
    # part for an automotive reference), while a better value (automotive for industrial) is fine
    # (an unknown value cannot prove it reaches the reference's level either)
    hard_fail = any(
        (d.hard and d.is_negative)
        or (d.must_meet and (d.is_negative or (d.status == UNKNOWN and rv.get(d.key) is not None)))
        for d in diffs
    )
    incomplete = any(d.status == UNKNOWN for d in diffs if d.priority in (1, 2))
    deviations = _deviations(diffs)
    rejected = feedback is not None and feedback.verdict == FeedbackVerdict.reject

    fff_status = None
    if fit.fits and not hard_fail and not deviations:
        fff_status = FFF_REJECTED if rejected else FFF_AUTO
    if hard_fail:
        category = None
    elif fff_status == FFF_AUTO:
        category = "fff"
    elif not fit.fits and len(deviations) <= max_deviations and (fit.same_package or not ref.package_locked):
        category = "functional"  # a package-locked reference only accepts its own package
    elif fit.same_package:
        category = "package"
    else:
        category = None
    cats = [category] if category else []

    return CrossResult(
        ref, cand, fit, diffs, _fit_diffs(ref, cand, fit), cats, hard_fail, incomplete, fff_status, feedback
    )


def sort_key(category: str):
    """Ordering within a category. Lifecycle-risk parts always sink to the bottom."""

    def key(r: CrossResult):
        if category == "functional":
            main = (len(r.deviations), len(r.exceptions), r.closeness)  # fewest deviations first
        elif category == "package":
            main = (not r.fit.same_pinout, len(r.deviations), len(r.exceptions), r.closeness)  # pin-to-pin first
        else:
            main = (len(r.exceptions), r.closeness)
        return (r.lifecycle_risk, main, r.candidate.label)

    return key


def find_crosses(
    ref: Part,
    candidates: list[Part],
    rules: FamilyRules,
    feedback: dict | None = None,
    max_deviations: int = DEFAULT_MAX_DEVIATIONS,
) -> dict[str, list[CrossResult]]:
    """``feedback`` maps candidate id -> CrossFeedback for this reference."""
    out: dict[str, list[CrossResult]] = {c: [] for c in CATEGORY_ORDER}
    feedback = feedback or {}
    for cand in candidates:
        if cand.id == ref.id or cand.family != ref.family:
            continue
        result = cross(ref, cand, rules, feedback.get(cand.id), max_deviations)
        for c in result.categories:
            out[c].append(result)
    for c in out:
        out[c].sort(key=sort_key(c))
    return out
