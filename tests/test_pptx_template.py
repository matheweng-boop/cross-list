"""Animated PowerPoint template (owner, 6 Nov 2026): scripts/build_pptx_template.py rebuilds the committed downloads
byte for byte, every slide uses theme colours only, the animation timing points at real shapes, the Morph slides
carry their "!!" names over, and Shareable > PowerPoint templates serves the four files."""

import io
import re
import sys
import zipfile
from pathlib import Path

import pytest
from lxml import etree
from pptx import Presentation

from app.services import pptx_template as pt

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_pptx_template as bt  # noqa: E402

P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
P159 = "{http://schemas.microsoft.com/office/powerpoint/2015/09/main}"


@pytest.fixture(scope="module")
def built():
    return {k: bt.build(k) for k in pt.FILES}


@pytest.mark.smoke
def test_committed_files_are_a_fresh_build(built):
    for key, name in pt.FILES.items():
        path = ROOT / "app/web/static/downloads" / name
        assert path.exists(), name
        assert path.read_bytes() == built[key], f"{name}: run uv run python scripts/build_pptx_template.py"


def test_build_is_deterministic(built):
    again = bt.build("default")
    assert bt.xml_parts(again) == bt.xml_parts(built["default"])
    assert again == built["default"]


def test_every_file_passes_the_checks(built):
    for key, blob in built.items():
        assert bt.check(blob) == [], key


def test_opens_in_python_pptx_as_16_9(built):
    prs = Presentation(io.BytesIO(built["default"]))
    assert (prs.slide_width, prs.slide_height) == (12192000, 6858000)
    assert len(prs.slides) == 29
    assert int(pt.SLIDES[-1][0].split("–")[-1]) == 29  # the page's slide list ends at the last slide
    texts = " ".join(sh.text_frame.text for s in prs.slides for sh in s.shapes if sh.has_text_frame)
    for placeholder in ("Your presentation title", "Point one", "Step one", "Milestone one", "Your caption"):
        assert placeholder in texts
    charts = [sh for s in prs.slides for sh in s.shapes if sh.has_chart]
    assert len(charts) == 1 and list(charts[0].chart.plots[0].categories) == ["Q1", "Q2", "Q3", "Q4"]


def test_theme_colours_only_on_slides_and_charts(built):
    z = zipfile.ZipFile(io.BytesIO(built["default"]))
    parts = [n for n in z.namelist() if re.match(r"ppt/(slides/slide\d+|charts/chart\d+)\.xml$", n)]
    assert len(parts) == 30
    for n in parts:
        x = z.read(n).decode()
        assert not re.search(r"<a:(srgbClr|sysClr|scrgbClr|hslClr|prstClr)\b", x), n
    assert "schemeClr" in z.read("ppt/slides/slide1.xml").decode()


def test_variants_differ_only_in_theme_colours(built):
    base = bt.xml_parts(built["default"])
    for key in ("ocean", "graphite", "sunrise"):
        other = bt.xml_parts(built[key])
        assert set(other) == set(base)
        diff = {n for n in base if base[n] != other[n]}
        # the theme, and the colours slide that names the set
        assert diff == {"ppt/theme/theme1.xml", "ppt/slides/slide29.xml"}, (key, diff)
        theme = other["ppt/theme/theme1.xml"].decode()
        name, _, hexes = pt.PALETTES[key]
        assert f'clrScheme name="BizDev {name}"' in theme
        assert hexes.split()[4] in theme  # accent1


def _slides(blob):
    z = zipfile.ZipFile(io.BytesIO(blob))
    names = sorted((n for n in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml$", n)),
                   key=lambda n: int(re.findall(r"\d+", n)[0]))
    return [etree.fromstring(z.read(n)) for n in names]


def _names(el):
    return {nv.get("name") for nv in el.iter(f"{P}cNvPr") if nv.get("name", "").startswith("!!")}


def test_timing_targets_and_ids(built):
    for i, el in enumerate(_slides(built["default"]), 1):
        ids = {nv.get("id") for nv in el.iter(f"{P}cNvPr")}
        targets = {t.get("spid") for t in el.iter(f"{P}spTgt")}
        assert targets <= ids, i
        ctn = [c.get("id") for c in el.iter(f"{P}cTn")]
        assert len(ctn) == len(set(ctn)), i
        for c in el.iter(f"{P}cTn"):  # effects 0.4-0.8 s (1 ms: the "make visible" step; pulse halves its own)
            d = c.get("dur")
            assert d in (None, "1", "indefinite") or 250 <= int(d) <= 800, (i, d)
        for c in el.iter(f"{P}cTn"):
            if c.get("presetClass"):
                assert c.get("nodeType") in ("clickEffect", "withEffect", "afterEffect"), i
        if targets:  # every animated text shape has its build entry
            blds = {b.get("spid") for b in el.iter(f"{P}bldP")} | {b.get("spid") for b in el.iter(f"{P}bldGraphic")}
            sps = {sp.find(f"{P}nvSpPr/{P}cNvPr").get("id") for sp in el.iter(f"{P}sp")}
            assert targets & sps <= blds, i


def test_presets_used(built):
    used = set()
    for el in _slides(built["default"]):
        used |= {(c.get("presetClass"), c.get("presetID")) for c in el.iter(f"{P}cTn") if c.get("presetClass")}
    want = {("entr", "10"), ("entr", "2"), ("entr", "22"), ("entr", "42"), ("entr", "49"), ("entr", "53"),
            ("emph", "6"), ("emph", "8"), ("emph", "26")}  # fmt: skip
    assert want <= used


MORPH_RUNS = [  # (first slide, last slide): one Morph run whose slides keep the same "!!" names
    (7, 8), (10, 13), (15, 17), (19, 22), (23, 24)]


def test_morph_slides_and_names(built):
    slides = _slides(built["default"])
    morph = [i for i, el in enumerate(slides, 1) if el.find(f".//{P159}morph") is not None]
    assert morph == [3, 4, 5, 8, 11, 12, 13, 16, 17, 20, 21, 22, 24]
    for i in morph:  # Morph inside mc:AlternateContent, with a Fade fallback
        alt = slides[i - 1].find("{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent")
        assert alt is not None and alt[0].get("Requires") == "p159"
        assert alt[1].find(f"{P}transition/{P}fade") is not None
        assert _names(slides[i - 1]) & _names(slides[i - 2]), i
    for a, b in MORPH_RUNS:
        first = _names(slides[a - 1])
        assert first, a
        for i in range(a, b + 1):
            assert _names(slides[i - 1]) == first, (a, i)
    assert {"!!Panel", "!!Num1", "!!Label1"} <= _names(slides[1]) & _names(slides[2])  # agenda -> section one
    assert {"!!Panel", "!!Num2", "!!Label2"} <= _names(slides[3]) & _names(slides[4])  # agenda -> section two


def test_check_catches_problems(built):
    """The checker itself: an unknown animation target and a lone "!!" name are reported."""
    z = zipfile.ZipFile(io.BytesIO(built["default"]))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as zo:
        for n in z.namelist():
            data = z.read(n)
            if n == "ppt/slides/slide6.xml":
                data = data.replace(b'spTgt spid="', b'spTgt spid="9', 1)
            if n == "ppt/slides/slide1.xml":
                data = data.replace(b'name="Accent bar"', b'name="!!Lonely"')
            zo.writestr(n, data)
    problems = " | ".join(bt.check(out.getvalue()))
    assert "slide 6: animation targets missing shape" in problems
    assert "!!Lonely" in problems


def test_downloads_are_served_as_pptx(client):
    for name in pt.FILES.values():
        r = client.get(pt.URL_DIR + name)
        assert r.status_code == 200, name
        assert r.headers["content-type"] == pt.MEDIA_TYPE
        assert r.content[:2] == b"PK"


@pytest.mark.smoke
def test_templates_page(client):
    r = client.get("/shareable/templates")
    assert r.status_code == 200
    page = r.text
    assert "<h1>PowerPoint templates</h1>" in page
    for key, name in pt.FILES.items():
        assert f'href="{pt.URL_DIR}{name}"' in page
        assert f"Download {pt.PALETTES[key][0]} (.pptx)" in page
    assert "Design › Variants › Colors" in page
    assert "Timeline that slides" in page and "Flow chart that moves" in page
    assert 'href="/shareable/templates"' in page  # the menu item
