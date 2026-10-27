"""Shareable system briefs (owner, 27 Oct 2026): "For the shareables, create a portion for UWB and for V2X and GNSS and
for Automotive Radio (AM/FM/DAB) with Block Diagrams and listing some parts from both Skyworks and Qorvo that's 4
different Docs." Each is a registry entry with the page, the A4 PDF and the PowerPoint; each has a block diagram
from a library diagram and a parts table split into the core solution (AEC-Q qualified only) and peripherals with
their automotive grade (owner, 27 Oct 2026); built only from the site's own content, with no reference to the site."""

import re
from datetime import date
from html import unescape

import pytest

from app.services import presentation_pptx as pp
from app.services import share_doc as sd
from app.services import share_pdf as spdf
from app.services import share_reports as sr
from app.services import share_systems as sy
from app.services import site_guard
from app.services import tech_overview as to
from app.services import tech_overview_edit as te

KEYS = ("uwb", "v2x", "gnss", "radio")
SITE_WORDS = ("BizDev", "/shareable", "http", "Shareable", "on the site", "see the site", "this site")


def default_doc(key: str) -> dict:
    e = sr.registry()[key]
    return e.content(e.build(), te.values({}, e.edit), date.today())


def page_text(html: str) -> str:
    body = html.split('id="share-report"', 1)[1].split("</main>", 1)[0]
    body = re.sub(r"<(script|style|template)\b.*?</\1>", " ", body, flags=re.S)
    body = re.sub(r'<div class="to-actions">.*?</div>', " ", body, flags=re.S)
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", body)).split())


def test_the_four_briefs_are_in_the_registry_with_the_title_style():
    reg = sr.registry()
    assert all(k in reg for k in KEYS)
    for k in KEYS:
        e = reg[k]
        assert e.edit is not None and e.body == "shareable/_system.html" and e.url == f"/shareable/{k}"
        assert te.values({}, e.edit)["hdr.title"].startswith("Skyworks + Qorvo · "), k
    assert [reg[k].label for k in KEYS] == ["UWB in the car", "V2X", "GNSS", "Car radio (AM/FM/DAB)"]


@pytest.mark.parametrize("key", KEYS)
def test_parts_are_active_core_is_automotive_and_both_companies_appear(key):
    b = sr.registry()[key].build()
    active = {r["mpn"] for r in to.active_rows()}
    every = b["core"] + b["peripherals"]
    assert b["left_out"] == [], b["left_out"]  # every listed part is active (and every core part AEC-Q)
    assert 6 <= len(every) <= 12 and b["core"] and b["peripherals"]
    assert all(p["mpn"] in active for p in every)
    assert all(p["aec"] and p["grade"] != sy.NOT_AUTO for p in b["core"]), key  # the core is automotive only
    assert {p["who"] for p in every} == {"Skyworks", "Qorvo"}, key  # the data has both for every brief
    for p in every:
        assert p["grade"] and p["block"] and p["spec"], p
        assert (p["grade"] == sy.NOT_AUTO) == (not p["aec"]), p
    # non-automotive parts appear only among the peripherals, as bundle options
    assert all(p["aec"] for p in b["core"]) and any(not p["aec"] for p in b["peripherals"]), key


def test_core_parts_must_be_automotive_or_they_are_left_out(monkeypatch):
    c = sy.cur("radio")
    bad = {**c, "parts": {"core": [{"mpn": "QPL7433", "at": "ant.lna", "spec": "x"}], "peripherals": []}}
    monkeypatch.setattr(sy, "cur", lambda key: bad)
    out = sy.parts("radio", {"ant.lna": "LNA"})
    assert out["core"] == [] and out["left_out"] == ["QPL7433"]


@pytest.mark.parametrize("key", KEYS)
def test_the_diagram_comes_from_the_library_and_marks_core_and_peripherals(key):
    b = sr.registry()[key].build()
    d = b["diagram"]
    src = sy.source(d["from"])
    assert src.get("groups"), d["from"]  # a library diagram (template or Systems library topic)
    src_ids = {g["id"] for g in src["groups"]}
    assert {g["id"] for g in d["groups"]} <= src_ids and len(d["groups"]) >= 4 and d["links"]
    for p in b["core"] + b["peripherals"]:
        assert p["at"] in d["at"], p  # every part sits in a block of the diagram
    marks = {bl["mark"] for g in d["groups"] for bl in g["blocks"]}
    assert {"core", "peripheral", ""} <= marks
    core_blocks = {f"{g['id']}.{bl['fn']}" for g in d["groups"] for bl in g["blocks"] if bl["mark"] == "core"}
    assert core_blocks == {p["at"] for p in b["core"]}
    svg = d["svg"]
    assert svg.startswith('<svg class="sd-diagram"') and svg.count("<rect") > 10 and "<polygon" in svg
    assert d["title"] in svg


@pytest.mark.parametrize("key", KEYS)
def test_each_brief_renders_on_screen_without_site_references(make_guest, key):
    g, _ = make_guest()
    url = f"/shareable/{key}"
    r = g.get(url)
    assert r.status_code == 200
    html = r.text
    assert html.count('class="to-page"') == 3 and '<svg class="sd-diagram"' in html
    assert html.count("<th>Automotive grade</th>") == 2  # core and peripherals, each with the grade column
    b = sr.registry()[key].build()
    for p in b["core"] + b["peripherals"]:
        assert f"<code>{p['mpn']}</code>" in html, p["mpn"]
    text = page_text(html)
    assert to.share_problems(text) == [] and site_guard.hits(text) == []
    assert not [w for w in SITE_WORDS if w in text]
    assert "would need qualification for the vehicle" in text
    assert g.get(url + "?embed=1").status_code == 200  # the lightbox preview
    assert g.get(url + "/edit", follow_redirects=False).status_code == 403


@pytest.mark.parametrize("key", KEYS)
def test_each_brief_as_pdf_and_powerpoint(client, key):
    d = default_doc(key)
    assert sd.all_text(d) and to.share_problems(sd.all_text(d)) == [] and site_guard.hits(sd.all_text(d)) == []
    r = client.get(f"/shareable/pdf?r={key}")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    pages = spdf.texts(r.content)
    assert 1 <= len(pages) <= 3, len(pages)
    assert all(p.startswith("Skyworks + Qorvo · ") for p in pages)
    text = " ".join(" ".join(pages).split())
    assert d["sections"][1]["blocks"][0]["title"] in text  # the diagram (a vector drawing): its title and blocks
    assert "Core: Skyworks / Qorvo part" in text and "Automotive grade" in text
    b = sr.registry()[key].build()
    for p in b["core"] + b["peripherals"]:
        assert p["mpn"] in text, p["mpn"]
    assert not [w for w in SITE_WORDS if w in text] and b"/URI" not in r.content
    assert site_guard.hits(text) == []
    deck = client.get(f"/shareable/pptx?r={key}")
    assert deck.status_code == 200
    slides = pp.texts(deck.content)
    assert 3 <= len(slides) <= 5, len(slides)
    flat = " ".join(x for s in slides for x in s)
    assert "Core: Skyworks / Qorvo part" in flat and "Automotive grade" in flat
    assert sum(1 for x in slides[1] if x) > 20  # the diagram slide: native boxes and labels
    for p in b["core"] + b["peripherals"]:
        assert p["mpn"] in flat, p["mpn"]
    assert not [w for w in SITE_WORDS if w in flat] and not [h for x in flat.split("\n") for h in site_guard.hits(x)]


def test_the_briefs_merge_with_the_other_reports(client):
    keys = "overview,synergies,automotive,uwb,v2x,gnss,radio"
    r = client.get(f"/shareable/pdf?r={keys}")
    assert r.status_code == 200
    pages = spdf.texts(r.content)
    assert len(pages) <= sum(sr.pages().values())
    heads = list(dict.fromkeys(p.split("\n", 1)[0] for p in pages))
    assert heads[-4:] == ["Skyworks + Qorvo · Automotive UWB", "Skyworks + Qorvo · V2X", "Skyworks + Qorvo · GNSS",
                          "Skyworks + Qorvo · Car radio"]  # fmt: skip
    assert sum(p.count("Sources") for p in pages) == 1
    deck = client.get(f"/shareable/pptx?r={keys}")
    assert deck.status_code == 200 and len(pp.texts(deck.content)) > 20
    html = client.get("/shareable").text
    for k in KEYS:
        assert f'value="{k}"' in html or f"r={k}" in html or f"/shareable/{k}" in html, k


def test_every_default_text_passes_the_checks():
    for k in KEYS:
        rep = sy.REPORTS[k]
        vals = te.values({}, rep)
        bad = {fid: te.check(fid, vals[fid], rep) for fid in rep.specs() if te.check(fid, vals[fid], rep)}
        bad |= {s: why for s in rep.sections() if (why := te.check(f"paras.{s}", vals[f"paras.{s}"], rep))}
        assert bad == {}, (k, bad)
        assert len(vals["paras.talk"]) in (2, 3)


@pytest.mark.parametrize("key", KEYS)
def test_every_block_is_checked_for_both_companies(key):
    """Depth rule (owner, 27 Oct 2026: "this is the sort of depth I expect"): every block of the diagram has a coverage
    entry for Skyworks and for Qorvo, each the best automotive part, a bundle option or "none" with the reason; every
    part named there is active, from that company and graded as stated; every part shown sits in its block's entry."""
    from app.services import autograde

    b = sr.registry()[key].build()
    cov = sy.coverage(key)
    at = b["diagram"]["at"]
    assert set(at) == set(cov), (sorted(set(at) - set(cov)), sorted(set(cov) - set(at)))
    rows = {r["mpn"].upper(): r for r in to.active_rows()}
    for ref, c in cov.items():
        for co in sy.COMPANIES:
            assert c[co], (ref, co)
            for f in c[co]:
                assert f["kind"] in sy.KINDS, (ref, co, f)
                assert len(f["why"]) >= 5, (ref, co, f)  # always a reason
                assert bool(f["mpns"]) == (f["kind"] != "none"), (ref, co, f)
                for m in f["mpns"]:
                    r = rows.get(m.upper())
                    assert r is not None, (ref, co, m)  # active in the catalogue
                    assert r["manufacturer"].lower() == co, (ref, co, m)
                    aec = r.get("automotive") is True or autograde.is_aec(r)
                    assert aec == (f["kind"] == "auto"), (ref, co, m, f["kind"])
    for p in b["core"] + b["peripherals"]:
        named = {m for co in sy.COMPANIES for f in cov[p["at"]][co] for m in f["mpns"]}
        assert p["mpn"] in named, (p["mpn"], p["at"])


def test_coverage_entries_parse():
    f = sy.finding("auto: TQM2M9016 - SDARS / GPS module; bundle: QPQ1063, QPQ1028 - L1 / L2 diplexers")
    assert [(x["kind"], x["mpns"]) for x in f] == [("auto", ["TQM2M9016"]), ("bundle", ["QPQ1063", "QPQ1028"])]
    assert sy.finding("none: all discontinued") == [{"kind": "none", "mpns": [], "why": "all discontinued"}]
    assert sy.finding("maybe QM1")[0]["kind"] == ""


@pytest.mark.parametrize("key", KEYS)
def test_the_gap_line_names_the_blocks_neither_company_covers(client, key):
    b = sr.registry()[key].build()
    cov = sy.coverage(key)
    at = b["diagram"]["at"]
    want = {label for ref, label in at.items() if not ref.endswith(".external_block")
            and all(f["kind"] == "none" for co in sy.COMPANIES for f in cov[ref][co])}  # fmt: skip
    gaps = sy.gaps(key, at)
    assert set(gaps) == want and gaps and b["gaps"] == sy.gap_line(gaps)
    text = page_text(client.get(f"/shareable/{key}").text)
    assert b["gaps"] in text
    assert "coverage" not in text.lower() and "not shown" not in text and "est fit" not in text  # no internal notes
