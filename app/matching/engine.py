"""Cross-reference matching engine.

Given a reference part (the Skyworks part being crossed) and a candidate, decide
which cross categories the candidate falls into:

* FFF       – fit (same package + same pinout), no priority 1 parameter worse.
              If every priority 2 parameter is also equal or better the cross is
              FFF automatically; otherwise it "needs review" until an engineer
              accepts or rejects it (stored feedback).
* P2P       – fit only; function is ignored, all differences are reported.
* Upgrade   – no priority 1 parameter worse and at least one better. The package
              may be the same or smaller, unless the reference is package-locked.
* Downgrade – at least one priority 1 parameter worse, same package; ranked by
              closeness to the reference.

A "hard" parameter mismatch (e.g. channel configuration) makes the parts
functionally different, which excludes FFF, Upgrade and Downgrade.
"""

from dataclasses import dataclass, field

from app.matching.rules import FamilyRules, ParamDef
from app.models import FeedbackVerdict, LifecycleStatus, Package, Part

EQUAL, BETTER, WORSE, DIFFERENT, UNKNOWN = "equal", "better", "worse", "different", "unknown"
PRIORITY_WEIGHT = {1: 100.0, 2: 10.0, 3: 1.0}
UNKNOWN_SEVERITY = 0.25
CATEGORY_ORDER = ("fff", "p2p", "upgrade", "downgrade")
CATEGORY_LABELS = {
    "fff": "FFF – form, fit & function",
    "p2p": "Pin-to-pin",
    "upgrade": "Upgrade",
    "downgrade": "Downgrade",
}
LIFECYCLE_RISK = {LifecycleStatus.nrnd, LifecycleStatus.last_time_buy, LifecycleStatus.obsolete}
# FFF status of a cross that fits and matches priority 1
FFF_AUTO, FFF_ACCEPTED, FFF_REVIEW, FFF_REJECTED = "auto", "accepted", "review", "rejected"
FFF_STATUS_LABELS = {
    FFF_AUTO: "FFF",
    FFF_ACCEPTED: "FFF – accepted",
    FFF_REVIEW: "FFF – needs review",
    FFF_REJECTED: "FFF – rejected",
}


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
    def review_items(self) -> list[Diff]:
        """Priority 2 differences an engineer has to judge for FFF."""
        return [d for d in self.diffs if d.priority == 2 and d.status not in (EQUAL, BETTER)]

    @property
    def all_diffs(self) -> list[Diff]:
        return self.fit_diffs + self.diffs

    @property
    def closeness(self) -> float:
        """Lower is closer to the reference."""
        return sum(d.score for d in self.all_diffs)

    @property
    def improvement(self) -> float:
        return sum(d.score for d in self.diffs if d.status == BETTER and d.priority == 1)

    def top_differences(self, n: int = 5) -> list[Diff]:
        ranked = sorted(
            (d for d in self.all_diffs if d.status != EQUAL),
            key=lambda d: (-d.score, d.priority, not d.is_negative),
        )
        return ranked[:n]

    def comment(self, n: int = 5) -> str:
        top = self.top_differences(n)
        if not top:
            return "No differences found in the compared parameters."
        return " · ".join(f"{i}) {d.summary()}" for i, d in enumerate(top, 1))

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
        r, c = {_norm(x) for x in ref}, {_norm(x) for x in cand}
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


def pins_compatible(ref: str, cand: str) -> bool:
    """Pins match when equal, or when a datasheet allows alternatives ("VDD1/NC")
    and the other part's function is one of them."""
    r, c = {_norm(x) for x in ref.split("/")}, {_norm(x) for x in cand.split("/")}
    return bool(r & c)


def same_package(a: Package, b: Package) -> bool:
    if a.id is not None and a.id == b.id:
        return True
    # Pin count may differ: one package can leave positions empty where another
    # has a no-connect pin. Pinouts are compared by position in check_fit.
    return (
        abs(a.pitch_mm - b.pitch_mm) <= 0.01
        and abs(a.body_length_mm - b.body_length_mm) <= 0.05
        and abs(a.body_width_mm - b.body_width_mm) <= 0.05
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
        if not pins_compatible(r, c):
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


def cross(ref: Part, cand: Part, rules: FamilyRules, feedback=None) -> CrossResult:
    fit = check_fit(ref, cand)
    rv, cv = ref.param_map(), cand.param_map()
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
            )
        )

    hard_fail = any(d.hard and d.is_negative for d in diffs)
    p1 = [d for d in diffs if d.priority == 1]
    p12 = [d for d in diffs if d.priority in (1, 2)]
    ok = (EQUAL, BETTER)
    incomplete = any(d.status == UNKNOWN for d in p12)

    cats = []
    fff_status = None
    if fit.fits and not hard_fail and all(d.status in ok for d in p1):
        if all(d.status in ok for d in p12):
            fff_status = FFF_AUTO
        elif feedback is None:
            fff_status = FFF_REVIEW
        else:
            fff_status = FFF_ACCEPTED if feedback.verdict == FeedbackVerdict.accept else FFF_REJECTED
        if fff_status != FFF_REJECTED:
            cats.append("fff")
    if fit.fits:
        cats.append("p2p")
    package_ok_for_upgrade = (
        fit.same_package if ref.package_locked else fit.package_relation in ("same", "smaller", "similar")
    )
    if (
        not hard_fail
        and package_ok_for_upgrade
        and all(d.status in ok for d in p1)
        and any(d.status == BETTER for d in p1)
    ):
        cats.append("upgrade")
    if not hard_fail and fit.same_package and any(d.is_negative for d in p1):
        cats.append("downgrade")

    return CrossResult(
        ref, cand, fit, diffs, _fit_diffs(ref, cand, fit), cats, hard_fail, incomplete, fff_status, feedback
    )


def sort_key(category: str):
    """Ordering within a category. Lifecycle-risk parts always sink to the bottom."""

    def key(r: CrossResult):
        if category == "upgrade":
            main = -r.improvement
        elif category == "downgrade":
            main = (not r.fit.same_pinout, r.closeness)
        elif category == "fff":
            main = (r.fff_status == FFF_REVIEW, r.closeness)  # confirmed FFF first
        else:
            main = r.closeness
        return (r.lifecycle_risk, main, r.candidate.label)

    return key


def find_crosses(
    ref: Part, candidates: list[Part], rules: FamilyRules, feedback: dict | None = None
) -> dict[str, list[CrossResult]]:
    """``feedback`` maps candidate id -> CrossFeedback for this reference."""
    out: dict[str, list[CrossResult]] = {c: [] for c in CATEGORY_ORDER}
    feedback = feedback or {}
    for cand in candidates:
        if cand.id == ref.id or cand.family != ref.family:
            continue
        result = cross(ref, cand, rules, feedback.get(cand.id))
        for c in result.categories:
            out[c].append(result)
    for c in out:
        out[c].sort(key=sort_key(c))
    return out
