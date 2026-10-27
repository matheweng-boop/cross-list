"""Block diagrams on the Shareable system documents (owner, 27 Oct 2026: "with Block Diagrams"): one layout of a library
diagram (groups, blocks, the main links) drawn three ways from the same shapes, so the screen, the A4 PDF and the
PowerPoint show the same picture:

- svg(layout): inline SVG for the page on screen;
- drawing(layout, width): a ReportLab vector drawing for the PDF (no image conversion, no extra library);
- to_slide(slide, layout, ...): native PowerPoint shapes (editable boxes, text and arrows).

layout(groups, links, marks) places the groups on their (col, row) grid, wraps the labels, sizes each row to its
tallest group and routes each link as a straight arrow between the two group boxes. Blocks are marked "core" (solid
highlight), "peripheral" (outline) or plain, by "<group id>.<function>" (the owner, 27 Oct 2026: core vs
peripherals)."""

import math
import textwrap
from xml.sax.saxutils import escape

W = 1000  # layout units across; every painter scales to its own width
GAP_X, GAP_Y, PAD = 46, 30, 10
TITLE_FS, BLOCK_FS, LEGEND_FS, LH = 16, 14, 13, 1.22
BLOCK_GAP = 6
INK, MUTED, ACCENT, LINE = "#1B1F27", "#5B6270", "#0B6B74", "#C9CFD9"
GROUP_FILL, WHITE, LINK = "#F6F8FA", "#FFFFFF", "#8A93A3"
STYLE = {  # fill, stroke, stroke width, text colour, bold
    "core": (ACCENT, ACCENT, 1.5, WHITE, True),
    "peripheral": (WHITE, ACCENT, 2.6, ACCENT, True),
    "": (WHITE, LINE, 1.0, MUTED, False),
}
LEGEND = (("core", "Core: Skyworks / Qorvo part"), ("peripheral", "Peripheral: Skyworks / Qorvo part"),
          ("", "Other blocks"))  # fmt: skip


def _wrap(text: str, width: float, size: float, bold: bool = False) -> list[str]:
    per = max(6, int(width / (size * (0.56 if bold else 0.51))))
    return textwrap.wrap(" ".join(str(text).split()), per, break_on_hyphens=False) or [""]


def layout(groups: list[dict], links: list[tuple[str, str]], title: str = "") -> dict:
    """groups: [{id, label, col, row, blocks: [{label, mark}]}] -> {"w", "h", "shapes": [...], "title", "labels"}.
    Shapes: rect (x, y, w, h, fill, stroke, sw, r), text (x, y baseline, s, size, bold, color, anchor) and arrow
    (x1, y1, x2, y2). Empty rows and columns are closed up."""
    cols = sorted({g["col"] for g in groups})
    rows = sorted({g["row"] for g in groups})
    ci, ri = {c: i for i, c in enumerate(cols)}, {r: i for i, r in enumerate(rows)}
    ncol = max(1, len(cols))
    cw = (W - GAP_X * (ncol - 1)) / ncol
    inner = cw - 2 * PAD
    sized = []
    for g in groups:
        tl = _wrap(g["label"], inner, TITLE_FS, bold=True)
        bl = [(b, _wrap(b["label"], inner - 12, BLOCK_FS, bold=bool(b.get("mark")))) for b in g["blocks"]]
        h = PAD + len(tl) * TITLE_FS * LH + 4 + sum(len(ls) * BLOCK_FS * LH + 9 + BLOCK_GAP for _, ls in bl) + PAD - 2
        sized.append((g, tl, bl, h))
    row_h = [max([h for g, _, _, h in sized if ri[g["row"]] == i] or [0]) for i in range(len(rows))]
    row_y = [sum(row_h[:i]) + GAP_Y * i for i in range(len(rows))]
    boxes, shapes, labels = {}, [], []
    for g, tl, bl, _ in sized:
        x, y = ci[g["col"]] * (cw + GAP_X), row_y[ri[g["row"]]]
        h = row_h[ri[g["row"]]]
        boxes[g["id"]] = (x, y, cw, h)
        shapes.append({"t": "rect", "x": x, "y": y, "w": cw, "h": h, "fill": GROUP_FILL, "stroke": LINE, "sw": 1,
                       "r": 6})  # fmt: skip
        ty = y + PAD + TITLE_FS
        for line in tl:
            shapes.append({"t": "text", "x": x + PAD, "y": ty, "s": line, "size": TITLE_FS, "bold": True,
                           "color": INK, "anchor": "start"})  # fmt: skip
            ty += TITLE_FS * LH
        by = ty - TITLE_FS * LH + TITLE_FS * 0.35 + 4
        labels.append(g["label"])
        for b, ls in bl:
            fill, stroke, sw, color, bold = STYLE[b.get("mark") or ""]
            bh = len(ls) * BLOCK_FS * LH + 9
            shapes.append({"t": "rect", "x": x + PAD, "y": by, "w": inner, "h": bh, "fill": fill, "stroke": stroke,
                           "sw": sw, "r": 4, "mark": b.get("mark") or ""})  # fmt: skip
            ly = by + 4.5 + BLOCK_FS * 0.95
            for line in ls:
                shapes.append({"t": "text", "x": x + PAD + inner / 2, "y": ly, "s": line, "size": BLOCK_FS,
                               "bold": bold, "color": color, "anchor": "middle"})  # fmt: skip
                ly += BLOCK_FS * LH
            labels.append(b["label"])
            by += bh + BLOCK_GAP
    for a, b in links:
        if a in boxes and b in boxes and a != b:
            shapes.append({"t": "arrow", **_connect(boxes[a], boxes[b])})
    h = (row_y[-1] + row_h[-1]) if rows else 0
    ly = h + 22
    lx = 0.0
    for mark, text in LEGEND:
        fill, stroke, sw, color, bold = STYLE[mark]
        shapes.append({"t": "rect", "x": lx, "y": ly, "w": 30, "h": 16, "fill": fill, "stroke": stroke, "sw": sw,
                       "r": 3, "mark": mark})  # fmt: skip
        shapes.append({"t": "text", "x": lx + 38, "y": ly + 13, "s": text, "size": LEGEND_FS, "bold": False,
                       "color": MUTED, "anchor": "start"})  # fmt: skip
        lx += 38 + len(text) * LEGEND_FS * 0.5 + 34
    return {"w": W, "h": ly + 22, "shapes": shapes, "title": title, "labels": labels}


def _edge(box: tuple, dx: float, dy: float) -> tuple[float, float]:
    """Where a ray from the box centre in direction (dx, dy) leaves the box."""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    tx = (w / 2) / abs(dx) if dx else math.inf
    ty = (h / 2) / abs(dy) if dy else math.inf
    t = min(tx, ty)
    return cx + dx * t, cy + dy * t


def _connect(a: tuple, b: tuple) -> dict:
    """A straight arrow from box a to box b; side by side boxes get a level arrow through the gap between them."""
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    top, bottom = max(ay, by), min(ay + ah, by + bh)
    if bottom - top > 20 and (ax + aw <= bx or bx + bw <= ax):  # overlapping rows: horizontal
        y = (top + bottom) / 2
        x1, x2 = (ax + aw, bx) if ax < bx else (ax, bx + bw)
        return {"x1": x1, "y1": y, "x2": x2, "y2": y}
    left, right = max(ax, bx), min(ax + aw, bx + bw)
    if right - left > 20:  # one above the other: vertical
        x = (left + right) / 2
        y1, y2 = (ay + ah, by) if ay < by else (ay, by + bh)
        return {"x1": x, "y1": y1, "x2": x, "y2": y2}
    dx, dy = (bx + bw / 2) - (ax + aw / 2), (by + bh / 2) - (ay + ah / 2)
    x1, y1 = _edge(a, dx, dy)
    x2, y2 = _edge(b, -dx, -dy)
    return {"x1": x1, "y1": y1, "x2": x2, "y2": y2}


def _head(s: dict, size: float = 9.0) -> list[tuple[float, float]]:
    ang = math.atan2(s["y2"] - s["y1"], s["x2"] - s["x1"])
    x, y = s["x2"], s["y2"]
    return [(x, y), (x - size * math.cos(ang - 0.45), y - size * math.sin(ang - 0.45)),
            (x - size * math.cos(ang + 0.45), y - size * math.sin(ang + 0.45))]  # fmt: skip


# ---- screen ---------------------------------------------------------------------------------------------------------
def svg(lay: dict) -> str:
    out = [f'<svg class="sd-diagram" viewBox="0 0 {lay["w"]:.0f} {lay["h"]:.0f}" role="img" '
           f'aria-label="{escape(lay["title"])}" xmlns="http://www.w3.org/2000/svg" '
           f'font-family="Helvetica, Arial, sans-serif">']  # fmt: skip
    for s in lay["shapes"]:
        if s["t"] == "rect":
            out.append(f'<rect x="{s["x"]:.1f}" y="{s["y"]:.1f}" width="{s["w"]:.1f}" height="{s["h"]:.1f}" '
                       f'rx="{s["r"]}" fill="{s["fill"]}" stroke="{s["stroke"]}" stroke-width="{s["sw"]}"/>')
        elif s["t"] == "text":
            bold = ' font-weight="bold"' if s["bold"] else ""
            out.append(f'<text x="{s["x"]:.1f}" y="{s["y"]:.1f}" font-size="{s["size"]}" fill="{s["color"]}" '
                       f'text-anchor="{s["anchor"]}"{bold}>{escape(s["s"])}</text>')
        elif s["t"] == "arrow":
            pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in _head(s))
            out.append(f'<line x1="{s["x1"]:.1f}" y1="{s["y1"]:.1f}" x2="{s["x2"]:.1f}" y2="{s["y2"]:.1f}" '
                       f'stroke="{LINK}" stroke-width="1.8"/><polygon points="{pts}" fill="{LINK}"/>')
    out.append("</svg>")
    return "".join(out)


# ---- PDF (ReportLab vector drawing) ---------------------------------------------------------------------------------
def drawing(lay: dict, width: float):
    from reportlab.graphics.shapes import Drawing, Line, Polygon, Rect, String
    from reportlab.lib import colors

    k = width / lay["w"]
    hh = lay["h"]
    d = Drawing(width, hh * k)

    def c(x):
        return colors.HexColor(x)

    for s in lay["shapes"]:
        if s["t"] == "rect":
            d.add(Rect(s["x"] * k, (hh - s["y"] - s["h"]) * k, s["w"] * k, s["h"] * k, rx=s["r"] * k, ry=s["r"] * k,
                       fillColor=c(s["fill"]), strokeColor=c(s["stroke"]), strokeWidth=s["sw"] * k))  # fmt: skip
        elif s["t"] == "text":
            d.add(String(s["x"] * k, (hh - s["y"]) * k, s["s"].encode("cp1252", "replace").decode("cp1252"),
                         fontName="Helvetica-Bold" if s["bold"] else "Helvetica", fontSize=s["size"] * k,
                         fillColor=c(s["color"]), textAnchor=s["anchor"]))  # fmt: skip
        elif s["t"] == "arrow":
            d.add(Line(s["x1"] * k, (hh - s["y1"]) * k, s["x2"] * k, (hh - s["y2"]) * k, strokeColor=c(LINK),
                       strokeWidth=1.8 * k))  # fmt: skip
            pts = [v for x, y in _head(s) for v in (x * k, (hh - y) * k)]
            d.add(Polygon(pts, fillColor=c(LINK), strokeColor=c(LINK), strokeWidth=0))
    return d


# ---- PowerPoint (native shapes) -------------------------------------------------------------------------------------
def to_slide(slide, lay: dict, left: int, top: int, width: int, height: int) -> None:
    """Draws the diagram into the box (EMU), centred and scaled to fit."""
    from pptx.dml.color import RGBColor
    from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.oxml.ns import qn
    from pptx.util import Emu, Pt

    k = min(width / lay["w"], height / lay["h"])
    ox = left + (width - lay["w"] * k) / 2
    oy = top + (height - lay["h"] * k) / 2
    pt = k / 12700  # points per layout unit

    def rgb(x):
        return RGBColor.from_string(x.lstrip("#"))

    def E(v):
        return Emu(int(v))

    for s in lay["shapes"]:
        if s["t"] == "rect":
            sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, E(ox + s["x"] * k), E(oy + s["y"] * k),
                                        E(s["w"] * k), E(s["h"] * k))  # fmt: skip
            sh.adjustments[0] = min(0.5, s["r"] / max(1.0, min(s["w"], s["h"])))
            sh.fill.solid()
            sh.fill.fore_color.rgb = rgb(s["fill"])
            sh.line.color.rgb = rgb(s["stroke"])
            sh.line.width = Pt(max(0.5, s["sw"] * pt))
            sh.shadow.inherit = False
        elif s["t"] == "text":
            size = s["size"] * pt
            w = (W / 2) * k if s["anchor"] == "middle" else len(s["s"]) * s["size"] * 0.62 * k + 12700 * 6
            x = ox + s["x"] * k - (w / 2 if s["anchor"] == "middle" else 0)
            y = oy + (s["y"] - s["size"] * 0.95) * k
            tb = slide.shapes.add_textbox(E(x), E(y), E(w), E(s["size"] * 1.25 * k))
            tf = tb.text_frame
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
            tf.word_wrap = False
            tf.vertical_anchor = MSO_ANCHOR.TOP
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.CENTER if s["anchor"] == "middle" else PP_ALIGN.LEFT
            r = p.add_run()
            r.text = s["s"]
            r.font.size = Pt(size)
            r.font.bold = s["bold"]
            r.font.name = "Calibri"
            r.font.color.rgb = rgb(s["color"])
        elif s["t"] == "arrow":
            y2 = s["y2"] + (0.01 if abs(s["y2"] - s["y1"]) < 0.01 else 0)  # some viewers drop a zero-height line
            x2 = s["x2"] + (0.01 if abs(s["x2"] - s["x1"]) < 0.01 else 0)
            cx = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, E(ox + s["x1"] * k), E(oy + s["y1"] * k),
                                            E(ox + x2 * k), E(oy + y2 * k))  # fmt: skip
            cx.line.color.rgb = rgb(LINK)
            cx.line.width = Pt(max(0.75, 1.8 * pt))
            ln = cx.line._get_or_add_ln()
            tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
            ln.append(tail)
