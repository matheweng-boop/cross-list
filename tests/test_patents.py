"""US patent landscape per technology platform (data/business/evidence/patents_platforms.yaml). Owner, 25 Oct 2026:
"Also scour more Skyworks and Qorvo patents", then "Keep it background only. No patent landscape page. Yes, also use it
in the priority score. Add it to the synergies, as long as the addition is not too verbose."""

from urllib.parse import urlparse

import pytest

from app.services import patents
from app.services import priority as pr
from app.web import nav

try:  # the browser fixture (a tab on the live app, checked at 390 px afterwards); skipped without Playwright
    from tests.test_browser import page  # noqa: F401
except pytest.skip.Exception:
    pass

# the platforms of the Shareable technology overview the owner asked about, plus GNSS for the automotive cut
PLATFORMS = {"baw", "saw", "gaas_hbt", "gaas_phemt", "gan", "soi", "sige", "modules", "beamformers", "isolation",
             "timing", "broadcast", "power", "motor", "uwb", "ble", "envelope_tracking", "antenna_tuning", "lna",
             "wifi_filters", "nr_5g", "gnss"}  # fmt: skip
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
        assert 1 <= sum(len(e["examples"][co]) for co in patents.COMPANIES), k
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


def _row(fn, feas):
    return {"fn": fn, "key": fn, "label": fn, "reach": 4, "background": 0, "feasibility": feas, "distance": None,
            "gap_type": "true_gap"}  # fmt: skip


def test_a_large_bonus_is_capped(monkeypatch):
    """Owner, 26 Oct 2026: patents are machine-checked, so the bonus stays small: whatever the table says, it never
    exceeds patent_bonus_cap (half the platform bonus), and L never exceeds 1.0."""
    cfg = pr.config()["likeliness"]
    assert cfg["patent_bonus_cap"] == 0.05 and cfg["patent_bonus_cap"] <= cfg["platform_bonus"] / 2
    monkeypatch.setitem(cfg["patent_bonus"], "strong", 0.5)
    li = pr.likeliness(_row("power_amplifier", 2))  # 0.6 + 0.1 (GaAs HBT platform of ours) + 0.05 (capped)
    assert li["value"] == pytest.approx(0.75) and li["patent"]["bonus"] == 0.05
    assert "+ 0.05 for US patents (strong, GaAs HBT power amplifiers platform; indicative, not reviewed)" in li["basis"]
    monkeypatch.setitem(cfg, "patent_bonus_cap", 0.5)  # a raised cap still stops L at 1.0
    li = pr.likeliness(_row("power_amplifier", 2))
    assert li["value"] == 1.0 and "(capped at 1.0)" in li["basis"]


def test_the_patent_bonus_never_decides_more_than_a_few_points():
    """At the default weights the patent bonus moves a priority by at most 1.5 of 100 points, less than any other
    part of the score can (platform bonus 3 points, a feasibility step 9 points)."""
    cfg, w = pr.config()["likeliness"], pr.default_weights()
    assert max(cfg["patent_bonus"].values()) <= cfg["patent_bonus_cap"]
    assert 100 * w["likeliness"] * cfg["patent_bonus_cap"] <= 1.5 + 1e-9
    assert cfg["patent_bonus_cap"] < cfg["platform_bonus"]
    steps = sorted(f["value"] for f in cfg["feasibility"].values())
    assert cfg["patent_bonus_cap"] < min(b - a for a, b in zip(steps, steps[1:], strict=False))


def test_patent_bonus_in_likeliness_capped_and_not_on_owner_answers():
    bonus = pr.config()["likeliness"]["patent_bonus"]
    assert bonus == {"strong": 0.05, "some": 0.025, "little": 0.0, "none_found": 0.0}
    assert pr.patent_bonus("pol_ldo")["bonus"] == 0.05  # strong
    assert pr.patent_bonus("adc")["bonus"] == 0.025  # some
    assert pr.patent_bonus("supervisor")["bonus"] == 0.0  # little
    assert pr.patent_bonus("frequency_multiplier") == {"depth": None, "bonus": 0.0, "source": "", "label": ""}
    adc = pr.likeliness(_row("adc", 2))  # 0.6 (+ 0.1 for a platform of ours) + 0.025
    plat = pr.config()["likeliness"]["platform_bonus"] if pr._platforms().get("adc") else 0
    assert adc["value"] == pytest.approx(0.6 + plat + 0.025)
    assert "+ 0.025 for US patents (some; indicative, not reviewed)" in adc["basis"]
    ldo = pr.likeliness(_row("pol_ldo", 1))  # 1.0 + 0.05 stays 1.0
    assert ldo["value"] == 1.0 and "L already 1.0" in ldo["basis"]
    flt = pr.likeliness(_row("filter_saw_baw", 3))  # 0.3 + 0.1 (platform of ours) + 0.05 (BAW platform, strong)
    assert flt["value"] == pytest.approx(0.45) and "BAW filters platform" in flt["basis"]
    temp = pr.likeliness(_row("temperature_sensor", 1))  # the owner's answer replaces the value: no bonus
    assert temp["value"] == 0.3 and temp["patent"]["bonus"] == 0.0
    for fn in ("pol_ldo", "adc", "filter_saw_baw", "power_amplifier", "circulator_isolator", "rf_synthesizer"):
        for feas in (1, 2, 3, None):
            assert 0 <= pr.likeliness(_row(fn, feas))["value"] <= 1.0


def test_no_patent_landscape_page(client):
    assert client.get("/business/competitors/patents").status_code == 404
    assert client.get("/business/patent-landscape").status_code == 404
    labels = [i[0] for s in (*nav.NAV, nav.UTILITY) for i in s[2]] + [t[0] for g in nav.TABS for t in g]
    assert not any("patent" in x.lower() for x in labels)


def test_evidence_page_shows_the_platform_and_bonus(client):
    r = client.get("/business/evidence/uwb_soc")
    assert r.status_code == 200
    assert "small bonus in the priority score" in r.text and "Platform: UWB" in r.text
    assert "image-ppubs.uspto.gov/dirsearch-public/print/downloadPdf/" in r.text
    assert "Priority score: + 0.025 to likeliness" in r.text or "Priority score: + 0.05 to likeliness" in r.text
    r = client.get("/business/evidence/pol_ldo")  # no platform: only its own entry and the bonus line
    assert "Platform:" not in r.text and "Priority score: + 0.05 to likeliness for strong patent depth" in r.text
    assert "indicative, not reviewed" in r.text


def test_patents_are_checked_automatically_not_reviewed(client):
    """Owner, 26 Oct 2026: "I can't check patents": no review buttons on patents, a "checked automatically" label with
    the date of the machine check on the evidence page and the Technology platforms page."""
    html = client.get("/business/evidence/pol_ldo").text
    assert "checked automatically, 19 Oct 2026" in html
    assert 'data-ds="patents"' not in html  # no ✓ / ✗ / ? on patents
    assert 'data-ds="foundry"' in html  # the other evidence keeps its review buttons
    caps = client.get("/business/capabilities").text
    assert "US patents:" in caps and "checked automatically, 25 Oct 2026" in caps and "indicative, not reviewed" in caps


def test_how_the_score_works_lists_the_patent_bonus(client):
    r = client.get("/business/opportunities?show=all")
    assert r.status_code == 200
    assert "US patents of Skyworks / Qorvo: strong / some depth" in r.text
    assert "patents: strong" in r.text or "patents: some" in r.text
    assert "for US patents" in r.text  # a worked example or a tooltip writes the bonus out


@pytest.mark.browser
def test_browser_evidence_patent_box_fits_a_phone(page):  # noqa: F811
    """The patents box with its platform bars on an evidence page; the page fixture reopens it at 390 px and fails on
    sideways scrolling or a console error."""
    pytest.importorskip("playwright.sync_api")
    from tests.test_browser import go

    go(page, "/business/evidence/filter_saw_baw")
    box = page.locator("article.bo-ev", has_text="small bonus in the priority score")
    assert box.locator(".pt-plat").is_visible() and box.locator(".pt-bar").count() == 2
    assert box.get_by_text("Platform: BAW filters").is_visible()


def test_maintenance_says_patents_feed_the_priority_score():
    from app.services import maintenance

    assert "likeliness" in maintenance.AFFECTS["patents"] and "not scored" not in maintenance.AFFECTS["patents"]
