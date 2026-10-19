from app.services import opportunity as op


def test_coverage_counts_positions_not_skus():
    p = op.Position
    ps = [p("a", "A", "G", 2, "supported"), p("b", "B", "G", 1, "gap"), p("c", "C", "G", 1, "competitor"),
          p("d", "D", "G", 1, "na"), p("e", "E", "G", 1, "unknown")]  # fmt: skip
    m = op.metrics(ps, {"a": 2.0, "b": 1.5})
    assert m["in_scope"] == 3 and m["supported"] == 1 and abs(m["coverage"] - 1 / 3) < 1e-9
    assert m["na"] == 1 and m["unknown"] == 1  # excluded from the denominator
    # revenue only on the priced subset, with its completeness
    assert m["priced"] == 2 and m["content_total"] == 2 * 2.0 + 1.5 and m["content_mine"] == 4.0
    assert abs(m["price_completeness"] - 2 / 3) < 1e-9


def test_pages_and_inputs(client):
    for path in ("/business", "/business/applications", "/business/attach", "/business/explorer", "/business/data"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert 'class="crumbs-bar' in r.text
    assert client.get("/business/applications/1?co=skyworks").status_code == 200
    r = client.post(
        "/business/data", data={"co": "combined", "asp:gate_driver": "2.80", "vol:Car radio tuner system": "1000"}
    )
    assert r.status_code in (200, 303)
    page = client.get("/business/data").text
    assert 'value="2.8"' in page and 'value="1000"' in page
    assert client.post("/api/business/asp", json={"gate_driver": None}).json()["ok"]
    assert 'value="2.8"' not in client.get("/business/data").text
    attach = client.get("/business/attach?fn=gate_driver").text
    assert "Cross-sell" in attach or "choose" in attach


def test_markets_competition_and_gap_rows(client):
    assert op.market_of("HEV/EV on-board charger", "Power & isolation") == "Automotive"
    assert op.market_of("Wi-Fi 6 combo (client / IoT / automotive module)", "RF & connectivity") == "RF & connectivity"
    assert op.market_of("Light EV BLDC drive, 48 V", "Motor drives") == "Motor drives"
    comp = op.competition()
    assert comp and all(e["crowding"] in op.CROWDING_LABEL for e in comp.values())
    assert not any(v in ("Skyworks", "Qorvo") for e in comp.values() for v in e["vendors"])
    for path in ("/business/markets", "/business/markets?view=requalify", "/business/markets?view=multi",
                 "/business/gaps?sort=crowding"):  # fmt: skip
        assert client.get(path).status_code == 200, path
    assert "About this page" in client.get("/business").text


def test_technology_fit_and_cases(client):
    assert "Technology fit" in client.get("/business/technology").text
    for v in ("develop", "low_attach", "chips"):
        assert client.get(f"/business/technology?view={v}").status_code == 200
    assert "Not our product type" in client.get("/business/applications/1").text
    page = client.get("/business/cases/new?fn=pol_ldo").text
    assert "What Cross List knows" in page and "PoL LDO" in page
    r = client.post("/business/cases", data={"title": "Automotive PoL LDO", "fn": "pol_ldo", "question": "Develop it?",
                                              "features": "3 A – fewer parts"})  # fmt: skip
    assert r.status_code in (200, 303)
    lst = client.get("/business/cases").text
    assert "Automotive PoL LDO" in lst
    import re

    cid = int(re.search(r"/business/cases/(\d+)", lst).group(1))
    brief = client.get(f"/business/cases/{cid}/brief.md").text
    assert "Market analysis task: Automotive PoL LDO" in brief and "Develop it?" in brief and "door openers" in brief
    client.post(f"/business/cases/{cid}", data={"act": "note", "kind": "upside", "text": "Reuses PMIC LDO IP"})
    client.post(f"/business/cases/{cid}", data={"act": "analysis", "analysis": "Market grows."})
    page = client.get(f"/business/cases/{cid}").text
    assert "Reuses PMIC LDO IP" in page and "Market grows." in page
    client.post(f"/business/cases/{cid}", data={"act": "delete"})
    assert client.get(f"/business/cases/{cid}").status_code == 404


def test_explanations_everywhere(client):
    help_ = op.explanations()
    for page in ("overview", "applications", "markets", "attach", "explorer", "cases", "data"):
        assert page in help_["pages"]
    for path in ("/business", "/business/applications", "/business/markets", "/business/attach", "/business/gaps",
                 "/business/technology", "/business/explorer", "/business/cases", "/business/data"):  # fmt: skip
        assert "About this page" in client.get(path).text, path
    method = client.get("/business/method").text
    assert "Formulas" in method and "Door opener" in method and "Data sources" in method


def test_hunt_capabilities_and_feedback(client):
    for path in ("/business/customers", "/business/customers?fn=pol_ldo", "/business/capabilities"):
        r = client.get(path)
        assert r.status_code == 200 and "About this page" in r.text, path
    client.post("/business/capabilities/feedback", data={"kind": "missing", "topic": "BAW filters", "text": "Add XBAW"})
    assert "Add XBAW" in client.get("/business/capabilities").text
    assert "Add XBAW" in client.get("/business/capabilities/feedback.txt").text


def test_evidence_reviews_and_mappings(client, session):
    from app.services import quality

    for path in ("/business/evidence/pol_ldo", "/business/quality", "/business/technology?view=short"):
        r = client.get(path)
        assert r.status_code == 200 and "About this page" in r.text, path
    assert client.get("/business/evidence/not_a_function").status_code == 404
    r = client.post("/api/business/review", json={"dataset": "technology", "key": "pol_ldo", "verdict": "wrong",
                                                   "comment": "Qorvo has LDOs", "author": "test"})  # fmt: skip
    assert r.json()["state"] == "disputed"
    assert (
        client.post("/api/business/review", json={"dataset": "nope", "key": "x", "verdict": "correct"}).status_code
        == 400
    )
    assert "Qorvo has LDOs" in client.get("/business/quality/todo.txt").text
    # a confirmed catalogue part turns the gap into a portfolio function
    mine = op.COMPANIES["combined"][1]
    assert op.status_of("pol_ldo", op.makers(session), mine) != "supported"
    client.post(
        "/business/evidence/pol_ldo/mapping", data={"mpn": "TESTLDO1", "manufacturer": "Qorvo", "verdict": "yes"}
    )
    session.expire_all()
    assert op.status_of("pol_ldo", op.makers(session), mine) == "supported"
    client.post("/business/evidence/pol_ldo/mapping", data={"mpn": "TESTLDO1", "verdict": "undo"})
    session.expire_all()
    assert op.status_of("pol_ldo", op.makers(session), mine) != "supported"
    assert any(c["level"] in ("ok", "warn", "error") for c in quality.checks(op.applications()))


def test_explore_page(client):
    for path in ("/business/explore", "/business/explore?fit=high"):
        r = client.get(path)
        assert r.status_code == 200 and "New markets" in r.text, path


def test_explorer_views_scope_and_old_links(client):
    for view in ("reach", "crosssell", "feasibility", "competition", "commercial", "evidence"):
        r = client.get(f"/business/explorer?view={view}")
        assert r.status_code == 200 and "Denominator" in r.text, view
    lib = client.get("/business/explorer?scope=library").text
    assert "Library architectures only" in lib and "reference architectures" in lib
    # old pages land on the matching view
    r = client.get("/business/gaps?sort=tam", follow_redirects=False)
    assert r.status_code == 307 and "view=commercial" in r.headers["location"]
    r = client.get("/business/technology?view=short", follow_redirects=False)
    assert "view=feasibility" in r.headers["location"] and "f=short" in r.headers["location"]
    # unknown TAM is shown as unknown, never as zero
    assert "unknown" in client.get("/business/explorer?view=commercial").text


def test_gap_types_and_qualification_states():
    assert op.gap_type("supported", None) == "candidate"
    assert op.gap_type("gap", {"path": "exists"}) == "mapping"
    assert op.gap_type("gap", {"path": "new_design"}) == "true_gap"
    assert op.gap_type("gap", None) == "unknown_evidence"
    assert op.gap_type("na", None) == "not_ours"
    q = op.qual_state
    assert q({"values": {"qualification": "automotive"}}) == "automotive"
    assert q({"values": {"qualification": "industrial"}}) == "not_automotive"
    assert q({"values": {"qualification": None}}) == "unknown"
