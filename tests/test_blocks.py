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
    assert client.get("/api/blocks/parts?fn=pmic").json()["total"] == 0  # opportunity
    d = client.post("/api/blocks/designs", json={"name": "T", "data": {"groups": [], "links": []}}).json()
    assert client.get(f"/blocks/{d['id']}").status_code == 200


def test_feedback_is_saved_for_discussion(client):
    d = client.post("/api/blocks/designs", json={"name": "Inverter", "data": {"groups": [], "links": []}}).json()
    fb = {"diagram_id": d["id"], "diagram_name": "Inverter", "target": "Gate drive", "message": "Needs DESAT"}
    r = client.post("/api/blocks/feedback", json=fb)
    assert r.status_code == 200
    assert client.get(f"/api/blocks/feedback?diagram_id={d['id']}").json()[0]["message"] == "Needs DESAT"
    assert "Needs DESAT" in client.get("/blocks/feedback").text
    assert "- [Open] Inverter / Gate drive: Needs DESAT" in client.get("/blocks/feedback.txt").text
    assert client.post("/api/blocks/feedback", json={"message": " "}).status_code == 400
