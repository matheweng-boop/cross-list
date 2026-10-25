"""Car radio market bottom-up (owner, 25 Oct 2026): two labelled layers inside the total radio market, content per
vehicle from the site's price estimates, "Not Enough Data" and a required to-do until the owner enters prices, one
content-driven CAGR, the owner's $5 / $10 as a cross-check, MarketIntelo as an open discrepancy, and the standards,
mandates and adoption that drive the system mix."""

from datetime import date

from app.services import radio_market as rm

CASE = "/business/reports/radio-tuner-next"


def _enter_all(client):
    """The owner enters what the Prices needed list asks for: a call, price breaks, and parts for the empty blocks."""
    posts = [{"mpn": "Si47961", "call": "ok", "note": "in band"},
             {"mpn": "Si46922A1GE1AM", "breaks": "1000 12.00\n2500 11.00", "currency": "USD", "note": "DigiKey"},
             {"block": "lna", "mpn": "TESTLNA1", "breaks": "1000 0.50\n3000 0.45"},
             {"block": "antenna_switch", "mpn": "TESTSW1", "breaks": "1000 0.40\n3000 0.36"},
             {"block": "audio_amp", "mpn": "TESTAMP1", "breaks": "1000 2.00\n2500 1.80"}]  # fmt: skip
    for data in posts:
        r = client.post("/business/tam/prices", data={**data, "back": "/pricing/estimate#prices-needed"},
                        follow_redirects=False)  # fmt: skip
        assert r.status_code == 303 and "price_saved=" in r.headers["location"]


def test_not_enough_data_before_prices_and_required_list(client, session):
    s = rm.summary(session)
    assert not s["layers"]["total"]["ok"] and s["layers"]["total"]["band"] == "Not Enough Data"
    needed = {n["part"] or n["block"] for n in s["needed"]}
    assert {"Si47961", "Si46922A1GE1AM", "lna", "antenna_switch", "audio_amp"} <= needed
    # Si47962 has public list prices (owner's DigiKey table): priced at 1M a year, not needed
    row = next(r for r in s["systems"][1]["rows"] if r["part"] == "Si47962")
    assert row["price"]["ok"] and 0 < row["price"]["low"] <= row["price"]["target"] <= row["price"]["high"]
    assert "Si47962" not in needed
    # the owner's $5 / $10 stay a cross-check: 90 M x $5 to 92 M x $10
    assert s["check"]["low"] == 450_000_000 and s["check"]["high"] == 920_000_000


def test_price_estimate_page_lists_required_prices_with_forms(client):
    html = client.get("/pricing/estimate").text
    assert "Required for market estimates" in html and 'action="/business/tam/prices"' in html
    assert "public distributor or list prices" in html and "never internal or customer pricing" in html
    assert "Si46922A1GE1AM" in html and "/pricing/estimate?name=Si47961" in html


def test_tam_page_two_layers_discrepancy_and_reported_growth(client):
    html = client.get("/business/tam").text
    assert "Radio content (tuners + digital radio demodulators)" in html
    assert "Tuner content (tuner ICs only)" in html and "Market at current BOM content" in html
    assert "Prices needed before this figure can be computed" in html
    assert "open discrepancy" in html and "MarketIntelo" in html
    assert "Growth as reported by" in html and "not used to project" in html
    assert "Owner cross-check" in html and "Standards, mandates and adoption" in html


def test_case_market_section_layers_drivers_and_us_am_mandate(client):
    html = client.get(CASE).text
    assert "Tuner content (tuner ICs only)" in html and "Radio content (tuners + digital radio demodulators)" in html
    for driver in ("Driver: standardization", "Driver: electrification", "Driver: integration"):
        assert driver in html
    assert "Standards, mandates and adoption" in html and 'id="mandate-us-am"' in html
    am = next(m for m in rm.config()["mandates"] if m["id"] == "us-am")
    assert "AM for Every Vehicle Act" in am["what"] and "passed the House" in am["status"]
    assert "Not law" in am["status"] and am["source"]["url"].startswith("https://")
    assert am["source"]["url"] in html
    assert "Prices needed before this figure can be computed" in html
    assert "vehicles flat at 90–92 M a year" in html


def test_computed_after_entry_and_applied_everywhere(client, session):
    _enter_all(client)
    s = rm.summary(session)
    assert s["needed"] == []
    tot, radio, tuner = s["layers"]["total"], s["layers"]["radio"], s["layers"]["tuner"]
    assert tot["ok"] and radio["ok"] and tuner["ok"]
    assert tuner["high"] <= radio["high"] <= tot["high"] and tot["low"] > 0
    # market = vehicles x content per vehicle (today's mix)
    assert abs(tot["low"] - 90_000_000 * tot["per_vehicle"]["low"]) < 1
    assert abs(tot["high"] - 92_000_000 * tot["per_vehicle"]["high"]) < 1
    # one content-driven CAGR per layer; vehicles flat, so the 2030 market = vehicles x 2030 content
    assert tot["cagr_max"] is not None and tot["cagr_min"] >= 0
    assert abs(tot["y_high"] - 92_000_000 * tot["end_per_vehicle"]) < 1
    case, page = client.get(CASE).text, client.get("/business/tam").text
    assert tot["band"] in case and tot["band"] in page
    assert tot["cagr_text"] in case and tot["cagr_text"] in page
    assert "Prices needed before this figure can be computed" not in case
    # entered prices are the part's own prices in the solution price builder too
    builder = client.post("/pricing/builder", data={"mpn": "Si46922A1GE1AM"}).text
    assert "entered by the owner" in builder


def test_inbox_has_prices_needed_section(client, session):
    from app.services import inbox

    text = inbox.collect(session, date(2026, 10, 1))
    assert "## Prices needed for market estimates" in text and "Si46922A1GE1AM" in text


def test_guests_cannot_enter_prices_or_see_the_list(make_guest):
    guest, _ = make_guest()
    r = guest.post("/business/tam/prices", data={"mpn": "Si47961", "call": "ok"}, follow_redirects=False)
    assert r.status_code in (302, 303, 403) and "price_saved" not in r.headers.get("location", "")
    assert "Required for market estimates" not in guest.get("/pricing/estimate").text
