"""Part knowledge › How it works (owner, 28 Oct 2026): one page per product group about the part itself, with the
key specs, the application-note details, our Skyworks / Qorvo parts and links to the applications; "Part reviews"
renamed "Part knowledge"; the Engineering knowledge page on error propagation."""

import re

import pytest

from app import yamlio
from app.services import digest, products, site_guard
from app.services import how_it_works as hw
from app.web import nav

GROUPS = ("motor", "uwb", "isolator", "gatedriver", "currentsense", "gnss")
PRELOAD = {"hw_parts": (("skyworks_si823x", "skyworks_si86", "skyworks_isolated_amplifiers",
                         "skyworks_switches", "qorvo_switches"), None)}  # fmt: skip


@pytest.fixture
def hw_parts(session):
    """Skyworks gate drivers, isolators, isolated amplifiers and switches with full data (loaded via PRELOAD)."""


def test_data_file_is_valid_and_complete():
    data = yamlio.load(hw.FILE.read_text())
    ids = [g["id"] for g in data["groups"]]
    assert set(GROUPS) <= set(ids) and len(ids) == len(set(ids))
    assert hw.problems() == []
    for g in hw.groups():
        assert len(g["gist"].split()) <= 25, g["id"]
        assert len(g["how"]["steps"]) >= 4 and g["specs"] and g["choosing"] and g["used_in"], g["id"]


def test_every_group_has_an_app_note_block_with_cited_bullets():
    for g in hw.groups():
        notes = g["appnotes"]
        assert 4 <= len(notes) <= 8, g["id"]
        cited = [a for a in notes if a["ref"] and str(a["page"]) and a["url"].startswith("https://")]
        assert len(cited) >= 3, g["id"]
        assert not any("qorvo.com" in a["url"] for a in notes)


def test_no_qorvo_com_source_and_site_guard_passes():
    text = hw.FILE.read_text()
    assert "www.qorvo.com" not in text.split("qorvo.com is never requested")[-1].replace("store.qorvo.com", "")
    assert site_guard.hits(text) == []


@pytest.mark.parametrize("gid", GROUPS)
def test_section_renders_with_every_part(client, hw_parts, gid):
    page = client.get(f"/reviews/how/{gid}")
    assert page.status_code == 200
    html = page.text
    for anchor in ("what", "how", "specs", "choosing", "appnotes", "parts", "used-in", "sources"):
        assert f'id="{anchor}"' in html, anchor
    assert "From the application notes" in html and "<svg" in html and "Part knowledge" in html
    assert site_guard.hits(re.sub(r"<[^>]+>", " ", html)) == []


@pytest.mark.parametrize("gid", GROUPS)
def test_listed_parts_exist_are_active_and_ours(session, hw_parts, gid):
    g = hw.group(gid)
    t = hw.parts_table(session, g)
    assert t["rows"] or t["series"], gid
    index = {r["mpn"]: r for r in products.index(session)}
    for r in t["rows"]:
        assert r["maker"] in ("Skyworks", "Qorvo") and index[r["mpn"]]["lifecycle"] == "active", r["mpn"]
    for s in t["series"]:
        assert s["variants"] > 0 and s["maker"] in ("Skyworks", "Qorvo"), s["mpn"]


def test_spec_links_and_used_in_links_resolve(client):
    for g in hw.groups():
        for s in g["specs"]:
            if s["note"]:
                link = hw.spec_link(s["note"])
                assert link, (g["id"], s["note"])
                assert client.get(link["href"].split("#")[0]).status_code == 200, link
        for u in hw.used_in(g):
            assert u["href"] and client.get(u["href"]).status_code == 200, u


def test_browse_page_and_part_pages_link_the_section(client, hw_parts, part):
    page = client.get("/parts?sub=motor_controller").text
    assert "How motor drivers work" in page and "/reviews/how/motor" in page
    assert "/reviews/how/uwb" in client.get("/parts?sub=uwb").text
    assert "/reviews/how/isolator" in client.get("/parts?sub=digital_isolator").text
    gd = part("SI8230BD-D-IS")
    assert "/reviews/how/gatedriver" in client.get(f"/parts/{gd.id}").text
    sw = part("SKY5A2108")
    assert "How UWB works" in client.get(f"/parts/{sw.id}").text


def test_reviews_and_library_topic_link_the_section(client):
    assert "/reviews/how/motor" in client.get("/reviews/qorvo-pac5527-motor-driver").text
    assert "/reviews/how/uwb" in client.get("/reviews/qorvo-dw3000-uwb").text
    assert "/reviews/how/uwb" in client.get("/library/auto_uwb").text


def test_renamed_label_and_old_urls(client):
    products_nav = next(s for s in nav.NAV if s[0] == "products")
    assert ("Part knowledge", "/reviews") in [(i[0], i[1]) for i in products_nav[2]]
    page = client.get("/reviews")
    assert page.status_code == 200 and "<h1>Part knowledge</h1>" in page.text and "/reviews/how/motor" in page.text
    assert client.get("/part-knowledge", follow_redirects=False).headers["location"] == "/reviews"
    assert client.get("/reviews/qorvo-dw3000-uwb").status_code == 200


def test_guest_can_read_the_section(make_guest):
    guest, _ = make_guest()
    assert guest.get("/reviews/how/uwb").status_code == 200


def test_to_confirm_items_for_every_group_and_the_knowledge_page(client):
    keys = digest.by_key()
    for gid in GROUPS:
        x = keys[f"howto:{gid}"]
        assert x["type_label"] == "Part knowledge: how it works" and digest.words(x["gist"]) <= 25 and not x["auto"]
    assert keys["guide:error_budget"]["href"] == "/engineering/error_budget"
    assert digest.TYPES["review"] == "Part knowledge"
    assert "How it works" in client.get("/manage/to-confirm?type=howto").text


def test_error_propagation_page_and_cross_links(client):
    page = client.get("/engineering/error_budget")
    assert page.status_code == 200
    for s in ("AN1270", "root-sum-of-squares", "four-line", "−0.530", "AN1359", "uncertainty band", "k = 2"):
        assert s in page.text, s
    for gid in ("currentsense", "isolator", "gatedriver"):
        assert "/engineering/error_budget" in client.get(f"/reviews/how/{gid}").text
    for note in ("cmti_kv_us", "prop_delay_ns", "pwd_ns"):
        assert "/engineering/error_budget" in client.get(f"/engineering/{note}").text
    cs = client.get("/reviews/how/currentsense").text
    assert "AN1270" in cs and "-0.530" in cs


# ---- GNSS (owner, 28 Oct 2026) ---------------------------------------------------------------------------------------
GNSS_VISUALS = ("gnssbands", "gnsstri", "gnssdop", "gnssiono")


def test_gnss_part_page_has_parts_grades_and_links(client, session):
    html = client.get("/reviews/how/gnss").text
    for s in ("SKY5A2110", "QPQ1060", "QPQ1062", "Friis", "bias-T", "From the application notes", "ZED-X20P",
              "/library/gnss_frontend", "/business/reports/auto-gnss-l1l5", "/engineering/gnss_how_it_works"):
        assert s in html, s
    t = hw.parts_table(session, hw.group("gnss"))
    sky = next(r for r in t["rows"] if r["mpn"] == "SKY5A2110")
    assert sky["automotive"] == "Yes"
    assert {"TQM2M9016", "QPQ1028"} <= set(t["missing"])  # no lifecycle status: left out, said so


def test_gnss_knowledge_page(client):
    page = client.get("/engineering/gnss_how_it_works")
    assert page.status_code == 200
    for s in ("four satellites", "1575.42", "1176.45", "E6", "B1I", "GLONASS", "NavIC", "40.3", "SBAS", "RTK", "PPP",
              "spoofing", "Time to first fix", "gssc.esa.int/navipedia"):
        assert s in page.text, s
    for vid in GNSS_VISUALS:
        assert f"/visuals#{vid}" in page.text
    assert "/engineering/gnss_how_it_works" in client.get("/engineering").text


def test_gnss_visuals_are_registered_with_explanations(client):
    from app.services import library, visuals

    ex = visuals.explanations()
    js = (hw.FILE.parents[2] / "app" / "web" / "static" / "vz" / "gnss.js").read_text()
    html = client.get("/visuals").text
    assert "/static/vz/gnss.js" in html
    for vid in GNSS_VISUALS:
        assert vid in library.VISUALS and vid in ex and f'id: "{vid}", group: "GNSS"' in js
        assert f'data-for="{vid}"' in html
    assert "How to read this visual" in html


def test_gnss_visual_maths():
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    js = hw.FILE.parents[2] / "app" / "web" / "static" / "vz" / "gnss.js"
    code = (f"global.window={{}};require({json.dumps(str(js))});const G=window.VZ_GNSS;"
            "const s=[[8,92],[50,98],[93,90]],r=[55,32],pr=s.map(q=>Math.hypot(r[0]-q[0],r[1]-q[1])+6);"
            "console.log(JSON.stringify({d:G.ionoDelay(1,1575.42),n:G.ionoFree(0,0).noise,"
            "h:G.dop([0,90,180,270]).hdop,sol:G.solve(s,pr,true,[45,35])}))")  # fmt: skip
    out = json.loads(subprocess.run([node, "-e", code], capture_output=True, text=True, check=True).stdout)
    assert abs(out["d"] - 0.1624) < 1e-3 and abs(out["n"] - 2.588) < 1e-2 and abs(out["h"] - 1) < 1e-9
    assert abs(out["sol"]["x"] - 55) < 1e-6 and abs(out["sol"]["b"] - 6) < 1e-6


# ---- UWB "Used in" (owner, 28 Oct 2026: "expand the UWB 'used in' cases, also ... more block diagrams") -----------
UWB_AREAS = ("Automotive", "Phones and wearables", "Smart home", "Industrial", "Healthcare", "Retail", "Sports",
             "Drones", "Access control")  # fmt: skip


def test_uwb_used_in_covers_the_application_range_with_sources():
    rows = hw.used_in(hw.group("uwb"))
    assert len(rows) >= 10
    assert set(UWB_AREAS) <= {u["area"] for u in rows}
    for u in rows:
        assert u["href"].startswith(("/business/applications/", "/library/")), u
        assert u["src"] and u["src_url"].startswith("https://") and "qorvo.com" not in u["src_url"], u
    labels = " ".join(u["label"] for u in rows).lower()
    for case in ("digital key", "child presence", "kick", "item tags", "door lock", "rtls", "agv", "worker safety",
                 "patient", "vital-sign", "payment", "indoor navigation", "player tracking", "drone", "access"):
        assert case in labels, case
    assert [a for a, _ in hw.used_in_areas(hw.group("uwb"))] == list(UWB_AREAS)


def test_uwb_used_in_links_render_and_stay_out_of_the_part_page(client):
    html = client.get("/reviews/how/uwb").text
    for u in hw.used_in(hw.group("uwb")):
        page = client.get(u["href"])
        assert page.status_code == 200 and "<h1" in page.text, u
        assert f'href="{u["href"]}"' in html and u["src_url"] in html
    for area in UWB_AREAS:
        assert f'<h3 class="hw-area">{area}</h3>' in html
    # the part page only links the applications (owner's rule): their notes are not retold here
    assert "landing stations" not in html and "foot-traffic" not in html


def test_uwb_page_says_where_it_is_seen_in_public_block_diagrams(client):
    s = hw.seen_in(hw.group("uwb"))
    assert s["n"] >= 10 and [f["fn"] for f in s["fns"]] == ["uwb_soc", "uwb_fem"]
    html = client.get("/reviews/how/uwb").text
    assert f'Seen in <a href="/reference-designs?fn=uwb_soc">{s["n"]} public block diagrams</a>' in html
    listed = client.get("/reference-designs?fn=uwb_soc").text
    assert "LBUA0ZZ2HQ" in listed and "AIROC-UWB-TSL100" in listed
    assert hw.seen_in({"id": "x"}) is None


def test_uwb_emerging_car_uses_are_tagged_and_sourced(client):
    rows = [u for u in hw.used_in(hw.group("uwb")) if u["emerging"]]
    assert len(rows) >= 4 and all(u["area"] == "Automotive" for u in rows)
    for u in rows:
        assert u["why"] and u["src"] and u["src_url"].startswith("https://") and "nxp.com" not in u["src_url"], u
    labels = " ".join(u["label"] for u in rows).lower()
    for case in ("seatbelt", "intrusion", "valet", "parking garage", "ride sharing"):
        assert case in labels, case
    html = client.get("/reviews/how/uwb").text
    assert html.count('<span class="emerging-tag"') == len(rows)
    # the tag also shows on the application entries they link to
    for href in {u["href"] for u in rows}:
        page = client.get(href).text
        assert page.count('class="emerging-tag"') == 1, href
    assert 'class="emerging-tag"' not in client.get(hw.used_in(hw.group("uwb"))[1]["href"]).text
