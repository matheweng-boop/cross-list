"""Animated PowerPoint building blocks (owner, 6 Nov 2026): standard animation presets as p:timing XML, the Morph
transition, theme-coloured shapes and text, the theme colour block, a deterministic save and the checks. Used by the
fill-in template (scripts/build_pptx_template.py) and the animated Shareable decks (app/services/share_animated.py).

Rules: every shape, line and text uses theme colours (bg1/tx1/bg2/tx2, accent1-6) and theme fonts (+mj-lt/+mn-lt),
so Design > Variants > Colors recolours a whole deck. Morph: the second slide of a pair carries p159:morph inside
mc:AlternateContent with a Fade fallback; objects that travel share a name starting with "!!" on both slides.
Animations follow ECMA-376 Part 1, 19.5 (p:timing) and [MS-PPTX] (p14/p159).
"""

import io
import re
import zipfile
from dataclasses import dataclass, field
from datetime import datetime

from lxml import etree
from pptx import Presentation
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.opc.constants import RELATIONSHIP_TYPE as RT
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
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
    "wipe": (22, "entr", {"left": 8, "bottom": 4, "top": 1}),
    "wheel": (21, "entr", {"": 1}),
    "float": (42, "entr", {"": 0}),
    "spinner": (49, "entr", {"": 0}),
    "zoom": (53, "entr", {"": 16}),
    "grow": (6, "emph", {"": 0}),
    "spin": (8, "emph", {"": 0}),
    "pulse": (26, "emph", {"": 0}),
}
WIPE_FILTER = {"left": "wipe(left)", "bottom": "wipe(down)", "top": "wipe(up)"}


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
    if e.kind == "wheel":
        return _set_visible(ids, t) + _effect_filter(ids, t, d, "wheel(1)")
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


def see_through(shp, alpha: int = 60):
    """Fill opacity in percent (an alpha on the theme colour, so it still recolours)."""
    clr = shp._element.spPr.find(qn("a:solidFill")).find(qn("a:schemeClr"))
    clr.append(etree.fromstring(f'<a:alpha xmlns:a="{NS_A}" val="{alpha * 1000}"/>'))
    return shp


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
    picture: bytes = b""
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


# ---------------------------------------------------------------- package


def set_theme(prs, name: str, hexes: str):
    """The theme's colour block (dk1 lt1 dk2 lt2 accent1..6 hlink folHlink, hex) and fonts (Calibri Light / Calibri)."""
    h = hexes.split()
    part = prs.slide_master.part.part_related_by(RT.THEME)
    root = etree.fromstring(part.blob)
    a = f"{{{NS_A}}}"
    root.set("name", name)
    cs = root.find(f".//{a}clrScheme")
    cs.set("name", name)
    for slot, val in zip(("dk1", "lt1", "dk2", "lt2", "accent1", "accent2", "accent3", "accent4", "accent5",
                          "accent6", "hlink", "folHlink"), h, strict=True):
        el = cs.find(a + slot)
        for c in list(el):
            el.remove(c)
        etree.SubElement(el, a + "srgbClr").set("val", val)
    fs = root.find(f".//{a}fontScheme")
    fs.set("name", "Calibri")
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


def new_presentation(theme_name: str, hexes: str):
    """An empty 16:9 presentation with the given theme colours."""
    prs = Presentation()
    prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)
    _widen_master(prs)
    set_theme(prs, theme_name, hexes)
    return prs


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


def _normalise_zip(blob: bytes) -> bytes:
    zin = zipfile.ZipFile(io.BytesIO(blob))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
        for info in zin.infolist():
            zi = zipfile.ZipInfo(info.filename, ZIP_TIME)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zo.writestr(zi, zin.read(info.filename))
    return out.getvalue()


def finish(dk: "Deck", title: str, author: str, subject: str = "", when: datetime = FIXED) -> bytes:
    """Transitions and animations onto every slide, fixed document properties, a deterministic zip."""
    for slide, seq, morph, ms in dk.slides:
        el = slide._element
        el.append(etree.fromstring(transition_xml(morph, ms)))
        tx = seq.xml()
        if tx:
            el.append(etree.fromstring(tx))
    cp = dk.prs.core_properties
    cp.title, cp.author, cp.last_modified_by = title, author, author
    cp.subject, cp.keywords, cp.revision = subject, "", 1
    cp.created = cp.modified = cp.last_printed = when
    for part in dk.prs.part.package.iter_parts():
        if part.partname.endswith(".xlsx"):
            part._blob = _normalise_xlsx(part.blob)
    buf = io.BytesIO()
    dk.prs.save(buf)
    return _normalise_zip(buf.getvalue())


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
