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
import re
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.services.pptx_template import FILES, PALETTES  # noqa: E402

OUT_DIR = ROOT / "app" / "web" / "static" / "downloads"
FIXED = datetime(2026, 11, 6, 9, 0, 0)
ZIP_TIME = (2026, 11, 6, 9, 0, 0)

W_IN, H_IN = 13.333, 7.5
NS_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
NS_A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS_MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
NS_P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
NS_P159 = "http://schemas.microsoft.com/office/powerpoint/2015/09/main"

T = MSO_THEME_COLOR
BG1, TX1, BG2, TX2 = T.BACKGROUND_1, T.TEXT_1, T.BACKGROUND_2, T.TEXT_2
A1, A2, A3 = T.ACCENT_1, T.ACCENT_2, T.ACCENT_3


def I(x: float) -> Emu:  # noqa: E743 - inches, short because the layout code is all numbers
    return Inches(x)


# ---------------------------------------------------------------- animations (p:timing)


@dataclass
class Effect:
    kind: str  # fade, fly, float, wipe, zoom, spinner, grow, pulse, spin
    shape: object  # the python-pptx shape
    dur: int = 500
    delay: int = 0
    sub: str = ""  # direction: left, right, bottom
    para: int | None = None  # paragraph index for a paragraph build
    chart: tuple | None = None  # ("gridLegend",) or ("category", i)
    scale: int = 115  # grow/shrink percent
    auto_rev: bool = False

    @property
    def spid(self) -> int:
        return self.shape.shape_id

    @property
    def total(self) -> int:
        return self.delay + self.dur * (2 if self.auto_rev else 1)


PRESETS = {  # kind -> (presetID, presetClass, presetSubtype by direction)
    "appear": (1, "entr", {"": 0}),
    "fly": (2, "entr", {"bottom": 4, "left": 8, "right": 2, "top": 1}),
    "fade": (10, "entr", {"": 0}),
    "wipe": (22, "entr", {"left": 8, "bottom": 4}),
    "float": (42, "entr", {"": 0}),
    "spinner": (49, "entr", {"": 0}),
    "zoom": (53, "entr", {"": 16}),
    "grow": (6, "emph", {"": 0}),
    "spin": (8, "emph", {"": 0}),
    "pulse": (26, "emph", {"": 0}),
}
WIPE_FILTER = {"left": "wipe(left)", "bottom": "wipe(down)"}


class Ids:
    def __init__(self):
        self.n = 0

    def __call__(self) -> int:
        self.n += 1
        return self.n


def _tgt(e: Effect) -> str:
    if e.chart:
        step = e.chart[0]
        ser, cat = ("-3", "-3") if step == "gridLegend" else ("-4", str(e.chart[1]))
        inner = f'<p:graphicEl><a:chart seriesIdx="{ser}" categoryIdx="{cat}" bldStep="{step}"/></p:graphicEl>'
        return f'<p:tgtEl><p:spTgt spid="{e.spid}">{inner}</p:spTgt></p:tgtEl>'
    if e.para is not None:
        rng = f'<p:txEl><p:pRg st="{e.para}" end="{e.para}"/></p:txEl>'
        return f'<p:tgtEl><p:spTgt spid="{e.spid}">{rng}</p:spTgt></p:tgtEl>'
    return f'<p:tgtEl><p:spTgt spid="{e.spid}"/></p:tgtEl>'


def _set_visible(ids, tgt) -> str:
    return (f'<p:set><p:cBhvr><p:cTn id="{ids()}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst>'
            f'</p:cTn>{tgt}<p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst></p:cBhvr>'
            '<p:to><p:strVal val="visible"/></p:to></p:set>')


def _val(v) -> str:
    return f'<p:fltVal val="{v}"/>' if isinstance(v, (int, float)) else f'<p:strVal val="{v}"/>'


def _anim(ids, tgt, attr, dur, a, b) -> str:
    return (f'<p:anim calcmode="lin" valueType="num"><p:cBhvr additive="base"><p:cTn id="{ids()}" dur="{dur}" '
            f'fill="hold"/>{tgt}<p:attrNameLst><p:attrName>{attr}</p:attrName></p:attrNameLst></p:cBhvr>'
            f'<p:tavLst><p:tav tm="0"><p:val>{_val(a)}</p:val></p:tav><p:tav tm="100000"><p:val>{_val(b)}</p:val>'
            '</p:tav></p:tavLst></p:anim>')


def _effect_filter(ids, tgt, dur, flt, transition="in", tm_filter="") -> str:
    tf = f' tmFilter="{tm_filter}"' if tm_filter else ""
    return (f'<p:animEffect transition="{transition}" filter="{flt}"><p:cBhvr><p:cTn id="{ids()}" dur="{dur}"{tf}/>'
            f'{tgt}</p:cBhvr></p:animEffect>')


def _behaviours(e: Effect, ids) -> str:
    t, d = _tgt(e), e.dur
    if e.kind == "appear":
        return _set_visible(ids, t)
    if e.kind == "fade":
        return _set_visible(ids, t) + _effect_filter(ids, t, d, "fade")
    if e.kind == "fly":
        x0 = {"left": "0-#ppt_w/2", "right": "1+#ppt_w/2"}.get(e.sub, "#ppt_x")
        y0 = {"bottom": "1+#ppt_h/2", "top": "0-#ppt_h/2"}.get(e.sub, "#ppt_y")
        return _set_visible(ids, t) + _anim(ids, t, "ppt_x", d, x0, "#ppt_x") + _anim(ids, t, "ppt_y", d, y0, "#ppt_y")
    if e.kind == "float":
        return (_set_visible(ids, t) + _effect_filter(ids, t, d, "fade")
                + _anim(ids, t, "ppt_x", d, "#ppt_x", "#ppt_x") + _anim(ids, t, "ppt_y", d, "#ppt_y+.1", "#ppt_y"))
    if e.kind == "wipe":
        return _set_visible(ids, t) + _effect_filter(ids, t, d, WIPE_FILTER[e.sub])
    if e.kind == "zoom":
        return (_set_visible(ids, t) + _anim(ids, t, "ppt_w", d, 0, "#ppt_w") + _anim(ids, t, "ppt_h", d, 0, "#ppt_h")
                + _effect_filter(ids, t, d, "fade"))
    if e.kind == "spinner":
        return (_set_visible(ids, t) + _anim(ids, t, "ppt_w", d, 0, "#ppt_w") + _anim(ids, t, "ppt_h", d, 0, "#ppt_h")
                + _anim(ids, t, "style.rotation", d, 90, 0) + _effect_filter(ids, t, d, "fade"))
    if e.kind == "grow":
        rev = ' autoRev="1"' if e.auto_rev else ""
        s = e.scale * 1000
        return (f'<p:animScale><p:cBhvr><p:cTn id="{ids()}" dur="{d}"{rev} fill="hold"/>{t}</p:cBhvr>'
                f'<p:by x="{s}" y="{s}"/></p:animScale>')
    if e.kind == "pulse":
        return (_effect_filter(ids, t, d, "fade", "out", "0, 0; .2, .5; .8, .5; 1, 0")
                + f'<p:animScale><p:cBhvr><p:cTn id="{ids()}" dur="{d // 2}" autoRev="1" fill="hold"/>{t}</p:cBhvr>'
                '<p:by x="105000" y="105000"/></p:animScale>')
    if e.kind == "spin":
        return (f'<p:animRot by="21600000"><p:cBhvr><p:cTn id="{ids()}" dur="{d}" fill="hold"/>{t}'
                '<p:attrNameLst><p:attrName>r</p:attrName></p:attrNameLst></p:cBhvr></p:animRot>')
    raise ValueError(e.kind)


class Seq:
    """The slide's main animation sequence: click groups, each a chain of after-previous steps of with-previous
    effects (PowerPoint's own structure)."""

    def __init__(self):
        self.groups: list[dict] = []

    def click(self, e: Effect) -> "Seq":
        self.groups.append({"auto": False, "steps": [[e]]})
        return self

    def after(self, e: Effect) -> "Seq":
        if not self.groups:
            self.groups.append({"auto": True, "steps": [[e]]})
        else:
            self.groups[-1]["steps"].append([e])
        return self

    def with_(self, e: Effect) -> "Seq":
        self.groups[-1]["steps"][-1].append(e)
        return self

    def xml(self) -> str:
        if not self.groups:
            return ""
        ids, grp, bld = Ids(), {}, {}
        ids(), ids()  # 1 = tmRoot, 2 = mainSeq
        parts = []
        for g in self.groups:
            gid = ids()
            cond = '<p:cond delay="indefinite"/>'
            if g["auto"]:
                cond += '<p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond>'
            steps, offset = [], 0
            for k, step in enumerate(g["steps"]):
                sid = ids()
                effs = []
                for j, e in enumerate(step):
                    node = "withEffect" if j else ("afterEffect" if (k or g["auto"]) else "clickEffect")
                    pid, pcls, subs = PRESETS[e.kind]
                    g = grp.setdefault(e.spid, {"n": 0})  # one build group per effect; one per paragraph build
                    if e.para is not None or e.chart:
                        if "p" not in g:
                            g["p"], g["n"] = g["n"], g["n"] + 1
                        gi = g["p"]
                    else:
                        gi, g["n"] = g["n"], g["n"] + 1
                    bld[(e.spid, gi)] = e
                    cid = ids()
                    effs.append(f'<p:par><p:cTn id="{cid}" presetID="{pid}" presetClass="{pcls}" '
                                f'presetSubtype="{subs[e.sub]}" fill="hold" grpId="{gi}" nodeType="{node}">'
                                f'<p:stCondLst><p:cond delay="{e.delay}"/></p:stCondLst>'
                                f'<p:childTnLst>{_behaviours(e, ids)}</p:childTnLst></p:cTn></p:par>')
                steps.append(f'<p:par><p:cTn id="{sid}" fill="hold"><p:stCondLst><p:cond delay="{offset}"/>'
                             f'</p:stCondLst><p:childTnLst>{"".join(effs)}</p:childTnLst></p:cTn></p:par>')
                offset += max(e.total for e in step)
            parts.append(f'<p:par><p:cTn id="{gid}" fill="hold"><p:stCondLst>{cond}</p:stCondLst>'
                         f'<p:childTnLst>{"".join(steps)}</p:childTnLst></p:cTn></p:par>')
        blds = []
        for (spid, gi), e in sorted(bld.items()):
            tag = e.shape._element.tag
            if e.chart:
                blds.append(f'<p:bldGraphic spid="{spid}" grpId="{gi}"><p:bldSub><a:bldChart bld="category"/>'
                            '</p:bldSub></p:bldGraphic>')
            elif tag == qn("p:sp"):
                kind = ' build="p"' if e.para is not None else ' animBg="1"'
                blds.append(f'<p:bldP spid="{spid}" grpId="{gi}"{kind}/>')
        bl = f'<p:bldLst>{"".join(blds)}</p:bldLst>' if blds else ""
        return (f'<p:timing xmlns:p="{NS_P}" xmlns:a="{NS_A}"><p:tnLst><p:par>'
                '<p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>'
                '<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>'
                f'{"".join(parts)}</p:childTnLst></p:cTn>'
                '<p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
                '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst>'
                f'</p:seq></p:childTnLst></p:cTn></p:par></p:tnLst>{bl}</p:timing>')


def transition_xml(morph: bool, ms: int = 1250) -> str:
    if not morph:
        return f'<p:transition xmlns:p="{NS_P}" spd="med"><p:fade/></p:transition>'
    return (f'<mc:AlternateContent xmlns:mc="{NS_MC}" xmlns:p="{NS_P}">'
            f'<mc:Choice xmlns:p14="{NS_P14}" xmlns:p159="{NS_P159}" Requires="p159">'
            f'<p:transition spd="slow" p14:dur="{ms}"><p159:morph option="byObject"/></p:transition></mc:Choice>'
            '<mc:Fallback><p:transition spd="slow"><p:fade/></p:transition></mc:Fallback></mc:AlternateContent>')


# ---------------------------------------------------------------- shapes


def _color(fmt, theme, bright: float = 0.0):
    fmt.theme_color = theme
    if bright:
        fmt.brightness = bright


def shape(slide, name, kind, x, y, w, h, fill=None, fill_b=0.0, line=None, line_w=0.0, rot=0.0):
    s = slide.shapes.add_shape(kind, I(x), I(y), I(w), I(h))
    s.name = name
    if fill is None:
        s.fill.background()
    else:
        s.fill.solid()
        _color(s.fill.fore_color, fill, fill_b)
    if line is None:
        s.line.fill.background()
    else:
        _color(s.line.color, line)
        s.line.width = Pt(line_w or 1)
    if rot:
        s.rotation = rot
    # no shadow from the default shape style
    style = s._element.find(qn("p:style"))
    if style is not None:
        s._element.remove(style)
    return s


def text(shp, paras, size=18, color=TX1, bold=False, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, heading=False,
         bullets=False, margin=0.08, spacing=0):
    """paras: list of strings or (string, size, bold, color) tuples."""
    tf = shp.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for side in ("left", "right", "top", "bottom"):
        setattr(tf, f"margin_{side}", I(margin))
    for i, p in enumerate(paras):
        t, sz, b, c = (p, size, bold, color) if isinstance(p, str) else p
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = align
        if spacing:
            para.space_after = Pt(spacing)
        r = para.add_run()
        r.text = t
        f = r.font
        f.size, f.bold = Pt(sz), b
        f.name = "+mj-lt" if heading else "+mn-lt"
        _color(f.color, c)
        if bullets:
            pPr = para._p.get_or_add_pPr()
            pPr.set("marL", str(I(0.4)))
            pPr.set("indent", str(-I(0.4)))
            for x in (f'<a:buClr xmlns:a="{NS_A}"><a:schemeClr val="accent1"/></a:buClr>',
                      f'<a:buFont xmlns:a="{NS_A}" typeface="Arial"/>', f'<a:buChar xmlns:a="{NS_A}" char="&#8226;"/>'):
                pPr.append(etree.fromstring(x))
    return shp


def box(slide, name, x, y, w, h, paras, kind=MSO_SHAPE.ROUNDED_RECTANGLE, fill=None, fill_b=0.0, line=None,
        line_w=0.0, **kw):
    s = shape(slide, name, kind, x, y, w, h, fill, fill_b, line, line_w)
    if kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = 0.12
    return text(s, paras, **kw)


def label(slide, name, x, y, w, h, paras, **kw):
    s = slide.shapes.add_textbox(I(x), I(y), I(w), I(h))
    s.name = name
    return text(s, paras, **kw)


def arrow(slide, name, x1, y1, x2, y2, color=TX2, width=2.25, begin=None, end=None):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, I(x1), I(y1), I(x2), I(y2))
    c.name = name
    if begin is not None:
        c.begin_connect(*begin)
    if end is not None:
        c.end_connect(*end)
    _color(c.line.color, color)
    c.line.width = Pt(width)
    ln = c.line._get_or_add_ln()
    ln.append(etree.fromstring(f'<a:tailEnd xmlns:a="{NS_A}" type="triangle" w="med" len="med"/>'))
    style = c._element.find(qn("p:style"))
    if style is not None:
        c._element.remove(style)
    return c


# ---------------------------------------------------------------- deck


@dataclass
class Deck:
    prs: object
    picture: bytes
    slides: list = field(default_factory=list)  # (slide, Seq, morph, morph_ms)

    def new(self, layout=6, morph=False, ms=1250, notes=""):
        s = self.prs.slides.add_slide(self.prs.slide_layouts[layout])
        seq = Seq()
        self.slides.append((s, seq, morph, ms))
        if notes:
            s.notes_slide.notes_text_frame.text = notes
        return s, seq


def title(slide, words, name="Title", size=32, x=0.6, y=0.35, w=12.13, h=0.9):
    t = slide.shapes.title
    t.name = name
    t.left, t.top, t.width, t.height = I(x), I(y), I(w), I(h)
    tf = t.text_frame
    tf.text = words
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    f = p.runs[0].font
    f.size, f.bold, f.name = Pt(size), True, "+mj-lt"
    _color(f.color, TX1)
    return t


def title_bar(slide):
    return shape(slide, "Title bar", MSO_SHAPE.RECTANGLE, 0.6, 1.25, 1.1, 0.07, fill=A1)


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
        ("Fill in", "Click any 'Your …' text and type. Delete the slides you do not need."),
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


# ---------------------------------------------------------------- package


def _theme(prs, key: str):
    name, _, hexes = PALETTES[key]
    h = hexes.split()
    part = prs.slide_master.part.part_related_by(RT.THEME)
    root = etree.fromstring(part.blob)
    a = f"{{{NS_A}}}"
    root.set("name", f"BizDev {name}")
    cs = root.find(f".//{a}clrScheme")
    cs.set("name", f"BizDev {name}")
    for slot, val in zip(("dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5",
                          "accent6", "hlink", "folHlink"), h, strict=True):
        el = cs.find(a + slot)
        for c in list(el):
            el.remove(c)
        etree.SubElement(el, a + "srgbClr").set("val", val)
    fs = root.find(f".//{a}fontScheme")
    fs.set("name", "BizDev")
    fs.find(f"{a}majorFont/{a}latin").set("typeface", "Calibri Light")
    fs.find(f"{a}minorFont/{a}latin").set("typeface", "Calibri")
    part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


def _widen_master(prs):
    """The python-pptx default master and layouts are 4:3: stretch their placeholders to 16:9."""
    k = 13.333 / 10.0
    for el in [prs.slide_master._element] + [lay._element for lay in prs.slide_layouts]:
        for off in el.iter(qn("a:off")):
            off.set("x", str(int(int(off.get("x")) * k)))
        for ext in el.iter(qn("a:ext")):
            if ext.get("cx") is not None:
                ext.set("cx", str(int(int(ext.get("cx")) * k)))


def _normalise_xlsx(blob: bytes) -> bytes:
    zin = zipfile.ZipFile(io.BytesIO(blob))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename == "docProps/core.xml":
                data = re.sub(rb"(<dcterms:(created|modified)[^>]*>)[^<]*", rb"\g<1>2026-11-06T09:00:00Z", data)
            zo.writestr(zipfile.ZipInfo(info.filename, ZIP_TIME), data, zipfile.ZIP_DEFLATED)
    return out.getvalue()


def build(key: str = "default") -> bytes:
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)
    _widen_master(prs)
    _theme(prs, key)
    dk = Deck(prs, picture_png())
    s_title(dk)
    s_agenda(dk, 0, build=True)
    s_section(dk, 0)
    s_agenda(dk, 1, build=False)
    s_section(dk, 1)
    s_bullets(dk)
    s_zoom(dk, False)
    s_zoom(dk, True)
    s_flow_build(dk)
    for i in range(4):
        s_flow_morph(dk, i)
    s_timeline_build(dk)
    for k, c in enumerate((1, 2, 3)):
        s_timeline_morph(dk, c, first=k == 0)
    s_cycle_build(dk)
    for i in range(4):
        s_cycle_morph(dk, i)
    s_compare(dk, False)
    s_compare(dk, True)
    s_kpi(dk)
    s_chart(dk)
    s_closing(dk)
    s_how(dk)
    s_colours(dk, PALETTES[key][0])
    for slide, seq, morph, ms in dk.slides:
        el = slide._element
        el.append(etree.fromstring(transition_xml(morph, ms)))
        tx = seq.xml()
        if tx:
            el.append(etree.fromstring(tx))
    cp = prs.core_properties
    cp.title, cp.author, cp.last_modified_by = "Animated template", "BizDev", "BizDev"
    cp.subject, cp.keywords, cp.revision = "Fill-in template with Morph and animations", "template", 1
    cp.created = cp.modified = FIXED
    cp.last_printed = FIXED
    for part in prs.part.package.iter_parts():
        if part.partname.endswith(".xlsx"):
            part._blob = _normalise_xlsx(part.blob)
    buf = io.BytesIO()
    prs.save(buf)
    return _normalise_zip(buf.getvalue())


def _normalise_zip(blob: bytes) -> bytes:
    zin = zipfile.ZipFile(io.BytesIO(blob))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
        for info in zin.infolist():
            zi = zipfile.ZipInfo(info.filename, ZIP_TIME)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zo.writestr(zi, zin.read(info.filename))
    return out.getvalue()


# ---------------------------------------------------------------- checks


COLOUR_TAGS = ("srgbClr", "sysClr", "scrgbClr", "hslClr", "prstClr")


def check(blob: bytes) -> list[str]:
    """Problems in a built template (empty: fine): zip and XML well-formed, opens in python-pptx, no fixed colours
    on slides and charts, timing targets exist, morph names pair up."""
    problems = []
    z = zipfile.ZipFile(io.BytesIO(blob))
    if z.testzip() is not None:
        problems.append("zip CRC error")
    for n in z.namelist():
        if n.endswith((".xml", ".rels")):
            try:
                etree.fromstring(z.read(n))
            except etree.XMLSyntaxError as e:
                problems.append(f"{n}: {e}")
    prs = Presentation(io.BytesIO(blob))
    for n in z.namelist():
        if re.match(r"ppt/(slides/slide\d+|charts/chart\d+)\.xml$", n):
            x = z.read(n).decode()
            for tag in COLOUR_TAGS:
                if f":{tag} " in x or f":{tag}>" in x:
                    problems.append(f"{n}: fixed colour <{tag}>")
            for m in re.finditer(r'typeface="([^"]+)"', x):
                if m.group(1) not in ("+mj-lt", "+mn-lt", "Arial"):  # Arial: the bullet glyph only
                    problems.append(f"{n}: fixed font {m.group(1)}")
    prev_names: set[str] = set()
    prev_kinds: dict[str, str] = {}
    morph_count = 0
    all_names: dict[str, int] = {}
    for idx, slide in enumerate(prs.slides, 1):
        el = slide._element
        ids = {int(sp.get("id")) for sp in el.iter(qn("p:cNvPr"))}
        for t in el.iter(f"{{{NS_P}}}spTgt"):
            if int(t.get("spid")) not in ids:
                problems.append(f"slide {idx}: animation targets missing shape {t.get('spid')}")
        for b in list(el.iter(qn("p:bldP"))) + list(el.iter(qn("p:bldGraphic"))):
            if int(b.get("spid")) not in ids:
                problems.append(f"slide {idx}: build list names missing shape {b.get('spid')}")
        ctn = [c.get("id") for c in el.iter(qn("p:cTn"))]
        if len(ctn) != len(set(ctn)):
            problems.append(f"slide {idx}: repeated timing ids")
        kinds = {}
        for nv in el.iter(qn("p:cNvPr")):
            nm = nv.get("name", "")
            if nm.startswith("!!"):
                if nm in kinds:
                    problems.append(f"slide {idx}: two shapes named {nm}")
                kinds[nm] = etree.QName(nv.getparent().getparent()).localname
        morph = el.find(f".//{{{NS_P159}}}morph") is not None
        if morph:
            morph_count += 1
            shared = set(kinds) & prev_names
            if not shared:
                problems.append(f"slide {idx}: Morph slide shares no !! name with the slide before")
            for nm in shared:
                if kinds[nm] != prev_kinds[nm]:
                    problems.append(f"slide {idx}: {nm} is a {kinds[nm]} here, a {prev_kinds[nm]} before")
            for nm in set(kinds) | prev_names:  # on a Morph slide or on the slide it morphs from
                all_names[nm] = all_names.get(nm, 0) + 1
        for nm in kinds:
            all_names.setdefault(nm, 0)
        prev_names, prev_kinds = set(kinds), kinds
    for nm, n in all_names.items():
        if n == 0:
            problems.append(f"{nm}: a !! name that no Morph slide carries over")
    if not morph_count:
        problems.append("no Morph slides")
    return problems


def xml_parts(blob: bytes) -> dict[str, bytes]:
    z = zipfile.ZipFile(io.BytesIO(blob))
    return {n: z.read(n) for n in z.namelist() if n.endswith((".xml", ".rels"))}


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
