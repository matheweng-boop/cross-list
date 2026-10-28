"""Owner's comments of 28 Oct 2026 on "Interior radar for child presence detection": the regulation note (a), the UWB /
Wi-Fi engineering page with its decision matrix (b), anchors vs tags (c), CPD vs ranging (d) and the QPF5100Q pairing
(e), all as application knowledge with sources and linked from Part knowledge and the Systems library."""

import pytest

from app import yamlio
from app.config import PROJECT_ROOT
from app.services import app_knowledge as ak
from app.services import blocks, engineering, knowledge, library, rf_bands
from app.services import how_it_works as hw

CPD_APP = "Interior radar for child presence detection"
RADAR_APP = "UWB radar in the car"
ACCESS_APP = "Smart car access (UWB anchors"
IDS = ("cpd_regulation", "anchors_tags", "cpd_vs_ranging", "qpf5100q_pairing")


def _tpl(prefix: str) -> tuple[int, dict]:
    return next((i, t) for i, t in enumerate(blocks.templates()) if t["name"].startswith(prefix))


def test_items_are_complete_and_sourced_without_blocked_hosts():
    assert ak.problems() == []
    assert {x["id"] for x in ak.items()} >= set(IDS)
    for x in ak.items():
        urls = [s["url"] for s in x["sources"]]
        assert urls and not any(h in u for u in urls for h in ("qorvo.com", "nxp.com", "analog.com", "mouser",
                                                               "digikey", "arrow.com")), x["id"]  # fmt: skip
        assert any(u.startswith("https://") for u in urls), x["id"]
    assert ak.get("nope") is None and ak.for_ids(["nope", "cpd_regulation"])[0]["id"] == "cpd_regulation"


def test_regulation_note_is_factual_and_marked_in_the_priority_data():
    text = " ".join(ak.get("cpd_regulation")["points"])
    for s in ("Euro NCAP", "direct sensing", "2025", "5 points", "15 s", "ANCAP", "NHTSA", "rear-seat reminder"):
        assert s in text, s
    trends = yamlio.load((PROJECT_ROOT / "data/business/evidence/trends.yaml").read_text())
    assert (
        "Euro NCAP" in trends["uwb_soc"]["regulation"] and "child presence" in trends["radar_transceiver"]["regulation"]
    )
    from app.services import scoring

    assert scoring._trend(trends["uwb_soc"])[1].startswith("regulation: Euro NCAP")
    reach = yamlio.load((PROJECT_ROOT / "data/business/auto_reach.yaml").read_text())
    cpd = next(r for r in reach["rows"] if r.get("app") == "incabin" and r.get("fn") == "uwb_soc")
    assert cpd["driver"].startswith("Regulation")
    topic = library.topic("auto_uwb")
    assert any(w.startswith("Why it matters: regulation") for w in topic["why_customer"])


def test_application_pages_show_their_knowledge(client):
    i, t = _tpl(CPD_APP)
    assert t["knowledge"] == ["cpd_regulation", "cpd_vs_ranging", "qpf5100q_pairing"]
    html = client.get(f"/blocks/new?template={i}").text
    for s in (
        'id="k-cpd_regulation"',
        "Why it matters: regulation",
        'id="k-cpd_vs_ranging"',
        "Radar (CPD, intrusion, kick)",
        'id="k-qpf5100q_pairing"',
        "QPF5001Q",
        "kn-est",
        "search snippet, not read",
    ):
        assert s in html, s
    assert 'id="k-anchors_tags"' not in html
    i, t = _tpl(RADAR_APP)
    html = client.get(f"/blocks/new?template={i}").text
    assert 'id="k-cpd_vs_ranging"' in html and 'id="k-anchors_tags"' in html
    assert 'id="k-cpd_vs_ranging"' in client.get(f"/business/applications/{i}").text
    i, t = _tpl(ACCESS_APP)
    html = client.get(f"/blocks/new?template={i}").text
    assert 'id="k-anchors_tags"' in html and "Huf" in html and "2 to 6 anchors" in html
    # a diagram without knowledge has no section
    plain = next(i for i, t in enumerate(blocks.templates()) if not t.get("knowledge"))
    assert 'id="app-knowledge"' not in client.get(f"/blocks/new?template={plain}").text


def test_anchors_and_cpd_vs_ranging_content():
    a = ak.get("anchors_tags")
    text = " ".join([a["intro"], *a["points"]])
    for s in (
        "tag",
        "four anchors",
        "corners",
        "2 to 6",
        "inside or outside",
        "roof lining",
        "kick",
        "Angle-capable",
        "ECU",
    ):
        assert s in text, s
    c = ak.get("cpd_vs_ranging")
    assert c["table"]["head"] == ["", "Ranging (key, access)", "Radar (CPD, intrusion, kick)"]
    rows = {r[0] for r in c["table"]["rows"]}
    assert {"Antennas", "TX power and duty", "Processing", "Second device"} <= rows
    assert "802.15.4ab" in " ".join(c["points"]) and "breathing" in " ".join(c["points"])


def test_qpf_pairing_states_what_our_data_says():
    p = ak.get("qpf5100q_pairing")
    text = " ".join(p["points"])
    assert "unknown" in text and "not in our data" in text and "8-12 GHz" in text and "not automotive" in text
    cat = (PROJECT_ROOT / "data/catalog/qorvo_parts.yaml").read_text()
    extra = (PROJECT_ROOT / "data/catalog/qorvo_extra_parts.yaml").read_text()
    assert "mpn: QPF5001Q" not in cat + extra  # not added without a public source
    assert "mpn: QPF5100Q" in extra and "mpn: QPF5001\n" in cat


def test_engineering_page_with_matrix_and_chart(client):
    assert "uwb_wifi_coexistence" in engineering.NOTES and "uwb_wifi_coexistence" in knowledge.data()["why_it_matters"]
    html = client.get("/engineering/uwb_wifi_coexistence").text
    for s in (
        "6489.6",
        "7987.2",
        "6988.8",
        "5925",
        "7125",
        "5855",
        "5895",
        "U-NII-5",
        "Decision matrix",
        "Recommended UWB channel",
        "Filtering",
        "Coexistence handling",
        "Risk",
        "Region China",
        "Region Japan",
        "desense",
        "Blocking",
        "SKY5A1008",
        "QPQ2230Q",
        "<svg",
        "uwf-uwbok",
        "kn-est",
        "carconnectivity.org",
        "standards.ieee.org",
        'href="/reviews/how/uwb"',
        'href="/library/auto_uwb"',
    ):
        assert s in html, s
    assert "qorvo.com" not in html
    assert "/engineering/uwb_wifi_coexistence" in client.get("/engineering").text


def test_part_knowledge_links_parts_and_pairing(client):
    g = hw.group("uwb")
    assert hw.problems() == []
    assert any(s.get("note") == "engineering:uwb_wifi_coexistence" for s in g["specs"])
    html = client.get("/reviews/how/uwb").text
    for s in (
        'href="/engineering/uwb_wifi_coexistence"',
        'href="/library/auto_uwb#k-anchors_tags"',
        "#k-cpd_vs_ranging",
        'id="pairing"',
        "QPF5001Q",
        ">QPF5100Q</a>",
        "status unknown in our data",
    ):
        assert s in html, s
    used = {u["label"]: u["href"] for u in hw.used_in(g)}
    assert used["Anchors vs tags: how many anchors a car uses and which anchor does what"].endswith("#k-anchors_tags")
    assert any(h.endswith("#k-cpd_vs_ranging") and h.startswith("/business/applications/") for h in used.values())


def test_library_topic_shows_regulation_knowledge_and_coexistence_link(client):
    html = client.get("/library/auto_uwb").text
    for x in IDS:
        assert f'id="k-{x}"' in html, x
    assert "Why it matters: regulation" in html and 'href="/engineering/uwb_wifi_coexistence"' in html
    assert ak.href("anchors_tags").startswith("/blocks/new?template=")


@pytest.mark.parametrize("bid", ["uwb5", "uwb6", "uwb9", "wifi6"])
def test_rf_bands_chart_carries_uwb_channels_and_wifi_6ghz(client, bid):
    b = rf_bands.band(bid)
    assert b
    lo = min(r[0] for r in b["ranges"])
    hi = max(r[1] for r in b["ranges"])
    assert {"uwb5": (6240, 6739), "uwb6": (6739, 7238), "uwb9": (7738, 8237), "wifi6": (5925, 7125)}[bid] == (lo, hi)
    assert client.get(f"/rf-bands?band={bid}").status_code == 200
