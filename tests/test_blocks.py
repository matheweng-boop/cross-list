from app.services import blocks


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
    assert "Car radio tuner system" in client.get("/blocks").text
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
