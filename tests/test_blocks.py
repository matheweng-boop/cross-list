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
    assert tuners["total"] > 5 and any(p["mpn"] == "Si47962" for p in tuners["parts"])
    assert client.get("/api/blocks/parts?fn=pmic").json()["total"] == 0  # opportunity
    d = client.post("/api/blocks/designs", json={"name": "T", "data": {"groups": [], "links": []}}).json()
    assert client.get(f"/blocks/{d['id']}").status_code == 200
