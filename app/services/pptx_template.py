"""Animated PowerPoint template (owner, 6 Nov 2026): the colour sets, the download files and the slide list, shared by
the generator (scripts/build_pptx_template.py) and the download page (Shareable > PowerPoint templates)."""

MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
URL_DIR = "/static/downloads/"

# key -> (name, one line, theme colours: dk1 lt1 dk2 lt2 accent1..6 hlink folHlink). Text on accent1 is white, so
# accent1 stays dark enough in every set.
PALETTES = {
    "default": ("Harbor", "Calm blue and teal; the main template",
                "1F2933 FFFFFF 334E68 EEF2F6 2F6690 3A9D9B E0A458 C8553D 6C5B9B 8AA899 2F6690 6C5B9B"),
    "ocean": ("Ocean", "Teal and sea blue with fresh accents",
              "10263B FFFFFF 0B3954 E6F2F5 087E8B 3FA7D6 59CD90 FAC05E EE6352 0B3954 087E8B 5E548E"),
    "graphite": ("Graphite", "Slate greys with one orange highlight",
                 "1E2228 FFFFFF 2E3440 ECEFF4 4C566A E07A1F 5E81AC A3BE8C B48EAD 88C0D0 5E81AC B48EAD"),
    "sunrise": ("Sunrise", "Warm orange and gold",
                "2B1B24 FFFFFF 5C2A3D FFF4EC C2410C F3A712 669BBC 29335C D1495B A8C686 C2410C 5C2A3D"),
}
FILES = {
    "default": "bizdev-animated-template.pptx",
    "ocean": "bizdev-animated-template-ocean.pptx",
    "graphite": "bizdev-animated-template-graphite.pptx",
    "sunrise": "bizdev-animated-template-sunrise.pptx",
}

# (slides, what it is, how it moves) in deck order
SLIDES = (
    ("1", "Title", "The bar wipes in, the title and circles zoom in, the subtitle floats in"),
    ("2–5", "Agenda and section dividers", "Morph zooms the highlighted agenda row into a big section number"),
    ("6", "Key points", "Each point floats in on its own click; the key message zooms in"),
    ("7–8", "Picture zoom", "Morph enlarges one detail of the picture to fill the frame"),
    ("9", "Flow chart that builds", "Arrows wipe in, then the next box zooms in, click by click"),
    ("10–13", "Flow chart that moves", "Morph grows the active step and shrinks the last one"),
    ("14", "Timeline that builds", "The progress bar wipes to each point; markers zoom, labels float in"),
    ("15–17", "Timeline that slides", "Morph slides the whole timeline so the current point is in the middle"),
    ("18", "Cycle that spins in", "Each stage spins in; the centre ring spins"),
    ("19–22", "Cycle that turns", "Morph turns the stages one place, next to the explanation"),
    ("23–24", "Comparison", "The cards fly in; Morph grows the winner and colours it"),
    ("25", "Numbers", "The numbers zoom in one after another; one pulses"),
    ("26", "Chart reveal", "The chart wipes in one category per click (edit the data in PowerPoint)"),
    ("27", "Block diagram that builds", "Blocks zoom in, connections wipe in, then a frame shows where our part fits"),
    ("28–29", "2×2 matrix", "Dots fly in; Morph moves them from today to in 3 years"),
    ("30–31", "Venn overlap", "Morph slides the two circles together; the overlap label pops in"),
    ("32", "Funnel", "One level per click wipes in with its number"),
    ("33", "Pyramid", "Builds from the base up, one level per click"),
    ("34", "Roadmap swimlanes", "Bars grow in lane by lane; the time gone by shades in and a Today line drops"),
    ("35–37", "Big number that counts up", "Morph grows the number and its bar over three slides"),
    ("38", "Table with a highlighted row", "The table fades in; a frame zooms onto one row and pulses"),
    ("39", "Progress rings", "Each ring fills like a clock hand; the percentage zooms in"),
    ("40", "Quote or key message", "Quote mark zooms, quote floats in, then grows a little on click"),
    ("41", "Closing", "Text and circles zoom in"),
    ("42–43", "How to use, how to change colours", "Delete these two before presenting"),
)


def swatches(key: str) -> list[str]:
    """The six accent colours and dark 2 / light 2, as CSS hex, for the page's colour chips."""
    h = PALETTES[key][2].split()
    return ["#" + x for x in h[4:10]] + ["#" + h[2], "#" + h[3]]
