"""Three versions per Shareable report (owner, 26 Oct 2026: "make distinct versions but that are more cleanly
formatted, even if information is changed"): the A4 PDF made on the server (Create PDF), the PowerPoint (Create
PowerPoint) and the page, all from one content model (app/services/share_doc.py). The facts, numbers, part names,
categories and sources are the same in the PDF and the slides; only the wording length and the layout differ. Both
files are made on every click from the current data and the owner's saved edits. The browser click is in
tests/test_browser.py."""

import re
from datetime import date

import pytest

from app.config import PROJECT_ROOT
from app.services import presentation_pptx as pp
from app.services import share_doc as sd
from app.services import share_pdf as spdf
from app.services import share_reports as sr
from app.services import share_slides as ss
from app.services import site_guard
from app.services import tech_overview_edit as te

PDF, PPTX = "/shareable/pdf", "/shareable/pptx"
KEYS = ("synergies", "automotive", "overview")


def norm(text: str) -> str:
    return " ".join(str(text).split())


def default_doc(key: str) -> dict:
    e = sr.registry()[key]
    vals = te.values({}, e.edit) if e.edit else te.values({})
    return e.content(e.build(), vals, date.today())


def in_pdf(fact: str, text: str, words: set[str]) -> bool:
    """A fact is in the PDF text: as written, or (a label wrapped inside a table cell) word by word."""
    return norm(fact) in text or all(w in words for w in norm(fact).split())


@pytest.mark.parametrize("key", KEYS)
def test_pdf_and_powerpoint_carry_the_same_facts_within_the_page_budget(client, key):
    d = default_doc(key)
    facts = sd.facts_of(d)
    assert len(facts) > 15, facts  # numbers, categories, part names, tags, sources
    r = client.get(f"{PDF}?r={key}")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == f'attachment; filename="skyworks-qorvo-{key}.pdf"'
    assert r.content.startswith(b"%PDF")
    pages = spdf.texts(r.content)
    assert 1 <= len(pages) <= sr.registry()[key].pages, len(pages)  # synergies 3, automotive 3, overview 4
    assert f"page {len(pages)} / {len(pages)}" in pages[-1] and "Public information" in pages[0]
    assert all(p.startswith("Skyworks + Qorvo · ") for p in pages)  # the header band on every page
    text = norm(" ".join(pages))
    words = set(text.split())
    assert [f for f in facts if not in_pdf(f, text, words)] == []
    slides = norm(" ".join(x for s in pp.texts(client.get(f"{PPTX}?r={key}").content) for x in s))
    assert [f for f in facts if norm(f) not in slides] == []
    for f in (x for x in facts if re.fullmatch(r"[\d,]+\+?", x)):  # every number, exactly
        assert f in text and f in slides, f


@pytest.mark.smoke
def test_pdf_has_no_reference_to_the_site_and_no_links(client):
    r = client.get(f"{PDF}?r=overview,synergies,automotive&wm=draft")
    text = " ".join(spdf.texts(r.content))
    assert "BizDev" not in text and "/shareable" not in text and "http" not in text and "Shareable" not in text
    assert b"/URI" not in r.content and b"/Link" not in r.content  # no clickable links
    assert "· Draft page" in text  # the watermark's tag in the footer
    assert len(spdf.texts(r.content)) <= sum(sr.pages().values())
    assert not [h for h in site_guard.hits(text)]


def test_pdf_refuses_when_the_word_check_finds_something(client, monkeypatch):
    monkeypatch.setattr(site_guard, "hits", lambda text: ["X"] if "Synergies" in text or "synergies" in text else [])
    assert client.get(f"{PDF}?r=synergies").status_code == 409


def test_pdf_with_nothing_ticked_goes_back_and_asks_to_pick(client):
    for q in ("", "?r=", "?r=nothing"):
        r = client.get(PDF + q, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/shareable?pick=1#build-pdf"


def test_combined_pdf_keeps_the_pack_order_and_one_sources_list(client):
    pages = spdf.texts(client.get(f"{PDF}?r=automotive,overview,synergies").content)
    heads = [p.split("\n", 1)[0] for p in pages]
    order = list(dict.fromkeys(heads))
    assert order == ["Skyworks + Qorvo · Technology overview", "Skyworks + Qorvo · Synergies",
                     "Skyworks + Qorvo · Automotive"]  # fmt: skip
    assert sum(p.count("Sources") for p in pages) == 1 and "Sources" in pages[-1]


@pytest.mark.parametrize("key", KEYS)
def test_slides_are_short_one_message_each(key):
    d = default_doc(key)
    slides = ss.from_doc(d, date.today())
    assert slides[0]["kind"] == "title" and slides[-1]["title"] == "Sources"
    for s in slides:
        b = s["body"]
        if s["kind"] == "bullets":
            assert 1 <= len(b["points"]) <= ss.BULLETS, s["title"]
        elif s["kind"] == "table":
            assert 1 <= len(b["rows"]) <= ss.TABLE_ROWS, s["title"]
            assert all(len(str(c)) <= 200 for r in b["rows"] for c in r), s["title"]  # no dense paragraphs
        elif s["kind"] == "cols":
            assert all(len(c["items"]) <= ss.COL_ITEMS for c in b["cols"]), s["title"]
        elif s["kind"] == "pairs":
            assert 1 <= len(b["items"]) <= ss.PAIRS, s["title"]
        assert len(b.get("lead") or "") <= sd.SLIDE_MAX, s["title"]
    data = pp.build(slides, d["head"], date.today())
    assert len(pp.texts(data)) == len(slides)


def test_slide_text_defaults_to_the_first_sentence_and_the_yaml_can_set_it():
    assert sd.first_sentence("One two. Three four.") == "One two."
    assert sd.first_sentence("No stop at all") == "No stop at all"
    long = sd.first_sentence("word " * 80)
    assert len(long) <= sd.SLIDE_MAX and long.endswith("…")
    vals = te.values({}, sr.SYNERGIES)
    assert sd.slide_text(vals, "glance").startswith("Two complementary portfolios")  # set in share_reports.yaml
    assert sd.slide_text(vals, "manufacturing") == sd.first_sentence(" ".join(sd.paras(vals, "manufacturing")))
    assert "slide.glance" in sr.specs_synergies() and "slide.offer" in sr.specs_automotive()
    assert "slide.glance" in te.specs() and te.specs()["slide.glance"].kind == "text"


def test_an_edit_to_a_paragraph_and_its_slide_text_shows_in_the_next_downloads(owner):
    """Owner, 26 Oct 2026: "the owner must be able to edit everything themselves, with no rebuild steps" - a saved
    paragraph and a saved slide text are in the very next PDF and PowerPoint; an empty slide text uses the first
    sentence of the (edited) paragraph."""
    url = sr.SYNERGIES.url
    para = "Both run their key RF processes in-house. Silicon comes from foundry partners."
    try:
        r = owner.post(url + "/edit", data={"paras.manufacturing": para, "pid.manufacturing": "syn-mfg-1",
                                            "slide.glance": "Our edited slide message."},
                       follow_redirects=False)  # fmt: skip
        assert r.status_code == 303, r.text[:300]
        edit = owner.get(url + "/edit").text
        assert 'name="slide.glance"' in edit and "Slide text (PowerPoint)" in edit
        assert "Leave empty to use the first sentence" in edit
        pdf = norm(" ".join(spdf.texts(owner.get(f"{PDF}?r=synergies").content)))
        assert para in pdf
        slides = [x for s in pp.texts(owner.get(f"{PPTX}?r=synergies").content) for x in s]
        assert "Our edited slide message." in slides
        assert "Both run their key RF processes in-house." in slides  # the first sentence, as the slide text
        assert para not in slides  # the slide shows the short version only
    finally:
        owner.post(url + "/edit/reset", data={"all": "1"})
    slides = [x for s in pp.texts(owner.get(f"{PPTX}?r=synergies").content) for x in s]
    assert "Our edited slide message." not in slides


def test_the_preview_has_no_print_button_and_the_pages_link_to_the_files(client):
    js = (PROJECT_ROOT / "app" / "web" / "static" / "shareable_lightbox.js").read_text()
    assert "print" not in js.lower().replace("// no print", "").split("(() =>", 1)[1]
    assert "lb-close" in js and "lb-new" in js  # Close and Open in a new tab stay
    for key in KEYS:
        url = sr.registry()[key].url
        html = client.get(url + "?wm=draft").text
        assert f'href="/shareable/pdf?r={key}&amp;wm=draft"' in html, key
        assert f'href="/shareable/pptx?r={key}&amp;wm=draft"' in html, key
        assert "window.print()" not in html and "Save as PDF" not in html, key
