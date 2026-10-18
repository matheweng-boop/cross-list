"""Package overlay: outline, leads and PCB land pattern of two packages drawn on top of each other.

Lead and land pattern data come from data/mechanical.yaml (read from the datasheets).
The checks place the candidate's leads on the reference's recommended pads: the board
was designed for the reference part, so that is the question a pre-mechanical review asks.
"""

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

import yaml

MECH_FILE = Path(__file__).resolve().parents[2] / "data" / "mechanical.yaml"


@dataclass(frozen=True)
class LandPattern:
    name: str
    pad_length: float  # along the lead
    pad_width: float  # across the lead
    row_spacing: float  # pad centre to pad centre across the body
    source: str = ""
    note: str = ""

    @property
    def inner_edge(self) -> float:  # distance from the package centre line
        return (self.row_spacing - self.pad_length) / 2

    @property
    def outer_edge(self) -> float:
        return (self.row_spacing + self.pad_length) / 2


@dataclass(frozen=True)
class Mechanical:
    lead_width: tuple[float, float]
    lead_length: tuple[float, float]
    source: str = ""
    note: str = ""
    land_patterns: tuple[LandPattern, ...] = ()


@lru_cache
def load_mechanical(path: Path = MECH_FILE) -> dict[str, Mechanical]:
    """Package code -> lead and land pattern data."""
    out = {}
    for packages in (yaml.safe_load(path.read_text()) or {}).values():
        for code, m in packages.items():
            lps = tuple(
                LandPattern(
                    name=lp["name"],
                    pad_length=lp["pad_length_mm"],
                    pad_width=lp["pad_width_mm"],
                    row_spacing=lp["row_spacing_mm"],
                    source=lp.get("source", ""),
                    note=lp.get("note", ""),
                )
                for lp in m.get("land_patterns", [])
            )
            out[code] = Mechanical(
                lead_width=tuple(m["lead_width_mm"]),
                lead_length=tuple(m["lead_length_mm"]),
                source=m.get("source", ""),
                note=m.get("note", ""),
                land_patterns=lps,
            )
    return out


def mid(r: tuple[float, float]) -> float:
    return round((r[0] + r[1]) / 2, 3)


@dataclass
class Outline:
    """One package, centred on the origin: pins on the left and right, pin 1 top left."""

    code: str
    label: str
    pitch: float
    body_length: float  # along the pin rows (vertical)
    body_width: float  # across the body (horizontal)
    span: float  # lead tip to lead tip
    height: float | None
    pins: list[tuple[int, float, int]]  # (pin number, y, side -1 left / +1 right)
    mech: Mechanical | None
    land: LandPattern | None

    @property
    def no_lead(self) -> bool:  # DFN / SON: terminals end at the body edge
        return self.span - self.body_width < 0.1

    def foot(self, length: float) -> tuple[float, float]:
        """x range (from the centre line) of the lead's foot that sits on the board."""
        tip = self.span / 2
        return tip - length, tip


def outline(package, label: str = "", land_index: int = 0) -> Outline:
    mech = load_mechanical().get(package.code)
    positions = package.positions_total or package.pin_count
    per_side = positions // 2
    numbers = package.pin_positions or list(range(1, package.pin_count + 1))
    pins = []
    for number, pos in zip(range(1, package.pin_count + 1), numbers, strict=False):
        if pos <= per_side:  # left side, top to bottom
            pins.append((number, (pos - 1 - (per_side - 1) / 2) * package.pitch_mm, -1))
        else:  # right side, bottom to top
            pins.append((number, ((positions - pos) - (per_side - 1) / 2) * package.pitch_mm, 1))
    lands = mech.land_patterns if mech else ()
    return Outline(
        code=package.code,
        label=label or package.code,
        pitch=package.pitch_mm,
        body_length=package.body_length_mm,
        body_width=package.body_width_mm,
        span=package.span_mm,
        height=package.height_mm,
        pins=pins,
        mech=mech,
        land=lands[min(land_index, len(lands) - 1)] if lands else None,
    )


@dataclass
class Check:
    label: str
    status: str  # ok / warn / bad / unknown
    detail: str


@dataclass
class Overlay:
    ref: Outline
    cand: Outline
    checks: list[Check] = field(default_factory=list)
    dims: list[tuple[str, str, str, str]] = field(default_factory=list)  # label, ref, cand, delta


def _mm(v: float | None) -> str:
    return "–" if v is None else f"{v:.3f}".rstrip("0").rstrip(".") + " mm"


def _delta(a: float | None, b: float | None) -> str:
    if a is None or b is None:
        return ""
    d = round(b - a, 3)
    return "same" if abs(d) < 0.005 else f"{d:+.3f}".rstrip("0").rstrip(".") + " mm"


def compare(ref: Outline, cand: Outline) -> Overlay:
    """Dimension table and fit checks of the candidate on the reference's pads."""
    ov = Overlay(ref, cand)
    rm, cm = ref.mech, cand.mech
    rows = [
        ("Pins", ref.pins and len(ref.pins), cand.pins and len(cand.pins)),
        ("Pitch", ref.pitch, cand.pitch),
        ("Body length", ref.body_length, cand.body_length),
        ("Body width", ref.body_width, cand.body_width),
        ("Lead span (tip to tip)", ref.span, cand.span),
        ("Height (max)", ref.height, cand.height),
    ]
    for label, a, b in rows:
        if label == "Pins":
            ov.dims.append((label, str(a), str(b), "same" if a == b else f"{b - a:+d}"))
        else:
            ov.dims.append((label, _mm(a), _mm(b), _delta(a, b)))
    for label, attr in (("Lead width b", "lead_width"), ("Foot length L", "lead_length")):
        a = getattr(rm, attr) if rm else None
        b = getattr(cm, attr) if cm else None
        ov.dims.append(
            (
                label,
                f"{a[0]}–{a[1]} mm" if a else "–",
                f"{b[0]}–{b[1]} mm" if b else "–",
                _delta(a and mid(a), b and mid(b)),
            )
        )
    for label, attr in (("Pad length", "pad_length"), ("Pad width", "pad_width"), ("Pad row spacing", "row_spacing")):
        a = getattr(ref.land, attr) if ref.land else None
        b = getattr(cand.land, attr) if cand.land else None
        ov.dims.append((label, _mm(a), _mm(b), _delta(a, b)))

    checks = ov.checks
    if abs(ref.pitch - cand.pitch) > 0.01:
        checks.append(Check("Pitch", "bad", f"{cand.pitch} mm vs {ref.pitch} mm: leads do not line up with the pads"))
        return ov
    checks.append(Check("Pitch", "ok", f"{ref.pitch} mm on both"))
    ref_nums = {n for n, _, _ in ref.pins}
    extra = sorted({n for n, _, _ in cand.pins} - ref_nums)
    if extra:
        checks.append(Check("Pin count", "bad", f"candidate pins {extra} have no pad on the reference footprint"))
    elif len(cand.pins) < len(ref.pins):
        checks.append(Check("Pin count", "warn", f"{len(ref.pins) - len(cand.pins)} reference pads left unused"))
    land = ref.land
    if land is None or cm is None:
        missing = "reference land pattern" if land is None else "candidate lead dimensions"
        checks.append(Check("Leads on pads", "unknown", f"no {missing} in the datasheet"))
    else:
        hi = cm.lead_length[1]
        tip = cand.span / 2
        toe = land.outer_edge - tip  # pad left beyond the lead tip
        heel = (tip - hi) - land.inner_edge  # pad left behind the longest foot
        if cand.no_lead:
            tip = cand.body_width / 2
            toe = land.outer_edge - tip
            heel = (tip - hi) - land.inner_edge
        if toe >= 0.05:
            checks.append(Check("Toe", "ok", f"lead tip {toe:.2f} mm inside the pad's outer edge"))
        elif toe >= 0:
            checks.append(
                Check("Toe", "warn", f"lead tip only {toe:.2f} mm inside the pad's outer edge (little toe fillet)")
            )
        else:
            checks.append(Check("Toe", "bad", f"lead tip overhangs the pad by {-toe:.2f} mm"))
        if heel >= 0.05:
            checks.append(Check("Heel", "ok", f"longest foot ({hi} mm) ends {heel:.2f} mm before the pad's inner edge"))
        elif heel >= 0:
            checks.append(
                Check("Heel", "warn", f"longest foot ({hi} mm) ends only {heel:.2f} mm before the inner edge")
            )
        else:
            checks.append(
                Check(
                    "Heel",
                    "warn",
                    f"longest foot ({hi} mm) runs {-heel:.2f} mm past the pad's inner edge (no heel fillet)",
                )
            )
        side = (land.pad_width - cm.lead_width[1]) / 2
        status = "ok" if side >= 0.025 else "warn" if side >= 0 else "bad"
        checks.append(
            Check(
                "Lead width",
                status,
                f"widest lead ({cm.lead_width[1]} mm) leaves {side:.2f} mm each side on a {land.pad_width} mm pad",
            )
        )
    if land is not None:
        gap = land.inner_edge - cand.body_width / 2
        if cand.no_lead:
            checks.append(Check("Body over pads", "ok", "no-lead package: terminals sit under the body"))
        elif gap >= 0:
            checks.append(Check("Body over pads", "ok", f"pads start {gap:.2f} mm outside the candidate body"))
        elif gap >= -0.25:  # IPC nominal patterns often reach slightly under a gull-wing body
            checks.append(Check("Body over pads", "ok", f"pads reach {-gap:.2f} mm under the candidate body (normal)"))
        else:
            checks.append(Check("Body over pads", "warn", f"pads reach {-gap:.2f} mm under the candidate body"))
        creep = land.row_spacing - land.pad_length
        checks.append(Check("Pad-to-pad gap", "ok", f"{creep:.2f} mm across the body on the reference footprint"))
    if ref.height and cand.height:
        dh = cand.height - ref.height
        if dh > 0.05:
            checks.append(Check("Height", "warn", f"candidate is {dh:.2f} mm taller"))
        else:
            checks.append(Check("Height", "ok", "same or lower" if dh > -0.05 else f"{-dh:.2f} mm lower"))
    if ref.body_length != cand.body_length or ref.body_width != cand.body_width:
        dl, dw = cand.body_length - ref.body_length, cand.body_width - ref.body_width
        status = "warn" if dl > 0.05 or dw > 0.05 else "ok"
        checks.append(Check("Body outline", status, f"length {dl:+.2f} mm, width {dw:+.2f} mm"))
    return ov


# --- SVG -------------------------------------------------------------------------------------

STYLE = """
.paper { fill: #fff; }
.axis { stroke: #9aa3ad; stroke-width: .03; stroke-dasharray: .4 .15 .08 .15; }
.ref .body { fill: rgba(31,95,191,.06); stroke: #1f5fbf; stroke-width: .06; }
.ref .lead { fill: rgba(31,95,191,.35); stroke: #1f5fbf; stroke-width: .03; }
.ref .pad { fill: rgba(31,95,191,.10); stroke: #1f5fbf; stroke-width: .05; stroke-dasharray: .15 .08; }
.cand .body { fill: none; stroke: #d0570f; stroke-width: .06; stroke-dasharray: .3 .12; }
.cand .lead { fill: rgba(208,87,15,.45); stroke: #d0570f; stroke-width: .03; }
.cand .pad { fill: none; stroke: #d0570f; stroke-width: .04; stroke-dasharray: .08 .08; }
.pin1 { stroke: none; }
.ref .pin1 { fill: #1f5fbf; } .cand .pin1 { fill: #d0570f; }
text { font-family: -apple-system, Segoe UI, Roboto, sans-serif; fill: #333; }
.num { font-size: .32px; fill: #555; }
.dim { stroke: #555; stroke-width: .025; }
.dimtext { font-size: .34px; fill: #333; }
.legend { font-size: .42px; }
"""


def _rect(x0, y0, x1, y1, cls, title=""):
    x, y = min(x0, x1), min(y0, y1)
    t = f"<title>{escape(title)}</title>" if title else ""
    return (
        f'<rect class="{cls}" x="{x:.3f}" y="{y:.3f}" width="{abs(x1 - x0):.3f}" height="{abs(y1 - y0):.3f}">{t}</rect>'
    )


def _layer(o: Outline, cls: str, numbers: bool) -> str:
    parts = [f'<g class="{cls}">']
    bw, bl = o.body_width / 2, o.body_length / 2
    if o.land:
        lp = o.land
        for n, y, side in o.pins:
            parts.append(
                _rect(
                    side * lp.inner_edge,
                    y - lp.pad_width / 2,
                    side * lp.outer_edge,
                    y + lp.pad_width / 2,
                    "pad layer-pads",
                    f"{o.label} pad {n}: {lp.pad_length} x {lp.pad_width} mm",
                )
            )
    parts.append(_rect(-bw, -bl, bw, bl, "body layer-body", f"{o.label} body {o.body_width} x {o.body_length} mm"))
    if o.mech:
        b, length = mid(o.mech.lead_width), mid(o.mech.lead_length)
        for n, y, side in o.pins:
            if o.no_lead:
                x0, x1 = bw - length, bw
            else:
                x0, x1 = bw, o.span / 2
            parts.append(_rect(side * x0, y - b / 2, side * x1, y + b / 2, "lead layer-leads", f"{o.label} pin {n}"))
            if not o.no_lead:  # foot in contact with the board
                f0, f1 = o.foot(length)
                parts.append(_rect(side * f0, y - b / 2, side * f1, y + b / 2, "lead layer-leads"))
    else:  # no lead data: mark the lead tips only
        for _n, y, side in o.pins:
            parts.append(_rect(side * (o.span / 2 - 0.05), y - 0.1, side * o.span / 2, y + 0.1, "lead layer-leads"))
    # pin 1 marker inside the body corner
    _, y1, _ = o.pins[0]
    r = min(0.25, o.body_width / 12)
    parts.append(
        f'<circle class="pin1" cx="{-bw + 2.2 * r:.3f}" cy="{y1:.3f}" r="{r:.3f}"><title>pin 1</title></circle>'
    )
    if numbers:
        for n, y, side in o.pins:
            x = side * (max(o.span / 2, o.land.outer_edge if o.land else 0) + 0.35)
            parts.append(f'<text class="num" x="{x:.3f}" y="{y + 0.11:.3f}" text-anchor="middle">{n}</text>')
    parts.append("</g>")
    return "".join(parts)


def _hdim(x0: float, x1: float, y: float, label: str) -> str:
    t = 0.12
    return (
        f'<g class="layer-dims"><line class="dim" x1="{x0:.3f}" y1="{y:.3f}" x2="{x1:.3f}" y2="{y:.3f}"/>'
        f'<line class="dim" x1="{x0:.3f}" y1="{y - t:.3f}" x2="{x0:.3f}" y2="{y + t:.3f}"/>'
        f'<line class="dim" x1="{x1:.3f}" y1="{y - t:.3f}" x2="{x1:.3f}" y2="{y + t:.3f}"/>'
        + _text((x0 + x1) / 2, y - 0.12, label, "dimtext", anchor="middle")
        + "</g>"
    )


def _text(x: float, y: float, label: str, cls: str, anchor: str = "start") -> str:
    return f'<text class="{cls}" x="{x:.3f}" y="{y:.3f}" text-anchor="{anchor}">{escape(label)}</text>'


def svg(ov: Overlay, standalone: bool = False) -> str:
    ref, cand = ov.ref, ov.cand
    half_w = max(o.span / 2 for o in (ref, cand))
    for o in (ref, cand):
        if o.land:
            half_w = max(half_w, o.land.outer_edge)
    half_h = max(max(o.body_length, (len(o.pins) // 2) * o.pitch) / 2 for o in (ref, cand))
    m = 1.2
    x0, w = -half_w - m, 2 * (half_w + m)
    y0, h = -half_h - m - 2.4, 2 * (half_h + m) + 2.4 + 1.6
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.3f} {y0:.3f} {w:.3f} {h:.3f}"'
        + (f' width="{w * 40:.0f}" height="{h * 40:.0f}"' if standalone else ' class="overlay-svg"')
        + ' role="img" aria-label="Package overlay">',
        f"<style>{STYLE}</style>",
        f'<rect class="paper" x="{x0:.3f}" y="{y0:.3f}" width="{w:.3f}" height="{h:.3f}"/>',
        f'<line class="axis" x1="{x0:.3f}" y1="0" x2="{x0 + w:.3f}" y2="0"/>',
        f'<line class="axis" x1="0" y1="{y0:.3f}" x2="0" y2="{y0 + h:.3f}"/>',
        _layer(ref, "ref", numbers=True),
        _layer(cand, "cand", numbers=False),
    ]
    top = -half_h - 0.5
    out.append(_hdim(-ref.span / 2, ref.span / 2, top - 0.9, f"span {ref.span} / {cand.span}"))
    out.append(_hdim(-ref.body_width / 2, ref.body_width / 2, top - 0.25, f"body {ref.body_width} / {cand.body_width}"))
    if ref.land:
        lp = ref.land
        out.append(_hdim(-lp.inner_edge, lp.inner_edge, half_h + 0.75, f"pad gap {lp.row_spacing - lp.pad_length:.2f}"))
    ly, lx = y0 + 0.55, x0 + 0.3
    for i, (o, cls, role) in enumerate(((ref, "ref", "reference"), (cand, "cand", "candidate"))):
        out.append(
            f'<g class="legend {cls}">{_rect(lx, ly - 0.3 + 0.6 * i, lx + 0.5, ly + 0.6 * i, "lead")}'
            + _text(lx + 0.65, ly + 0.6 * i, f"{o.label} ({role})", "legend")
            + "</g>"
        )
    pads = ref.land.name if ref.land else "none published"
    out.append(_text(lx, y0 + h - 0.75, "Top view, mm. Leads at nominal b and L.", "dimtext"))
    out.append(_text(lx, y0 + h - 0.3, f"Reference pads: {pads}", "dimtext"))
    out.append("</svg>")
    return "".join(out)
