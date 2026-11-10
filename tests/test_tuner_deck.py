"""Skyworks tuner portfolio deck (owner, 10 Nov 2026): an animated, high-level .pptx with no product numbers, built
on request and downloadable only by the owner from Shareable > Private · only for you."""

import io
import re
import zipfile
from pathlib import Path

import pytest
from pptx import Presentation

from app.services import pptx_anim as pa
from app.services import site_guard
from app.services import tuner_deck as td

ROOT = Path(__file__).resolve().parent.parent
P159 = "{http://schemas.microsoft.com/office/powerpoint/2015/09/main}"
URL = "/shareable/private/" + td.FILENAME
PART = re.compile(r"\b(?:Si|SKY|TEF|TDA|SAF|ADV|AK|LC|STA|QP[A-Z]?)\d{2,}|\b[A-Za-z]{1,5}-?\d{3,}[A-Za-z]*\b")


@pytest.fixture(scope="module")
def blob():
    return td.build()


def _texts(blob) -> list[str]:
    prs = Presentation(io.BytesIO(blob))
    out = []
    for s in prs.slides:
        out += [sh.text_frame.text for sh in s.shapes if sh.has_text_frame]
        out.append(s.notes_slide.notes_text_frame.text if s.has_notes_slide else "")
    return out


@pytest.mark.smoke
def test_deck_passes_the_checks(blob):
    assert pa.check(blob) == []
    assert td.build() == blob  # deterministic


def test_slide_count_notes_and_morph(blob):
    prs = Presentation(io.BytesIO(blob))
    assert len(prs.slides) == td.SLIDE_COUNT == len(td.OUTLINE) == 10
    assert prs.slide_width * 9 == prs.slide_height * 16
    for i, s in enumerate(prs.slides, 1):
        assert s.has_notes_slide and len(s.notes_slide.notes_text_frame.text) > 150, f"slide {i}: no talk track"
    morph = [i for i, s in enumerate(prs.slides, 1) if s._element.find(f".//{P159}morph") is not None]
    assert morph == [4, 5]  # block diagram -> analog -> digital
    xml = zipfile.ZipFile(io.BytesIO(blob))
    slides = [xml.read(f"ppt/slides/slide{i}.xml").decode() for i in range(1, 11)]
    assert all('presetClass="entr"' in x for i, x in enumerate(slides) if i not in (3, 4))  # Morph does slides 4-5
    assert 'presetClass="entr"' in slides[3] and 'presetClass="entr"' in slides[4]
    assert "!!Copro" in slides[4] and "!!Copro" not in slides[3]  # the digital block appears with Morph
    assert "Harbor" in xml.read("ppt/theme/theme1.xml").decode()


def test_no_part_numbers_or_site_references(blob):
    texts = _texts(blob)
    joined = "\n".join(texts)
    assert not PART.findall(joined), PART.findall(joined)
    for word in ("BizDev", "http", "www.", "Questions?", "est)"):
        assert word not in joined, word
    assert not [h for t in texts for h in site_guard.hits(t)]
    for must in ("Noise cancellation", "phase diversity", "co-processor", "DAB/DAB+", "HD Radio", "DRM", "CDR"):
        assert must in joined, must


def test_owner_downloads_it(client):
    r = client.get(URL)
    assert r.status_code == 200
    assert r.headers["content-type"] == td.MEDIA_TYPE
    assert r.headers["content-disposition"] == f'attachment; filename="{td.FILENAME}"'
    assert r.content[:2] == b"PK" and pa.check(r.content) == []
    page = client.get("/shareable/private")
    assert page.status_code == 200
    assert "<h1>Private · only for you</h1>" in page.text
    assert "Material for your own use; not listed for guests" in page.text
    assert f'href="{URL}"' in page.text
    assert 'href="/shareable/private"' in client.get("/shareable").text  # the menu item


def test_guest_is_refused_and_sees_nothing(make_guest):
    guest, _ = make_guest()
    assert guest.get(URL).status_code == 403
    assert guest.get("/shareable/private").status_code == 403
    for page in ("/shareable", "/shareable/templates"):
        html = guest.get(page).text
        assert "/shareable/private" not in html and "Private · only for you" not in html


def test_not_stored_under_static():
    """Built on request: no copy under static/ (any signed-in guest can read those) or anywhere in app/."""
    assert not [p for p in (ROOT / "app").rglob("*.pptx") if "tuner" in p.name]
