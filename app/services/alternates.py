"""Sister families that are often interchangeable, e.g. Si86xx and Si86S6xx: the same base number
in the other family, kept only where the engine finds it the same or better on every priority 1
parameter (no deviation, no hard mismatch, automotive grade respected).

``alternates(session, part)`` -> [Alternate], best first. relation is "same" (all priority 1 equal),
"upgrade" (some better, none worse) or "lower" (the older family going the other way: some priority 1
values lower, listed in ``lower``). Si86 -> Si86S shows same / upgrade only; Si86S -> Si86 also shows the
lower-spec Si86 version, since that is the part a customer may already use."""

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.matching.engine import cross
from app.matching.rules import get_rules
from app.models import Part

# (pattern on this family's part number -> prefix of the sister family's part numbers)
SISTERS = (
    (re.compile(r"^SI86S6(\d\d)"), "SI86{}", "Si86", True),  # True: lower-spec alternates allowed
    (re.compile(r"^SI86(\d\d)(?=[A-Z])"), "SI86S6{}", "Si86S", False),
)


@dataclass
class Alternate:
    part: Part
    relation: str  # same | upgrade | lower
    pin_to_pin: bool
    family_label: str
    lower: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        what = {"same": "same", "upgrade": "upgrade"}.get(self.relation) or f"lower {', '.join(self.lower)}"
        return f"{what}{', pin-to-pin' if self.pin_to_pin else ', other package'}"


def sister_prefix(mpn: str) -> tuple[str, str, bool] | None:
    up = (mpn or "").upper()
    for pattern, template, label, allow_lower in SISTERS:
        m = pattern.match(up)
        if m:
            return template.format(m.group(1)), label, allow_lower
    return None


def alternates(session: Session, part: Part, limit: int = 3) -> list[Alternate]:
    sp = sister_prefix(part.mpn)
    if not sp:
        return []
    prefix, label, allow_lower = sp
    cands = session.scalars(select(Part).where(Part.family == part.family, Part.mpn.like(f"{prefix}%"))).unique().all()
    rules = get_rules(part.family)
    out = []
    for c in cands:
        r = cross(part, c, rules)
        if r.hard_fail or (r.deviations and not allow_lower):
            continue
        better = any(d.priority == 1 and d.status == "better" for d in r.diffs)
        if r.deviations:
            out.append((r, Alternate(c, "lower", r.fit.fits, label, tuple(d.label for d in r.deviations))))
        else:
            out.append((r, Alternate(c, "upgrade" if better else "same", r.fit.fits, label)))
    rank = {"same": 0, "upgrade": 1, "lower": 2}
    out.sort(
        key=lambda x: (not x[1].pin_to_pin, rank[x[1].relation], len(x[1].lower), x[0].lifecycle_risk, x[0].closeness)
    )
    return [a for _, a in out[:limit]]


# Si86 / Si86S ordering codes: <device><isolation-rating letter>-<grade><package code>, e.g. SI86S641EC-IS1:
# device SI86S641E, rating C (3.75 kVrms, NB SOIC-16), I = industrial, S1 = package. The same device comes in
# other packages under other rating letters (EB-IU = QSOP-16, EE-IS2 = WB SOIC-16).
_ORDER_CODE = re.compile(r"^(SI86\w*?\d{2,3}[A-Z])([A-Z])-([AI])([A-Z]+\d?)$")


def package_options(session: Session, part: Part) -> list[Part]:
    """The same Skyworks device in its other packages (same grade), smallest body first."""
    m = _ORDER_CODE.match((part.mpn or "").upper())
    if not m:
        return []
    device, _, grade, _ = m.groups()
    out = []
    for c in session.scalars(
        select(Part).where(Part.family == part.family, Part.mpn.like(f"{device}_-{grade}%"))
    ).unique():
        cm = _ORDER_CODE.match(c.mpn.upper())
        if (
            c.id != part.id
            and cm
            and cm.group(1) == device
            and cm.group(3) == grade
            and c.package_id != part.package_id
        ):
            out.append(c)
    seen, unique = set(), []
    for c in sorted(out, key=lambda c: ((c.package.body_length_mm or 99) * (c.package.span_mm or 99), c.mpn)):
        if c.package_id not in seen:
            seen.add(c.package_id)
            unique.append(c)
    return unique
