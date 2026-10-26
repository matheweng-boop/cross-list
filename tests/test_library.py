"""Systems library: topic files are consistent (six references, valid functions, rules cite references) and the pages
and the workspace open them."""

import html as h
import re
from datetime import UTC, datetime, timedelta

import pytest

from app.services import blocks, key_apps, library, opportunity, refdesigns, vocab
from app.services import portfolio as pf
from app.services import systems as sy
from app.web import nav

KEYS = sorted(p.stem for p in (library.FOLDER / "topics").glob("*.yaml"))


def test_sources_page(client):
    assert len(library.sources()) >= 20
    assert all(s["feasibility"] in library.FEASIBILITY for s in library.sources())
    html = client.get("/library/sources").text
    assert "OpenAlex" in html and "Blocked" in html
    assert client.get("/library").status_code == 200


@pytest.mark.parametrize("key", KEYS)
def test_topic_file_is_consistent(key):
    t = library.topic(key)
    refs = library.refs_by_id(t)
    assert t.get("title") and t.get("summary") and len(t["references"]) == 6 and len(refs) == 6
    assert all(r.get("url") and r.get("licence") for r in t["references"])
    fns = vocab.functions()
    d = t["block_diagram"]
    gids = {g["id"] for g in d["groups"]}
    for g in d["groups"]:
        for b in g["blocks"]:
            fn = b["fn"] if isinstance(b, dict) else b
            assert vocab.canonical(fn) in fns, fn
    assert all(lk[0] in gids and lk[1] in gids for lk in d.get("links") or [])
    for x in [*t["design_rules"], *t["trends"]]:
        assert x.get("refs") and set(x["refs"]) <= set(refs), x
    assert all(vocab.canonical(s["fn"]) in fns for s in t.get("skyworks_fit") or [])


@pytest.mark.parametrize("key", KEYS)
def test_topic_pages(client, key):
    t = library.topic(key)
    html = client.get(f"/library/{key}").text
    assert t["title"].replace("&", "&amp;") in html or t["title"] in html
    assert client.get(f"/blocks/new?library={key}").status_code == 200


def test_library_feeds_the_decision_pages(client):
    ev = client.get("/business/evidence/digital_isolator").text
    assert "From the systems library" in ev and "/library/traction_asil_d" in ev
    case = client.get("/business/reports/auto-cv2x-fe").text
    assert "From the systems library" in case and "/library/v2x_frontend" in case
    topic = client.get("/library/v2x_frontend").text
    assert "/business/reports/auto-cv2x-fe" in topic and "Full research notes" in topic
    hits = client.get("/technical?q=DESAT blanking").text
    assert "/library/traction_asil_d#" in hits
    assert {c["slug"] for c in library.cases_using("auto_uwb")} == {"auto-uwb-15-4ab", "auto-uwb-cpd"}
    assert library.for_function("digital_isolator")[0]["ours"]


def test_disagree_lowers_a_rule_confidence(client, session):
    t = library.topic("traction_asil_d")
    rule = next(r for r in t["design_rules"] if r.get("conf") in ("high", "med"))
    r = client.post("/library/traction_asil_d/react", data={"item": rule["id"], "verdict": "disagree",
                                                            "comment": "datasheet says otherwise"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    got = next(x for x in library.reviewed(session, "traction_asil_d")["design_rules"] if x["id"] == rule["id"])
    assert got["conf_was"] == rule["conf"] and got["conf"] != rule["conf"] and got["fb"]["verdict"] == "wrong"
    assert "/library/traction_asil_d#i-" in client.get("/manage/reviews").text
    assert client.post("/library/traction_asil_d/react", data={"item": "nope", "verdict": "agree"}).status_code == 400


# ---- from tests/test_fb_1025_ag.py -----------------------------------------------------------------------------------
# Owner's site comments of 25 Oct 2026 (worker AG): block-diagram indicator and one-click links in the libraries,
# a shorter key-applications table on the eFuse bigger picture, and what Euro NCAP is.


def _card(page: str, system: str, sub: str) -> str:
    return page.split(f'id="card-{system}-{sub}"')[1].split("</article>")[0]


def _with_and_without():
    subs = [(s["key"], x) for s in sy.systems() for x in s["subsystems"]]
    has = next((k, x) for k, x in subs if x["idx"])
    none = next(((k, x) for k, x in subs if not x["idx"]), None)
    return has, none


def test_application_library_shows_diagram_indicator_and_one_click_links(client):
    page = client.get("/blocks").text
    (sk, x), missing = _with_and_without()
    card = _card(page, sk, x["key"])
    assert f"Block diagram ✓ ({len(x['idx'])})" in card
    assert f'href="/blocks/new?template={x["idx"][0]}"' in card  # one click opens the diagram
    if missing:
        assert "No diagram yet" in _card(page, missing[0], missing[1]["key"])
    assert 'id="diagrams"' in page and "block diagrams</b>" in page.split('id="area-')[0]  # summary near the top
    one = client.get(f"/blocks?system={sk}&sub={x['key']}").text
    assert f'id="diagrams-{sk}"' in one and "Block diagrams in" in one


def test_new_systems_have_indicators_in_both_libraries(client):
    blocks_page, library_page = client.get("/blocks").text, client.get("/library").text
    for key in ("industrial", "aerospace", "consumer", "home", "medical"):
        s = sy.get(key)
        assert s, key
        for x in s["subsystems"]:
            for page in (blocks_page, library_page):
                card = _card(page, key, x["key"])
                assert ("Block diagram ✓" in card) == bool(x["idx"]) and ("No diagram yet" in card) != bool(x["idx"])
                if x["idx"]:
                    assert f'href="/blocks/new?template={x["idx"][0]}"' in card


def test_efuse_key_applications_table_has_short_cells_and_a_more_line(client):
    d = key_apps.for_function("efuse_hotswap")
    for a in d["applications"]:
        assert a["where"] and len(a["where"]) <= 50 and len(a["v"]) <= 20 and len(a["a"]) <= 20, a["key"]
    page = h.unescape(client.get("/business/evidence/efuse_hotswap").text)
    table = page.split('class="small ka-table"')[1].split("</table>")[0]
    assert table.count('class="ka-more"') == len(d["applications"]) and "More: uses, full ranges" in table
    assert 'data-label="Voltage"' in table and "12 V · 48 V" in table


def test_euro_ncap_is_explained_where_it_is_first_mentioned(client):
    t = opportunity.explanations()["terms"]["euro_ncap"]
    assert "European New Car Assessment Programme" in t["short"] and "euroncap.com" in t["href"]
    page = h.unescape(client.get("/business/reports/auto-uwb-cpd").text)
    box = page.index("What is Euro NCAP?")
    assert page.index("Euro NCAP") < box < page.index('class="rpt"')
    assert 'href="https://www.euroncap.com/"' in page and 'href="/business/method#t-euro_ncap"' in page
    method = client.get("/business/method").text
    assert 'id="t-euro_ncap"' in method and "Source: euroncap.com" in method


# ---- from tests/test_systems_1023.py ---------------------------------------------------------------------------------
# Owner feedback 23 Oct 2026: Systems & applications by full systems and sub-systems, Cross-sell bottom up, gaps
# and new technology under Opportunities, TAM estimates under Future growth, and a Data management overview with
# everything on it plus one "Site data" item with tabs.


# ---- systems and sub-systems --------------------------------------------------------------------------------------
def test_every_diagram_is_in_a_sub_system_or_other():
    assert sy.unknown_diagrams() == []  # every name in systems.yaml is a library diagram
    n = len(blocks.templates())
    assert sy.assigned() | set(sy.unassigned()) == set(range(n)) and not sy.assigned() & set(sy.unassigned())
    for i in sy.unassigned():
        assert sy.place_of(i)[0][0] == sy.OTHER
    assert [s["key"] for s in sy.systems()][:4] == ["automotive", "datacenter", "drones", "cellular"]  # + 25 Oct
    for s in sy.systems():
        assert s["subsystems"], s["key"]  # at least one sub-system per system
        assert len({x["key"] for x in s["subsystems"]}) == len(s["subsystems"])
        for x in s["subsystems"]:
            assert x["idx"] and x["elements"] and x["title"], (s["key"], x["key"])


def test_topics_and_radio_attach_to_their_systems():
    keys = {t["key"] for t in library.topics()}
    for s in sy.systems():
        for x in s["subsystems"]:
            assert set(x["topics"]) <= keys, x["key"]
    assert sy.topic_place("auto_uwb") == ("automotive", "car-access")
    assert sy.topic_place("v2x_frontend") == ("automotive", "telematics-v2x")
    radio = sy.sub("automotive", "car-radio")
    assert ("Tuners & demodulators", "/broadcast") in radio["links"]
    assert any("tuner" in e.lower() for e in radio["elements"]) and any("demodulator" in e for e in radio["elements"])
    uwb = sy.sub("automotive", "car-access")
    assert any("Kick sensor" in e for e in uwb["elements"]) and any("child presence" in e for e in uwb["elements"])
    v2x = [blocks.templates()[i]["name"] for i in sy.sub("automotive", "telematics-v2x")["idx"]]
    assert any("Autotalks" in n for n in v2x)  # owner: Autotalks as the reference for the V2X applications


def test_systems_library_shows_systems_with_sub_system_cards(client):
    html = client.get("/library").text
    for s in sy.systems():
        assert f'id="sys-{s["key"]}"' in html
        for x in s["subsystems"]:
            assert f'id="card-{s["key"]}-{x["key"]}"' in html
    assert 'href="/library/auto_uwb"' in html and 'href="/broadcast"' in html
    uwb = html.index('href="/library/auto_uwb"')
    assert html.index('id="sys-automotive"') < uwb < html.index('id="sys-datacenter"')


def test_application_library_groups_by_system_and_sub_system(client):
    html = client.get("/blocks").text
    order = [html.index(f'id="area-{s["key"]}"') for s in sy.systems()]
    assert order == sorted(order) and order[-1] < html.index('id="other-areas"')
    assert 'href="/blocks?system=automotive&amp;sub=car-radio#sub-car-radio"' in html
    n_radio = len(sy.sub("automotive", "car-radio")["idx"])
    assert f"Block diagram ✓ ({n_radio})" in html.split('id="card-automotive-car-radio"')[1].split("</article>")[0]
    one = client.get("/blocks?system=automotive&sub=car-radio").text
    assert 'id="sub-car-radio"' in one and 'id="sub-adas"' not in one and 'id="area-datacenter"' not in one
    assert "Cross-sell in Car radio" in one and 'href="/blocks/cross-sell?system=automotive&amp;sub=car-radio"' in one
    assert "Car radio tuner system" in one
    other = client.get("/blocks?system=other").text
    assert "<details class=\"lib-other\" id=\"other-areas\" open>" in other and 'id="area-automotive"' not in other


def test_radio_is_an_application_not_a_menu_item(client):
    labels = [i[0] for s in nav.NAV for i in s[2]]
    assert "Radio & audio" not in labels
    page = client.get("/broadcast").text
    assert 'href="/blocks?system=automotive&amp;sub=car-radio#sub-car-radio"' in page
    assert client.get("/broadcast/configurations").status_code == 200


# ---- menu tree and redirects --------------------------------------------------------------------------------------
def test_menu_tree_23_oct():
    menu = {k: [i[0] for i in items] for k, _, items in nav.NAV}
    assert menu["systems"] == ["Systems library", "Application library", "Application workspace",
                               "Cross-sell", "RF coverage", "Automotive map"]  # fmt: skip
    assert menu["opportunities"] == ["Gaps & new technology", "Competitive analytics", "Risks"]
    assert menu["growth"][-1] == "TAM estimates"
    # owner, 24 Oct 2026: a section for shareable content, after Engineering knowledge, with its own landing page
    assert list(menu)[-2:] == ["knowledge", "shareable"]
    assert menu["shareable"] == ["Reports"]  # owner, 25 Oct 2026: one page, no sub-items
    assert nav.HOMES == {"shareable": "/shareable"}
    manage = [i[0] for i in nav.UTILITY[2]]
    # owner, 25 Oct 2026: To confirm first; 26 Oct 2026: Data flow after Schedule
    assert manage == ["To confirm", "Overview", "Schedule", "Data flow", "Site data", "Uploads", "Data quality",
                      "People & invites", "Methodology"]
    tabs = next(g for g in nav.TABS if g[0][1] == "/manage/verify")
    # owner, 24 Oct 2026: part requests, diagram feedback and area requests as one Requests tab
    assert tabs == (("Verify next", "/manage/verify"), ("Review queue", "/manage/reviews"),
                    ("Requests", "/manage/requests"), ("Site feedback", "/manage/feedback"),
                    ("Guest input", "/manage/guest-input"))  # fmt: skip


def test_old_urls_keep_working(client):
    r = client.get("/business/explorer", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/business/opportunities?co=combined"
    gaps = client.get("/business/gaps", follow_redirects=False)
    assert gaps.headers["location"].startswith("/business/explorer/table")
    assert client.get("/business/technology", follow_redirects=False).status_code == 307
    r = client.get("/manage/site-data", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/manage/verify"
    for url in ("/business/rf-coverage", "/business/automotive", "/business/tam", "/business/attach", "/broadcast",
                "/blocks/cross-sell", "/business/opportunities", "/manage/reviews", "/manage/feedback"):
        assert client.get(url).status_code == 200, url
    page = client.get("/manage/feedback").text
    for label in ("Site feedback", "Site data"):  # the tab and the menu item
        assert f'aria-current="page" class="on">{label}<' in page


def test_guest_does_not_see_owner_pages_in_future_growth(make_guest, owner):
    g, _ = make_guest()
    html = g.get("/business/markets").text
    assert 'href="/business/reports"' in html and 'href="/business/tam"' not in html
    assert g.get("/business/tam", follow_redirects=False).status_code in (303, 403, 404)
    assert 'href="/business/tam"' in owner.get("/business/markets").text


# ---- Data management overview ----------------------------------------------------------------------------------------
def test_overview_counts_today_and_open_requests(client, session):
    from app.models import AreaRequest, BlockFeedback, CrossRequest, SiteFeedback
    from app.web.verify import overview_counts

    now = datetime(2026, 10, 23, 10, 0, tzinfo=UTC)
    session.add_all([SiteFeedback(text="today 1", path="/", created_at=now - timedelta(hours=1)),
                     SiteFeedback(text="today 2", path="/", created_at=now - timedelta(hours=11)),  # 01:00 in Berlin
                     SiteFeedback(text="yesterday", path="/", created_at=now - timedelta(hours=13)),  # Berlin, 22nd
                     CrossRequest(mpn="X1"), CrossRequest(mpn="X2", status="done"),
                     BlockFeedback(message="m"), BlockFeedback(message="n", status="done"),
                     AreaRequest(area="Robotics")])  # fmt: skip
    session.commit()
    c = overview_counts(session, now)
    assert c["feedback_today"] == 2 and c["part_requests"] == 1
    assert c["diagram_feedback"] == 1 and c["area_requests"] == 1
    html = client.get("/manage/overview").text
    for text in ("came in today", "open in Verify next", "pending your review", "open part requests",
                 "open diagram feedback", "new area requests", "TAM figures to review", "Raw data",
                 "Skyworks and Qorvo parts", "library diagrams"):  # fmt: skip
        assert text in html, text
    assert 'class="ov-table"' in html and 'href="/manage/verify"' in html


# ---- from tests/test_systems_1026.py ---------------------------------------------------------------------------------
# Owner, 25 Oct 2026: more block-diagram sources; the library diagrams under "Other" become more systems; the kick
# sensor and the interior radar (child presence) get their own diagrams under UWB in the car; the UWB anchor gets a
# clock block from a public reference design; new public reference designs show on /reference-designs.

NEW_SYSTEMS = ("industrial", "aerospace", "consumer", "home", "medical")
NEW = {  # name prefix -> (system, sub-system)
    "Kick-to-open sensor module": ("automotive", "car-access"),
    "Interior radar for child presence detection": ("automotive", "car-access"),
    "Automotive smart power closure": ("automotive", "cockpit"),
    "UWB + Bluetooth LE module for anchors and tags": ("consumer", "connectivity"),
    "Smartwatch with UWB": ("consumer", "wearables-xr"),
    "Drone power management, ESC, flight controller and gimbal": ("drones", "flight"),
    "48 V intermediate bus converter": ("datacenter", "rack-power"),
    "SATCOM user terminal": ("aerospace", "satcom"),
    "Satellite ground station power supply": ("aerospace", "satcom"),
    "SATCOM Ku-band block upconverter": ("aerospace", "satcom"),
    "Redundant L-band amplifier": ("aerospace", "satcom"),
    "Ka-band LEO gateway": ("aerospace", "satcom"),
    "Phased-array beamforming network": ("aerospace", "radar"),
    "AESA radar T/R module": ("aerospace", "radar"),
}


def _index(prefix: str) -> int:
    hits = [i for i, t in enumerate(blocks.templates()) if t["name"].startswith(prefix)]
    assert len(hits) == 1, prefix
    return hits[0]


def test_other_is_regrouped_into_new_systems_with_sub_systems():
    keys = [s["key"] for s in sy.systems()]
    assert keys[:4] == ["automotive", "datacenter", "drones", "cellular"] and set(NEW_SYSTEMS) <= set(keys)
    for k in NEW_SYSTEMS:
        s = sy.get(k)
        assert len(s["subsystems"]) >= 3, k
        for x in s["subsystems"]:
            assert x["idx"] and x["elements"] and x["title"] and x["summary"], (k, x["key"])
    assert sy.unassigned() == []  # nothing left under Other


def test_new_diagrams_validate_cite_sources_and_sit_in_their_sub_system():
    lib = blocks.templates()
    fns = blocks.catalogue()["functions"]
    for prefix, place in NEW.items():
        i = _index(prefix)
        t = lib[i]
        assert re.search(r"\(after [^()]+\)$", t["name"]), t["name"]  # marks itself "after <source>"
        assert t["sources"] and all(s["url"].startswith("https://") and s["doc"] and s["title"] for s in t["sources"])
        assert t["note"].startswith("After ") and all(s["doc"] in t["note"] for s in t["sources"][:1])
        ids = {g["id"] for g in t["groups"]}
        assert len(ids) == len(t["groups"]) >= 5
        for g in t["groups"]:
            assert g["blocks"] and all(b.split()[0] in fns for b in g["blocks"]), (prefix, g["id"])
        assert all(a in ids and b in ids for a, b, _ in t["links"]), prefix
        assert place in sy.place_of(i), (prefix, sy.place_of(i))
        assert "(after" not in blocks.display_name(t) and "Murata" not in blocks.display_name(t)


def test_kick_sensor_and_interior_radar_have_their_own_diagrams_under_uwb_in_the_car():
    names = [blocks.templates()[i]["name"] for i in sy.sub("automotive", "car-access")["idx"]]
    kick = next(n for n in names if n.startswith("Kick-to-open"))
    radar = next(n for n in names if n.startswith("Interior radar for child presence"))
    t = blocks.templates()[_index(kick)]
    assert any(s["url"] == "https://www.ti.com/solution/automotive-kick-to-open-module" for s in t["sources"])
    fns = {b for g in t["groups"] for b in g["blocks"]}
    assert {"touch_controller", "ultrasonic_afe", "radar_transceiver", "lin_transceiver", "mcu"} <= fns
    t = blocks.templates()[_index(radar)]
    assert {"radar_transceiver", "mcu", "can_transceiver"} <= {b for g in t["groups"] for b in g["blocks"]}
    assert any("infineon.com" in s["url"] for s in t["sources"])


def test_uwb_anchor_has_a_clock_block_from_a_public_reference_design():
    t = blocks.templates()[_index("Smart car access (UWB anchors")]
    clock = next(g for g in t["groups"] if g["id"] == "uwb_clock")
    assert clock["blocks"] == ["crystal_oscillator"] and "MURATA-2AB-DS" in clock["source"]
    assert ["uwb_clock", "uwb_anchor_outside", "reference clock"] in t["links"]
    docs = {s["doc"]: s["url"] for s in t["sources"]}
    assert docs["MURATA-2AB-DS"].startswith("https://www.murata.com/") and "MURATA-2BP" in docs


def test_qorvo_uwb_and_skyworks_timing_pair_appears_with_a_reason():
    pairs = pf.together_in(sy.sub("automotive", "car-access")["idx"])["synergies"]
    pair = next(x for x in pairs if (x["skyworks"], x["qorvo"]) == ("crystal_oscillator", "uwb_soc"))
    assert pair["reason"] and "38.4 MHz" in pair["reason"]


def test_new_public_reference_designs_are_listed():
    rows = {(d["vendor"], d["id"]): d for d in refdesigns.designs()}
    assert ("Skyworks", "SKY-RD-TIMING-NXP") in rows and ("Murata", "LBUA5QJ2AB-828") in rows
    for (vendor, _), d in rows.items():
        if vendor in ("Skyworks", "Murata"):
            assert d["url"].startswith("https://www.skyworksinc.com/") or d["url"].startswith("https://www.murata.com/")
            assert d["_type"] != refdesigns.OTHER_TYPE, d["id"]


@pytest.mark.parametrize("key", NEW_SYSTEMS)
def test_pages_pick_up_the_new_systems(client, key):
    s = sy.get(key)
    assert f'id="sys-{key}"' in client.get("/library").text
    lib = client.get("/blocks").text
    assert f'id="area-{key}"' in lib and lib.index(f'id="area-{key}"') < lib.index('id="other-areas"')
    x = s["subsystems"][0]
    one = client.get(f"/blocks?system={key}&sub={x['key']}").text
    assert f'id="sub-{x["key"]}"' in one
    xs = client.get(f"/blocks/cross-sell?sel={key}:{x['key']}").text
    assert x["title"] in xs and f'value="{key}:{x["key"]}"' in xs


def test_presentation_topics_include_the_new_systems():
    from app.services import presentation

    groups = {t["group"] for t in presentation.topics()}
    for k in NEW_SYSTEMS:
        assert sy.get(k)["title"] in groups, k
