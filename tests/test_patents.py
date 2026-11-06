"""US patent landscape per technology platform (data/business/evidence/patents_platforms.yaml). Owner, 25 Oct 2026:
"Also scour more Skyworks and Qorvo patents", then "Keep it background only. No patent landscape page. Yes, also use it
in the priority score. Add it to the synergies, as long as the addition is not too verbose."""

from urllib.parse import urlparse

import pytest

from app.services import patents
from app.web import nav

try:  # the browser fixture (a tab on the live app, checked at 390 px afterwards); skipped without Playwright
    from tests.test_browser import page  # noqa: F401
except pytest.skip.Exception:
    pass

# the platforms of the Shareable technology overview the owner asked about, plus GNSS for the automotive cut
PLATFORMS = {"baw", "saw", "gaas_hbt", "gaas_phemt", "gan", "soi", "sige", "modules", "beamformers", "isolation",
             "timing", "broadcast", "power", "motor", "uwb", "ble", "envelope_tracking", "antenna_tuning", "lna",
             "wifi_filters", "nr_5g", "gnss"}  # fmt: skip
# the areas added on 6 Nov 2026 (owner's item 2)
NEW = {"pcie_timing", "isolated_sensing", "desat_gate_drivers", "ntn", "gnss_antijam", "motor_hvac", "robotics",
       "efuse"}  # fmt: skip
PLATFORMS |= NEW
AUTO = {"auto_uwb", "auto_isolation", "auto_timing", "auto_fem", "auto_gnss", "auto_broadcast", "auto_power_motor"}


def _urls(entry):
    for co in patents.COMPANIES:
        for x in (entry.get("examples") or {}).get(co) or []:
            yield x["url"]
    for ev in (entry.get("check") or {}).get("evidence") or []:
        if ev.startswith("http"):
            yield ev.split()[0]


def test_yaml_validates():
    d = patents.load()
    assert d["source"].startswith("USPTO Patent Public Search") and "not legal advice" in d["disclaimer"]
    assert set(patents.platforms()) == PLATFORMS and set(patents.automotive()) == AUTO
    for k, e in {**patents.platforms(), **patents.automotive()}.items():
        for f in ("query", "count", "date", "confidence", "skyworks", "qorvo", "check"):
            assert e.get(f) is not None, (k, f)
        assert ".as." in e["query"] and "skyworks" in e["query"] and "qorvo" in e["query"], k
        assert e["confidence"] in ("high", "medium", "low"), k
        assert e["skyworks"] + e["qorvo"] >= e["count"] >= max(e["skyworks"], e["qorvo"]), k
        assert e["check"]["status"] in ("confirmed", "partly") and e["check"]["evidence"], k
        for u in _urls(e):  # examples and checks link to the USPTO only
            assert urlparse(u).scheme == "https" and urlparse(u).hostname in patents.USPTO_HOSTS, (k, u)
    for k, e in patents.platforms().items():
        assert e["depth"] in patents.DEPTHS and e["leader"] in ("skyworks", "qorvo", "both"), k
        assert all(len(e["trend"][co]) == 3 and sum(e["trend"][co]) == e[co] for co in patents.COMPANIES), k
        assert e["count"] == 0 or 1 <= sum(len(e["examples"][co]) for co in patents.COMPANIES), k
        assert e["examples"]["skyworks"][:3] == e["examples"]["skyworks"] and len(e["examples"]["qorvo"]) <= 3, k
    for e in patents.automotive().values():
        assert e["platform"] in PLATFORMS and "vehicle" in e["query"] and e["broad_count"] >= e["count"]
    ov = d["overlap"]
    assert set(ov["overlap"]) <= PLATFORMS and set(ov["thin"]) <= PLATFORMS
    assert not set(ov["complement"]["skyworks"]) & set(ov["complement"]["qorvo"])


def test_every_function_named_in_a_platform_exists():
    from app.services import blocks

    fns = blocks.catalogue()["functions"]
    for k, e in patents.platforms().items():
        assert set(e.get("functions") or []) <= set(fns), k


def test_patent_summary_is_compact_and_public():
    s = patents.patent_summary()
    assert set(s["platforms"]) == PLATFORMS and "not legal advice" in s["note"]
    for k, r in s["platforms"].items():
        assert set(r) == {"label", "leader", "skyworks", "qorvo", "automotive"}, k
        assert r["leader"] in ("skyworks", "qorvo", "both") and isinstance(r["automotive"], bool)
        assert r["skyworks"] < 20 or r["skyworks"] % 5 == 0  # rounded for sharing
    assert s["platforms"]["uwb"]["automotive"] and not s["platforms"]["baw"]["automotive"]
    assert s["platforms"]["gan"]["leader"] == "qorvo" and s["platforms"]["saw"]["leader"] == "skyworks"
    assert patents._round(7) == 7 and patents._round(47) == 45 and patents._round(274) == 270
    assert set(s["overlap"]) <= PLATFORMS and set(s["complement"]) == {"skyworks", "qorvo"}


def test_depth_per_function_then_platform():
    assert patents.depth("pol_ldo") == {"depth": "strong", "source": "function", "label": ""}
    got = patents.depth("filter_saw_baw")  # an RF band gap with no per-function entry: its BAW platform
    assert got["source"] == "platform" and got["depth"] == patents.platforms()["baw"]["depth"]
    assert patents.depth("frequency_multiplier") is None and patents.depth("no_such_function") is None


def test_no_patent_landscape_page(client):
    assert client.get("/business/competitors/patents").status_code == 404
    assert client.get("/business/patent-landscape").status_code == 404
    labels = [i[0] for s in (*nav.NAV, nav.UTILITY) for i in s[2]] + [t[0] for g in nav.TABS for t in g]
    assert not any("patent" in x.lower() for x in labels)


def test_evidence_page_shows_the_platform_and_barrier(client):
    r = client.get("/business/evidence/uwb_soc")
    assert r.status_code == 200
    assert "± a few points in the priority score" in r.text and "Platform: UWB" in r.text
    assert "image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/" in r.text
    assert "Patent barrier " in r.text and "Similarity to our technology:" in r.text
    assert "Distance to our technology:" in r.text and "Difficulty of recreating it:" in r.text
    assert "Patents (US, 5 years): ours " in r.text and "not legal advice" in r.text
    assert "Competitors, last 5 years" in r.text and "Whole US portfolio" in r.text
    r = client.get("/business/evidence/pol_ldo")  # no platform: only its own entry, no adjustment
    assert "Platform:" not in r.text and "no patent adjustment" in r.text
    assert "indicative, not reviewed" in r.text


def test_patents_are_checked_automatically_not_reviewed(client):
    """Owner, 26 Oct 2026: "I can't check patents": no review buttons on patents, a "checked automatically" label with
    the date of the machine check on the evidence page and the Technology platforms page."""
    html = client.get("/business/evidence/pol_ldo").text
    assert "checked automatically, 19 Oct 2026" in html
    assert 'data-ds="patents"' not in html  # no ✓ / ✗ / ? on patents
    assert 'data-ds="foundry"' in html  # the other evidence keeps its review buttons
    from app.services import opportunity as op
    from app.services import quality

    low = next(c for c in quality.checks(op.applications()) if c["title"] == "Low-confidence evidence")
    assert any(e.get("confidence") == "low" for e in patents.per_function().values())  # there are some to leave out
    assert low["n"] == sum(e.get("confidence") == "low" for t in op.EVIDENCE_TOPICS if t != "patents"
                           for e in op.evidence(t).values() if isinstance(e, dict))  # fmt: skip
    assert not any(x.startswith("patents:") for x in low["examples"])  # Data quality never asks for a patent review
    caps = client.get("/business/capabilities").text
    assert "US patents:" in caps and "checked automatically, 25 Oct 2026" in caps and "indicative, not reviewed" in caps


def test_how_the_score_works_explains_the_patent_barrier(client):
    r = client.get("/business/opportunities?show=all")
    assert r.status_code == 200
    assert 'id="how-patents"' in r.text and "Similarity to our technology" in r.text
    assert "Difficulty of recreating it" in r.text and "Distance to our technology" in r.text
    assert "patents: barrier " in r.text and "Patents (US, 5 years): ours " in r.text
    assert "(patents) = " in r.text  # the worked example writes the adjustment out


@pytest.mark.browser
def test_browser_evidence_patent_box_fits_a_phone(page):  # noqa: F811
    """The patents box with its platform bars on an evidence page; the page fixture reopens it at 390 px and fails on
    sideways scrolling or a console error."""
    pytest.importorskip("playwright.sync_api")
    from tests.test_browser import go

    go(page, "/business/evidence/filter_saw_baw")
    box = page.locator("article.bo-ev", has_text="± a few points in the priority score")
    assert box.locator(".pt-plat").is_visible() and box.locator(".pt-bar").count() == 2
    assert box.get_by_text("Platform: BAW filters").is_visible()


def test_maintenance_says_patents_feed_the_priority_score():
    from app.services import maintenance

    assert "patent barrier" in maintenance.AFFECTS["patents"] and "not scored" not in maintenance.AFFECTS["patents"]
