"""Package overlay: outline, leads and PCB land pattern of two packages drawn on top of each other.

Lead and land pattern data come from data/mechanical.yaml (read from the datasheets).
The checks place the candidate's leads on the reference's recommended pads: the board
was designed for the reference part, so that is the question a pre-mechanical review asks.
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

from app import yamlio

MECH_FILE = Path(__file__).resolve().parents[2] / "data" / "mechanical.yaml"


@dataclass(frozen=True)
class LandPattern:
    name: str
    pad_length: float  # along the lead
    pad_width: float  # across the lead
    row_spacing: float  # pad centre to pad centre across the body
    source: str = ""
    note: str = ""
    row_spacing_y: float | None = None  # top/bottom rows of a 4-sided package, if different

    @property
    def inner_edge(self) -> float:  # distance from the package centre line
        return (self.row_spacing - self.pad_length) / 2

    @property
    def outer_edge(self) -> float:
        return (self.row_spacing + self.pad_length) / 2

    def edges(self, vertical: bool) -> tuple[float, float]:
        """Inner and outer pad edge for the left/right rows, or the top/bottom rows."""
        spacing = (self.row_spacing_y or self.row_spacing) if vertical else self.row_spacing
        return (spacing - self.pad_length) / 2, (spacing + self.pad_length) / 2


@dataclass(frozen=True)
class Mechanical:
    lead_width: tuple[float, float] | None  # None: not given in the datasheet
    lead_length: tuple[float, float] | None
    source: str = ""
    note: str = ""
    land_patterns: tuple[LandPattern, ...] = ()
    sides: int = 2  # 2 = dual row (SOIC, DFN), 4 = quad (QFN, MLP)


@lru_cache
def load_mechanical(path: Path = MECH_FILE) -> dict[str, Mechanical]:
    """Package code -> lead and land pattern data (data/mechanical.yaml plus generated
    data/mechanical_*.yaml files written by the importers)."""
    out = {}
    files = [path, *sorted(path.parent.glob("mechanical_*.yaml"))] if path == MECH_FILE else [path]
    tree = {}
    for file in files:
        for maker, packages in (yamlio.load(file.read_text()) or {}).items():
            tree.setdefault(maker, {}).update(packages)
    for packages in tree.values():
        for code, m in packages.items():
            lps = tuple(
                LandPattern(
                    name=lp["name"],
                    pad_length=lp["pad_length_mm"],
                    pad_width=lp["pad_width_mm"],
                    row_spacing=lp["row_spacing_mm"],
                    source=lp.get("source", ""),
                    note=lp.get("note", ""),
                    row_spacing_y=lp.get("row_spacing_y_mm"),
                )
                for lp in m.get("land_patterns", [])
            )
            out[code] = Mechanical(
                lead_width=tuple(m["lead_width_mm"]) if m.get("lead_width_mm") else None,
                lead_length=tuple(m["lead_length_mm"]) if m.get("lead_length_mm") else None,
                source=m.get("source", ""),
                note=m.get("note", ""),
                land_patterns=lps,
                sides=int(m.get("sides") or 2),
            )
    return out


def mid(r: tuple[float, float]) -> float:
    return round((r[0] + r[1]) / 2, 3)


@dataclass
class Outline:
    """One package, centred on the origin, pin 1 top left. Dual-row packages have pins on the
    left and right; quad packages also on the bottom and top."""

    code: str
    label: str
    pitch: float
    body_length: float  # along the pin rows (vertical)
    body_width: float  # across the body (horizontal)
    span: float  # lead tip to lead tip
    height: float | None
    # (pin number, position along its side, side): -1 left, +1 right, +2 bottom, -2 top
    pins: list[tuple[int, float, int]]
    mech: Mechanical | None
    land: LandPattern | None

    @property
    def no_lead(self) -> bool:  # DFN / SON: terminals end at the body edge
        return self.span - self.body_width < 0.1

    @property
    def quad(self) -> bool:
        return any(abs(side) == 2 for _, _, side in self.pins)

    def half(self, side: int) -> tuple[float, float]:
        """Body edge and lead tip distance from the centre for pins on ``side``."""
        if abs(side) == 1:
            return self.body_width / 2, (self.body_width if self.no_lead else self.span) / 2
        return self.body_length / 2, self.body_length / 2  # quad packages here are no-lead

    def foot(self, length: float) -> tuple[float, float]:
        """x range (from the centre line) of the lead's foot that sits on the board."""
        tip = self.span / 2
        return tip - length, tip


def outline(package, label: str = "", land_index: int = 0) -> Outline:
    mech = load_mechanical().get(package.code)
    positions = package.positions_total or package.pin_count
    sides = mech.sides if mech else 2
    n = positions // sides
    pitch = package.pitch_mm
    numbers = package.pin_positions or list(range(1, package.pin_count + 1))
    pins = []
    for number, pos in zip(range(1, package.pin_count + 1), numbers, strict=False):
        k, i = divmod(pos - 1, n)  # side index counter-clockwise from the left, place on that side
        if sides == 2:
            k = 0 if k == 0 else 2  # dual row: left side then right side
        t = (i - (n - 1) / 2) * pitch
        if k == 0:  # left, top to bottom
            pins.append((number, t, -1))
        elif k == 1:  # bottom, left to right
            pins.append((number, t, 2))
        elif k == 2:  # right, bottom to top
            pins.append((number, -t, 1))
        else:  # top, right to left
            pins.append((number, -t, -2))
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
    if land is None or cm is None or not (cm.lead_width and cm.lead_length):
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


def _style(k: float) -> str:
    """STYLE with stroke widths, dashes and font sizes scaled by k (drawings are in mm)."""

    def scaled(m: re.Match) -> str:
        values = " ".join(f"{float(v) * k:.4g}" for v in m.group(2).split())
        return f"{m.group(1)}{values}{m.group(3) or ''};"

    return re.sub(r"(stroke-width: |stroke-dasharray: |font-size: )([\d. ]+?)(px)?;", scaled, STYLE)


def _rect(x0, y0, x1, y1, cls, title=""):
    x, y = min(x0, x1), min(y0, y1)
    t = f"<title>{escape(title)}</title>" if title else ""
    return (
        f'<rect class="{cls}" x="{x:.3f}" y="{y:.3f}" width="{abs(x1 - x0):.3f}" height="{abs(y1 - y0):.3f}">{t}</rect>'
    )


def _side_rect(side: int, r0: float, r1: float, t: float, w: float, cls: str, title: str = "") -> str:
    """Rectangle from r0 to r1 out from the centre on ``side``, centred at t along it, w wide."""
    sign = 1 if side > 0 else -1
    if abs(side) == 1:
        return _rect(sign * r0, t - w / 2, sign * r1, t + w / 2, cls, title)
    return _rect(t - w / 2, sign * r0, t + w / 2, sign * r1, cls, title)


def _layer(o: Outline, cls: str, numbers: bool, k: float = 1.0) -> str:
    parts = [f'<g class="{cls}">']
    bw, bl = o.body_width / 2, o.body_length / 2
    if o.land:
        lp = o.land
        for n, t, side in o.pins:
            r0, r1 = lp.edges(abs(side) == 2)
            title = f"{o.label} pad {n}: {lp.pad_length} x {lp.pad_width} mm"
            parts.append(_side_rect(side, r0, r1, t, lp.pad_width, "pad layer-pads", title))
    parts.append(_rect(-bw, -bl, bw, bl, "body layer-body", f"{o.label} body {o.body_width} x {o.body_length} mm"))
    for n, t, side in o.pins:
        edge, tip = o.half(side)
        if o.mech and o.mech.lead_width and o.mech.lead_length:
            b, length = mid(o.mech.lead_width), mid(o.mech.lead_length)
            r0 = edge - length if o.no_lead else edge
            parts.append(_side_rect(side, r0, tip, t, b, "lead layer-leads", f"{o.label} pin {n}"))
            if not o.no_lead:  # foot in contact with the board
                parts.append(_side_rect(side, tip - length, tip, t, b, "lead layer-leads"))
        else:  # no lead data: mark the lead tips only
            parts.append(_side_rect(side, tip - 0.05, tip, t, 0.2, "lead layer-leads"))
    # pin 1 marker inside the body corner
    _, t1, _ = o.pins[0]
    r = min(0.25, min(o.body_width, o.body_length) / (25 if o.quad else 12))
    cy = -bl + 2.2 * r if o.quad else t1
    parts.append(
        f'<circle class="pin1" cx="{-bw + 2.2 * r:.3f}" cy="{cy:.3f}" r="{r:.3f}"><title>pin 1</title></circle>'
    )
    if numbers:
        for n, t, side in o.pins:
            _, tip = o.half(side)
            out = max(tip, o.land.edges(abs(side) == 2)[1] if o.land else 0) + 0.3 * k
            sign = 1 if side > 0 else -1
            x, y = (sign * out, t + 0.11 * k) if abs(side) == 1 else (t, sign * out + 0.11 * k)
            parts.append(f'<text class="num" x="{x:.3f}" y="{y:.3f}" text-anchor="middle">{n}</text>')
    parts.append("</g>")
    return "".join(parts)


def _hdim(x0: float, x1: float, y: float, label: str, k: float = 1.0) -> str:
    t = 0.12 * k
    return (
        f'<g class="layer-dims"><line class="dim" x1="{x0:.3f}" y1="{y:.3f}" x2="{x1:.3f}" y2="{y:.3f}"/>'
        f'<line class="dim" x1="{x0:.3f}" y1="{y - t:.3f}" x2="{x0:.3f}" y2="{y + t:.3f}"/>'
        f'<line class="dim" x1="{x1:.3f}" y1="{y - t:.3f}" x2="{x1:.3f}" y2="{y + t:.3f}"/>'
        + _text((x0 + x1) / 2, y - t, label, "dimtext", anchor="middle")
        + "</g>"
    )


def _text(x: float, y: float, label: str, cls: str, anchor: str = "start") -> str:
    return f'<text class="{cls}" x="{x:.3f}" y="{y:.3f}" text-anchor="{anchor}">{escape(label)}</text>'


def svg(ov: Overlay, standalone: bool = False) -> str:
    ref, cand = ov.ref, ov.cand
    half_w = max(o.span / 2 for o in (ref, cand))
    half_h = max(max(o.body_length, (len(o.pins) // 2) * o.pitch) / 2 for o in (ref, cand))
    for o in (ref, cand):
        if o.land:
            half_w = max(half_w, o.land.outer_edge)
            if o.quad:
                half_h = max(half_h, o.land.edges(True)[1])
    k = min(max(max(half_w, half_h) / 5.5, 0.22), 1.5)  # text and spacing scale with the package
    if ref.quad or cand.quad:
        half_h += 0.4 * k  # room for the pin numbers above and below
    m = 1.2 * k
    x0, w = -half_w - m, 2 * (half_w + m)
    y0, h = -half_h - m - 2.4 * k, 2 * (half_h + m) + 4.0 * k
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0:.3f} {y0:.3f} {w:.3f} {h:.3f}"'
        + (f' width="{w * 40:.0f}" height="{h * 40:.0f}"' if standalone else ' class="overlay-svg"')
        + ' role="img" aria-label="Package overlay">',
        f"<style>{_style(k)}</style>",
        f'<rect class="paper" x="{x0:.3f}" y="{y0:.3f}" width="{w:.3f}" height="{h:.3f}"/>',
        f'<line class="axis" x1="{x0:.3f}" y1="0" x2="{x0 + w:.3f}" y2="0"/>',
        f'<line class="axis" x1="0" y1="{y0:.3f}" x2="0" y2="{y0 + h:.3f}"/>',
        _layer(ref, "ref", numbers=True, k=k),
        _layer(cand, "cand", numbers=False, k=k),
    ]
    top = -half_h - 0.5 * k
    out.append(_hdim(-ref.span / 2, ref.span / 2, top - 0.9 * k, f"span {ref.span} / {cand.span}", k))
    body = f"body {ref.body_width} / {cand.body_width}"
    out.append(_hdim(-ref.body_width / 2, ref.body_width / 2, top - 0.25 * k, body, k))
    if ref.land:
        lp = ref.land
        gap = f"pad gap {lp.row_spacing - lp.pad_length:.2f}"
        out.append(_hdim(-lp.inner_edge, lp.inner_edge, half_h + 0.75 * k, gap, k))
    ly, lx = y0 + 0.55 * k, x0 + 0.3 * k
    for i, (o, cls, role) in enumerate(((ref, "ref", "reference"), (cand, "cand", "candidate"))):
        out.append(
            f'<g class="legend {cls}">{_rect(lx, ly + (0.6 * i - 0.3) * k, lx + 0.5 * k, ly + 0.6 * i * k, "lead")}'
            + _text(lx + 0.65 * k, ly + 0.6 * i * k, f"{o.label} ({role})", "legend")
            + "</g>"
        )
    pads = ref.land.name if ref.land else "none published"
    out.append(_text(lx, y0 + h - 0.75 * k, "Top view, mm. Leads at nominal b and L.", "dimtext"))
    out.append(_text(lx, y0 + h - 0.3 * k, f"Reference pads: {pads}", "dimtext"))
    out.append("</svg>")
    return "".join(out)
