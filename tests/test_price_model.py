"""Price model: curve fit, cost floor, band per volume and the owner's low / in-band / high calls."""

from datetime import UTC, datetime

from sqlalchemy import select

from app.models import PriceQuote
from app.services import price_model as pm
from tests.conftest import ids

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


def test_band_floor_and_calls(client, session, part, real):
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


def test_no_quote_says_what_is_missing(client, real):
    pid = ids(client, "SI86S641EC-IS1")
    html = client.get(f"/pricing/{pid}/model").text
    assert "Not Enough Data</b> to model yet" in html
    assert 'id="price-model"' not in client.get(f"/parts/{pid}").text  # no DigiKey and no list price: no panel


def test_list_price_when_no_digikey(client, session, part, real):
    assert len(pm.list_prices()) >= 10
    p = part("ISO7741DBQR")  # TI list price tiers from ti.com, no DigiKey quote in the test database
    m = pm.model(session, p, None)
    assert m["source"].startswith("TI list price") and len(m["rows"]) == 3 and not m["missing"]
    assert m["rows"][0]["high"] < pm.list_prices()["ISO7741DBQR"]["breaks"][-1][1]  # direct below the list price
    assert 'id="price-model"' in client.get(f"/parts/{p.id}").text
    assert "TI list price" in client.get(f"/pricing/{p.id}/model").text


def test_monte_carlo_is_stable_and_ordered(session, part, real):
    p = part("ISO7741DBQR")
    a, b = pm.model(session, p, None), pm.model(session, p, None)
    assert [r["target"] for r in a["rows"]] == [r["target"] for r in b["rows"]]  # seeded by the part number
    for r in a["rows"]:
        assert r["low"] <= r["target"] <= r["high"]
    f = pm.fit([(q, pr) for q, pr in BREAKS])
    draws = pm.simulate(p, f, pm.cost(p), 100000, [0.5, 0.67], 1.0)
    assert len(draws) == pm.config()["monte_carlo"]["draws"] and min(draws) >= pm.cost(p)["levels"]["low"]["total"]
    assert {v["test"][:12] for v in pm.config()["validation"]} and len(pm.list_prices()) >= 60


DK_PASTE = """QUANTITY
UNIT PRICE	EXT PRICE
1
€ 18,66000	€ 18,66
10
€ 16,26300	€ 162,63
100
€ 14,29280	€ 1.429,28
500
€ 13,13008	€ 6.565,04"""


def test_parse_breaks_both_layouts():
    assert pm.parse_breaks(DK_PASTE) == [(1, 18.66), (10, 16.263), (100, 14.2928), (500, 13.13008)]
    assert pm.parse_breaks("1 3.035\n1,000 1.355\n2.500 $1.20") == [(1, 3.035), (1000, 1.355), (2500, 1.2)]


def test_classes_and_estimate_page(client, session):
    assert pm.complexity("am_fm_tuner") == "complex" and pm.complexity("rf_switch") == "commodity"
    f = pm.fit(pm.parse_breaks(DK_PASTE))
    assert pm.extension(f, "am_fm_tuner")[2] == "flat"  # a complex part follows its own flat curve
    m = pm.estimate(session, "am_fm_tuner", pm.parse_breaks(DK_PASTE), "QFN-48", 48, automotive=True, name="Si47962")
    assert m["cost"]["automotive"] and len(m["rows"]) == 3 and m["rows"][-1]["target"] < 13.13
    html = client.get("/pricing/estimate", params={"family": "am_fm_tuner", "breaks": DK_PASTE, "package": "QFN-48",
                                                   "pins": 48, "currency": "EUR", "name": "Si47962"}).text  # fmt: skip
    assert "Si47962" in html and "1,000,000" in html and "converted from EUR" in html and "Low end" not in html
    assert "€" not in html.split('id="price-model"')[1]  # results all in USD
    assert client.get("/pricing/estimate").status_code == 200


def test_usd_conversion():
    assert pm.usd_rate("EUR") == pm.config()["fx"]["usd_per"]["EUR"] > 1 and pm.usd_rate(None) == 1.0
    from types import SimpleNamespace

    pq = SimpleNamespace(found=True, currency="EUR", offers=[{"breaks": [[100, 10.0], [1000, 8.0]]}])
    assert pm.breaks(pq) == [(100, 10.0 * pm.usd_rate("EUR")), (1000, 8.0 * pm.usd_rate("EUR"))]


GD3162 = "1 10.80\n10 8.43\n25 7.8388\n176 6.98864\n352 6.78261\n528 6.67943\n1,056 6.52815"


def test_oem_targets_and_our_part_from_a_competitor(client, session):
    m = pm.estimate(session, "gate_driver", pm.parse_breaks(GD3162), "SOIC-32W", 32, automotive=True)
    o = pm.oem_path(m, 2028)
    assert [r["phase"] for r in o["rows"]][:3] == ["today", "before SOP", "SOP"] and o["rows"][0]["low"] == o["start"]
    sop = next(r for r in o["rows"] if r["phase"] == "SOP")
    assert abs(sop["high"] - o["start"] * 0.95**2) < 1e-9 and abs(sop["low"] - o["start"] * 0.93**2) < 1e-9
    ours = pm.scaled(m, 0.9, 1.0)
    assert all(a["low"] < b["low"] and a["high"] == b["high"] for a, b in zip(ours, m["rows"], strict=True))
    html = client.get(
        "/pricing/estimate",
        params={
            "family": "gate_driver",
            "breaks": GD3162,
            "name": "GD3162",
            "package": "SOIC-32W",
            "pins": 32,
            "wide": "true",
            "automotive": "true",
            "sop": 2029,
            "ours": "Si82900",
        },
    ).text
    assert "OEM target prices" in html and "SOP 2029" in html
    # owner, 23 Oct 2026: "take out the our part price": no field, an old link's value is ignored
    assert "Si82900" not in html and 'name="ours"' not in html and "pe-ours" not in html


def test_owner_digikey_tables_in_usd(session, part, real):
    lp = pm.list_prices()["ISO7710FDR"]
    assert lp["currency"] == "EUR" and lp["source"].startswith("DigiKey")
    m = pm.model(session, part("ISO7710FDR"), None)
    assert m["converted_from"] == "EUR" and m["source"].startswith("DigiKey (owner")
    assert abs(m["fit"]["p_end"] - lp["breaks"][-1][1] * pm.usd_rate("EUR")) < 1e-9


def test_gross_margin_slider(client, session, part, real):
    p = part("ISO7741DBQR")
    low, high = pm.model(session, p, None, 0.30), pm.model(session, p, None, 0.70)
    assert low["gm"] == 0.30 and high["gm"] == 0.70 and high["cost"]["floor"] > low["cost"]["floor"]
    assert all(h["allowed_cost"] < lo["allowed_cost"] for h, lo in zip(high["rows"], low["rows"], strict=True))
    assert pm.margin(0.99) == pm.config()["margin"]["slider"][1] and pm.margin(None) == pm.config()["margin"]["floor"]
    html = client.get(f"/pricing/{p.id}/model?gm=55").text
    assert 'type="range" name="gm"' in html and "At 55 % gross margin" in html
    est = client.get("/pricing/estimate", params={"family": "gate_driver", "breaks": GD3162, "gm": 60}).text
    assert "At 60 % gross margin" in est and 'value="60"' in est


def test_fab_scenarios_and_cost_adjustment(client, session, part, real):
    p = part("ISO7741DBQR")
    ext, own = pm.cost(p, None, "external"), pm.cost(p, None, "in_house")
    assert own["levels"]["mid"]["total"] < ext["levels"]["mid"]["total"] and pm.config()["cost_adjust"] == 0.9
    assert pm.cost(p, None, "nonsense")["fab"] == pm.fab_scenarios()[0] == "external"
    assert all("fab" not in fam for fam in pm.config()["families"].values())  # no claim about where anything is made
    html = client.get(f"/pricing/{p.id}/model?gm=45").text
    # both scenarios are on the page; the reference shows, the other is hidden until the reader flips the switch
    assert 'data-fab="external">' in html and 'data-fab="in_house" hidden>' in html
    assert 'data-fab-pick="in_house"' in html and 'aria-pressed="false"' in html
    assert "never sent, saved or put in the link" in html
    assert 'name="fab"' not in html and "?fab=" not in html and "&fab=" not in html  # never a form field or link
    est = client.get("/pricing/estimate", params={"family": "gate_driver", "breaks": GD3162, "ours": "X"}).text
    assert 'data-fab="in_house" hidden>' in est and 'name="fab"' not in est and 'class="pe-ours"' not in est


def test_oem_path_flattens_after_the_price_down_years():
    m = {"rows": [{"volume": 100000, "low": 0.9, "target": 1.0, "high": 1.1}]}
    new, old = pm.oem_path(m, 2028), pm.oem_path(m, 2028, released=2016)
    assert new["assumed_new"] and not old["assumed_new"] and old["released"] == 2016
    assert new["rows"][-1]["low"] < new["rows"][1]["low"] < 1.0  # a new part keeps getting cheaper
    assert all(r["low"] == r["high"] == 1.0 and r["flat"] for r in old["rows"])  # ten years on the market: flat
    mid = pm.oem_path(m, 2028, released=2022)  # 5 % stops after 2027, 7 % after 2028
    by = {r["year"]: r for r in mid["rows"]}
    assert by[2027]["high"] == by[2032]["high"] < by[2026]["high"] and by[2028]["low"] == by[2032]["low"]
    assert by[2029]["flat"] and not by[2028]["flat"]


def test_channels_scale_the_cost_and_the_package_sets_wide_body():
    one, four, eight = (pm.cost(pm.part_ns("digital_isolator", "SOIC-16", 16, units=n)) for n in (1, 4, 8))
    assert one["levels"]["mid"]["die"] < four["levels"]["mid"]["die"] < eight["levels"]["mid"]["die"]
    assert four["scale"] == (1.0, 1.0) and pm.units_of(pm.part_ns("x", units=None)) is None
    two, three = (pm.cost(pm.part_ns("radio_coprocessor", "QFN-88", 88, units=n)) for n in (2, 3))
    assert three["levels"]["mid"]["total"] > two["levels"]["mid"]["total"]
    for code in ("SOIC-16W", "SOIC-16 (DW)", "SOIC-8 (DWV)", "SOIC-20 (DFM)", "SOIC-16 WB"):
        assert pm.is_wide(code), code
        assert pm.cost(pm.part_ns("digital_isolator", code, 16))["package_key"] == "soic_wide"
    assert not pm.is_wide("SOIC-16N") and not pm.is_wide("SOIC-8 (D)") and pm.is_wide("SOIC-8", 10.3)
