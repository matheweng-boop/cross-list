"""Skyworks tuner portfolio deck (owner, 10 Nov 2026): "a downloadable PPTX with animations that explains the
Skyworks tuner portfolio. Focus on high-level slides, NO product numbers, including one general block diagram as
well as highlighting how it's built up for digital and analog radio and shows scalability over multiple
applications", plus "a slide for Noise Cancellation and Usage".

Built with the animated-deck blocks (app/services/pptx_anim.py): Harbor theme, theme colours and fonts only, no
watermark, Morph from the general block diagram into the analog build-up and on into the digital build-up.

Content: only what the site already holds (car radio case and market notes, the broadcast configurator's
explanations and tuner features, the Car radio tuner system diagram, the device data shorts' family descriptions).
Public facts only, described by function and family: no part numbers, no customer names, no site references.
Owner only (Shareable > Private · only for you); built on request, never stored under static/.
"""

from functools import lru_cache

from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Pt

from app.services import pptx_anim as pa
from app.services.pptx_anim import A1, A2, A3, BG1, BG2, TX1, TX2, Deck, Effect, I, arrow, box, label, shape, title
from app.services.pptx_template import PALETTES

MEDIA_TYPE = pa.MEDIA_TYPE
FILENAME = "skyworks-tuner-portfolio.pptx"
DECK_TITLE = "The Skyworks broadcast radio tuner portfolio"
FOOTER = "Skyworks broadcast radio tuner portfolio · Public information"
SLIDE_COUNT = 10

C = PP_ALIGN.CENTER
MID = MSO_ANCHOR.MIDDLE


# ---------------------------------------------------------------- helpers


def _content(dk: Deck, words: str, notes: str, morph: bool = False):
    s, q = dk.new(5, morph=morph, notes=notes)
    title(s, words, size=30)
    pa.title_bar(s)
    label(s, "Footer", 0.6, 7.0, 10.5, 0.35, [FOOTER], size=10, color=TX2)
    return s, q


def _block(s, name, x, y, w, h, head, sub="", fill=BG2, line=A1, hs=17, ss=13, hc=TX1, sc=TX2):
    paras = [(head, hs, True, hc)] + ([(sub, ss, False, sc)] if sub else [])
    return box(s, name, x, y, w, h, paras, fill=fill, line=line, line_w=1.5, align=C, anchor=MID, margin=0.1)


def _card(s, name, x, y, w, h, head, body, fill=BG2, hs=17, bs=14):
    return box(s, name, x, y, w, h, [(head, hs, True, TX1), (body, bs, False, TX2)], fill=fill, anchor=MSO_ANCHOR.TOP,
               margin=0.15, spacing=4)


def _cover_text(s, words, x, y, w, h, size, color, anchor, heading, name, bold=False):
    ph = s.shapes.title if name == "Title" else s.placeholders[1]
    ph.name = name
    ph.left, ph.top, ph.width, ph.height = I(x), I(y), I(w), I(h)
    ph.text_frame.text = words
    ph.text_frame.word_wrap = True
    ph.text_frame.vertical_anchor = anchor
    p = ph.text_frame.paragraphs[0]
    p.alignment = PP_ALIGN.LEFT
    f = p.runs[0].font
    f.size, f.bold, f.name = Pt(size), bold, "+mj-lt" if heading else "+mn-lt"
    pa._color(f.color, color)
    return ph


# ---------------------------------------------------------------- slides


def s_title(dk: Deck):
    s, q = dk.new(0, notes=(
        "Talk track: This deck gives a high-level view of the Skyworks broadcast radio tuner portfolio: what a radio "
        "receiver is made of, how the same building blocks serve analog AM/FM and digital radio, how reception stays "
        "clean in noisy cars, and how one architecture scales from a portable receiver to a premium multi-tuner car "
        "radio. We describe products by function and family only."))
    t = _cover_text(s, DECK_TITLE, 0.9, 1.6, 8.0, 2.4, 40, TX1, MSO_ANCHOR.BOTTOM, True, "Title", bold=True)
    sub = _cover_text(s, "AM/FM · HD Radio · DAB/DAB+ · DRM · CDR\nFrom portable receivers to multi-tuner car radios",
                      0.9, 4.2, 8.0, 1.3, 20, TX2, MSO_ANCHOR.TOP, False, "Subtitle")
    for p in sub.text_frame.paragraphs:  # the second line comes from the newline: give it the same look
        p.alignment = PP_ALIGN.LEFT
        for r in p.runs:
            r.font.size, r.font.name = Pt(20), "+mn-lt"
            pa._color(r.font.color, TX2)
    bar = shape(s, "Accent bar", MSO_SHAPE.RECTANGLE, 0.9, 1.4, 1.6, 0.1, fill=A1)
    c1 = shape(s, "Circle large", MSO_SHAPE.OVAL, 9.6, 1.3, 3.2, 3.2, fill=A1)
    rings = [shape(s, f"Wave {i + 1}", MSO_SHAPE.OVAL, 9.6 - 0.4 * (i + 1), 1.3 - 0.4 * (i + 1),
                   3.2 + 0.8 * (i + 1), 3.2 + 0.8 * (i + 1), line=A2, line_w=3) for i in range(2)]
    c2 = shape(s, "Circle small", MSO_SHAPE.OVAL, 10.6, 4.9, 1.4, 1.4, fill=A3)
    q.after(Effect("wipe", bar, 500, sub="left"))
    q.after(Effect("zoom", t, 700)).with_(Effect("zoom", c1, 700)).with_(Effect("zoom", c2, 600, delay=200))
    q.after(Effect("zoom", rings[0], 400)).after(Effect("zoom", rings[1], 400))
    q.with_(Effect("float", sub, 600))


def s_why(dk: Deck):
    s, q = _content(dk, "Why radio still matters", notes=(
        "Talk track: Radio is free, live and local, and it is in practically every new car: around 90 million car "
        "radios a year. Regulation keeps it there and pushes it to digital. In the EU, car radios in new cars must "
        "receive digital radio since December 2020, and DAB+ is in almost all new cars. In the US, HD Radio is in "
        "more than 60 percent of new cars, and a bill to keep AM in every new vehicle passed the House in September "
        "2026 (a bill, not law). India has DRM in about one in three cars; China has drafted an in-car broadcast "
        "receiver standard (CDR and DRM). Electric cars add a new problem: motor and charger noise swamps AM. "
        "Bottom line: the radio stays, and its content per car grows as the mix moves to digital."))
    cards = [
        ("In every car", "Around 90 million car radios a year. Free, live and local; it works without a phone or "
                         "data plan."),
        ("Europe: digital by rule", "New car radios in the EU must receive digital radio (since Dec 2020). DAB+ is in "
                                    "almost all new cars."),
        ("US: AM and HD Radio", "HD Radio in more than 60 % of new cars. A bill to keep AM in every new vehicle passed "
                                "the House (Sep 2026)."),
        ("India and China", "DRM in about 1 in 3 Indian cars. China has drafted an in-car broadcast receiver standard "
                            "(CDR, DRM)."),
        ("Electric cars", "Motor and charger noise swamps AM. Noise cancelling in the tuner keeps AM usable."),
    ]
    w, gap = 2.3, 0.14
    for i, (head, body) in enumerate(cards):
        x = 0.6 + i * (w + gap)
        dot = shape(s, f"Dot {i + 1}", MSO_SHAPE.OVAL, x + 0.15, 1.75, 0.45, 0.45, fill=[A1, A2, A3, A1, A2][i])
        c = _card(s, f"Card {i + 1}", x, 2.35, w, 3.35, head, body)
        e = Effect("float", c, 500)
        (q.click(e) if i == 0 else q.after(e)).with_(Effect("zoom", dot, 400))
    msg = box(s, "Message", 0.6, 5.95, 12.1, 0.75, ["Radio stays in the car, and its content per car grows as the "
                                                    "mix moves from analog to digital."],
              fill=A1, size=18, bold=True, color=BG1, align=C, anchor=MID)
    q.click(Effect("zoom", msg, 500))


ROW_Y, ROW_H = 2.0, 1.45
CHAIN = [  # name, x, w
    ("!!Ant", 0.5, 1.7), ("!!FE", 2.55, 1.95), ("!!Tuner", 4.85, 2.2), ("!!DSP", 7.4, 2.4), ("!!Host", 10.15, 2.65)]


def _chain_arrows(s, y, prefix="Link", boxes=CHAIN):
    out = []
    for i in range(len(boxes) - 1):
        _, x, w = boxes[i]
        _, nx, _ = boxes[i + 1]
        out.append(arrow(s, f"{prefix} {i + 1}", x + w + 0.03, y, nx - 0.03, y))
    return out


def s_block_diagram(dk: Deck):
    s, q = _content(dk, "One radio receiver, block by block", notes=(
        "Talk track: Every broadcast receiver we make follows the same chain. The antenna, or two antennas, picks up "
        "the signal. A front end with an amplifier, switch and filters protects and conditions it. The tuner converts "
        "the wanted station down, digitises it and filters it. Demodulation and DSP turn it into audio and data, for "
        "analog AM/FM and for digital radio. The result goes to the head unit or infotainment processor as digital "
        "audio and data. One reference clock feeds every tuner and decoder, and the host controls everything over a "
        "simple serial interface and boots the firmware. What changes from product to product is how many tuners, "
        "which standards, and where the blocks sit."))
    texts = [("Antennas", "AM/FM, Band III"), ("Front end", "amplifier · switch · filter · protection"),
             ("Tuner", "RF · mixer · ADC · digital filter"), ("Demodulation + DSP", "analog and digital radio"),
             ("Head unit", "infotainment processor: audio + data")]
    blocks = [_block(s, n, x, ROW_Y, w, ROW_H, h, sub) for (n, x, w), (h, sub) in zip(CHAIN, texts, strict=True)]
    links = _chain_arrows(s, ROW_Y + ROW_H / 2)
    clk = _block(s, "!!Clock", 4.85, 4.3, 2.2, 1.0, "One reference clock", "shared by all chips", line=A2, hs=15)
    ctl = _block(s, "!!Ctrl", 7.4, 4.3, 2.4, 1.0, "Control + firmware", "serial interface from the host", line=A2,
                 hs=15)
    a_clk = arrow(s, "Clock link", 5.95, 4.27, 5.95, ROW_Y + ROW_H + 0.03, color=A2)
    a_ctl = arrow(s, "Control link", 8.6, 4.27, 8.6, ROW_Y + ROW_H + 0.03, color=A2)
    sig = label(s, "Signal", 0.6, 1.5, 12.1, 0.4, ["Signal path: RF → digital samples → audio and data"], size=14,
                color=TX2)
    cap = label(s, "Caption", 0.6, 5.75, 12.1, 0.9, [
        "The same chain in every product. What changes: how many tuners, which standards, and where the blocks sit."],
        size=18, color=TX1, bold=True)
    q.after(Effect("fade", sig, 400))
    q.click(Effect("zoom", blocks[0], 450))
    for a, b in zip(links, blocks[1:], strict=True):
        q.click(Effect("wipe", a, 300, sub="left")).after(Effect("zoom", b, 450))
    q.click(Effect("zoom", clk, 450)).with_(Effect("zoom", ctl, 450, delay=150))
    q.after(Effect("wipe", a_clk, 300, sub="bottom")).with_(Effect("wipe", a_ctl, 300, sub="bottom"))
    q.click(Effect("fade", cap, 500))


def _chips(s, q, items, y0, h=1.05, cols=3, first_click=True):
    w = (12.1 - (cols - 1) * 0.2) / cols
    for i, (head, body) in enumerate(items):
        r, c = divmod(i, cols)
        chip = box(s, f"Chip {i + 1}", 0.6 + c * (w + 0.2), y0 + r * (h + 0.15), w, h,
                   [(head, 15, True, TX1), (body, 13, False, TX2)], fill=BG2, line=A2, line_w=1.0, margin=0.12)
        e = Effect("float", chip, 450)
        q.click(e) if (i == 0 and first_click) else q.after(e)


def s_analog(dk: Deck):
    s, q = _content(dk, "Built for analog radio: AM/FM", morph=True, notes=(
        "Talk track: For analog AM/FM the chain stays the same; Morph shows the blocks taking their analog jobs. Two "
        "antennas allow FM phase diversity. The front end keeps strong FM signals out of the AM path and protects "
        "the input. The tuner, single or dual, receives AM and FM; demodulation and an audio DSP on the same chip "
        "produce the audio, with RDS data such as station name and traffic. A second tuner keeps the station list "
        "fresh in the background while you listen. In weak signals the receiver mutes softly and blends stereo to "
        "mono, and an AM interference canceller removes the switching noise of electric cars. Some tuners also carry "
        "a full audio system, so an entry radio needs no separate audio chip."))
    texts = [("Two antennas", "for FM phase diversity"), ("Front end", "AM/FM filter · protection"),
             ("AM/FM tuner", "single or dual"), ("AM/FM demod + audio DSP", "on the tuner chip"),
             ("Head unit", "audio + RDS text")]
    for (n, x, w), (h, sub) in zip(CHAIN, texts, strict=True):
        _block(s, n, x, 1.6, w, 1.35, h, sub)
    _chain_arrows(s, 1.6 + 1.35 / 2)
    _chips(s, q, [
        ("RDS data", "station name, traffic, alternative frequencies"),
        ("Background tuner", "keeps the station list fresh while you listen"),
        ("FM phase diversity", "two antennas, two tuners combined against multipath"),
        ("Weak-signal handling", "soft mute, stereo-to-mono blend, high cut"),
        ("AM interference canceller", "removes switching noise, e.g. in electric cars"),
        ("On-chip audio option", "an entry radio needs no separate audio chip"),
    ], 3.35)


def s_digital(dk: Deck):
    s, q = _content(dk, "Built for digital radio: HD Radio, DAB/DAB+, DRM, CDR", morph=True, notes=(
        "Talk track: For digital radio the same tuner stays in place and sends digital I/Q samples to a digital "
        "radio co-processor, the new block that Morph brings in. One co-processor family decodes HD Radio, DAB and "
        "DAB+, DRM and China's CDR; the region is set by software licence. Analog AM/FM still runs on the tuner, so "
        "the receiver can blend seamlessly between the analog and digital version of the same station, or link FM "
        "and DAB. Digital radio adds data services such as slideshow pictures, programme guide and traffic. With "
        "two antennas, maximum ratio combining (MRC) adds both signals for HD Radio and DAB. Error correction keeps "
        "the sound clean up to the edge of coverage."))
    texts = [("Antennas", "AM/FM + Band III (DAB)"), ("Front end", "AM/FM/DAB filter · protection"),
             ("Tuner", "AM/FM/DAB · digital I/Q out"), None, ("Head unit", "audio + data services")]
    y, h = 1.6, 2.3
    for (n, x, w), t in zip(CHAIN, texts, strict=True):
        if t:
            _block(s, n, x, y, w, h, *t)
    _, dx, dw = CHAIN[3]
    _block(s, "!!DSP", dx, y, dw, 0.95, "Analog AM/FM demod", "on the tuner chip", hs=15)
    cop = _block(s, "!!Copro", dx, y + 1.1, dw, 1.2, "Digital radio co-processor", "HD Radio · DAB/DAB+ · DRM · CDR",
                 fill=A1, hc=BG1, sc=BG1, hs=15)
    _chain_arrows(s, y + h / 2, boxes=CHAIN[:3])
    ty = y + 0.47
    arrow(s, "Link analog", 7.08, ty, dx - 0.03, ty)
    arrow(s, "Link I/Q", 7.08, y + 1.7, dx - 0.03, y + 1.7, color=A1)
    hx = CHAIN[4][1]
    arrow(s, "Link audio", dx + dw + 0.03, ty, hx - 0.03, ty)
    arrow(s, "Link digital", dx + dw + 0.03, y + 1.7, hx - 0.03, y + 1.7, color=A1)
    blend = label(s, "Blend", hx, y + h + 0.05, 2.65, 0.4, ["⇅ seamless blend"], size=13, color=TX2, align=C)
    q.after(Effect("pulse", cop, 800)).with_(Effect("fade", blend, 500))
    _chips(s, q, [
        ("Worldwide standards", "HD Radio, DAB/DAB+, DRM, CDR: region set by software licence"),
        ("Seamless blending and linking", "analog ↔ digital of the same station; FM ↔ DAB"),
        ("Data services", "slideshow pictures, programme guide, traffic"),
        ("MRC", "two antennas combined for HD Radio and DAB"),
        ("Error correction", "clean sound up to the edge of coverage"),
        ("Scan-less service list", "a background tuner keeps the DAB list current"),
    ], 4.4, h=0.95)


def s_noise(dk: Deck):
    s, q = _content(dk, "Noise cancellation and where it is used", notes=(
        "Talk track: Reception problems in a car come from a few typical situations, and each has a technique in the "
        "tuner or co-processor. Electric and hybrid cars: the inverter, motor and DC-DC converters create switching "
        "and impulse noise that swamps the AM band; the AM interference canceller removes it, which matters now that "
        "the US debates keeping AM in every vehicle. City streets: reflections from buildings make FM fade and "
        "distort; phase diversity combines two antennas. Fringe areas: as the signal weakens the receiver mutes "
        "softly, blends stereo to mono and cuts treble instead of hissing, and MRC combines two antennas for HD Radio "
        "and DAB. Noisy car electronics on DAB: a DAB noise canceller and digital gain control in the tuner. Moving "
        "between transmitters or out of digital coverage: error correction first, then a seamless blend to analog or "
        "a link from DAB to FM, so the listener hears no gap. Here noise cancellation means reception: noise picked "
        "up by the radio, not road-noise cancellation in the car's audio system."))
    hy = 1.5
    for x, w, words in ((0.6, 3.8, "Where it happens"), (5.05, 4.3, "What the receiver does"),
                        (9.55, 3.2, "What the listener gets")):
        label(s, f"Head {words}", x, hy, w, 0.4, [words], size=14, bold=True, color=A1)
    rows = [
        ("Electric and hybrid cars", "inverter and DC-DC switching noise in the AM band",
         "AM interference canceller removes switching and impulse noise", "AM stays usable in EVs"),
        ("City streets", "reflections from buildings: FM multipath fading",
         "FM phase diversity: two antennas, two tuners combined", "fewer dropouts, less distortion"),
        ("Fringe reception", "weak or fading signal",
         "Soft mute, stereo-to-mono blend, high cut; MRC on two antennas", "a smooth fade, not hiss"),
        ("Noisy electronics on DAB", "interference in Band III",
         "DAB noise canceller and digital gain control in the tuner", "cleaner DAB reception"),
        ("Edge of digital coverage", "or moving between transmitters",
         "Error correction, then seamless blend to analog or FM ↔ DAB link", "no gap, no audible switch"),
    ]
    y0, step, h = 1.95, 0.97, 0.82
    for i, (where, why, how, gets) in enumerate(rows):
        y = y0 + i * step
        a = box(s, f"Where {i + 1}", 0.6, y, 3.8, h, [(where, 15, True, TX1), (why, 12, False, TX2)], fill=BG2,
                margin=0.1, anchor=MID)
        ar = arrow(s, f"Arrow {i + 1}", 4.45, y + h / 2, 5.0, y + h / 2, color=A1)
        b = box(s, f"How {i + 1}", 5.05, y, 4.3, h, [how], fill=A1, size=14, bold=True, color=BG1, margin=0.1,
                anchor=MID)
        c = label(s, f"Gets {i + 1}", 9.55, y, 3.2, h, [gets], size=14, color=TX1, anchor=MID)
        q.click(Effect("fly", a, 450, sub="left")).after(Effect("wipe", ar, 250, sub="left"))
        q.after(Effect("zoom", b, 400)).after(Effect("fade", c, 350))


def s_multi(dk: Deck):
    s, q = _content(dk, "Multi-tuner architectures: more tuners, more at once", notes=(
        "Talk track: The first question for any car radio is how many tuners. One tuner is an entry radio: you "
        "listen to one station, and the list updates only when you seek. Two tuners, one dual-tuner chip, let you "
        "listen while the second tuner scans in the background, or combine two antennas for phase diversity or MRC. "
        "Four tuners, two dual chips, do it all at once: phase diversity on FM while the second pair receives DAB "
        "and links FM and DAB seamlessly. Five tuners is the superset with a spare for background data. Tuner chips "
        "chain on one reference clock and one boot flash, and the antenna signal loops through from the first chip, "
        "so adding tuners needs no extra splitter. Each extra tuner costs board space and power, so the count "
        "follows the car's segment."))
    cols = [(1, "Entry radio", "Listen to one station; the list updates only on a seek."),
            (2, "Listen + background", "Background scan keeps the list and RDS fresh; or phase diversity or MRC."),
            (4, "Everything at once", "Phase diversity on FM while a second pair receives DAB and links FM ↔ DAB."),
            (5, "Superset", "Every function at the same time, plus a spare for background data.")]
    w, gap = 2.85, 0.23
    for i, (n, head, body) in enumerate(cols):
        x = 0.6 + i * (w + gap)
        num = box(s, f"Count {i + 1}", x, 1.6, 0.95, 0.95, [str(n)], kind=MSO_SHAPE.OVAL, fill=A1, size=30,
                  bold=True, color=BG1, align=C, anchor=MID, heading=True, margin=0)
        cap = label(s, f"Unit {i + 1}", x + 1.05, 1.6, w - 1.05, 0.95, ["tuner" if n == 1 else "tuners"], size=18,
                    color=TX2, anchor=MID)
        icons = []
        for k in range(n):
            icons.append(box(s, f"Tuner {i + 1}.{k + 1}", x + k * 0.55, 2.75, 0.45, 0.45, ["T"], fill=A2, size=13,
                             bold=True, color=BG1, align=C, anchor=MID, margin=0))
        card = _card(s, f"Use {i + 1}", x, 3.4, w, 2.3, head, body)
        q.click(Effect("zoom", num, 400)).with_(Effect("fade", cap, 400))
        for k, ic in enumerate(icons):
            (q.after if k == 0 else q.with_)(Effect("zoom", ic, 300, delay=k * 120))
        q.after(Effect("float", card, 450))
    foot = box(s, "Chain", 0.6, 5.95, 12.1, 0.8, [
        "Tuner chips chain on one reference clock and one boot flash; the antenna signal loops through from the "
        "first chip, so no extra splitter."], fill=BG2, line=A1, line_w=1.0, size=15, color=TX1, anchor=MID)
    q.click(Effect("wipe", foot, 500, sub="left"))


def s_scale(dk: Deck):
    s, q = _content(dk, "One architecture, many applications", notes=(
        "Talk track: The same architecture scales across applications. At the bottom, portable and home audio use "
        "single-chip FM or AM/FM/shortwave/longwave receivers: small and low power. Consumer digital radios use "
        "single-chip receivers that add DAB/DAB+ or HD Radio. An entry car radio uses one automotive AM/FM tuner, "
        "optionally with the audio system on the chip. A mid-range head unit adds a second tuner and a digital "
        "radio co-processor. A premium, multi-standard car radio uses two or more dual tuners with a multi-channel "
        "co-processor, in the head unit or in a module at the antenna; data receivers serve telematics and traffic "
        "data. What scales: tuners, standards, diversity and software features. What stays common: one programming "
        "interface, shared board footprints for single and dual tuners, one clock and boot chain, and the same "
        "reception algorithms."))
    steps = [("Portable and home audio", "single-chip FM or AM/FM/SW/LW receiver"),
             ("Consumer digital radio", "single-chip receiver adding DAB/DAB+ or HD Radio"),
             ("Entry car radio", "one automotive AM/FM tuner, audio system on chip as an option"),
             ("Mid-range head unit", "dual tuner + digital radio co-processor"),
             ("Premium infotainment", "two or more dual tuners + multi-channel co-processor; head unit or antenna "
                                      "module. Data receivers for telematics and traffic")]
    base, w, gap = 6.2, 2.3, 0.15
    fills = [(BG2, TX1, TX2), (BG2, TX1, TX2), (A2, BG1, BG1), (A1, BG1, BG1), (A1, BG1, BG1)]
    common = _card(s, "Common", 0.6, 1.55, 4.75, 1.85, "Stays common", "One programming interface · shared board "
                   "footprints for single and dual tuners · one clock and boot chain · the same reception algorithms",
                   fill=BG1, hs=16, bs=13)
    common.line.width = Pt(1.5)
    pa._color(common.line.color, A1)
    q.after(Effect("fade", common, 500))
    for i, (head, body) in enumerate(steps):
        h = 1.55 + i * 0.75
        x = 0.6 + i * (w + gap)
        f, hc, bc = fills[i]
        st = box(s, f"Step {i + 1}", x, base - h, w, h, [(head, 15, True, hc), (body, 12, False, bc)], fill=f,
                 line=A1, line_w=1.0, margin=0.12, spacing=3)
        q.click(Effect("wipe", st, 500, sub="bottom"))
    sc = box(s, "Scales", 0.6, 6.3, 12.1, 0.5, ["More tuners · more standards · diversity · more software features  →"],
             kind=MSO_SHAPE.PENTAGON, fill=A3, size=15, bold=True, color=TX1, anchor=MID, margin=0.15)
    q.click(Effect("wipe", sc, 700, sub="left"))


def s_benefits(dk: Deck):
    s, q = _content(dk, "What the portfolio offers", notes=(
        "Talk track: Six points sum up the design benefits. Integration: RF, conversion and DSP on one chip mean "
        "fewer external parts and a smaller board. Worldwide standards: one co-processor family covers HD Radio, "
        "DAB/DAB+, DRM and CDR, so one design serves every region. Software-defined features: phase diversity, MRC, "
        "noise cancellers and blending run in firmware and are enabled by licence, not extra hardware. One board, "
        "several variants: single and dual tuners share a footprint and one programming interface. Flexible "
        "placement: the radio can sit in the head unit, in a module at the antenna, or pass samples to a central "
        "computer. Automotive grade: the car tuners and co-processors are qualified for automotive use."))
    tiles = [("Integrated", "RF, conversion and DSP on one chip: fewer external parts, a smaller board."),
             ("Worldwide standards", "HD Radio, DAB/DAB+, DRM and CDR from one co-processor family."),
             ("Software-defined features", "Diversity, MRC, noise cancellers and blending in firmware, enabled by "
                                           "licence."),
             ("One board, several variants", "Single and dual tuners share a footprint and one programming "
                                             "interface."),
             ("Flexible placement", "In the head unit, in a module at the antenna, or samples to a central computer."),
             ("Automotive grade", "Car tuners and co-processors qualified for automotive use.")]
    w, h = 3.9, 2.25
    for i, (head, body) in enumerate(tiles):
        r, c = divmod(i, 3)
        x, y = 0.6 + c * (w + 0.2), 1.65 + r * (h + 0.25)
        bar = shape(s, f"Tile bar {i + 1}", MSO_SHAPE.RECTANGLE, x, y, w, 0.1, fill=[A1, A2, A3][c])
        t = _card(s, f"Tile {i + 1}", x, y + 0.1, w, h - 0.1, head, body, hs=21, bs=17)
        e = Effect("zoom", t, 450)
        (q.click(e) if c == 0 else q.after(e)).with_(Effect("wipe", bar, 400, sub="left"))
    del s


def s_summary(dk: Deck):
    s, q = _content(dk, "Summary", notes=(
        "Talk track: To sum up. Radio stays in every car, and the mix moves to digital: DAB+ by EU rule, HD Radio "
        "in the US, DRM in India, and a draft standard in China. One block diagram describes every receiver. "
        "Analog and digital radio share the tuner; a "
        "co-processor adds the digital standards. Noise cancelling and diversity keep reception clean in electric "
        "cars, cities and fringe areas. And one architecture scales by adding tuners and standards on a common "
        "software and board platform, from a portable receiver to a premium multi-tuner car radio."))
    key = box(s, "Key message", 0.6, 1.65, 4.3, 4.9, [
        ("One radio architecture", 26, True, BG1),
        ("from a portable receiver to a premium multi-tuner car radio", 20, False, BG1)],
        fill=A1, anchor=MID, margin=0.3, spacing=8, heading=True)
    pts = box(s, "Points", 5.3, 1.65, 7.45, 4.9, [
        "Radio stays in every car, and the mix moves to digital: DAB+ by EU rule, HD Radio in the US, DRM in India.",
        "One block diagram: antennas, front end, tuner, demodulation, head unit.",
        "Analog and digital share the tuner; a co-processor adds HD Radio, DAB/DAB+, DRM and CDR.",
        "Noise cancelling and diversity keep reception clean in EVs, cities and fringe areas.",
        "Scale by adding tuners and standards on a common software and board platform."],
        fill=None, size=18, color=TX1, bullets=True, spacing=12, anchor=MID)
    q.after(Effect("zoom", key, 600))
    for i in range(5):
        q.click(Effect("float", pts, 450, para=i))


SLIDES = (s_title, s_why, s_block_diagram, s_analog, s_digital, s_noise, s_multi, s_scale, s_benefits, s_summary)

# (slide, what it shows) for the download page
OUTLINE = ("Title", "Why radio still matters", "One general block diagram", "Built for analog radio (AM/FM)",
           "Built for digital radio (HD Radio, DAB/DAB+, DRM, CDR)", "Noise cancellation and where it is used",
           "Multi-tuner architectures", "One architecture, many applications", "What the portfolio offers",
           "Summary")


def build() -> bytes:
    name, _, hexes = PALETTES["default"]  # Harbor
    dk = Deck(pa.new_presentation(name, hexes))
    for make in SLIDES:
        make(dk)
    return pa.finish(dk, DECK_TITLE, "Skyworks", "Broadcast radio tuner portfolio, high level")


@lru_cache(maxsize=1)
def cached() -> bytes:
    """Built once per process (deterministic), for the owner's download."""
    return build()
