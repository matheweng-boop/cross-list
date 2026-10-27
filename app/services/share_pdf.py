"""Shareable > Create PDF (owner, 26 Oct 2026: "the overall formatting between the PDF ... and what's displayed on the
screen really sucks"): a real A4 PDF per report, and for several reports in one file, made on the server with
ReportLab from the same content model as the slides and the page (app/services/share_doc.py). Built fresh on every
download from the current data and the owner's saved edits; nothing is stored.

Layout: a header band on every page ("Skyworks + Qorvo · <report>", optional logo and subtitle), a title block, section
headings, number tiles, clean tables (header row repeated after a page break, rows never split), the Skyworks /
Qorvo / Both marks right-aligned, and the footer "Public information · <date> · page n / N". No reference to the site
itself: no site name, no addresses of it, no links."""

import io
from datetime import date
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    CondPageBreak,
    Flowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,  # fmt: skip
    Table,
    TableStyle,
)

from app.services import share_doc as sd

MEDIA_TYPE = "application/pdf"
PAGE_W, PAGE_H = A4
MX, TOP, BOTTOM = 18 * mm, 27 * mm, 16 * mm
BODY_W = PAGE_W - 2 * MX - 12  # the frame keeps 6 pt padding on each side
INK, MUTED, ACCENT = colors.HexColor("#1B1F27"), colors.HexColor("#5B6270"), colors.HexColor("#0B6B74")
SOFT, LINE, ZEBRA = colors.HexColor("#E7F3F2"), colors.HexColor("#D7DBE3"), colors.HexColor("#F6F8FA")
SKY, QOR, WM = colors.HexColor("#1F5FA8"), colors.HexColor("#C2410C"), colors.HexColor("#EEF0F3")
TINT = {"Skyworks": colors.HexColor("#E8F0FA"), "Both": SOFT, "Qorvo": colors.HexColor("#FCEDE6")}
WHO_COLOR = {"Skyworks": SKY, "Qorvo": QOR, "Both": ACCENT}


def _hex(c) -> str:
    return "#" + c.hexval()[2:]


def clean(text: object) -> str:
    """Text the built-in PDF fonts can show (Windows-1252), escaped for ReportLab's paragraph markup."""
    t = " ".join(str(text or "").split())
    for a, b in (("≤", "<="), ("≥", ">="), ("→", "->"), ("Ω", "Ohm"), ("−", "-"), ("…", "...")):
        t = t.replace(a, b)
    t = t.encode("cp1252", "replace").decode("cp1252")
    return escape(t)


S = {
    "kicker": ParagraphStyle("kicker", fontName="Helvetica-Bold", fontSize=8.5, leading=11, textColor=ACCENT,
                             spaceAfter=3),
    "h1": ParagraphStyle("h1", fontName="Helvetica-Bold", fontSize=21, leading=25, textColor=INK, spaceAfter=6),
    "lead": ParagraphStyle("lead", fontName="Helvetica", fontSize=10.5, leading=14.5, textColor=INK, spaceAfter=6),
    "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, leading=16, textColor=ACCENT, spaceBefore=10,
                         spaceAfter=3),
    "sub": ParagraphStyle("sub", fontName="Helvetica", fontSize=9.5, leading=13, textColor=MUTED, spaceAfter=6),
    "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.8, leading=11.2, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Helvetica-Bold", fontSize=8.8, leading=11.2, textColor=INK),
    "cell_s": ParagraphStyle("cell_s", fontName="Helvetica", fontSize=8.2, leading=10.2, textColor=INK),
    "cellb_s": ParagraphStyle("cellb_s", fontName="Helvetica-Bold", fontSize=8.2, leading=10.2, textColor=INK),
    "th": ParagraphStyle("th", fontName="Helvetica-Bold", fontSize=8.5, leading=10.5, textColor=colors.white),
    "mark": ParagraphStyle("mark", fontName="Helvetica-Bold", fontSize=8, leading=11.2, textColor=INK,
                           alignment=TA_RIGHT),
    "num": ParagraphStyle("num", fontName="Helvetica-Bold", fontSize=8.8, leading=11.2, textColor=INK,
                          alignment=TA_RIGHT),
    "small": ParagraphStyle("small", fontName="Helvetica", fontSize=7.8, leading=10, textColor=MUTED),
    "note": ParagraphStyle("note", fontName="Helvetica-Oblique", fontSize=7.8, leading=10, textColor=MUTED,
                           spaceBefore=3, spaceAfter=2),
    "tile_n": ParagraphStyle("tile_n", fontName="Helvetica-Bold", fontSize=17, leading=20, textColor=ACCENT),
    "tile_l": ParagraphStyle("tile_l", fontName="Helvetica", fontSize=8.5, leading=10.5, textColor=INK),
    "colh": ParagraphStyle("colh", fontName="Helvetica-Bold", fontSize=10, leading=12.5, textColor=INK),
    "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=9.5, leading=12, textColor=INK, spaceBefore=8,
                         spaceAfter=2),
}  # fmt: skip


def P(text: str, style: str = "cell", markup: bool = False) -> Paragraph:
    return Paragraph(text if markup else clean(text), S[style])


def mark_html(text: str, kind: str) -> str:
    """One right-aligned mark: who (company colour), ip (small muted), ben (accent), num (bold)."""
    t = clean(text)
    if kind == "who":
        return f'<font color="{_hex(WHO_COLOR.get(text, INK))}">{t}</font>'
    if kind == "ip":
        return f'<font name="Helvetica" size="7.2" color="{_hex(MUTED)}">{t}</font>'
    if kind == "ben":
        return f'<font color="{_hex(ACCENT)}">{t}</font>'
    return t


def code_html(series: list[str]) -> str:
    return "  ".join(f'<font name="Courier-Bold" size="8.2">{clean(x)}</font>' for x in series)


def _cell(c: dict, width: float, first: bool = False, compact: bool = False):
    """A table cell: text (bold in the first column), part series, and marks right-aligned."""
    body = clean(c["t"]) + ((" " if c["t"] else "") + code_html(c["code"]) if c["code"] else "")
    marks = "  ".join(mark_html(m, k) for m, k in c["marks"])
    if not marks:
        return Paragraph(body, S[("cellb" if first else "cell") + ("_s" if compact else "")])
    if not c["t"] and not c["code"]:
        return Paragraph(marks, S["mark"])
    plain = "  ".join(m for m, _ in c["marks"])
    mw = min(width * 0.45, stringWidth(plain, "Helvetica-Bold", 8) + 4)
    t = Table([[Paragraph(body, S[("cellb" if first else "cell") + ("_s" if compact else "")]),
                Paragraph(marks, S["mark"])]],
              colWidths=[width - mw, mw])  # fmt: skip
    t.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))  # fmt: skip
    return t


BASE = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5), ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]  # fmt: skip


def _widths(ws: list[float], n: int) -> list[float]:
    ws = [float(x) for x in ws] if len(ws) == n else [1.0] * n
    return [BODY_W * x / sum(ws) for x in ws]


def _finish(data: list, widths: list[float], st: list, notes: list, tight: bool = False) -> Table:
    """The table with its notes as a last, full-width row that never parts from the row above it, so a note never
    stands alone at the top of a page; the header row repeats after a page break; rows never split."""
    end = len(data) - 1

    def fix(cmd):
        name, (c0, r0), (c1, r1), *rest = cmd
        return (name, (c0, end if r0 == -1 else r0), (c1, end if r1 == -1 else r1), *rest)

    st = [fix(c) for c in st]
    if tight:  # the second try, when only a few lines spilled onto an extra page
        st += [("TOPPADDING", (0, 1), (-1, end), 2), ("BOTTOMPADDING", (0, 1), (-1, end), 2)]
    if notes:
        data = [*data, [notes] + [""] * (len(widths) - 1)]
        n = end + 1
        st += [("SPAN", (0, n), (-1, n)), ("NOSPLIT", (0, end), (-1, n)), ("LEFTPADDING", (0, n), (-1, n), 0),
               ("TOPPADDING", (0, n), (-1, n), 3), ("BOTTOMPADDING", (0, n), (-1, n), 0)]  # fmt: skip
    t = Table(data, colWidths=widths, repeatRows=1, splitInRow=0)
    t.setStyle(TableStyle(st))
    return t


def _notes(b: dict, *extra) -> list:
    return [*extra, *([P(b["note"], "note")] if b.get("note") else [])]


def table(b: dict) -> list:
    cols, rows = b["cols"], b["rows"]
    widths = _widths(b.get("widths") or [], len(cols))
    nums = set(b.get("num_cols") or [])
    dots = b.get("dots")
    head = [P(c, "th") for c in cols]
    if nums or dots:
        head = [Paragraph(clean(c), ParagraphStyle("thr", parent=S["th"], alignment=TA_RIGHT if i in nums else 1))
                if i and (i in nums or dots) else P(c, "th") for i, c in enumerate(cols)]  # fmt: skip
    data = [head]
    for r in rows:
        out = []
        for i, c in enumerate(r):
            if dots and i:
                who = c["t"]
                out.append(Paragraph(f'<font size="13" color="{_hex(WHO_COLOR[who])}">•</font>'
                                     if who in WHO_COLOR else "", ParagraphStyle("dot", parent=S["cell"], alignment=1,
                                                                                 leading=12)))  # fmt: skip
            elif i in nums:
                out.append(P(c["t"], "num"))
            else:
                out.append(_cell(c, widths[i] - 10, first=i == 0, compact=bool(b.get("compact"))))
        data.append(out)
    st = [*BASE, ("BACKGROUND", (0, 0), (-1, 0), ACCENT), ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE)]
    st += [("BACKGROUND", (0, i), (-1, i), ZEBRA) for i in range(2, len(data), 2)]
    extra = []
    if dots:
        st += [("VALIGN", (1, 1), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 1), (-1, -1), 3),
               ("BOTTOMPADDING", (0, 1), (-1, -1), 3)]  # fmt: skip
        legend = " ".join(f'<font size="12" color="{_hex(WHO_COLOR[w])}">•</font> {w}' for w in sd.WHO)
        extra.append(Paragraph(f'<font color="{_hex(MUTED)}">Dot colour:</font> {legend}', S["small"]))
    return [_finish(data, widths, st, _notes(b, *extra), b.get("tight", False))]


def facts(b: dict) -> list:
    items = b["items"]
    n = max(1, len(items))
    gap = 3 * mm
    w = (BODY_W - gap * (n - 1)) / n
    row, widths = [], []
    for i, f in enumerate(items):
        if i:
            row.append("")
            widths.append(gap)
        tile = [P(f["num"], "tile_n"), P(f["label"], "tile_l")]
        if f.get("note"):
            tile.append(P(f["note"], "small"))
        row.append(tile)
        widths.append(w)
    t = Table([row], colWidths=widths)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 7),
          ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 7),
          ("BOTTOMPADDING", (0, 0), (-1, -1), 8)]  # fmt: skip
    st += [("BACKGROUND", (i, 0), (i, 0), SOFT) for i in range(0, len(row), 2)]
    st += [("LINEABOVE", (i, 0), (i, 0), 1.6, ACCENT) for i in range(0, len(row), 2)]
    t.setStyle(TableStyle(st))
    return [Spacer(1, 2 * mm), t, Spacer(1, 2 * mm)]


def cols(b: dict) -> list:
    cs = b["cols"]
    w = BODY_W / len(cs)
    head = [Paragraph(f'<font color="{_hex(WHO_COLOR[c["who"]])}">{clean(c["head"])}</font>'
                      f'  <font name="Helvetica" size="8" color="{_hex(MUTED)}">{clean(c["count"])}</font>', S["colh"])
            for c in cs]  # fmt: skip
    data = [head]
    if any(c["line"] or c["tag"] for c in cs):
        data.append([[P(c["line"], "cell"), Paragraph(mark_html(c["tag"], "ben"), S["mark"])] if c["tag"]
                     else P(c["line"], "cell") for c in cs])  # fmt: skip
    first_item = len(data)
    for r in sd.zipped([c["items"] for c in cs]):
        data.append([_cell(x, w - 10) if x else "" for x in r])
    st = [*BASE, ("LINEBELOW", (0, first_item), (-1, -1), 0.4, LINE), ("LINEBELOW", (0, 0), (-1, 0), 1.2, ACCENT)]
    st += [("BACKGROUND", (i, 0), (i, first_item - 1), TINT[c["who"]]) for i, c in enumerate(cs)]
    st += [("LINEAFTER", (0, 0), (-2, -1), 3, colors.white)]
    return [_finish(data, [w] * len(cs), st, _notes(b), b.get("tight", False))]


def pairs(b: dict) -> list:
    data = [[P("#", "th"), P("Skyworks + Qorvo, and what the pair is useful for", "th"),
             Paragraph("Benefit", ParagraphStyle("thr", parent=S["th"], alignment=TA_RIGHT))]]  # fmt: skip
    for p in b["items"]:
        name = (f'<font color="{_hex(SKY)}">Skyworks</font> {clean(p["skyworks"])}  '
                f'<font color="{_hex(MUTED)}">+</font>'
                f'  <font color="{_hex(QOR)}">Qorvo</font> {clean(p["qorvo"])}')  # fmt: skip
        cell = [Paragraph(name, S["cellb"]), Spacer(1, 1.5), P(p["line"], "cell")]
        if p["ex"]:
            cell.append(Paragraph(f'{clean(p["ex_word"])} ' + ' <font color="#5B6270">with</font> '.join(
                code_html([x]) for x in p["ex"]), S["small"]))  # fmt: skip
        data.append([P(str(p["n"]), "cellb"), cell, Paragraph(mark_html(p["benefit"], "ben"), S["mark"])])
    st = [*BASE, ("BACKGROUND", (0, 0), (-1, 0), ACCENT), ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
          ("TOPPADDING", (0, 1), (-1, -1), 6), ("BOTTOMPADDING", (0, 1), (-1, -1), 6)]  # fmt: skip
    return [_finish(data, [8 * mm, BODY_W - 8 * mm - 34 * mm, 34 * mm], st, _notes(b), b.get("tight", False))]


def links(b: dict) -> list:
    return [P(b["head"], "h3"), *(Paragraph("•  " + clean(x), S["cell"]) for x in b["items"])]


def diagram(b: dict) -> list:
    """A system brief's block diagram (app/services/share_diagram.py) as a vector drawing, with its title and note."""
    from app.services import share_diagram

    d = share_diagram.drawing(b["layout"], BODY_W)
    head = P(b["title"], "h3") if b.get("title") else Spacer(1, 2)
    return [head, d, *_notes(b)]


def bullets(b: dict) -> list:
    return [Paragraph("•  " + clean(x), ParagraphStyle("bul", parent=S["sub"], textColor=INK, leftIndent=9,
                                                        firstLineIndent=-9)) for x in b["items"]]  # fmt: skip


BLOCKS = {"table": table, "facts": facts, "cols": cols, "pairs": pairs, "links": links, "diagram": diagram,
          "bullets": bullets}  # fmt: skip


class Head(Flowable):
    """Zero-size marker: from here on the header band shows this report's title (read when the page is finished)."""

    def __init__(self, head: str, subtitle: str):
        super().__init__()
        self.head, self.subtitle = head, subtitle
        self.width = self.height = 0

    def draw(self):
        self.canv.share_head = (self.head, self.subtitle)


FRAME_H = PAGE_H - TOP - BOTTOM - 12


def _height(flows: list) -> float:
    return sum(f.wrap(BODY_W, FRAME_H)[1] + f.getSpaceBefore() + f.getSpaceAfter() for f in flows)


def story(d: dict, first: bool, with_sources: bool = True, tight: bool = False) -> list:
    out: list = [] if first else [PageBreak()]
    out += [Head(d["head"], d.get("subtitle", "")), P(d["kicker"], "kicker"), P(d["title"], "h1")]
    for i, s in enumerate(d["sections"]):
        part: list = []
        if i == 0:
            part += [P(x, "lead") for x in s["paras"]]
        else:
            part += [P(s["heading"], "h2")] + [P(x, "sub") for x in s["paras"]]
        blocks = [f for b in s["blocks"] for f in BLOCKS[b["kind"]]({**b, "tight": tight})]
        if not part:
            out += blocks
        elif _height([*part, *blocks]) < FRAME_H * 0.45:  # a short section stays on one page
            out += [KeepTogether([*part, *blocks])]
        else:  # a long one starts where at least its heading and first rows fit, its table continues
            out += [CondPageBreak(55 * mm), *part, *blocks]
    if with_sources:
        out += sources(d["sources"], d["prepared"])
    return out


def sources(lines: list[str], prepared: str) -> list:
    return [KeepTogether([P("Sources", "h3"), *(P(x, "small") for x in lines), Spacer(1, 2), P(prepared, "small")])]


def _canvas_class(today, wm_text: str, logo: bytes | None, logo_right: bool):
    date_s = sd.date_text(today)
    try:
        img = ImageReader(io.BytesIO(logo)) if logo else None
    except Exception:  # noqa: BLE001 - a logo the PDF cannot read (SVG): left out
        img = None

    class _Canvas(rl_canvas.Canvas):
        """Keeps every page until the end, so the footer can say "page n / N" and the header the report's title."""

        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._pages: list[dict] = []
            self.share_head = ("", "")

        def showPage(self):
            self._pages.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._pages)
            for n, state in enumerate(self._pages, start=1):
                self.__dict__.update(state)
                self._decorate(n, total)
                rl_canvas.Canvas.showPage(self)
            rl_canvas.Canvas.save(self)

        def _decorate(self, n: int, total: int):
            head, sub = self.share_head
            self.saveState()
            band = 15 * mm
            self.setFillColor(SOFT)
            self.rect(0, PAGE_H - band, PAGE_W, band, stroke=0, fill=1)
            self.setFillColor(ACCENT)
            self.rect(0, PAGE_H - band - 0.8 * mm, PAGE_W, 0.8 * mm, stroke=0, fill=1)
            x, y = MX, PAGE_H - band / 2 - 1.3 * mm
            if img is not None:
                iw, ih = img.getSize()
                h = 8 * mm
                w = h * iw / max(ih, 1)
                lx = PAGE_W - MX - w if logo_right else MX
                self.drawImage(img, lx, PAGE_H - band / 2 - h / 2, w, h, mask="auto")
                if not logo_right:
                    x = MX + w + 4 * mm
            self.setFont("Helvetica-Bold", 10)
            title = "Skyworks + Qorvo · " + head if head else "Skyworks + Qorvo"
            self.drawString(x, y, title.encode("cp1252", "replace").decode("cp1252"))
            if sub:
                self.setFont("Helvetica", 8.5)
                self.setFillColor(MUTED)
                end = PAGE_W - MX - (0 if not (img and logo_right) else 30 * mm)
                self.drawRightString(end, y, sub.encode("cp1252", "replace").decode("cp1252"))
            self.setStrokeColor(LINE)
            self.setLineWidth(0.5)
            self.line(MX, 12 * mm, PAGE_W - MX, 12 * mm)
            self.setFont("Helvetica", 7.8)
            self.setFillColor(MUTED)
            foot = f"Public information · {date_s}" + (f" · {wm_text}" if wm_text else "")
            self.drawString(MX, 8 * mm, foot.encode("cp1252", "replace").decode("cp1252"))
            self.drawRightString(PAGE_W - MX, 8 * mm, f"page {n} / {total}")
            self.restoreState()

    return _Canvas


def _watermark(wm_text: str):
    def draw(canv, _doc):
        if not wm_text:
            return
        canv.saveState()
        canv.setFillColor(WM)
        canv.setFont("Helvetica-Bold", 84 if len(wm_text) < 12 else 56)
        canv.translate(PAGE_W / 2, PAGE_H / 2)
        canv.rotate(35)
        canv.drawCentredString(0, -20, wm_text.upper().encode("cp1252", "replace").decode("cp1252"))
        canv.restoreState()

    return draw


def build(docs: list[dict], today=None, wm_text: str = "", logo: bytes | None = None, logo_right: bool = False,
          title: str = "") -> bytes:  # fmt: skip
    """The PDF bytes of one or more reports (content models from share_doc.doc), each from a new page. With several
    reports, the sources come once, at the end."""
    today = today or date.today()
    data = _build(docs, today, wm_text, logo, logo_right, title, tight=False)
    pages = texts(data)
    if len(pages) > 1 and pages[-1].split("\n", 2)[1:2] == ["Sources"]:  # only the sources spilled over: try tighter
        tighter = _build(docs, today, wm_text, logo, logo_right, title, tight=True)
        if len(texts(tighter)) < len(pages):
            return tighter
    return data


def _build(docs: list[dict], today, wm_text: str, logo: bytes | None, logo_right: bool, title: str,
           tight: bool) -> bytes:  # fmt: skip
    buf = io.BytesIO()
    pdf = SimpleDocTemplate(buf, pagesize=A4, leftMargin=MX, rightMargin=MX, topMargin=TOP, bottomMargin=BOTTOM,
                            title="Skyworks + Qorvo · " + (title or " + ".join(d["head"] for d in docs)),
                            author="Skyworks + Qorvo", subject="Public information", creator="",
                            producer="")  # fmt: skip
    flow: list = []
    for i, d in enumerate(docs):
        flow += story(d, first=i == 0, with_sources=len(docs) == 1, tight=tight)
    if len(docs) > 1:
        lines = list(dict.fromkeys(x for d in docs for x in d["sources"]))
        flow += sources(lines, docs[0]["prepared"])
    wm = _watermark(wm_text)
    pdf.build(flow, onFirstPage=wm, onLaterPages=wm, canvasmaker=_canvas_class(today, wm_text, logo, logo_right))
    return buf.getvalue()


def texts(data: bytes) -> list[str]:
    """The text of every page (tests)."""
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        return [p.extract_text() or "" for p in pdf.pages]


def filename(keys: list[str]) -> str:
    return "skyworks-qorvo-" + "-".join(keys) + ".pdf"
