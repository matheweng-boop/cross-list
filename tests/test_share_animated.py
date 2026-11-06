"""Animated presentation of each Shareable document (owner, 6 Nov 2026): /shareable/animated/<key> builds the
report's slides as an animated .pptx (app/services/share_animated.py). Every deck opens in python-pptx, passes the
template checks (theme colours, timing targets, Morph names), carries the same words as Create PowerPoint, has no
reference to the site and passes the public-safe word check."""

import io
import re
import zipfile

import pytest
from pptx import Presentation

from app.services import pptx_anim as pa
from app.services import presentation_pptx as pp
from app.services import share_animated as sa
from app.services import share_reports as sr
from app.services import site_guard

SITE_WORDS = ("BizDev", "/shareable", "http", "Shareable", "on the site", "see the site", "this site")
KEYS = [r.key for r in sr.REGISTRY]
P159 = "{http://schemas.microsoft.com/office/powerpoint/2015/09/main}"


@pytest.mark.parametrize("key", KEYS)
def test_each_report_as_an_animated_deck(client, key):
    r = client.get(f"/shareable/animated/{key}")
    assert r.status_code == 200, key
    assert r.headers["content-type"] == sa.MEDIA_TYPE
    assert f'filename="{sa.filename(key)}"' in r.headers["content-disposition"]
    deck = r.content
    assert pa.check(deck) == [], key  # zip, XML, theme colours only, timing targets, Morph names
    prs = Presentation(io.BytesIO(deck))
    slides = list(prs.slides)
    assert slides[-1].shapes.title.text == "Thank you"
    morph = [i for i, s in enumerate(slides) if s._element.find(f".//{P159}morph") is not None]
    assert morph, key
    for i in morph:  # agenda -> section divider: the highlighted row and number travel
        names = {sh.name for sh in slides[i].shapes} & {sh.name for sh in slides[i - 1].shapes}
        assert "!!Panel" in names and any(n.startswith("!!Num") for n in names), (key, i)
    texts = sa.texts(deck)
    flat = "\n".join(texts)
    assert not [w for w in SITE_WORDS if w in flat], key
    assert not [h for t in texts for h in site_guard.hits(t)], key
    # the same words as Create PowerPoint: every table cell and point of the plain deck is in the animated one
    plain = pp.texts(client.get(f"/shareable/pptx?r={key}").content)
    lines = {ln.strip().lstrip("•").strip() for s in plain[1:] for x in s for ln in x.split("\n")}
    words = {w for w in lines if w and "·" not in w and not re.fullmatch(r"\d+ / \d+|\d+\.?", w)}
    missing = [w for w in words if w not in flat]
    assert not missing, (key, missing[:5])


def test_system_brief_diagram_builds_and_highlights_our_parts(client):
    deck = client.get("/shareable/animated/uwb").content
    prs = Presentation(io.BytesIO(deck))
    diagram = next(s for s in prs.slides if s.shapes.title is not None and s.shapes.title.text == "Block diagram")
    x = diagram._element.xml
    assert x.count('presetClass="entr" presetSubtype="16"') > 20  # blocks zoom in
    assert 'filter="wipe(' in x  # connections wipe in
    assert 'presetClass="emph"' in x  # our parts pulse
    z = zipfile.ZipFile(io.BytesIO(deck))
    assert not [n for n in z.namelist() if n.startswith("ppt/slides/") and b"srgbClr" in z.read(n)]


def test_animated_deck_carries_the_owners_edits(client):
    client.post("/shareable/automotive/edit", data={"title": "Cars: our edited title"})
    try:
        deck = client.get("/shareable/animated/automotive").content
        assert "Cars: our edited title" in sa.texts(deck)
    finally:
        client.post("/shareable/automotive/edit/reset", data={"all": "1"})


def test_animated_deck_refuses_when_the_word_check_finds_something(client, monkeypatch):
    monkeypatch.setattr(site_guard, "hits", lambda text: ["X"] if "Synergies" in text else [])
    assert client.get("/shareable/animated/synergies").status_code == 409
    assert client.get("/shareable/animated/nothing").status_code == 404


def test_each_row_offers_the_animated_download(client):
    html = client.get("/shareable").text
    for key in KEYS:
        assert f'href="/shareable/animated/{key}" download' in html, key
    assert html.count(">Animated .pptx</a>") == len(KEYS)
