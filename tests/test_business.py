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
    for path in ("/business", "/business/applications", "/business/attach", "/business/gaps", "/business/data"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "Business opportunity" in r.text
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
    assert "How to read this" in client.get("/business").text
