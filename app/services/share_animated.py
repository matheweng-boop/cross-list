"""Animated presentation of a Shareable document (owner, 6 Nov 2026: "make it shareable presentations as
animations"): the same slides as Create PowerPoint (the report's share_slides list: same words, same depth), laid
out with the animated template's look (app/services/pptx_anim.py, theme colours, Harbor colours) and moving:

    title (zooms in) -> agenda -> Morph into each section's divider (the agenda returns between sections when there
    are at most five) -> the section's slides (bullets float in one by one, the block diagram builds group by group
    with its connections wiping in and our parts pulsing, tables fade in, tiles zoom, columns and cards fly in)
    -> closing.

Like every Shareable output it carries no reference to the site; the caller runs the public-safe word check."""

import io
import re
from datetime import date, datetime

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

from app.services import pptx_anim as pa
from app.services.pptx_anim import A1, A2, BG1, BG2, TX1, TX2, Deck, Effect, I, box, label, shape, title
from app.services.pptx_template import PALETTES

MEDIA_TYPE = pa.MEDIA_TYPE
AUTHOR = "Skyworks + Qorvo"
MAX_RETURNS = 5  # sections up to which the agenda comes back before each one


def filename(key: str) -> str:
    return "skyworks-qorvo-" + re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-") + "-animated.pptx"


def _date(d) -> str:
    return f"{d.day} {d:%b %Y}" if isinstance(d, date) else str(d or "")


def _base(t: str) -> str:
    return re.sub(r"\s*\(continued\)\s*$", "", t or "").strip()


def _fit(texts, base: float, chars: int) -> float:
    n = sum(len(str(t)) for t in texts)
    return base if n <= chars else max(12.0, round(base * (chars / n) ** 0.5))


class _Builder:
    def __init__(self, deck_title: str, today):
        name, _, hexes = PALETTES["default"]
        self.dk = Deck(pa.new_presentation(name, hexes))
        self.deck_title, self.today = deck_title, today
        self.n = 0

    # ---- frame
    def content(self, words: str, morph=False):
        s, q = self.dk.new(5, morph=morph)
        self.n += 1
        title(s, words, size=30 if len(words) < 50 else 24)
        pa.title_bar(s)
        label(s, "Footer", 0.6, 7.0, 10.5, 0.35, [f"{self.deck_title} · {_date(self.today)} · Public information"],
              size=10, color=TX2)
        return s, q

    # ---- title, agenda, sections, closing
    def cover(self, b: dict):
        s, q = self.dk.new(0)
        t = s.shapes.title
        t.name = "Title"
        t.left, t.top, t.width, t.height = I(0.9), I(1.9), I(8.2), I(2.1)
        t.text_frame.text = b.get("heading") or self.deck_title
        t.text_frame.vertical_anchor = MSO_ANCHOR.BOTTOM
        p = t.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        f = p.runs[0].font
        f.size, f.bold, f.name = Pt(40 if len(t.text_frame.text) < 45 else 32), True, "+mj-lt"
        pa._color(f.color, TX1)
        sub = s.placeholders[1]
        sub.name = "Subtitle"
        sub.left, sub.top, sub.width, sub.height = I(0.9), I(4.2), I(8.2), I(1.2)
        sub.text_frame.text = " · ".join(x for x in (b.get("sub", ""), _date(b.get("date") or self.today)) if x)
        p = sub.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        f = p.runs[0].font
        f.size, f.name = Pt(20), "+mn-lt"
        pa._color(f.color, TX2)
        bar = shape(s, "Accent bar", MSO_SHAPE.RECTANGLE, 0.9, 1.7, 1.6, 0.1, fill=A1)
        c1 = shape(s, "Circle large", MSO_SHAPE.OVAL, 9.6, 1.4, 3.2, 3.2, fill=A1)
        c2 = shape(s, "Circle small", MSO_SHAPE.OVAL, 11.1, 4.3, 1.6, 1.6, fill=A2)
        q.after(Effect("wipe", bar, 500, sub="left"))
        q.after(Effect("zoom", t, 700)).with_(Effect("zoom", c1, 700)).with_(Effect("zoom", c2, 600, delay=200))
        q.after(Effect("float", sub, 600))

    def agenda(self, sections: list[str], active: int, build: bool):
        s, q = self.dk.new(5)  # back to the agenda with a fade; the section after it is the Morph
        title(s, "Agenda")
        pa.title_bar(s)
        n = len(sections)
        step = min(1.2, 5.3 / n)
        d = min(0.85, step - 0.15)
        y0 = 1.6
        panel = shape(s, "!!Panel", MSO_SHAPE.ROUNDED_RECTANGLE, 0.7, y0 - 0.08 + active * step, 11.0, d + 0.16,
                      fill=BG2)
        panel.adjustments[0] = 0.18
        for i, words in enumerate(sections):
            y = y0 + i * step
            done = i < active and not build
            num = box(s, f"!!Num{i + 1}", 1.0, y, d, d, [f"{i + 1:02d}"], kind=MSO_SHAPE.OVAL, fill=A1,
                      fill_b=0.6 if done else 0.0, size=18 if d > 0.6 else 14, bold=True, color=TX1 if done else BG1,
                      align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, heading=True, margin=0)
            lab = label(s, f"!!Label{i + 1}", 2.1, y, 9.4, d, [words], size=24 if n <= 5 else 20,
                        color=TX2 if done else TX1, anchor=MSO_ANCHOR.MIDDLE, heading=True)
            if build:
                q.after(Effect("zoom", num, 400)).with_(Effect("fly", lab, 500, sub="left"))

    def section(self, i: int, words: str, morph: bool):
        s, q = self.dk.new(6, morph=morph)
        shape(s, "!!Panel", MSO_SHAPE.ROUNDED_RECTANGLE, -0.3, -0.3, 5.6, 8.1, fill=A1).adjustments[0] = 0.04
        num = box(s, f"!!Num{i + 1}", 1.0, 1.95, 3.2, 3.2, [f"{i + 1:02d}"], kind=MSO_SHAPE.OVAL, fill=BG1, size=96,
                  bold=True, color=A1, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, heading=True, margin=0)
        lab = label(s, f"!!Label{i + 1}", 6.0, 2.0, 6.8, 2.6, [words], size=40 if len(words) < 40 else 32,
                    anchor=MSO_ANCHOR.MIDDLE, heading=True, bold=True)
        if not morph:  # a divider the agenda does not lead into
            q.after(Effect("zoom", num, 600)).with_(Effect("float", lab, 600))

    def closing(self):
        s, q = self.dk.new(0)
        t = s.shapes.title
        t.name = "Title"
        t.left, t.top, t.width, t.height = I(0.9), I(2.2), I(8.0), I(1.6)
        t.text_frame.text = "Thank you"
        t.text_frame.vertical_anchor = MSO_ANCHOR.BOTTOM
        p = t.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        f = p.runs[0].font
        f.size, f.bold, f.name = Pt(54), True, "+mj-lt"
        pa._color(f.color, TX1)
        sub = s.placeholders[1]
        sub.name = "Subtitle"
        sub.left, sub.top, sub.width, sub.height = I(0.9), I(4.0), I(8.0), I(1.0)
        sub.text_frame.text = f"Questions? · {self.deck_title}"
        p = sub.text_frame.paragraphs[0]
        p.alignment = PP_ALIGN.LEFT
        f = p.runs[0].font
        f.size, f.name = Pt(22), "+mn-lt"
        pa._color(f.color, TX2)
        c1 = shape(s, "Circle large", MSO_SHAPE.OVAL, 9.4, 1.6, 3.2, 3.2, fill=A1)
        c2 = shape(s, "Circle small", MSO_SHAPE.OVAL, 8.8, 4.6, 1.6, 1.6, fill=A2)
        q.after(Effect("zoom", t, 600)).with_(Effect("zoom", c1, 600)).with_(Effect("zoom", c2, 500, delay=150))
        q.after(Effect("float", sub, 600))

    # ---- bodies
    def lead(self, s, q, words: str, y: float = 1.5) -> float:
        if not words:
            return y
        h = 0.5 if len(words) < 95 else 0.85
        ld = label(s, "Lead", 0.6, y, 12.1, h, [words], size=18, color=TX2)
        q.after(Effect("fade", ld, 500))
        return y + h + 0.15

    def notes(self, s, lines: list[str], bottom: float = 6.9) -> float:
        lines = [x for x in lines if x]
        if not lines:
            return bottom
        h = 0.28 * len(lines) + 0.1
        label(s, "Notes", 0.6, bottom - h, 12.1, h, [(x, 11, False, TX2) for x in lines])
        return bottom - h - 0.1

    def bullets(self, sl: dict):
        b = sl.get("body") or {}
        s, q = self.content(sl.get("title", ""))
        y = self.lead(s, q, b.get("lead", ""))
        bottom = self.notes(s, list(b.get("note") or []))
        pts = [str(p) for p in b.get("points") or []]
        if not pts:
            return
        size = _fit(pts, 22, 900)
        body = label(s, "Points", 0.8, y + 0.1, 11.8, bottom - y - 0.1, pts, size=size, bullets=True,
                     spacing=size * 0.6)
        for i in range(len(pts)):
            (q.click if i < 8 else q.after)(Effect("float", body, 600, para=i))

    def table(self, sl: dict):
        b = sl.get("body") or {}
        cols, rows = list(b.get("cols") or []), [list(r) for r in b.get("rows") or []]
        s, q = self.content(sl.get("title", ""))
        y = self.lead(s, q, b.get("lead", ""))
        bottom = self.notes(s, [b.get("note", "")])
        if not cols:
            return
        longest = max((sum(len(str(c)) for c in r) for r in rows), default=0)
        chars = sum(len(str(c)) for r in rows for c in r)
        size = 16.0 if longest < 70 and len(rows) <= 5 else 14.0 if longest < 150 or chars < 950 else 12.0
        width = 12.13
        row_h = 0.5 if size >= 14 else 0.42
        gf = s.shapes.add_table(len(rows) + 1, len(cols), I(0.6), I(y), I(width),
                                I(min(bottom - y, row_h * (len(rows) + 1))))
        gf.name = "Table"
        t = gf.table
        widths = [float(x) for x in b.get("widths") or []]
        if len(widths) != len(cols):
            widths = [1.0] * len(cols)
        for i, x in enumerate(widths):
            t.columns[i].width = Emu(int(I(width) * x / sum(widths)))
        who_cols = set(b.get("who_cols") or [])
        for r in range(len(rows) + 1):
            t.rows[r].height = I(row_h)
            for c in range(len(cols)):
                cell = t.cell(r, c)
                cell.margin_left = cell.margin_right = I(0.08)
                cell.margin_top = cell.margin_bottom = I(0.04)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                words = str(cols[c] if r == 0 else (rows[r - 1][c] if c < len(rows[r - 1]) else ""))
                if r and c in who_cols:  # "Skyworks · IP: Skyworks-led": the company, then its tag
                    who, _, tag = words.partition(" · ")
                    words = f"{who}  {tag}" if tag else who
                cell.text = words
                for p in cell.text_frame.paragraphs:
                    for run in p.runs:
                        run.font.size = Pt(size * (0.9 if r == 0 else 1))
                        run.font.bold = r == 0 or c == 0
        q.after(Effect("fade", gf, 600))

    def glance(self, sl: dict):
        b = sl.get("body") or {}
        s, q = self.content(sl.get("title", ""))
        y = max(self.lead(s, q, b.get("lead", "")), 2.3)
        facts = b.get("facts") or []
        n = max(1, len(facts))
        gap = 0.25
        tw = (12.13 - gap * (n - 1)) / n
        th = 2.3 if any(f.get("note") for f in facts) else 1.9
        for i, f in enumerate(facts):
            paras = [(str(f.get("num", "")), 36 if n <= 4 else 28, True, A1), (str(f.get("label", "")), 15, False, TX1)]
            if f.get("note"):
                paras.append((str(f["note"]), 11, False, TX2))
            tile = box(s, f"Tile {i + 1}", 0.6 + i * (tw + gap), y, tw, th, paras, fill=BG2, anchor=MSO_ANCHOR.MIDDLE,
                       margin=0.15, spacing=3)
            q.after(Effect("zoom", tile, 500))
        if b.get("pairs"):
            pr = label(s, "Pairs", 0.6, y + th + 0.35, 12.1, 1.6,
                       [("Where the two combine: ", 16, True, TX1), (" · ".join(b["pairs"]), 15, False, TX1)])
            q.click(Effect("float", pr, 600))

    def cols(self, sl: dict):
        b = sl.get("body") or {}
        s, q = self.content(sl.get("title", ""))
        y = self.lead(s, q, b.get("lead", ""))
        bottom = self.notes(s, [b.get("note", "")])
        cols = b.get("cols") or []
        n = max(1, len(cols))
        gap = 0.3
        cw = (12.13 - gap * (n - 1)) / n
        most = max((len(c.get("items") or []) for c in cols), default=1)
        size = 15 if most <= 5 else 13 if most <= 7 else 12
        for i, c in enumerate(cols):
            x = 0.6 + i * (cw + gap)
            head = box(s, f"Head {i + 1}", x, y, cw, 0.55, [(str(c.get("head", "")), 18, True, BG1)], fill=A1,
                       anchor=MSO_ANCHOR.MIDDLE, margin=0.12)
            paras = ([(str(c["line"]), 12, False, TX2)] if c.get("line") else [])
            items = ["  ".join(str(it).partition(" · ")[::2]).strip() for it in c.get("items") or []]
            paras += [(it, size, False, TX1) for it in items]
            body = label(s, f"Items {i + 1}", x, y + 0.65, cw, bottom - y - 0.65, paras or [""], spacing=size * 0.4)
            q.click(Effect("fly", head, 500, sub="bottom")).with_(Effect("float", body, 600, delay=150))

    def pairs(self, sl: dict):
        b = sl.get("body") or {}
        s, q = self.content(sl.get("title", ""))
        y = self.lead(s, q, b.get("lead", ""))
        bottom = self.notes(s, [b.get("note", "")])
        items = b.get("items") or []
        gap = 0.18
        ch = min(1.55, (bottom - y - gap * (len(items) - 1)) / max(1, len(items)))
        for i, it in enumerate(items):
            top = y + i * (ch + gap)
            paras = [(f"{it.get('n', i + 1)}.  Skyworks {it.get('skyworks', '')}  +  Qorvo {it.get('qorvo', '')}",
                      16, True, TX1), (str(it.get("line", "")), 13, False, TX1)]
            if it.get("ex"):
                paras.append((f"{it.get('ex_word', 'For example')} " + " with ".join(it["ex"]), 11, False, TX2))
            card = box(s, f"Card {i + 1}", 0.6, top, 9.6, ch, paras, fill=BG2, anchor=MSO_ANCHOR.MIDDLE, margin=0.2,
                       spacing=2)
            ben = box(s, f"Benefit {i + 1}", 10.35, top, 2.38, ch, [(str(it.get("benefit", "")), 13, True, BG1)],
                      fill=A1, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, margin=0.12)
            q.click(Effect("fly", card, 500, sub="left")).after(Effect("zoom", ben, 400))

    def sysdiagram(self, sl: dict):
        """The system brief's block diagram (share_diagram layout) as theme-coloured shapes: each group builds on a
        click (its frame fades in, its blocks zoom in), then the connections wipe in, then our parts pulse."""
        b = sl.get("body") or {}
        lay = b["layout"]
        s, q = self.content(sl.get("title", ""))
        y = self.lead(s, q, b.get("lead", ""))
        left, top, width, height = 0.6, y + 0.05, 12.13, 6.85 - y - 0.05
        k = min(width / lay["w"], height / lay["h"])
        ox, oy = left + (width - lay["w"] * k) / 2, top + (height - lay["h"] * k) / 2
        groups = [sh for sh in lay["shapes"] if sh["t"] == "rect" and "mark" not in sh]

        def owner(x, y):
            for gi, g in enumerate(groups):
                if g["x"] <= x <= g["x"] + g["w"] and g["y"] <= y <= g["y"] + g["h"]:
                    return gi
            return None

        steps: dict = {}
        arrows, ours = [], []
        colours = {"#FFFFFF": BG1, "#0B6B74": A1, "#1B1F27": TX1}
        for n, sh in enumerate(lay["shapes"], 1):
            if sh["t"] == "rect":
                X, Y, Wd, Ht = ox + sh["x"] * k, oy + sh["y"] * k, sh["w"] * k, sh["h"] * k
                mark = sh.get("mark")
                if mark is None:
                    shp = shape(s, f"Group {n}", MSO_SHAPE.ROUNDED_RECTANGLE, X, Y, Wd, Ht, fill=BG2)
                    kind = "frame"
                else:
                    shp = shape(s, f"Block {n}", MSO_SHAPE.ROUNDED_RECTANGLE, X, Y, Wd, Ht,
                                fill=A1 if mark == "core" else BG1, line=A1 if mark else TX2,
                                line_w=2.25 if mark == "peripheral" else 0.75)
                    kind = "block"
                    if mark in ("core", "peripheral"):
                        ours.append(shp)
                shp.adjustments[0] = min(0.5, sh.get("r", 4) / max(1.0, min(sh["w"], sh["h"])))
                key = owner(sh["x"] + sh["w"] / 2, sh["y"] + sh["h"] / 2)
                steps.setdefault(key, []).append((kind, shp))
            elif sh["t"] == "text":
                size = sh["size"] * k * 72
                w = (lay["w"] / 2) * k if sh["anchor"] == "middle" else len(sh["s"]) * sh["size"] * 0.62 * k + 0.1
                X = ox + sh["x"] * k - (w / 2 if sh["anchor"] == "middle" else 0)
                Y = oy + (sh["y"] - sh["size"] * 0.95) * k
                tb = label(s, f"Text {n}", X, Y, w, sh["size"] * 1.25 * k, [sh["s"]], size=size, bold=sh["bold"],
                           color=colours.get(sh["color"], TX2), margin=0,
                           align=PP_ALIGN.CENTER if sh["anchor"] == "middle" else PP_ALIGN.LEFT)
                tb.text_frame.word_wrap = False
                steps.setdefault(owner(sh["x"], sh["y"] - sh["size"] / 3), []).append(("text", tb))
            elif sh["t"] == "arrow":
                x1, y1, x2, y2 = (ox + sh["x1"] * k, oy + sh["y1"] * k, ox + sh["x2"] * k, oy + sh["y2"] * k)
                if abs(y2 - y1) < 0.001:
                    y2 += 0.001
                if abs(x2 - x1) < 0.001:
                    x2 += 0.001
                c = pa.arrow(s, f"Connection {n}", x1, y1, x2, y2, color=TX2, width=1.75)
                horiz = abs(x2 - x1) >= abs(y2 - y1)
                arrows.append((c, ("left" if x2 > x1 else "right") if horiz else ("top" if y2 > y1 else "bottom")))
        for key in [i for i in range(len(groups)) if i in steps] + ([None] if None in steps else []):
            for j, (kind, shp) in enumerate(steps[key]):  # a group on a click; the legend after the last group
                e = Effect("fade" if kind != "block" else "zoom", shp, 400 if kind != "block" else 500,
                           delay=0 if kind == "frame" else min(600, 40 * j))
                (q.with_ if j else q.click if key is not None else q.after)(e)
        for j, (c, way) in enumerate(arrows):
            e = Effect("wipe", c, 500, sub=way, delay=min(600, 100 * j))
            (q.with_ if j else q.click)(e)
        for j, shp in enumerate(ours):
            (q.with_ if j else q.click)(Effect("grow", shp, 300, scale=108, auto_rev=True))

    def build(self, slides: list[dict]) -> bytes:
        cover = next((sl for sl in slides if sl.get("kind") == "title"), None)
        self.cover((cover or {}).get("body") or {"heading": self.deck_title})
        rest = [sl for sl in slides if sl.get("kind") != "title"]
        sections: list[tuple[str, list[dict]]] = []
        for sl in rest:
            base = _base(sl.get("title", ""))
            if sections and sections[-1][0] == base:
                sections[-1][1].append(sl)
            else:
                sections.append((base, [sl]))
        names = [n for n, _ in sections]
        returns = len(sections) <= MAX_RETURNS
        if sections:
            self.agenda(names, 0, build=True)
        for i, (words, group) in enumerate(sections):
            if i and returns:
                self.agenda(names, i, build=False)
            self.section(i, words, morph=i == 0 or returns)
            for sl in group:
                make = {"bullets": self.bullets, "agenda": self.bullets, "table": self.table, "glance": self.glance,
                        "cols": self.cols, "pairs": self.pairs, "sysdiagram": self.sysdiagram}.get(sl.get("kind"))
                if make:
                    make(sl)
                else:  # a kind this deck does not lay out: its words as points
                    self.bullets({"title": sl.get("title", ""), "body": {"points": _words(sl.get("body") or {})}})
        self.closing()
        return pa.finish(self.dk, f"Skyworks + Qorvo · {self.deck_title}", AUTHOR, "Public information",
                         when=datetime(self.today.year, self.today.month, self.today.day))


def _words(b: dict) -> list[str]:
    out = []
    for v in b.values():
        if isinstance(v, str) and v.strip():
            out.append(v)
        elif isinstance(v, list):
            out += [x for x in v if isinstance(x, str) and x.strip()]
    return out[:10]


def build(slides: list[dict], deck_title: str, today: date | None = None) -> bytes:
    """The animated .pptx of one Shareable document's slides (its ShareReport.slides(...) list)."""
    today = today or date.today()
    return _Builder(deck_title, today).build(slides)


def texts(data: bytes) -> list[str]:
    """Every text in the deck (shapes, tables, notes) and its document properties, for the word check."""
    prs = Presentation(io.BytesIO(data))
    out = [prs.core_properties.title or "", prs.core_properties.author or "", prs.core_properties.subject or ""]
    for slide in prs.slides:
        for sh in slide.shapes:
            if sh.has_text_frame:
                out.append(sh.text_frame.text)
            if getattr(sh, "has_table", False) and sh.has_table:
                out += [c.text for row in sh.table.rows for c in row.cells]
        if slide.has_notes_slide:
            out.append(slide.notes_slide.notes_text_frame.text)
    return out
