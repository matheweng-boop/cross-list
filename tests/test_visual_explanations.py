"""Owner's 26 Oct 2026 feedback: a plain-language explanation under every interactive visual's graph ("I want slightly
longer technical explanations. This assumes a lot of pre Knowledge. It would be good to have the explanations below
all graphs"); plus the data written for that day's comments (site_guard, Data quality second round)."""

import re
from datetime import date

import yaml

from app.config import PROJECT_ROOT
from app.services import digest, library, quality, site_guard, visuals

STATIC = PROJECT_ROOT / "app" / "web" / "static"


def _sentences(text: str) -> int:
    return len(re.findall(r"[.!?](?:\s|$)", text.strip()))


def _visual_ids_in_js() -> set[str]:
    ids = set()
    for path in [STATIC / "visuals.js", *sorted((STATIC / "vz").glob("*.js"))]:
        ids |= set(re.findall(r'\bid: "([a-z0-9-]+)", group: "', path.read_text()))
    return ids


def test_every_visual_has_an_explanation_of_3_to_6_sentences():
    ex = visuals.explanations()
    ids = set(library.VISUALS) | _visual_ids_in_js()
    assert len(ids) >= 25 and not ids - set(ex), sorted(ids - set(ex))
    for vid in ids:
        parts = dict(ex[vid])
        assert set(parts) == {"What it shows", "How to read it", "What to try", "Why it matters"}, vid
        n = sum(_sentences(t) for t in parts.values())
        assert 3 <= n <= 6, (vid, n)
        assert not site_guard.hits(" ".join(parts.values())), vid


def test_visuals_page_renders_one_box_per_visual_and_the_panel_slot(client):
    html = client.get("/visuals").text
    src = html.split('id="vz-explain-src"', 1)[1]
    for vid in _visual_ids_in_js():
        assert f'class="vz-explain" data-for="{vid}"' in src, vid
    assert src.count("How to read this visual") == len(_visual_ids_in_js())
    js = (STATIC / "visuals.js").read_text()
    # the box goes below the graph (and below a diagram drawn in .vz-more), before the "what to notice" note
    assert (
        js.index('class="vz-chartwrap"')
        < js.index('class="vz-more"')
        < js.index("vz-explain-slot")
        < js.index('<p class="vz-note">')
    )
    assert "#vz-explain-src" in js


def test_rf_bands_page_has_its_explanation_below_the_chart(client):
    html = client.get("/rf-bands").text
    assert html.index('id="rbt-chart"') < html.index('data-for="rf-bands"')
    assert "How to read this visual" in html and ".vz-explain" in (STATIC / "app.css").read_text()


def test_quality_checked_entries_are_valid():
    data = yaml.safe_load((PROJECT_ROOT / "data" / "business" / "quality_checked.yaml").read_text())
    entries = data["checked"]
    keys = {(e["dataset"], e["key"]) for e in entries}
    assert {("competition", "pol_ldo"), ("competition", "efuse_hotswap")} <= keys
    ds = quality.datasets()
    for e in entries:
        if e["dataset"] == digest.DATASET:  # a To confirm comment the inbox listed with the quality ones (28 Oct 2026)
            assert e["key"].split(":")[0] in digest.TYPES and e.get("comment_at"), e
        else:
            assert e["dataset"] in ds and e["key"] in ds[e["dataset"]][1], e
        assert isinstance(e["date"], date) and str(e.get("note") or "").strip(), e
        assert not site_guard.hits(e["note"])
    assert set(quality.checked()) >= keys


def test_26_oct_texts_pass_site_guard():
    biz = PROJECT_ROOT / "data" / "business"
    risks = yaml.safe_load((biz / "risks.yaml").read_text())
    rs = {r["id"]: r for g in risks["groups"] for r in g.get("risks") or []}
    for rid in ("radio-broadcast-decline", "radio-low-cost-consumer"):
        assert rs[rid].get("answer") and not site_guard.hits(str(rs[rid])), rid
    assert "mandates" in rs["radio-broadcast-decline"]["impact"]
    assert "Not Enough Data" in rs["radio-low-cost-consumer"]["answer"]
    topic = next(t for t in yaml.safe_load((biz / "tam_topics.yaml").read_text())["topics"]
                 if t["id"] == "auto-radio-tuner-ics")  # fmt: skip
    assert "90–92 M" in topic["note"] and "Radio vs. tuner" in topic["note"] and not site_guard.hits(str(topic))
    nm = yaml.safe_load((biz / "evidence" / "new_markets.yaml").read_text())
    answered = [i for t in nm.values() if isinstance(t, dict) for i in t.get("ideas") or [] if i.get("answer")]
    assert len(answered) >= 5 and not any(site_guard.hits(i["answer"]) for i in answered)
    review = (PROJECT_ROOT / "data" / "reviews" / "ti-tpsi3050-q1-isolated-switch.yaml").read_text()
    assert "secondary bias supply" in review and "back-to-back" in review and "optocouplers" in review
    assert not site_guard.hits(review)


def test_low_volume_ideas_moved_to_the_end_and_answers_render(client):
    ideas = yaml.safe_load((PROJECT_ROOT / "data" / "business" / "evidence" / "new_markets.yaml").read_text())
    markets = [i["market"] for i in ideas["wireless_audio"]["ideas"]]
    assert markets[-2].startswith("Musician") and markets[-1].startswith("Assistive listening")
    html = client.get("/business/explore").text
    assert "On your comment:" in html and "low-volume market" in html
    assert "On your comment:" in client.get("/business/risks").text
