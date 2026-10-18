import io
import json
import urllib.error

import pytest

from app.config import get_settings
from app.services import pricing
from app.sources.digikey import DigiKeyClient, parse_product

# Shape of a DigiKey Product Information v4 "productdetails" response (values made up for the test).
PRODUCT = {
    "ManufacturerProductNumber": "SA7741",
    "Manufacturer": {"Name": "SynAlpha"},
    "QuantityAvailable": 1234,
    "ProductStatus": {"Status": "Active"},
    "ManufacturerLeadWeeks": "8",
    "ProductUrl": "https://www.digikey.com/en/products/detail/x/SA7741/1",
    "ProductVariations": [
        {
            "DigiKeyProductNumber": "SA7741-CT-ND",
            "PackageType": {"Name": "Cut Tape (CT)"},
            "MinimumOrderQuantity": 1,
            "QuantityAvailableforPackageType": 1234,
            "StandardPricing": [
                {"BreakQuantity": 1, "UnitPrice": 3.0},
                {"BreakQuantity": 100, "UnitPrice": 2.0},
            ],
        },
        {
            "DigiKeyProductNumber": "SA7741-TR-ND",
            "PackageType": {"Name": "Tape & Reel (TR)"},
            "MinimumOrderQuantity": 1000,
            "StandardPricing": [{"BreakQuantity": 1000, "UnitPrice": 1.5}],
        },
    ],
}


class FakeDigiKey:
    """Stands in for urllib.request.urlopen against api.digikey.com."""

    def __init__(self, products):
        self.products, self.calls = products, []

    def __call__(self, req, timeout=30):
        self.calls.append((req.get_method(), req.full_url))
        if req.full_url.endswith("/oauth2/token"):
            return io.BytesIO(json.dumps({"access_token": "t", "expires_in": 600}).encode())
        assert req.headers["Authorization"] == "Bearer t"
        if req.full_url.endswith("/search/keyword"):
            return io.BytesIO(json.dumps({"Products": [], "ExactMatches": []}).encode())
        mpn = req.full_url.split("/search/")[1].split("/")[0]
        if mpn not in self.products:
            raise urllib.error.HTTPError(req.full_url, 404, "not found", {}, None)
        return io.BytesIO(json.dumps({"Product": self.products[mpn]}).encode())


@pytest.fixture
def digikey(monkeypatch):
    fake = FakeDigiKey({"SA7741": PRODUCT, "SR8641": {**PRODUCT, "ManufacturerProductNumber": "SR8641"}})
    monkeypatch.setattr(pricing, "_client", DigiKeyClient("id", "secret", opener=fake))
    monkeypatch.setattr(pricing, "get_client", lambda: pricing._client)
    monkeypatch.setattr(pricing, "enabled", lambda: True)
    return fake


def test_parse_product_keeps_every_packaging():
    q = parse_product(PRODUCT)
    assert q.found and q.stock == 1234 and q.lead_weeks == "8"
    assert [o.package for o in q.offers] == ["Cut Tape (CT)", "Tape & Reel (TR)"]
    assert q.offers[1].breaks == [(1000, 1.5)]


def test_price_at_picks_cheapest_packaging_for_the_quantity(session, part, digikey):
    pq = pricing.quote_for(session, part("SA7741"))
    assert pricing.price_at(pq, 1) == (3.0, "Cut Tape (CT)")
    assert pricing.price_at(pq, 500) == (2.0, "Cut Tape (CT)")
    assert pricing.price_at(pq, 1000) == (1.5, "Tape & Reel (TR)")


def test_quotes_are_cached(session, part, digikey):
    pricing.quote_for(session, part("SA7741"))
    n = len(digikey.calls)
    pricing.quote_for(session, part("SA7741"))
    assert len(digikey.calls) == n


def test_unlisted_part_is_marked_not_found(session, part, digikey):
    pq = pricing.quote_for(session, part("SB8441"))
    assert not pq.found and pricing.price_at(pq, 1) is None


def test_delta_vs_reference(session, part, digikey):
    ref = pricing.quote_for(session, part("SR8641"))
    cand = pricing.quote_for(session, part("SA7741"))
    ref.offers = [{"package": "Cut Tape (CT)", "min_qty": 1, "breaks": [[1, 4.0]]}]
    assert pricing.delta_pct(ref, cand, 1) == -25


def test_part_page_without_api_key(client, monkeypatch):
    monkeypatch.setattr(get_settings(), "digikey_client_id", "")
    pid = next(p["id"] for p in client.get("/api/parts?q=SR8641").json() if p["mpn"] == "SR8641")
    html = client.get(f"/parts/{pid}").text
    assert "Not connected" in html and 'hx-get="/pricing/' not in html


def test_pricing_line_and_comparison(client, digikey):
    parts = {p["mpn"]: p["id"] for p in client.get("/api/parts").json()}
    html = client.get(f"/pricing/{parts['SA7741']}?ref={parts['SR8641']}").text
    assert "1,234 in stock" in html and "$3.00" in html and "@1k" in html
    assert 'hx-get="/pricing/' in client.get(f"/parts/{parts['SR8641']}").text
    html = client.get(f"/compare?ids={parts['SR8641']},{parts['SA7741']}").text
    assert "DigiKey stock" in html and "Price @1k" in html
