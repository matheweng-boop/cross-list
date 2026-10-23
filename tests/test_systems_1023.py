"""Owner feedback 23 Oct 2026: Systems & applications by full systems and sub-systems, Cross-sell bottom up, gaps
and new technology under Opportunities, TAM estimates under Future growth, and a Data management overview with
everything on it plus one "Site data" item with tabs."""

from datetime import UTC, datetime, timedelta

from app.services import blocks, library
from app.services import systems as sy
from app.web import nav


# ---- systems and sub-systems --------------------------------------------------------------------------------------
def test_every_diagram_is_in_a_sub_system_or_other():
    assert sy.unknown_diagrams() == []  # every name in systems.yaml is a library diagram
    n = len(blocks.templates())
    assert sy.assigned() | set(sy.unassigned()) == set(range(n)) and not sy.assigned() & set(sy.unassigned())
    for i in sy.unassigned():
        assert sy.place_of(i)[0][0] == sy.OTHER
    assert [s["key"] for s in sy.systems()] == ["automotive", "datacenter", "drones", "cellular"]
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
    assert f"{n_radio} diagrams" in html.split('id="card-automotive-car-radio"')[1].split("</article>")[0]
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
    assert menu["systems"] == ["Systems library", "Application library", "Application workspace", "Reference designs",
                               "Cross-sell", "RF coverage", "Automotive map"]  # fmt: skip
    assert menu["opportunities"] == ["Gaps & new technology", "Competitive analytics"]
    assert menu["growth"][-1] == "TAM estimates"
    manage = [i[0] for i in nav.UTILITY[2]]
    assert manage == ["Overview", "Schedule", "Site data", "Uploads", "Data quality", "People & invites", "Methodology"]
    tabs = next(g for g in nav.TABS if g[0][1] == "/manage/verify")
    assert [h for _, h in tabs] == ["/manage/verify", "/manage/reviews", "/requests", "/blocks/feedback",
                                    "/blocks/area-requests", "/manage/feedback", "/manage/guest-input"]  # fmt: skip


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
