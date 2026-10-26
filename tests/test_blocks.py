from app.services import blocks, refdesigns


def test_templates_use_known_functions():
    fns = blocks.catalogue()["functions"]
    for t in blocks.templates():
        ids = {g["id"] for g in t["groups"]}
        for g in t["groups"]:
            for b in g["blocks"]:
                assert (b["fn"] if isinstance(b, dict) else b.split()[0]) in fns, (t["name"], b)
        for a, b, _ in t["links"]:
            assert a in ids and b in ids, (t["name"], a, b)
        for q in t.get("questions") or []:  # answers map only to existing requirements and choices
            for st in q.get("sets") or []:
                assert st["req"] in {r["id"] for r in fns[st["fn"]].get("requirements") or []}, (q["id"], st)
                assert set(st["map"]) <= set(q["choices"]), q["id"]
    for key, f in fns.items():
        assert f["category"] in blocks.catalogue()["categories"], key
        for c in f.get("companions") or []:
            assert c in fns, (key, c)


def test_pages_counts_and_parts(client):
    assert "Car radio tuner system" in client.get("/blocks?system=automotive").text  # diagrams open per system
    page = client.get("/blocks/new?template=1").text
    assert 'id="bk-template"' in page and "am_fm_tuner" in page
    assert "opportunity" in client.get("/blocks/coverage").text
    tuners = client.get("/api/blocks/parts?fn=am_fm_tuner").json()
    sky = tuners["manufacturers"][0]
    assert tuners["total"] > 5 and sky["manufacturer"] == "Skyworks" and len(sky["best"]) == 2
    assert any(p["mpn"] == "Si47962" for p in sky["all"])
    # requirements narrow the parts: DAB + phase diversity + no audio question -> Si47962 among few
    import json

    req = json.dumps({"dab": True, "pd": True})
    narrowed = client.get(f"/api/blocks/parts?fn=am_fm_tuner&req={req}").json()
    assert 0 < narrowed["total"] < tuners["total"]
    assert all("DAB" in p["detail"] and "PD" in p["detail"] for m in narrowed["manufacturers"] for p in m["all"])
    counts = client.post("/api/blocks/counts", json={"req": {"am_fm_tuner": {"dab": True, "pd": True}}}).json()
    assert counts["am_fm_tuner"] == narrowed["total"] and counts["soc"] is None
    assert client.get("/api/blocks/parts?fn=reverse_polarity").json()["total"] == 0  # opportunity
    d = client.post("/api/blocks/designs", json={"name": "T", "data": {"groups": [], "links": []}}).json()
    assert client.get(f"/blocks/{d['id']}").status_code == 200


def test_feedback_is_saved_for_discussion(client):
    d = client.post("/api/blocks/designs", json={"name": "Inverter", "data": {"groups": [], "links": []}}).json()
    fb = {"diagram_id": d["id"], "diagram_name": "Inverter", "target": "Gate drive", "message": "Needs DESAT"}
    r = client.post("/api/blocks/feedback", json=fb)
    assert r.status_code == 200
    assert client.get(f"/api/blocks/feedback?diagram_id={d['id']}").json()[0]["message"] == "Needs DESAT"
    assert "Needs DESAT" in client.get("/blocks/feedback").text
    assert "- [To review] Inverter / Gate drive: Needs DESAT" in client.get("/blocks/feedback.txt").text
    assert client.post("/api/blocks/feedback", json={"message": " "}).status_code == 400


def test_qorvo_and_skyworks_best_two_each(client):
    pmic = client.get("/api/blocks/parts?fn=pmic").json()
    qorvo = {m["manufacturer"]: m for m in pmic["manufacturers"]}["Qorvo"]
    assert qorvo["total"] >= 10 and len(qorvo["best"]) == 2
    assert all(not p["risk"] for p in qorvo["best"])  # active parts first
    switches = {m["manufacturer"] for m in client.get("/api/blocks/parts?fn=rf_switch").json()["manufacturers"]}
    assert "Qorvo" in switches


def test_inverter_template_questions(client):
    names = [t["name"] for t in blocks.templates()]
    i = names.index("HEV/EV traction inverter (TI reference)")
    page = client.get(f"/blocks/new?template={i}").text
    assert "sc_detect" in page and "slua963b" in page
    # DESAT answer narrows the gate drivers; Si823x has no DESAT, so none are left (an opportunity)
    import json

    req = json.dumps({"desat": True})
    assert client.get("/api/blocks/parts?fn=gate_driver").json()["total"] > 0
    assert client.get(f"/api/blocks/parts?fn=gate_driver&req={req}").json()["total"] == 0


def test_motor_and_rf_templates(client):
    page = client.get("/blocks").text
    assert "Motor drives" in page and "RF &amp; connectivity" in page and "72 V" in page
    names = [t["name"] for t in blocks.templates()]
    i = next(n for n, x in enumerate(names) if x.startswith("Wi-Fi front end"))
    t = blocks.templates()[i]
    q = next(q for q in t["questions"] if q["id"] == "antenna_diversity_switch")
    assert q["sets"][0]["fn"] == "rf_switch"
    assert client.get(f"/blocks/new?template={i}").status_code == 200


def test_applications_without_vendor_names_and_coverage_uses(client):
    from app.services import blocks as b

    assert b.display_name({"name": "Light EV BLDC drive, 48 V (TI)"}) == "Light EV BLDC drive, 48 V"
    assert b.display_name({"name": "E-mobility drive up to 85 V (Microchip AN5324)"}) == "E-mobility drive up to 85 V"
    page = client.get("/blocks").text
    assert (
        "Application library" in page
        and "Possible variants" in page
        and "(TI)" not in page
        and "(NXP)" not in page
        and "tpl-chip" in page
    )
    uses = b.function_uses()
    assert any("radio" in a["name"].lower() for a in uses["am_fm_tuner"])
    assert 'data-fn="pmic"' in client.get("/blocks/coverage").text


def test_catalogue_parts_fill_functions(client):
    lna = client.get("/api/blocks/parts?fn=lna").json()
    mfrs = {m["manufacturer"] for m in lna["manufacturers"]}
    assert lna["total"] > 20 and "Skyworks" in mfrs
    # Si86 parts already in BizDev are not listed twice from the catalogue
    iso = client.get("/api/blocks/parts?fn=digital_isolator").json()
    names = [p["mpn"].upper() for m in iso["manufacturers"] for p in m["all"]]
    assert len(names) == len(set(names))


def test_report_diagram_links_use_names_that_exist(client):
    """Reports link to library diagrams by name (?diagram=), so adding a diagram never moves a link."""
    import pathlib
    import re
    import urllib.parse

    from app.services import blocks

    names = {t.get("name") for t in blocks.templates()}
    found = 0
    for f in pathlib.Path("app/web/templates/business/reports").glob("*.html"):
        for raw in re.findall(r"/blocks/new\?diagram=([^\"&#]+)", f.read_text()):
            assert urllib.parse.unquote(raw) in names, (f.name, urllib.parse.unquote(raw))
            found += 1
    assert found >= 10
    wind = next(n for n in names if n and n.startswith("Wind turbine converter"))
    page = client.get("/blocks/new", params={"diagram": wind}).text
    assert "Wind turbine converter" in page


def test_diagram_feedback_can_be_deleted_with_confirmation(client):
    """Owner, 22 Oct 2026 (Requests & reviews › Diagram feedback): items can be deleted there."""
    fid = client.post("/api/blocks/feedback", json={"message": "Remove this note please"}).json()["id"]
    html = client.get("/blocks/feedback").text
    form = html.split(f'action="/blocks/feedback/{fid}" class="fb-del"', 1)[1].split("</form>", 1)[0]
    assert 'data-confirm="Delete this diagram feedback for good?"' in form and 'name="delete"' in form
    assert "confirm(f.dataset.confirm)" in html
    r = client.post(f"/blocks/feedback/{fid}", data={"delete": "1"}, follow_redirects=False)
    assert r.status_code == 303 and "Remove this note please" not in client.get("/blocks/feedback").text
    assert client.post(f"/blocks/feedback/{fid}", data={"delete": "1"}).status_code == 404


# ---- from tests/test_fb_w4.py ----------------------------------------------------------------------------------------
# Site feedback 2026-10-20, W4: verified applications, the editor in its own window, broad reference-design groups.


def test_application_verified_flag_and_filter(client):
    i = 0
    page = client.get(f"/blocks/new?template={i}").text
    assert "Entered, not verified" in page and "Mark technically verified" in page
    r = client.post("/blocks/verify", data={"i": i, "on": "1", "author": "Ana", "note": "checked vs datasheet"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    page = client.get(f"/blocks/new?template={i}").text
    assert "Technically verified" in page and "Ana" in page and "Back to entered" in page
    lib = client.get("/blocks?verified=yes").text
    assert "Technically verified" in lib and blocks.title_parts(blocks.templates()[i])[0] in lib
    client.post("/blocks/verify", data={"i": i, "on": "0"})
    assert "Entered, not verified" in client.get(f"/blocks/new?template={i}").text
    assert client.post("/blocks/verify", data={"i": 99999, "on": "1"}).status_code == 404


def test_editor_own_window(client):
    full = client.get("/blocks/new?template=0").text
    assert 'id="bk-window"' in full and 'class="shell"' in full
    bare = client.get("/blocks/new?template=0&bare=1").text
    assert 'class="shell bare"' in bare and "Full page" in bare and 'id="bk-window"' not in bare


def test_reference_design_types():
    rows = list(refdesigns.designs())
    tree = refdesigns.type_tree(rows)
    assert sum(t["n"] for t in tree) == len(rows)
    names = [t["type"] for t in tree]
    assert "RF & communications" in names and "Power conversion & energy" in names
    rf = next(t for t in tree if t["type"] == "RF & communications")
    assert all(k in refdesigns.BAND_CLASSES for k, _ in rf["subs"])
    assert refdesigns.sub_class({"title": "800 V traction inverter"}, "Motor drives & motion") == "Above 600 V"
    assert refdesigns.sub_class({"title": "28 GHz beamformer"}, "RF & communications") == "Above 6 GHz"


def test_reference_designs_page_groups(client):
    page = client.get("/reference-designs").text
    assert "rd-types" in page and "By application type" in page
    r = client.get("/reference-designs?atype=RF+%26+communications&view=list")
    assert r.status_code == 200 and "rd-card" in r.text and "Frequency band" in r.text
