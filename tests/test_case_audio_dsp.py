"""Case "SKY4680x automotive audio DSP" (owner, 10 Nov 2026: "Today Skyworks announced an audio DSP processor, SKY48 -
make one [research + business case] for that, especially the use cases, where to apply it, and where to hunt"): it is
listed under Research & ideas, the in-depth part follows the research order (product, adjacent parts, use cases,
ranked hunting list, companies per region, competitors, market), names companies only as possible customers and is
free of site names and blocked hosts."""

import html
import re

from app.services import autograde, digest, prelim, site_guard
from app.services import reports as rp

SLUG = "auto-audio-dsp"


def test_case_is_registered_with_a_complete_storyline():
    r = rp.report(SLUG)
    assert r and r["kind"] == "idea" and r["app_type"] == "Car radio" and r["feasibility"] == 1
    assert rp.story_problems(r) == [] and rp.has_background(SLUG) and r["answer"]["conf"] == "low"
    assert rp.blocked_words(r["say_externally"]) == []
    assert [x["age"] for x in rp.learn(r)] == list(rp.LEARN_AGES)
    c = prelim.raw(SLUG)
    assert digest.words(c["gist"]) <= digest.MAX_WORDS and len(c["abstract"]) == 3
    assert not digest.by_key()[f"background:{SLUG}"]["auto"]


def test_depth_follows_the_research_order_and_ranks_the_hunt():
    d = prelim.raw(SLUG)["depth"]
    assert [t["id"] for t in d["tables"]] == ["product", "attach", "where", "hunt", "who", "rivals", "market"]
    for t in d["tables"]:
        assert t["rows"] and all(len(row) == len(t["columns"]) for row in t["rows"]), t["id"]
    hunt = next(t for t in d["tables"] if t["id"] == "hunt")
    scores = [int(r[5]) for r in hunt["rows"]]
    assert scores == sorted(scores, reverse=True)
    for r in hunt["rows"]:  # score = fit x size x access
        f, s, a = (int(x.split(":")[0]) for x in r[2:5])
        assert f * s * a == int(r[5]), r[1]
    regions = {r[0] for r in next(t for t in d["tables"] if t["id"] == "who")["rows"]}
    assert {"Americas", "EMEA", "Asia"} <= {x.strip() for g in regions for x in g.split(",")}


def test_public_facts_parts_and_grades_stay_honest():
    c = prelim.raw(SLUG)
    text = " ".join(str(x) for t in c["depth"]["tables"] for r in t["rows"] for x in r)
    for t in ("SKY46801A1GE1AM", "SKY46803A1GC1AM", "on-chip SRAM", "Audio Weaver", "Not found", "AM2754-Q1",
              "AM62D-Q1", "$28.43–33.23", "No part named SKY48 found", "see the UL2X case"):  # fmt: skip
        assert t in text, t
    for mpn in ("Si47971", "Si46921", "Si5332A-AM1", "QPF4239Q", "SKYA21040", "ACT4751MQI101"):
        assert autograde.is_aec(mpn), mpn
    for mpn in ("SKY76360-22", "Si8241"):
        assert not autograde.is_aec(mpn), mpn
    assert not autograde.is_aec("SKY46801A1GE1AM")  # grade not stated publicly: never marked AEC-Q here


def test_page_renders_and_is_public_safe(client):
    page = html.unescape(client.get(f"/business/reports/{SLUG}").text)
    assert 'id="in-depth"' in page and "Where to hunt" in page and "Companies that publicly build" in page
    assert page.index("1. Position against the competition") < page.index('id="in-depth"')
    bg = html.unescape(client.get(f"/business/reports/{SLUG}/background").text)
    assert (
        "Requests made for this report" in bg
        and "SKY4680x-Automotive-Audio-DSP" in bg
        and "ti.com/product/AM2754-Q1" in bg
    )
    assert "/business/reports/" + SLUG in client.get("/business/reports").text
    for name in (f"{SLUG}.html", f"{SLUG}.background.html"):
        body = (rp.BODIES / name).read_text()
        assert not site_guard.hits(body), name
    raw = (prelim.FOLDER / f"{SLUG}.yaml").read_text()
    assert not site_guard.hits(raw) and "data centre" not in raw.lower()
    links = re.findall(r'href="(https?://[^"]+)"', (rp.BODIES / f"{SLUG}.background.html").read_text())
    assert len(links) >= 8
    for host in (
        "qorvo.com",
        "globenewswire",
        "sec.gov",
        "analog.com",
        "nxp.com",
        "www.qualcomm.com",
        "mouser",
        "digikey",
    ):
        assert not any(host in u for u in links), host  # named as "not requested" in the text, never linked
    assert "qorvo.com" not in raw
    low = raw.lower()
    assert not re.search(r"\b(buys? from|customer of|design[- ]win)\b", low)
