def test_cross_requests_flow(client):
    r = client.post(
        "/requests",
        data={"mpns": "ADUM1401ARWZ, ISO7841DWR\nADUM1401ARWZ", "note": "customer X"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    html = client.get("/requests").text
    assert html.count("ADUM1401ARWZ</b>") == 1 and "ISO7841DWR" in html and "customer X" in html
    text = client.get("/requests.txt").text
    assert "- ADUM1401ARWZ (customer X)" in text and "- ISO7841DWR (customer X)" in text
    # a requested part that exists is linked
    client.post("/requests", data={"mpns": "SR8641"})
    assert "yes, see crosses" in client.get("/requests").text


def test_find_without_results_offers_a_request(client):
    html = client.get("/find?q=ZZZ9999").text
    assert "Request a cross for ZZZ9999" in html
