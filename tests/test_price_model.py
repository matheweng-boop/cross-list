"""Price model: curve fit, cost floor, band per volume and the owner's low / in-band / high calls."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.models import PriceQuote
from app.services import price_model as pm
from tests.test_pipeline import ids, real  # noqa: F401  (fixture)

BREAKS = [[1, 2.50], [10, 2.10], [100, 1.60], [1000, 1.20], [2500, 1.05]]


def _quote(session, part_id, breaks=BREAKS):
    session.add(PriceQuote(part_id=part_id, source="digikey", found=True, currency="USD", stock=1000,
                           offers=[{"package": "Cut Tape (CT)", "min_qty": 1, "breaks": breaks}],
                           fetched_at=datetime.now(UTC)))  # fmt: skip
    session.commit()


def test_fit_and_package_classes():
    f = pm.fit([(q, p) for q, p in BREAKS])
    assert -0.2 < f["slope"] < -0.05 and f["q_end"] == 2500 and f["fitted"]
    assert pm.fit([(1, 3.0)])["slope"] == pm.config()["curve"]["default_slope"]
    assert pm.package_class("SSOP-16") == "soic" and pm.package_class("SSO-8") == "soic_wide"
    assert pm.package_class("SOT-23") == "small_leadframe" and pm.package_class("LGA-36") == "laminate"
    assert 0.01 < pm._die_cost(1.2, 200, 750, 0.1) < 0.1


def test_band_floor_and_calls(client, session, part, real):  # noqa: F811
    p = part("ISO7741DBQR")
    _quote(session, p.id)
    m = pm.model(session, p, session.scalar(select(PriceQuote).where(PriceQuote.part_id == p.id)))
    assert [r["volume"] for r in m["rows"]] == [10000, 100000, 1000000] and not m["missing"]
    for r in m["rows"]:
        assert m["cost"]["floor"] <= r["low"] <= r["target"] <= r["high"]
    assert m["rows"][0]["target"] > m["rows"][-1]["target"]  # cheaper at higher volume
    html = client.get(f"/pricing/{p.id}/model").text
    assert "1,000,000" in html and "Cost floor" in html and "Low end" in html
    before = m["rows"][1]["target"]
    r = client.post(f"/pricing/{p.id}/call", data={"verdict": "low", "comment": "about 0.5 at 100k"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and "#price-model" in r.headers["location"]
    after = pm.model(session, p, session.scalar(select(PriceQuote).where(PriceQuote.part_id == p.id)))
    assert after["factor"] < 1 and after["call"]["verdict"] == "low" and after["rows"][1]["target"] < before
    assert client.post(f"/pricing/{p.id}/call", data={"verdict": "cheap"}).status_code == 400


def test_no_quote_says_what_is_missing(client, real):  # noqa: F811
    pid = ids(client, "SI86S641EC-IS1")
    html = client.get(f"/pricing/{pid}/model").text
    assert "Not enough to model yet" in html
    assert 'id="price-model"' not in client.get(f"/parts/{pid}").text  # no DigiKey and no list price: no panel


def test_list_price_when_no_digikey(client, session, part, real):  # noqa: F811
    assert len(pm.list_prices()) >= 10
    p = part("ISO7741DBQR")  # TI list price tiers from ti.com, no DigiKey quote in the test database
    m = pm.model(session, p, None)
    assert m["source"].startswith("TI list price") and len(m["rows"]) == 3 and not m["missing"]
    assert m["rows"][0]["high"] < pm.list_prices()["ISO7741DBQR"]["breaks"][-1][1]  # direct below the list price
    assert 'id="price-model"' in client.get(f"/parts/{p.id}").text
    assert "TI list price" in client.get(f"/pricing/{p.id}/model").text
