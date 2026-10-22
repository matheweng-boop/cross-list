"""Physics behind our products (owner, 22 Oct 2026): physics topics per product family, new interactive visuals,
public physics and maths resources, and the weekly standing work."""

import re
from urllib.parse import urlparse

from app.config import PROJECT_ROOT
from app.services import knowledge, library, rf_notes, runs

JS = (PROJECT_ROOT / "app" / "web" / "static" / "visuals.js").read_text()
NEW_VISUALS = ("bvd", "mod", "jitter", "swloss")


def physics():
    return [t for t in rf_notes.topics() if t["category"] == "physics"]


def test_physics_topics_complete_and_linked():
    assert len(physics()) >= 18
    assert rf_notes.problems() == []
    for t in physics():
        assert t["id"].startswith("phys_") and t["equations"] and len(t["why"]) >= 2, t["id"]
        assert t["sources"] and t["try"], t["id"]


def test_every_product_family_has_its_physics():
    ids = {t["id"] for t in physics()}
    fams = {k for t in physics() for k in t["families"]}
    for p in knowledge.data()["products"]:
        assert p["key"] in fams, p["key"]
        assert ids & set(p.get("rf_notes") or []), p["key"]  # shown on the By product card
    # the owner's list: RF, timing, isolation, power and broadcast radio
    for words in ("SAW and BAW", "noise", "Linearity", "RF switches", "GaN", "VSWR", "superheterodyne", "Phase noise",
                  "quartz", "Phase-locked", "capacitive and magnetic", "breakdown", "Creepage",
                  "inductors and capacitors", "Switching and conduction", "AM and FM"):
        assert any(words in t["title"] for t in physics()), words


def test_links_go_to_openstax_first_and_polite_hosts():
    blocked = {urlparse(s["url"]).netloc for s in library.sources() if s["feasibility"] == "blocked" and s.get("url")}
    for t in physics():
        hosts = [urlparse(s["url"]).netloc for s in t["sources"] + t["try"]]
        assert not any(h.endswith("qorvo.com") or h == "www.qualcomm.com" or h in blocked for h in hosts), t["id"]
    # owner, 22 Oct 2026: HyperPhysics replaced by OpenStax University Physics
    assert not any("hyperphysics" in s["url"] for t in physics() for s in t["sources"] + t["try"])
    first = [t for t in physics() if t["sources"][0]["url"].startswith("https://openstax.org/books/university-physics-volume-")]
    assert len(first) >= 14


def test_rf_notes_page_shows_physics(client):
    page = client.get("/rf-notes").text
    assert 'id="cat-physics"' in page and 'id="phys_am_fm"' in page
    assert "Key equations" in page and "Why it matters to the customer" in page
    assert 'href="/knowledge#p-tuners"' in page and 'href="/find?q=Si47"' in page and 'href="/visuals#mod"' in page
    assert 'href="/engineering/cmti_kv_us"' in page and "Try it yourself" in page
    assert "university-physics-volume-2/pages/15-5-resonance-in-an-ac-circuit" in page and "hyperphysics" not in page


def test_by_product_cards_link_the_physics(client):
    page = client.get("/knowledge").text
    assert 'href="/rf-notes#phys_isolation_coupling"' in page and 'href="/visuals#jitter"' in page


def test_new_visuals_name_their_families_and_topics(client):
    ids = {t["id"] for t in physics()}
    fams = {p["key"] for p in knowledge.data()["products"]}
    for v in NEW_VISUALS:
        assert v in library.VISUALS
        block = JS.split(f'id: "{v}", group:')[1].split("V.push(")[0]
        assert {f for f in re.findall(r"/knowledge#p-([a-z_]+)", block)} <= fams and "/knowledge#p-" in block, v
        topics = re.findall(r'"(phys_[a-z_]+)"\]', block)
        assert topics and set(topics) <= ids, v
    assert "vz-explains" in JS
    assert client.get("/visuals").status_code == 200


def test_resources_recorded_with_what_they_are_good_for(client):
    src = {s["id"]: s for s in library.sources()}
    for k in ("hyperphysics", "openstax", "falstad", "phet", "wolframdemos", "desmos", "lamar", "betterexplained", "microwaves101"):
        assert src[k]["offers"] and src[k]["access"] and src[k]["licence"], k
    page = client.get("/library/sources").text
    assert "physics and maths" in page and "Falstad" in page


def test_weekly_physics_run():
    weekly = [j for j in runs.jobs() if j["frequency"] == "weekly"]
    job = next(j for j in weekly if j["name"] == "Physics & visuals")
    assert "tonight" not in job and job["where"] == "/visuals" and "Saturday" in job["what"]
    doc = (PROJECT_ROOT / "docs" / "daily_update.md").read_text()
    line = "Physics & visuals (weekly, the Saturday evening run only): one or two more fundamentals topics or visuals"
    assert line in doc


def test_search_finds_physics():
    from app.services import notes_search

    assert any(h.source == "RF note" and "AM and FM" in h.title for h in notes_search.search("Carson"))
