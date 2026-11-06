"""Animated PowerPoint template (owner, 6 Nov 2026): "PowerPoint templates that include morphing and different types
of animations, like zoom-ins, that I can just fill with content", downloadable from the site, with colour schemes
to change and moving diagrams (a flow chart that moves, a timeline that builds up), with options.

Writes one 16:9 template and three ready colour versions to app/web/static/downloads/:
    uv run python scripts/build_pptx_template.py           # write the four files
    uv run python scripts/build_pptx_template.py --check   # rebuild in memory, validate, compare with the files

Design rules:
- every shape, line and text uses theme colours (bg1/tx1/bg2/tx2, accent1-6) and theme fonts (+mj-lt / +mn-lt),
  never a fixed RGB, so Design > Variants > Colors recolours the whole deck; the colour versions differ only in the
  theme's colour block;
- Morph: the second slide of a pair carries the Morph transition (p159:morph inside mc:AlternateContent, with a
  Fade fallback for older viewers); objects that must travel share a name starting with "!!" on both slides;
- animations are PowerPoint's standard presets (Fade, Fly In, Float In, Wipe, Zoom, Spinner; Grow/Shrink, Pulse,
  Spin), written as p:timing XML (ECMA-376 Part 1, 19.5; [MS-PPTX] for p14/p159), on click or after previous;
- the build is deterministic (fixed dates, fixed zip times), so a test can rebuild it and compare.
"""


import io
import math
import sys
from pathlib import Path

from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Pt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.services.pptx_anim import (  # noqa: E402
    A1,
    A2,
    A3,
    BG1,
    BG2,
    TX1,
    TX2,
    W_IN,
    Deck,
    Effect,
    I,
    T,
    _color,
    arrow,
    box,
    check,
    finish,
    label,
    new_presentation,
    see_through,
    shape,
    text,
    title,
    title_bar,
)
from app.services.pptx_template import FILES, PALETTES  # noqa: E402

OUT_DIR = ROOT / "app" / "web" / "static" / "downloads"


def picture_png() -> bytes:
    """A neutral grey stand-in picture (16:9) with one detail area, for the zoom slides."""
    from PIL import Image, ImageDraw, ImageFont

    w, h = 1600, 900
    im = Image.new("L", (w, h), 232)
    d = ImageDraw.Draw(im)
    d.polygon([(0, 700), (300, 420), (560, 640), (820, 360), (1180, 700), (1600, 520), (1600, 900), (0, 900)],
              fill=196)
    d.ellipse((180, 120, 340, 280), fill=210)
    for i in range(6):
        d.rounded_rectangle((90 + i * 140, 560 + (i % 2) * 40, 190 + i * 140, 640 + (i % 2) * 40), 12, fill=170)
    # the detail area: fraction 0.60-0.90 across, 0.55-0.85 down (see zoom slides)
    x0, y0, x1, y1 = 960, 495, 1440, 765
    d.rounded_rectangle((x0, y0, x1, y1), 18, fill=245, outline=120, width=6)
    for r in range(4):
        for c in range(7):
            cx, cy = x0 + 50 + c * 63, y0 + 50 + r * 57
            d.ellipse((cx - 16, cy - 16, cx + 16, cy + 16), fill=150 if (r + c) % 3 else 90)
    font = ImageFont.load_default(size=64)
    d.text((800, 90), "Your picture here", fill=110, font=font, anchor="mm")
    font2 = ImageFont.load_default(size=30)
    d.text(((x0 + x1) // 2, y0 - 26), "Detail", fill=90, font=font2, anchor="mm")
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ---- slides


def s_title(dk: Deck):
    s, q = dk.new(0, notes="Title slide. The bar wipes in, the title zooms in and the subtitle floats in, all "
                           "automatically. Change timing in Animations > Animation Pane.")
    t = s.shapes.title
    t.name = "Title"
    t.left, t.top, t.width, t.height = I(0.9), I(2.3), I(7.9), I(1.7)
    t.text_frame.text = "Your presentation title"
    p = t.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    f = p.runs[0].font
    f.size, f.bold, f.name = Pt(48), True, "+mj-lt"
    _color(f.color, TX1)
    t.text_frame.vertical_anchor = MSO_ANCHOR.BOTTOM
    sub = s.placeholders[1]
    sub.name = "Subtitle"
    sub.left, sub.top, sub.width, sub.height = I(0.9), I(4.15), I(7.9), I(1.0)
    sub.text_frame.text = "Your subtitle · Your name · Date"
    p = sub.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    f = p.runs[0].font
    f.size, f.name = Pt(22), "+mn-lt"
    _color(f.color, TX2)
    bar = shape(s, "Accent bar", MSO_SHAPE.RECTANGLE, 0.9, 2.05, 1.6, 0.1, fill=A1)
    c1 = shape(s, "Circle large", MSO_SHAPE.OVAL, 9.2, 1.3, 3.5, 3.5, fill=A1)
    c2 = shape(s, "Circle small", MSO_SHAPE.OVAL, 11.0, 4.2, 1.8, 1.8, fill=A2)
    c3 = shape(s, "Ring", MSO_SHAPE.OVAL, 8.7, 4.4, 1.5, 1.5, line=A3, line_w=6)
    q.after(Effect("wipe", bar, 500, sub="left"))
    q.after(Effect("zoom", t, 700)).with_(Effect("zoom", c1, 700)).with_(Effect("zoom", c2, 600, delay=200))
    q.with_(Effect("spinner", c3, 700, delay=300))
    q.after(Effect("float", sub, 600))


AGENDA = ["Section one", "Section two", "Section three", "Section four"]


def s_agenda(dk: Deck, active: int, build: bool):
    morph = not build
    s, q = dk.new(5, morph=morph, ms=1250, notes=(
        "Agenda. The highlighted row ('!!Panel') and the numbers zoom into the next slide with Morph. To add a "
        "section: duplicate this slide and the section slide after it, move the panel to the next row, and keep the "
        "names that start with !! (Home > Arrange > Selection Pane)."))
    title(s, "Agenda")
    title_bar(s)
    y0, step = 1.75, 1.3
    panel = shape(s, "!!Panel", MSO_SHAPE.ROUNDED_RECTANGLE, 0.7, y0 - 0.15 + active * step, 9.6, 1.2, fill=BG2)
    panel.adjustments[0] = 0.18
    for i, words in enumerate(AGENDA):
        y = y0 + i * step
        done = i < active
        num = box(s, f"!!Num{i + 1}", 1.0, y, 0.9, 0.9, [f"0{i + 1}"], kind=MSO_SHAPE.OVAL,
                  fill=A1, fill_b=0.6 if done else 0.0, size=20, bold=True, color=TX1 if done else BG1,
                  align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, heading=True, margin=0)
        lab = label(s, f"!!Label{i + 1}", 2.2, y, 7.6, 0.9, [words], size=26, color=TX2 if done else TX1,
                    anchor=MSO_ANCHOR.MIDDLE, heading=True)
        if build:
            q.after(Effect("zoom", num, 400))
            q.with_(Effect("fly", lab, 500, sub="left"))


def s_section(dk: Deck, i: int):
    s, q = dk.new(6, morph=True, ms=1250, notes=(
        "Section divider. The number, label and highlight panel come from the agenda slide before it (Morph). The "
        "intro line floats in after the move."))
    shape(s, "!!Panel", MSO_SHAPE.ROUNDED_RECTANGLE, -0.3, -0.3, 5.6, 8.1, fill=A1).adjustments[0] = 0.04
    box(s, f"!!Num{i + 1}", 1.0, 1.95, 3.2, 3.2, [f"0{i + 1}"], kind=MSO_SHAPE.OVAL, fill=BG1, size=96, bold=True,
        color=A1, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, heading=True, margin=0)
    label(s, f"!!Label{i + 1}", 6.0, 2.3, 6.8, 1.3, [AGENDA[i]], size=48, anchor=MSO_ANCHOR.BOTTOM, heading=True,
          bold=True)
    intro = label(s, "Intro", 6.0, 3.75, 6.6, 1.6, ["One sentence on what this section covers."], size=22,
                  color=TX2)
    q.after(Effect("float", intro, 600))


def s_bullets(dk: Deck):
    s, q = dk.new(5, notes=(
        "Bullet build. Each point floats in on its own click (fade and rise); the key message zooms in last. "
        "Add points with Enter: new paragraphs get the same animation in Animations > Animation Pane > Effect "
        "Options > Text Animation > By paragraph."))
    title(s, "Your key points")
    title_bar(s)
    pts = ["Point one: a short sentence", "Point two: a short sentence", "Point three: a short sentence",
           "Point four: a short sentence"]
    body = label(s, "Points", 0.9, 1.75, 7.4, 4.8, pts, size=26, bullets=True, spacing=18)
    card = box(s, "Key message", 8.8, 1.75, 3.9, 4.6, [("Key message", 16, True, A1),
                                                        ("One line that sums it up.", 26, True, TX1)],
               fill=BG2, anchor=MSO_ANCHOR.MIDDLE, margin=0.35, spacing=8)
    for i in range(len(pts)):
        q.click(Effect("float", body, 600, para=i))
    q.click(Effect("zoom", card, 500))


ZOOM = (0.60, 0.55, 0.30)  # the detail: left, top, size as fractions of the picture (same ratio as the picture)
PIC = (0.9, 1.6, 9.0, 5.0625)  # where the picture sits; the zoomed detail fills the same box


def s_zoom(dk: Deck, zoomed: bool):
    s, q = dk.new(5, morph=zoomed, ms=1500, notes=(
        "Picture zoom. Replace the picture on BOTH slides (right-click > Change Picture). On the zoomed slide, "
        "use Picture Format > Crop to choose the detail again. Keep the name !!Picture on both."
        if not zoomed else
        "Zoomed slide: Morph enlarges the picture to the detail (the same picture, cropped). After changing the "
        "picture, crop it again (Picture Format > Crop) so the detail fills the frame."))
    title(s, "Your picture" if not zoomed else "Your detail")
    title_bar(s)
    x, y, w, h = PIC
    fx, fy, fs = ZOOM
    pic = s.shapes.add_picture(io.BytesIO(dk.picture), I(x), I(y), I(w), I(h))
    pic.name = "!!Picture"
    if zoomed:
        pic.crop_left, pic.crop_top = fx, fy
        pic.crop_right, pic.crop_bottom = 1 - fx - fs, 1 - fy - fs
        frame = (x, y, w, h)
    else:
        frame = (x + fx * w, y + fy * h, fs * w, fs * h)
    fr = shape(s, "!!Focus", MSO_SHAPE.RECTANGLE, *frame, line=A2, line_w=4)
    label(s, "!!Caption", 10.2, 1.6, 2.6, 3.0, [
        ("Your caption", 20, True, TX1),
        ("Say what to look at." if not zoomed else "Say what the detail shows.", 16, False, TX2)], spacing=6)
    if not zoomed:
        q.click(Effect("zoom", fr, 500)).after(Effect("pulse", fr, 600))
    else:
        note = box(s, "Callout", 10.2, 4.2, 2.6, 1.6, [("Why it matters", 16, True, BG1)], fill=A1,
                   anchor=MSO_ANCHOR.MIDDLE, margin=0.2)
        q.click(Effect("zoom", note, 500))


FLOW = ["Step one", "Step two", "Decision?", "Result"]


def s_flow_build(dk: Deck):
    s, q = dk.new(5, notes=(
        "Flow chart that builds. Each click wipes in the next arrow, then the next box zooms in. The arrows are "
        "glued to the boxes: move a box and its arrows follow."))
    title(s, "How it works")
    title_bar(s)
    w, h, gap, y = 2.4, 1.3, 0.85, 2.7
    x0 = (W_IN - (4 * w + 3 * gap)) / 2
    nodes, notes = [], []
    kinds = [MSO_SHAPE.ROUNDED_RECTANGLE, MSO_SHAPE.RECTANGLE, MSO_SHAPE.DIAMOND, MSO_SHAPE.ROUNDED_RECTANGLE]
    for i, words in enumerate(FLOW):
        x = x0 + i * (w + gap)
        hh = 1.7 if kinds[i] == MSO_SHAPE.DIAMOND else h
        nodes.append(box(s, f"Box {i + 1}", x, y + (h - hh) / 2, w, hh, [words], kind=kinds[i],
                         fill=A1 if i in (0, 3) else BG2, line=None, size=18, bold=True,
                         color=BG1 if i in (0, 3) else TX1, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE))
        notes.append(label(s, f"Note {i + 1}", x, 4.75, w, 1.2, ["A short note"], size=15, color=TX2,
                           align=PP_ALIGN.CENTER))
    links = []
    for i in range(3):
        a, b = nodes[i], nodes[i + 1]
        links.append(arrow(s, f"Arrow {i + 1}", 0, 0, 1, 1, begin=(a, 3), end=(b, 1)))
    yes = label(s, "Yes label", x0 + 3 * w + 2 * gap, y - 0.45, gap, 0.4, ["Yes"], size=14, bold=True, color=A1,
                align=PP_ALIGN.CENTER)
    q.after(Effect("zoom", nodes[0], 500)).with_(Effect("fade", notes[0], 500))
    for i in range(3):
        q.click(Effect("wipe", links[i], 400, sub="left"))
        if i == 2:
            q.with_(Effect("fade", yes, 400))
        q.after(Effect("zoom", nodes[i + 1], 500)).with_(Effect("fade", notes[i + 1], 500))


def s_flow_morph(dk: Deck, active: int):
    s, q = dk.new(5, morph=active > 0, ms=1000, notes=(
        "Flow chart that moves (Morph, 4 slides). On each slide the active step is bigger and coloured; Morph "
        "grows it and shrinks the last one. Edit the step names on all four slides; keep the !! names."))
    title(s, "Your process")
    title_bar(s)
    big, small, gap, cy = (3.3, 2.0), (2.2, 1.2), 0.62, 3.3
    widths = [big[0] if i == active else small[0] for i in range(4)]
    x = (W_IN - sum(widths) - 3 * gap) / 2
    boxes = []
    for i in range(4):
        bw, bh = big if i == active else small
        done = i < active
        st = box(s, f"!!Step{i + 1}", x, cy - bh / 2, bw, bh, [f"Step {['one', 'two', 'three', 'four'][i]}"],
                 fill=A1 if i == active else BG2, fill_b=0.0, size=24 if i == active else 16, bold=True,
                 color=BG1 if i == active else (A1 if done else TX2), align=PP_ALIGN.CENTER,
                 anchor=MSO_ANCHOR.MIDDLE)
        boxes.append((x, bw, st))
        x += bw + gap
    for i in range(3):
        x1 = boxes[i][0] + boxes[i][1] + 0.08
        x2 = boxes[i + 1][0] - 0.08
        arrow(s, f"!!Link{i + 1}", x1, cy, x2, cy, color=A1 if i < active else TX2)
    ax, aw, act = boxes[active]
    label(s, "!!Detail", ax - 0.4, cy + big[1] / 2 + 0.3, aw + 0.8, 1.4, [f"What happens in step {active + 1}."],
          size=18, color=TX2, align=PP_ALIGN.CENTER)
    label(s, "!!Counter", 9.9, 0.5, 2.8, 0.6, [f"Step {active + 1} of 4"], size=16, bold=True, color=A1,
          align=PP_ALIGN.RIGHT)
    q.after(Effect("pulse", act, 600))


MILESTONES = [("Q1 2026", "Milestone one"), ("Q2 2026", "Milestone two"), ("Q3 2026", "Milestone three"),
              ("Q4 2026", "Milestone four"), ("Q1 2027", "Milestone five")]


def s_timeline_build(dk: Deck):
    s, q = dk.new(5, notes=(
        "Timeline that builds up. Each click wipes the progress bar to the next point, then the marker zooms in "
        "and its label floats in. For a hands-free build, set every effect to After Previous in the Animation "
        "Pane."))
    title(s, "Our timeline")
    title_bar(s)
    x0, x1, ty = 1.4, 11.93, 4.0
    track = shape(s, "Track", MSO_SHAPE.RECTANGLE, x0, ty - 0.06, x1 - x0, 0.12, fill=BG2)
    xs = [x0 + i * (x1 - x0) / 4 for i in range(5)]
    segs, marks, labs = [], [], []
    for i in range(4):
        segs.append(shape(s, f"Progress {i + 1}", MSO_SHAPE.RECTANGLE, xs[i], ty - 0.06, xs[i + 1] - xs[i], 0.12,
                          fill=A1))
    for i, (when, what) in enumerate(MILESTONES):
        marks.append(shape(s, f"Marker {i + 1}", MSO_SHAPE.OVAL, xs[i] - 0.25, ty - 0.25, 0.5, 0.5, fill=A1,
                           line=BG1, line_w=3))
        up = i % 2 == 0
        labs.append(label(s, f"Label {i + 1}", xs[i] - 1.2, ty - 1.65 if up else ty + 0.45, 2.4, 1.2,
                          [(when, 16, True, A1), (what, 18, False, TX1)], align=PP_ALIGN.CENTER,
                          anchor=MSO_ANCHOR.BOTTOM if up else MSO_ANCHOR.TOP))
    q.after(Effect("fade", track, 500)).after(Effect("zoom", marks[0], 400)).with_(Effect("float", labs[0], 500))
    for i in range(4):
        q.click(Effect("wipe", segs[i], 800, sub="left"))
        q.after(Effect("zoom", marks[i + 1], 400)).with_(Effect("float", labs[i + 1], 500))


def s_timeline_morph(dk: Deck, current: int, first: bool):
    s, q = dk.new(5, morph=not first, ms=1500, notes=(
        "Timeline that slides along (Morph, 3 slides). The whole timeline moves so the current point sits in the "
        "middle; points off the slide wait outside it. For another step, duplicate the last slide and move every "
        "!! object one gap (3.2 in) to the left."))
    title(s, "Where we are")
    title_bar(s)
    gap, mid, ty = 3.2, W_IN / 2, 4.1
    items = [("2025", "Start")] + [(w, m) for w, m in MILESTONES] + [("2027+", "Next")]
    xs = [mid + (i - current) * gap for i in range(len(items))]
    shape(s, "!!Track", MSO_SHAPE.RECTANGLE, xs[0] - 1.0, ty - 0.05, xs[-1] - xs[0] + 2.0, 0.1, fill=BG2)
    shape(s, "!!Progress", MSO_SHAPE.RECTANGLE, xs[0] - 1.0, ty - 0.05, xs[current] - xs[0] + 1.0, 0.1, fill=A1)
    for i, (when, what) in enumerate(items):
        now = i == current
        d = 0.8 if now else 0.4
        shape(s, f"!!Mark{i + 1}", MSO_SHAPE.OVAL, xs[i] - d / 2, ty - d / 2, d, d,
              fill=A1 if i <= current else BG2, line=BG1, line_w=3)
        label(s, f"!!When{i + 1}", xs[i] - 1.4, ty - 1.55, 2.8, 0.9, [when], size=28 if now else 18, bold=True,
              color=A1 if now else TX2, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.BOTTOM, heading=True)
        label(s, f"!!What{i + 1}", xs[i] - 1.4, ty + 0.6, 2.8, 1.0, [what], size=20 if now else 15,
              color=TX1 if now else TX2, align=PP_ALIGN.CENTER)
    now = shape(s, "Now marker", MSO_SHAPE.ISOSCELES_TRIANGLE, mid - 0.18, 2.05, 0.36, 0.28, fill=A2, rot=180)
    if first:
        q.after(Effect("fade", now, 500))


CYCLE = ["Stage one", "Stage two", "Stage three", "Stage four"]


def _polar(cx, cy, r, deg):
    a = math.radians(deg)
    return cx + r * math.cos(a), cy + r * math.sin(a)


def s_cycle_build(dk: Deck):
    s, q = dk.new(5, notes=(
        "Cycle that spins in. Each click spins in the next stage and its arrow; the last click spins the centre "
        "ring once. Edit the stage names in the circles and the notes on the right."))
    title(s, "Your cycle")
    title_bar(s)
    cx, cy, r, d = 4.3, 4.3, 2.05, 1.6
    shape(s, "Ring path", MSO_SHAPE.OVAL, cx - r, cy - r, 2 * r, 2 * r, line=BG2, line_w=10)
    spin = shape(s, "Hub ring", MSO_SHAPE.BLOCK_ARC, cx - 1.2, cy - 1.2, 2.4, 2.4, fill=A2)
    spin.adjustments[2] = 0.12
    hub = box(s, "Hub", cx - 0.92, cy - 0.92, 1.84, 1.84, [("Your cycle", 16, True, TX2)], kind=MSO_SHAPE.OVAL,
              fill=BG2, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    items, arrows = [], []
    for i, words in enumerate(CYCLE):
        x, y = _polar(cx, cy, r, -90 + 90 * i)
        items.append(box(s, f"Stage {i + 1}", x - d / 2, y - d / 2, d, d, [words], kind=MSO_SHAPE.OVAL, fill=A1,
                         size=15, bold=True, color=BG1, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, margin=0.05))
        ax, ay = _polar(cx, cy, r, -45 + 90 * i)
        arrows.append(shape(s, f"Arrow {i + 1}", MSO_SHAPE.ISOSCELES_TRIANGLE, ax - 0.2, ay - 0.17, 0.4, 0.34,
                            fill=A2, rot=(45 + 90 * i) % 360))
    notes = label(s, "Notes", 7.6, 1.8, 5.2, 4.8, [(f"{w}: what happens", 20, False, TX1) for w in CYCLE],
                  bullets=True, spacing=16)
    q.after(Effect("zoom", hub, 500)).with_(Effect("zoom", spin, 500))
    for i in range(4):
        q.click(Effect("spinner", items[i], 600)).with_(Effect("float", notes, 600, para=i))
        q.after(Effect("fade", arrows[i], 400))
    q.click(Effect("spin", spin, 800))


def s_cycle_morph(dk: Deck, active: int):
    s, q = dk.new(5, morph=active > 0, ms=1250, notes=(
        "Cycle that turns (Morph, 4 slides). Each slide turns the stages one place, so the active stage sits next "
        "to its explanation. Edit the names on every slide; keep the !! names."))
    title(s, "Our cycle, step by step")
    title_bar(s)
    cx, cy, r = 4.0, 4.3, 2.05
    shape(s, "!!Ring", MSO_SHAPE.OVAL, cx - r, cy - r, 2 * r, 2 * r, line=BG2, line_w=10)
    shape(s, "Pointer", MSO_SHAPE.OVAL, cx + r - 1.2, cy - 1.2, 2.4, 2.4, line=A2, line_w=4)  # the active place
    act = None
    for i, words in enumerate(CYCLE):
        now = i == active
        d = 1.9 if now else 1.3
        x, y = _polar(cx, cy, r, 90 * (i - active))
        b = box(s, f"!!Stage{i + 1}", x - d / 2, y - d / 2, d, d, [words], kind=MSO_SHAPE.OVAL,
                fill=A1 if now else BG2, size=17 if now else 13, bold=True, color=BG1 if now else TX2,
                align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, margin=0.05)
        act = b if now else act
    box(s, "!!Detail", 7.4, 2.6, 5.3, 3.4, [(CYCLE[active], 26, True, A1), ("What happens in this stage, in one or "
                                                                            "two lines.", 20, False, TX1)],
        fill=BG2, anchor=MSO_ANCHOR.MIDDLE, margin=0.35, spacing=8)
    q.after(Effect("grow", act, 400, scale=110, auto_rev=True))


def s_compare(dk: Deck, decided: bool):
    s, q = dk.new(5, morph=decided, ms=1250, notes=(
        "Comparison. On the second slide the winner grows and takes the accent colour (Morph); the badge zooms in. "
        "To make A the winner, swap the two cards' sizes and colours on the second slide."))
    title(s, "Option A or option B?")
    title_bar(s)
    body = [("Point one", 20, False, None), ("Point two", 20, False, None), ("Point three", 20, False, None)]

    def card(name, head, x, y, w, h, win, dim):
        fg = BG1 if win else (TX2 if dim else TX1)
        paras = [(head, 28, True, fg)] + [(t, sz, b, fg) for t, sz, b, _ in body]
        return box(s, name, x, y, w, h, paras, fill=A1 if win else BG2, anchor=MSO_ANCHOR.TOP, margin=0.4,
                   spacing=10)

    if not decided:
        a = card("!!CardA", "Option A", 0.9, 1.75, 5.6, 4.9, False, False)
        b = card("!!CardB", "Option B", 6.83, 1.75, 5.6, 4.9, False, False)
        q.after(Effect("fly", a, 600, sub="left")).after(Effect("fly", b, 600, sub="right"))
    else:
        card("!!CardA", "Option A", 0.9, 2.05, 5.0, 4.4, False, True)
        card("!!CardB", "Option B", 6.4, 1.6, 6.3, 5.3, True, False)
        badge = box(s, "Badge", 10.2, 1.3, 2.2, 0.6, [("Recommended", 16, True, TX1)], fill=A2,
                    align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        badge.adjustments[0] = 0.5
        q.after(Effect("zoom", badge, 500)).after(Effect("pulse", badge, 600))


def s_kpi(dk: Deck):
    s, q = dk.new(5, notes=(
        "Numbers. The tiles' numbers zoom in one after another; the next click makes the first number pulse to "
        "point at it. Type your own numbers over the samples."))
    title(s, "Results at a glance")
    title_bar(s)
    kpis = [("42%", "Your first measure"), ("1.2 M", "Your second measure"), ("3×", "Your third measure"),
            ("+18", "Your fourth measure")]
    w, gap = 2.75, 0.38
    x0 = (W_IN - 4 * w - 3 * gap) / 2
    nums = []
    for i, (n, what) in enumerate(kpis):
        x = x0 + i * (w + gap)
        shape(s, f"Tile {i + 1}", MSO_SHAPE.ROUNDED_RECTANGLE, x, 2.0, w, 3.6, fill=BG2).adjustments[0] = 0.08
        nums.append(label(s, f"Number {i + 1}", x, 2.4, w, 1.6, [n], size=60, bold=True, color=A1,
                          align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, heading=True))
        lab = label(s, f"Measure {i + 1}", x + 0.2, 4.1, w - 0.4, 1.2, [what], size=17, color=TX2,
                    align=PP_ALIGN.CENTER)
        step = q.after(Effect("zoom", nums[i], 500))
        step.with_(Effect("fade", lab, 500, delay=200))
    q.click(Effect("grow", nums[0], 400, scale=120, auto_rev=True))


def s_chart(dk: Deck):
    s, q = dk.new(5, notes=(
        "Chart reveal. The axes appear first, then each click wipes in one category from the bottom. Change the "
        "numbers: right-click the chart > Edit Data. The colours follow the theme."))
    title(s, "Your chart")
    title_bar(s)
    cd = CategoryChartData()
    cats = ["Q1", "Q2", "Q3", "Q4"]
    cd.categories = cats
    cd.add_series("Series 1", (12, 18, 23, 31))
    cd.add_series("Series 2", (9, 14, 16, 20))
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, I(0.9), I(1.6), I(8.4), I(5.3), cd)
    gf.name = "Chart"
    ch = gf.chart
    ch.has_legend = True
    ch.legend.position = XL_LEGEND_POSITION.BOTTOM
    ch.legend.include_in_layout = False
    ch.font.size = Pt(14)
    _color(ch.font.color, TX2)
    take = box(s, "Takeaway", 9.7, 1.75, 3.0, 4.9, [("What it shows", 16, True, A1),
                                                     ("One line on the trend.", 22, True, TX1)],
               fill=BG2, anchor=MSO_ANCHOR.MIDDLE, margin=0.3, spacing=8)
    q.after(Effect("wipe", gf, 500, sub="bottom", chart=("gridLegend",)))
    for i in range(len(cats)):
        q.click(Effect("wipe", gf, 600, sub="bottom", chart=("category", i)))
    q.click(Effect("float", take, 600))


def s_closing(dk: Deck):
    s, q = dk.new(0, notes="Closing slide. The text zooms in and the circles follow, automatically.")
    t = s.shapes.title
    t.name = "Title"
    t.left, t.top, t.width, t.height = I(0.9), I(2.2), I(7.6), I(1.6)
    t.text_frame.text = "Thank you"
    p = t.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    f = p.runs[0].font
    f.size, f.bold, f.name = Pt(60), True, "+mj-lt"
    _color(f.color, TX1)
    t.text_frame.vertical_anchor = MSO_ANCHOR.BOTTOM
    sub = s.placeholders[1]
    sub.name = "Subtitle"
    sub.left, sub.top, sub.width, sub.height = I(0.9), I(4.0), I(7.6), I(1.2)
    sub.text_frame.text = "Questions? · Your name · your.email@example.com"
    p = sub.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    f = p.runs[0].font
    f.size, f.name = Pt(22), "+mn-lt"
    _color(f.color, TX2)
    c1 = shape(s, "Circle large", MSO_SHAPE.OVAL, 9.2, 1.6, 3.2, 3.2, fill=A1)
    c2 = shape(s, "Circle small", MSO_SHAPE.OVAL, 8.6, 4.6, 1.6, 1.6, fill=A2)
    c3 = shape(s, "Ring", MSO_SHAPE.OVAL, 11.0, 4.7, 1.5, 1.5, line=A3, line_w=6)
    q.after(Effect("zoom", t, 600)).after(Effect("float", sub, 600))
    q.with_(Effect("zoom", c1, 600)).with_(Effect("zoom", c2, 500, delay=150))
    q.with_(Effect("spinner", c3, 700, delay=250))


def s_how(dk: Deck):
    s, q = dk.new(5, notes="How to use the template. Delete this slide and the next before presenting.")
    title(s, "How to use this template")
    title_bar(s)
    tips = [
        ("Fill in", "Click any 'Your …' text and type. Delete the slides you do not need. Each slide's notes "
                    "say how it moves and how to change it."),
        ("Morph pairs", "A slide with the Morph transition moves objects from the slide before it. Duplicate both "
                        "slides together; keep the names that start with !! the same on both "
                        "(Home > Arrange > Selection Pane)."),
        ("Animations", "Animations > Animation Pane: change the order, On Click or After Previous, and the speed."),
        ("Pictures", "Right-click > Change Picture, on both zoom slides. On the zoomed one, crop again."),
        ("Charts", "Right-click the chart > Edit Data. The bars keep their animation."),
        ("Colours", "Design > Variants > Colors recolours every slide (next slide)."),
    ]
    w, h, gx, gy = 3.85, 2.45, 0.29, 0.25
    for i, (head, body) in enumerate(tips):
        x, y = 0.6 + (i % 3) * (w + gx), 1.65 + (i // 3) * (h + gy)
        card = box(s, f"Tip {i + 1}", x, y, w, h, [(f"{i + 1}. {head}", 18, True, A1), (body, 14, False, TX1)],
                   fill=BG2, margin=0.22, spacing=6)
        q.after(Effect("fade", card, 400))


def s_colours(dk: Deck, scheme: str):
    s, q = dk.new(5, notes="Changing colours. Every shape uses the theme colours shown here.")
    title(s, "How to change the colours")
    title_bar(s)
    names = [("accent1", "Accent 1", T.ACCENT_1), ("accent2", "Accent 2", T.ACCENT_2),
             ("accent3", "Accent 3", T.ACCENT_3), ("accent4", "Accent 4", T.ACCENT_4),
             ("accent5", "Accent 5", T.ACCENT_5), ("accent6", "Accent 6", T.ACCENT_6),
             ("tx2", "Text 2", TX2), ("bg2", "Background 2", BG2)]
    for i, (_, words, col) in enumerate(names):
        x = 0.9 + (i % 4) * 1.45
        y = 1.75 + (i // 4) * 1.75
        sw = shape(s, f"Swatch {i + 1}", MSO_SHAPE.ROUNDED_RECTANGLE, x, y, 1.2, 1.0, fill=col, line=TX2, line_w=0.75)
        label(s, f"Swatch name {i + 1}", x - 0.1, y + 1.02, 1.4, 0.45, [words], size=12, color=TX2,
              align=PP_ALIGN.CENTER)
        if i == 0:
            q.after(Effect("zoom", sw, 400))
        else:
            q.with_(Effect("zoom", sw, 400, delay=80 * i))
    label(s, "Scheme name", 0.9, 5.4, 5.6, 0.9, [(f"This file: '{scheme}' colours.", 16, True, TX1),
                                                ("Fonts: Design > Variants > Fonts.", 14, False, TX2)])
    steps = [("Windows", "Design > Variants > More (▾) > Colors, then pick a set, or Customize Colors to make "
                         "your own."),
             ("Mac", "Design > Variants (▾) > Colors."),
             ("iPad, phone, web", "Download a ready colour version from the website (Ocean, Graphite, Sunrise).")]
    paras = []
    for head, body in steps:
        paras += [(head, 18, True, A1), (body, 16, False, TX1)]
    box(s, "Steps", 7.0, 1.75, 5.7, 4.6, paras, fill=BG2, margin=0.3, spacing=6)


# ---------------------------------------------------------------- more ideas (owner, 6 Nov 2026: "expand a bit")


def s_blocks(dk: Deck):
    s, q = dk.new(5, notes=(
        "Block diagram that builds. The blocks appear together, each click wipes in the connections, and the last "
        "click frames the block where our part fits. Rename the blocks; move the frame to another block if needed."))
    title(s, "Where our part fits")
    title_bar(s)
    names = ["Input", "Block A", "Our part", "Block B", "Output"]
    w, h, gap, y = 1.9, 1.2, 0.55, 2.5
    x0 = (W_IN - (5 * w + 4 * gap)) / 2
    blocks = []
    for i, nm in enumerate(names):
        ours = nm == "Our part"
        blocks.append(box(s, f"Block {i + 1}", x0 + i * (w + gap), y, w, h, [nm], fill=A1 if ours else BG2,
                          size=17, bold=True, color=BG1 if ours else TX1, align=PP_ALIGN.CENTER,
                          anchor=MSO_ANCHOR.MIDDLE))
    px = x0 + w + gap
    power = box(s, "Power", px, 4.65, 3 * w + 2 * gap, 0.9, ["Power and control"], fill=BG2, size=16, bold=True,
                color=TX2, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    links = [arrow(s, f"Link {i + 1}", 0, 0, 1, 1, begin=(blocks[i], 3), end=(blocks[i + 1], 1)) for i in range(4)]
    feeds = [arrow(s, f"Feed {i + 1}", px + i * (w + gap) + w / 2, 4.65, px + i * (w + gap) + w / 2, y + h + 0.02)
             for i in range(3)]
    fx = x0 + 2 * (w + gap)
    frame = shape(s, "Highlight", MSO_SHAPE.ROUNDED_RECTANGLE, fx - 0.15, y - 0.15, w + 0.3, h + 0.3, line=A2,
                  line_w=5)
    callout = label(s, "Callout", fx - 1.0, y - 1.05, w + 2.0, 0.7, ["Where our part fits"], size=18, bold=True,
                    color=A2, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.BOTTOM)
    q.after(Effect("zoom", blocks[0], 500))
    for i in range(1, 5):
        q.with_(Effect("zoom", blocks[i], 500, delay=100 * i))
    q.with_(Effect("float", power, 600, delay=300))
    q.click(Effect("wipe", links[0], 400, sub="left"))
    for k in links[1:]:
        q.after(Effect("wipe", k, 400, sub="left"))
    q.after(Effect("wipe", feeds[0], 400, sub="bottom"))
    for k in feeds[1:]:
        q.with_(Effect("wipe", k, 400, sub="bottom"))
    q.click(Effect("zoom", frame, 500)).with_(Effect("float", callout, 500)).after(Effect("pulse", frame, 600))


MATRIX = [((0.25, 0.30), (0.40, 0.70)), ((0.70, 0.25), (0.85, 0.40)), ((0.35, 0.75), (0.30, 0.88)),
          ((0.80, 0.70), (0.65, 0.85)), ((0.55, 0.50), (0.82, 0.78))]  # (today, later): x to the right, y up
ORDINAL = ["one", "two", "three", "four", "five"]


def s_matrix(dk: Deck, later: bool):
    s, q = dk.new(5, morph=later, ms=1500, notes=(
        "2×2 matrix (Morph pair). The dots move from today's place to where they will be. Move the dots on the "
        "second slide; keep the !! names on both."))
    title(s, "Where we play")
    title_bar(s)
    x0, y0, size = 1.3, 1.65, 5.2
    half = size / 2
    for i in range(4):
        qx, qy = x0 + (i % 2) * half, y0 + (i // 2) * half
        sh = box(s, f"Quadrant {i + 1}", qx + 0.03, qy + 0.03, half - 0.06, half - 0.06, [f"Quadrant {ORDINAL[i]}"],
                 kind=MSO_SHAPE.RECTANGLE, fill=BG2, size=13, bold=True, color=TX2,
                 align=PP_ALIGN.LEFT if i % 2 == 0 else PP_ALIGN.RIGHT,
                 anchor=MSO_ANCHOR.TOP if i < 2 else MSO_ANCHOR.BOTTOM, margin=0.12)
        if not later:
            if i == 0:
                q.after(Effect("fade", sh, 500))
            else:
                q.with_(Effect("fade", sh, 500))
    label(s, "X axis", x0, y0 + size + 0.05, size, 0.4, ["Your x-axis →"], size=14, color=TX2, align=PP_ALIGN.RIGHT)
    yax = label(s, "Y axis", x0 - 2.85, y0 + size / 2 - 0.2, size, 0.4, ["Your y-axis →"], size=14, color=TX2,
                align=PP_ALIGN.RIGHT)
    yax.rotation = 270
    accents = [T.ACCENT_1, T.ACCENT_2, T.ACCENT_3, T.ACCENT_4, T.ACCENT_5]
    for i, (now, then) in enumerate(MATRIX):
        fx, fy = then if later else now
        cx, cy = x0 + fx * size, y0 + (1 - fy) * size
        dot = shape(s, f"!!Dot{i + 1}", MSO_SHAPE.OVAL, cx - 0.22, cy - 0.22, 0.44, 0.44, fill=accents[i], line=BG1,
                    line_w=2)
        nm = label(s, f"!!Name{i + 1}", cx + 0.25, cy - 0.2, 1.5, 0.4, [f"Item {ORDINAL[i]}"], size=13, bold=True)
        if not later:
            q.after(Effect("fly", dot, 500, sub="bottom")).with_(Effect("fade", nm, 400, delay=200))
    box(s, "!!Era", 7.4, 1.65, 5.3, 1.1, [("In 3 years" if later else "Today", 28, True, BG1)], fill=A1,
        anchor=MSO_ANCHOR.MIDDLE, margin=0.3)
    label(s, "Explain", 7.4, 3.0, 5.3, 2.5, ["Say what moves and why." if later else
                                             "Say where each item stands today. The next slide moves them."],
          size=18, color=TX2)


def s_venn(dk: Deck, together: bool):
    s, q = dk.new(5, morph=together, ms=1500, notes=(
        "Venn overlap (Morph pair). The circles slide together and the overlap label pops in. Rename the circles "
        "and the overlap; keep the !! names on both slides."))
    title(s, "What we share")
    title_bar(s)
    d, cy = 3.8, 4.2
    ax, bx = (5.45, 7.9) if together else (3.3, 10.0)
    a = see_through(shape(s, "!!CircleA", MSO_SHAPE.OVAL, ax - d / 2, cy - d / 2, d, d, fill=A1), 55)
    b = see_through(shape(s, "!!CircleB", MSO_SHAPE.OVAL, bx - d / 2, cy - d / 2, d, d, fill=A2), 55)
    wa = 2.1 if together else 3.4
    ta = label(s, "!!TextA", ax - 1.7, cy - 0.7, wa, 1.4,
               [("Side A", 24, True, TX1), ("What A brings", 15, False, TX1)],
               align=PP_ALIGN.LEFT if together else PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    tb = label(s, "!!TextB", bx - 0.4 if together else bx - 1.7, cy - 0.7, wa, 1.4,
               [("Side B", 24, True, TX1), ("What B brings", 15, False, TX1)],
               align=PP_ALIGN.RIGHT if together else PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    if not together:
        q.after(Effect("fly", a, 600, sub="left")).with_(Effect("fly", b, 600, sub="right"))
        q.after(Effect("fade", ta, 400)).with_(Effect("fade", tb, 400))
    else:
        mid = (ax + bx) / 2
        both = box(s, "Overlap", mid - 0.75, cy - 0.45, 1.5, 0.9, [("Together", 16, True, BG1)], fill=TX1,
                   align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, margin=0.04)
        both.adjustments[0] = 0.5
        q.after(Effect("zoom", both, 500)).after(Effect("pulse", both, 600))


def s_funnel(dk: Deck):
    s, q = dk.new(5, notes="Funnel that builds. Each click adds the next level and its number. Type your own "
                           "stages and values.")
    title(s, "Your funnel")
    title_bar(s)
    widths, h, cx = [7.4, 6.0, 4.6, 3.2], 1.0, 4.6
    for i, w in enumerate(widths):
        y = 1.75 + i * (h + 0.14)
        lvl = box(s, f"Level {i + 1}", cx - w / 2, y, w, h, [f"Stage {ORDINAL[i]}"], fill=A1, fill_b=0.2 * i, size=18,
                  bold=True, color=BG1 if i < 2 else TX1, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        val = label(s, f"Value {i + 1}", 8.9, y, 3.8, h, [(f"{[1000, 400, 120, 30][i]:,}", 24, True, A1),
                                                          ("Your note", 14, False, TX2)], anchor=MSO_ANCHOR.MIDDLE)
        q.click(Effect("wipe", lvl, 500, sub="left")).with_(Effect("float", val, 500, delay=200))


def s_pyramid(dk: Deck):
    s, q = dk.new(5, notes="Pyramid that builds from the base up, one level per click. Type your own levels and "
                           "notes.")
    title(s, "Your pyramid")
    title_bar(s)
    cx, top, base, height, gap, n = 4.4, 1.7, 7.0, 5.0, 0.08, 4
    lh = height / n
    slope = (base / 2) / height
    words = ["Foundation", "Level two", "Level three", "Top"]
    for k in range(n):  # k = 0 at the bottom
        y = top + height - (k + 1) * lh
        wb = 2 * slope * (height - k * lh)
        hh = lh - gap
        if k == n - 1:
            lvl = shape(s, f"Level {k + 1}", MSO_SHAPE.ISOSCELES_TRIANGLE, cx - wb / 2, y + gap, wb, hh, fill=A1,
                        fill_b=0.15 * k)
            text(lvl, [words[k]], size=15, bold=True, color=TX1, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.BOTTOM)
        else:
            lvl = box(s, f"Level {k + 1}", cx - wb / 2, y + gap, wb, hh, [words[k]], kind=MSO_SHAPE.TRAPEZOID,
                      fill=A1, fill_b=0.15 * k, size=17, bold=True, color=BG1 if k < 2 else TX1,
                      align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
            lvl.adjustments[0] = slope * hh / min(wb, hh)
        note = label(s, f"Note {k + 1}", 8.4, y + gap, 4.3, hh, [(words[k], 18, True, A1),
                                                                 ("One line about this level.", 14, False, TX2)],
                     anchor=MSO_ANCHOR.MIDDLE)
        q.click(Effect("wipe", lvl, 500, sub="bottom")).with_(Effect("float", note, 500, delay=200))


def s_roadmap(dk: Deck):
    s, q = dk.new(5, notes=(
        "Roadmap with swimlanes. Each click grows one lane's bars; the last click shades the time gone by and "
        "drops the 'Today' line. Stretch the bars to your dates; move the Today line."))
    title(s, "Roadmap")
    title_bar(s)
    gx, gw = 2.6, 10.1
    qw = gw / 4
    for i in range(4):
        label(s, f"Quarter {i + 1}", gx + i * qw, 1.55, qw, 0.4, [f"Q{i + 1}"], size=15, bold=True, color=TX2,
              align=PP_ALIGN.CENTER)
    today = gx + 1.4 * qw
    y0, lh = 2.05, 1.35
    elapsed = shape(s, "Time gone", MSO_SHAPE.RECTANGLE, gx, y0, today - gx, 3 * lh, fill=BG2)
    bars = [[(0.1, 1.6), (1.9, 3.7)], [(0.5, 2.2), (2.5, 3.9)], [(0.0, 1.1), (1.4, 3.1)]]
    for i in range(3):
        y = y0 + i * lh
        shape(s, f"Lane {i + 1} line", MSO_SHAPE.RECTANGLE, 0.6, y + lh - 0.02, gx + gw - 0.6, 0.02, fill=BG2)
        label(s, f"Lane {i + 1}", 0.6, y, 1.9, lh, [f"Lane {ORDINAL[i]}"], size=17, bold=True,
              anchor=MSO_ANCHOR.MIDDLE)
        for j, (a, b) in enumerate(bars[i]):
            bar = box(s, f"Bar {i + 1}.{j + 1}", gx + a * qw, y + 0.3, (b - a) * qw, lh - 0.6, ["Work item"],
                      fill=A1, fill_b=0.4 * j, size=14, bold=True, color=BG1 if j == 0 else TX1,
                      anchor=MSO_ANCHOR.MIDDLE, margin=0.12)
            if j == 0:
                q.click(Effect("wipe", bar, 600, sub="left"))
            else:
                q.after(Effect("wipe", bar, 600, sub="left"))
    line = shape(s, "Today line", MSO_SHAPE.RECTANGLE, today - 0.02, y0 - 0.1, 0.04, 3 * lh + 0.2, fill=A2)
    tl = box(s, "Today", today - 0.55, y0 + 3 * lh + 0.15, 1.1, 0.42, [("Today", 14, True, TX1)], fill=A2,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, margin=0.02)
    q.click(Effect("wipe", elapsed, 800, sub="left"))
    q.after(Effect("wipe", line, 500, sub="top")).with_(Effect("zoom", tl, 400, delay=200))


COUNT = [("250", 0.2), ("750", 0.55), ("1,200", 0.9)]


def s_countup(dk: Deck, step: int):
    s, q = dk.new(5, morph=step > 0, ms=1000, notes=(
        "Big number that counts up (Morph, 3 slides). Each slide shows a bigger value and a longer bar. Type your "
        "values; add a slide for each extra step and keep the !! names."))
    title(s, "Our growth")
    title_bar(s)
    words, frac = COUNT[step]
    big = label(s, "!!Big", 0.9, 1.9, 11.5, 2.4, [words], size=130, bold=True, color=A1, align=PP_ALIGN.CENTER,
                anchor=MSO_ANCHOR.MIDDLE, heading=True)
    shape(s, "!!Track", MSO_SHAPE.ROUNDED_RECTANGLE, 2.2, 4.6, 8.9, 0.32, fill=BG2)
    shape(s, "!!Bar", MSO_SHAPE.ROUNDED_RECTANGLE, 2.2, 4.6, 8.9 * frac, 0.32, fill=A1)
    label(s, "!!Caption", 2.2, 5.15, 8.9, 0.8, [f"Your measure · step {step + 1}"], size=20, color=TX2,
          align=PP_ALIGN.CENTER)
    if step == 0:
        q.after(Effect("zoom", big, 600))
    elif step == len(COUNT) - 1:
        q.after(Effect("grow", big, 400, scale=110, auto_rev=True))


def s_table(dk: Deck):
    s, q = dk.new(5, notes=(
        "Table with a highlighted row. The table fades in; a click frames one row and pulses it, and the note "
        "floats in. Edit the cells; drag the frame onto another row. The table style follows the theme colours."))
    title(s, "Your table")
    title_bar(s)
    rows, cols, rh = 6, 4, 0.62
    gf = s.shapes.add_table(rows, cols, I(0.9), I(1.75), I(8.4), I(rows * rh))
    gf.name = "Table"
    t = gf.table
    heads = ["Item", "Measure one", "Measure two", "Note"]
    for r in range(rows):
        t.rows[r].height = I(rh)
        for c in range(cols):
            cell = t.cell(r, c)
            cell.text = heads[c] if r == 0 else (f"Row {r}" if c == 0 else "Short note" if c == 3 else str(r * 10 + c))
            f = cell.text_frame.paragraphs[0].runs[0].font
            f.size, f.bold = Pt(16), r == 0 or c == 0
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    frame = shape(s, "Row frame", MSO_SHAPE.ROUNDED_RECTANGLE, 0.8, 1.75 + 3 * rh - 0.05, 8.6, rh + 0.1, line=A2,
                  line_w=4)
    note = box(s, "Row note", 9.8, 1.75 + 2 * rh, 2.9, 2.2,
               [("Row 3", 16, True, A2), ("Why this row matters.", 18, True, TX1)],
               fill=BG2, anchor=MSO_ANCHOR.MIDDLE, margin=0.25, spacing=6)
    q.after(Effect("fade", gf, 600))
    q.click(Effect("zoom", frame, 500)).with_(Effect("float", note, 500, delay=200)).after(Effect("pulse", frame, 600))


def s_rings(dk: Deck):
    s, q = dk.new(5, notes=(
        "Progress rings. Each ring fills like a clock hand, one after another. To change a value, select the "
        "coloured ring, drag its yellow handle, and type the new percentage."))
    title(s, "Progress")
    title_bar(s)
    d, cy, thick = 2.6, 3.7, 0.12
    dr = d * thick
    for i, (pct, cx) in enumerate(zip((75, 50, 90), (2.9, 6.67, 10.43), strict=True)):
        shape(s, f"Ring {i + 1}", MSO_SHAPE.OVAL, cx - d / 2 + dr / 2, cy - d / 2 + dr / 2, d - dr, d - dr, line=BG2,
              line_w=dr * 72)
        arc = shape(s, f"Fill {i + 1}", MSO_SHAPE.BLOCK_ARC, cx - d / 2, cy - d / 2, d, d, fill=[A1, A2, A3][i])
        arc.adjustments[0] = 270 * 0.6  # angles in 60000ths of a degree; python-pptx divides by 100000
        arc.adjustments[1] = ((270 + 360 * pct / 100) % 360) * 0.6
        arc.adjustments[2] = thick
        num = label(s, f"Percent {i + 1}", cx - 1.0, cy - 0.5, 2.0, 1.0, [f"{pct}%"], size=34, bold=True,
                    align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, heading=True)
        label(s, f"Measure {i + 1}", cx - 1.6, cy + d / 2 + 0.2, 3.2, 0.8, ["Your measure"], size=18, color=TX2,
              align=PP_ALIGN.CENTER)
        q.after(Effect("wheel", arc, 800)).with_(Effect("zoom", num, 500, delay=300))


def s_quote(dk: Deck):
    s, q = dk.new(6, notes=(
        "Quote or key message. The quote mark zooms in, the quote floats in and the name follows; a click makes "
        "the quote grow a little for emphasis."))
    mark = label(s, "Quote mark", 0.9, 0.5, 2.0, 2.2, ["“"], size=180, bold=True, color=A1, heading=True)
    quote = label(s, "Quote", 1.6, 2.2, 10.2, 2.6, ["Your quote or key message, short and strong."], size=40,
                  bold=True, anchor=MSO_ANCHOR.MIDDLE, heading=True)
    bar = shape(s, "Quote bar", MSO_SHAPE.RECTANGLE, 1.6, 5.05, 1.2, 0.07, fill=A2)
    who = label(s, "Who", 1.6, 5.25, 9.0, 0.6, ["Name, role"], size=20, color=TX2)
    q.after(Effect("zoom", mark, 500)).after(Effect("float", quote, 700)).after(Effect("wipe", bar, 400, sub="left"))
    q.with_(Effect("fade", who, 500, delay=100))
    q.click(Effect("grow", quote, 500, scale=106, auto_rev=True))


SLIDE_ORDER = [  # (deck, colour key) -> one or more slides, in deck order
    lambda dk, k: s_title(dk),
    lambda dk, k: s_agenda(dk, 0, build=True),
    lambda dk, k: s_section(dk, 0),
    lambda dk, k: s_agenda(dk, 1, build=False),
    lambda dk, k: s_section(dk, 1),
    lambda dk, k: s_bullets(dk),
    lambda dk, k: s_zoom(dk, False),
    lambda dk, k: s_zoom(dk, True),
    lambda dk, k: s_flow_build(dk),
    *[lambda dk, k, i=i: s_flow_morph(dk, i) for i in range(4)],
    lambda dk, k: s_timeline_build(dk),
    *[lambda dk, k, i=i: s_timeline_morph(dk, i + 1, first=i == 0) for i in range(3)],
    lambda dk, k: s_cycle_build(dk),
    *[lambda dk, k, i=i: s_cycle_morph(dk, i) for i in range(4)],
    lambda dk, k: s_compare(dk, False),
    lambda dk, k: s_compare(dk, True),
    lambda dk, k: s_kpi(dk),
    lambda dk, k: s_chart(dk),
    lambda dk, k: s_blocks(dk),
    lambda dk, k: s_matrix(dk, False),
    lambda dk, k: s_matrix(dk, True),
    lambda dk, k: s_venn(dk, False),
    lambda dk, k: s_venn(dk, True),
    lambda dk, k: s_funnel(dk),
    lambda dk, k: s_pyramid(dk),
    lambda dk, k: s_roadmap(dk),
    *[lambda dk, k, i=i: s_countup(dk, i) for i in range(3)],
    lambda dk, k: s_table(dk),
    lambda dk, k: s_rings(dk),
    lambda dk, k: s_quote(dk),
    lambda dk, k: s_closing(dk),
    lambda dk, k: s_how(dk),
    lambda dk, k: s_colours(dk, PALETTES[k][0]),
]


# ---------------------------------------------------------------- package


def build(key: str = "default") -> bytes:
    name, _, hexes = PALETTES[key]
    dk = Deck(new_presentation(name, hexes), picture_png())
    for make in SLIDE_ORDER:
        make(dk, key)
    return finish(dk, "Animated template", "Template", "Fill-in template with Morph and animations")


def main(argv: list[str]) -> int:
    bad = 0
    for key, fname in FILES.items():
        blob = build(key)
        problems = check(blob)
        for p in problems:
            print(f"{fname}: {p}")
        bad += len(problems)
        path = OUT_DIR / fname
        if "--check" in argv:
            if not path.exists() or path.read_bytes() != blob:
                print(f"{fname}: differs from a fresh build; run scripts/build_pptx_template.py")
                bad += 1
        else:
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            path.write_bytes(blob)
            print(f"wrote {path.relative_to(ROOT)} ({len(blob) // 1024} KB)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
