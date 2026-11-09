"""The owner's price levels (9 Nov 2026), the 55-70 % margin, the cost blend, the maker scale and the single price at
1M a year. Synthetic parts (SR8641 by SynRef, SC141 by SynGamma) and invented prices only: the owner's real levels
are confidential and live only in the live site's database."""

import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import DataReview, PriceQuote
from app.services import price_model as pm
from tests.conftest import ids

BREAKS = [[1, 2.50], [10, 2.10], [100, 1.60], [1000, 1.20], [2500, 1.05]]


def _quote(session, part_id, breaks=BREAKS):
    session.add(PriceQuote(part_id=part_id, source="digikey", found=True, currency="USD", stock=1000,
                           offers=[{"package": "Cut Tape (CT)", "min_qty": 1, "breaks": breaks}],
                           fetched_at=datetime.now(UTC)))  # fmt: skip
    session.commit()


def _setup(client, session, part, mpn="SR8641"):
    p = part(mpn)
    _quote(session, p.id)
    return p, session.scalar(select(PriceQuote).where(PriceQuote.part_id == p.id))


def _bases(html: str) -> str:
    return re.search(r'name="bases" value="([^"]*)"', html).group(1)


@pytest.mark.parametrize("text,lo,hi", [("3.5", 3.5, 3.5), ("0.71-0.76", 0.71, 0.76), ("$0.71 – 0.76", 0.71, 0.76),
                                        ("0.7x", 0.70, 0.79), ("0,84", 0.84, 0.84), ("about 3.5", 3.5, 3.5),
                                        ("0.76 to 0.71", 0.71, 0.76), ("USD 3", 3.0, 3.0)])  # fmt: skip
def test_parse_level(text, lo, hi):
    assert pm.parse_level(text) == pytest.approx((lo, hi))


@pytest.mark.parametrize("text", ["", "abc", "0", "1 2 3", "cheap"])
def test_parse_level_refuses(text):
    with pytest.raises(ValueError):
        pm.parse_level(text)


def test_margin_55_70_and_the_floor(session, part):
    cfg = pm.config()["margin"]
    assert cfg["typical"] == [0.55, 0.70] and cfg["draw"] == [0.55, 0.625, 0.70] and pm.margin(None) == 0.625
    assert pm.floor_margin(None) == 0.55 and pm.floor_margin(0.30) == 0.30  # the slider overrides both
    p = part("SR8641")
    cb = pm.cost(p)
    assert cb["floor"] == pytest.approx(cb["levels"]["mid"]["total"] / 0.45)
    assert cb["cost_price"] == pytest.approx(cb["levels"]["mid"]["total"] / 0.375)


def test_cost_blend_leans_on_cost_at_volume(client, session, part):
    p, pq = _setup(client, session, part)
    m = pm.model(session, p, pq)
    w = {r["volume"]: r["weight"] for r in m["rows"]}
    assert w[10000] > 0.5 > w[1000000] and w[10000] > w[100000] > w[1000000]
    for r in m["rows"]:  # never below the unit cost at the 55 % floor margin
        assert r["low"] <= r["target"] <= r["high"] and r["low"] >= m["cost"]["levels"]["low"]["total"] / 0.45
    few = pm.fit([(1000, 1.25), (2500, 1.05)])
    assert pm.market_weight(10000, few) == pytest.approx(w[10000] * pm.config()["blend"]["few_breaks_factor"])
    assert pm.market_weight(10000, None) == 0
    html = client.get(f"/pricing/{p.id}/model").text
    assert "% market at 10,000" in html and "leans on the curve at 10k" in html


def test_cost_only_band_without_a_curve(session, part):
    m = pm.model(session, part("SR8641"), None)
    assert m.get("cost_only") and len(m["rows"]) == 3 and all(r["distributor"] is None for r in m["rows"])
    assert m["single"]["price"] >= m["single"]["floor"] > 0


def test_maker_scale_tiers(client, session, part):
    sc = pm.config()["scale"]
    assert pm.scale_for(session, "TI", "digital_isolator")["tier"] == 1
    assert pm.scale_for(session, "Skyworks", "digital_isolator")["why"] == "large volume in this technology class"
    unknown = pm.scale_for(session, "", "digital_isolator")
    assert unknown["tier"] == sc["default_tier"] and unknown["factor"] == 1.0
    syn = pm.scale_for(session, "SynRef", "gate_driver")  # by breadth: its parts in the isolation class on the site
    assert syn["count"] >= 1 and syn["cls"] == "isolation" and syn["tier"] in (3, 4)
    p = part("SR8641")
    a, b = pm.cost(p, maker_k=0.7), pm.cost(p, maker_k=1.0)
    assert a["levels"]["mid"]["total"] == pytest.approx(0.7 * b["levels"]["mid"]["total"])
    # the page names the maker's tier and the cost side against ours
    _quote(session, p.id)
    html = client.get(f"/pricing/{p.id}/model").text
    assert "<b>Scale:</b> SynRef, tier" in html and "Cost side against ours" in html
    # our own makers: a generic reason only, never a node, fab, foundry or site
    for m in sc["own_makers"]:
        why = sc["makers"][m]["why"].lower()
        assert not re.search(r"\bnm\b|fab|foundry|site|um\b", why), why


def test_single_price_at_1m(client, session, part):
    p, pq = _setup(client, session, part)
    m = pm.model(session, p, pq)
    row = next(r for r in m["rows"] if r["volume"] == 1000000)
    assert m["single"]["price"] == pytest.approx(max(row["target"], m["cost"]["floor"]))
    html = client.get(f"/pricing/{p.id}/model").text
    assert "at 1M / year</b>" in html and "· floor $" in html and "never below the floor" in html
    est = client.get("/pricing/estimate", params={"family": "digital_isolator", "breaks": "1000 1.20\n2500 1.05",
                                                  "name": "SYN-EST-1"}).text  # fmt: skip
    assert "at 1M / year</b>" in est


def test_owner_level_recentres_the_part_and_sets_the_family(client, session, part):
    p, pq = _setup(client, session, part)
    before = pm.model(session, p, pq, owner=True)
    html = client.get(f"/pricing/{p.id}/model").text  # no sign-in in this client: the owner's view
    assert 'id="price-level"' in html and "Save price level" in html
    r = client.post("/pricing/level", data={"mpn": "SR8641", "family": "digital_isolator", "volume": "100000",
                                            "price": "0.90-1.10", "whose": "ours", "bases": _bases(html),
                                            "back": f"/parts/{p.id}?price=open"}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"] == f"/parts/{p.id}?price=open#price-level"
    after = pm.model(session, p, pq, owner=True)
    rows = {r["volume"]: r for r in after["rows"]}
    assert rows[100000]["target"] == pytest.approx(1.0) and rows[100000]["set_by"]
    k = 1.0 / next(r for r in before["rows"] if r["volume"] == 100000)["target"]
    assert after["n_levels"] == 1 and after["factor"] != 1.0
    for b in before["rows"]:  # every volume moves by the same ratio, low and high keep their distance
        a = rows[b["volume"]]
        assert a["low"] / a["target"] == pytest.approx(b["low"] / b["target"], rel=0.05)
    assert after["single"]["by_level"]
    page = client.get(f"/pricing/{p.id}/model").text
    assert "set by your price level" in page and "Your price levels on 1 part of this family" in page
    assert "$0.900–$0.900" not in page and "$0.900–$1.10" in page  # the stored range
    # a guest's view and any non-owner model ignore it
    plain = pm.model(session, p, pq)
    assert [r["target"] for r in plain["rows"]] == [r["target"] for r in pm.model(session, p, pq, owner=False)["rows"]]
    assert not any(r.get("set_by") for r in plain["rows"]) and k > 0
    # a family member with no level of its own moves with the family factor
    q = part("SC141")
    _quote(session, q.id)
    other = pm.model(session, q, session.scalar(select(PriceQuote).where(PriceQuote.part_id == q.id)), owner=True)
    assert other["factor"] == after["factor"] and not any(r.get("set_by") for r in other["rows"])
    # delete: the part's band is the model's again; history is kept
    client.post("/pricing/level/delete", data={"key": "SR8641", "volume": "100000", "back": f"/parts/{p.id}"})
    gone = pm.model(session, p, pq, owner=True)
    assert not gone["levels"] and gone["n_levels"] == 0
    assert session.query(DataReview).filter(DataReview.dataset == pm.LEVELS).count() == 2


def test_learned_parity_from_pairs(client, session, part):
    p, pq = _setup(client, session, part)
    html = client.get(f"/pricing/{p.id}/model").text
    assert "No pairs in this family yet" in html and "default parity of 90–100 %" in html
    base = {"family": "digital_isolator", "volume": "100000", "back": f"/parts/{p.id}?price=open"}
    client.post("/pricing/level", data={**base, "mpn": "SR8641", "price": "1.00", "whose": "ours", "cross": "SYN-X1"})
    client.post("/pricing/level", data={**base, "mpn": "SR8641", "price": "0.50", "whose": "theirs",
                                        "cross": "SYN-X1"})  # fmt: skip
    lv = pm.points(session)
    assert {(x["key"], x["whose"]) for x in lv} == {("SR8641", "ours"), ("SYN-X1", "theirs")}
    par = pm.parity(lv, "digital_isolator")
    assert par["learned"] and par["n"] == 1 and par["ratio"] == pytest.approx(2.0)
    assert par["lo"] <= 2.0 <= par["hi"]
    assert pm.parity(lv, "gate_driver")["learned"] is False
    html = client.get(f"/pricing/{p.id}/model").text
    assert "Our parts sit at about <b>2.00 ×</b> the competitor's cross in this family, from 1 pair you entered" in html
    # the estimate page: a competitor's part priced with the learned parity; its own level through "this_theirs"
    est = {"family": "digital_isolator", "breaks": "1000 0.60\n2500 0.55", "name": "SYN-X2"}
    page = client.get("/pricing/estimate", params=est).text
    assert "2.00 ×" in page and "If this part is a competitor's, ours would sit at about" in page
    back = "/pricing/estimate?" + "&".join(f"{k}={v}" for k, v in est.items() if k != "breaks")
    r = client.post("/pricing/level", data={**base, "mpn": "SYN-X2", "price": "0.4x", "whose": "this_theirs",
                                            "ourpn": "SYN-OURS-2", "back": back}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"].startswith("/pricing/estimate?")
    x2 = next(x for x in pm.points(session) if x["key"] == "SYN-X2")
    assert (x2["whose"], x2["ours"], x2["low"], x2["high"]) == ("theirs", "SYN-OURS-2", 0.40, 0.49)


def test_bad_level_is_not_stored(client, session, part):
    p, _ = _setup(client, session, part)
    r = client.post("/pricing/level", data={"mpn": "SR8641", "volume": "100000", "price": "cheap", "whose": "ours",
                                            "back": f"/parts/{p.id}?price=open"}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and "level_error=" in r.headers["location"]
    assert not pm.points(session)
    r = client.post("/pricing/level", data={"mpn": "SR8641", "volume": "5000", "price": "1", "whose": "ours",
                                            "back": "https://evil.example/x"}, follow_redirects=False)  # fmt: skip
    assert r.headers["location"].startswith("/pricing/estimate?level_error=") and not pm.points(session)
    page = client.get(f"/pricing/{p.id}/model", params={"level_error": "enter a price"}).text
    assert "Not saved: enter a price." in page


def test_guests_never_see_or_enter_levels(owner, make_guest, session, part):
    p, pq = _setup(owner, session, part)
    owner.post("/pricing/level", data={"mpn": "SR8641", "family": "digital_isolator", "volume": "100000",
                                       "price": "7.777", "whose": "ours"})  # fmt: skip
    assert "$7.78" in owner.get(f"/pricing/{p.id}/model").text
    guest, _ = make_guest("Anna Guest")
    html = guest.get(f"/pricing/{p.id}/model").text
    assert "7.77" not in html and "7.78" not in html and 'id="price-level"' not in html
    assert "set by your price level" not in html
    assert guest.post("/pricing/level", data={"mpn": "SR8641", "volume": "100000", "price": "1",
                                              "whose": "ours"}).status_code == 403  # fmt: skip
    assert guest.post("/pricing/level/delete", data={"key": "SR8641", "volume": "100000"}).status_code == 403
    est = guest.get("/pricing/estimate", params={"family": "digital_isolator", "breaks": "1000 1.25",
                                                 "name": "SR8641"}).text  # fmt: skip
    assert "7.77" not in est and 'id="price-level"' not in est


def test_inbox_counts_levels_only(client, session, part):
    from app.services import inbox

    p, _ = _setup(client, session, part)
    client.post("/pricing/level", data={"mpn": "SR8641", "family": "digital_isolator", "volume": "100000",
                                        "price": "6.543", "whose": "ours", "cross": "SYN-Q9"})  # fmt: skip
    out = inbox.collect(session, (datetime.now(UTC) - timedelta(days=1)).date())
    assert "1 price point(s) entered" in out
    assert "6.543" not in out and "SYN-Q9" not in out and "price_point" not in out


def test_levels_stay_out_of_shareables_and_exports(client, session, part):
    """A synthetic level with a unique number: not in any Shareable page, the combined PDF, the PowerPoint or the
    downloads (the replacements and comparison CSV / Excel)."""
    from app.services import presentation_pptx as pp
    from app.services import share_pdf as spdf
    from app.services import share_reports as sr

    mark, pid = "8.642", ids(client, "SR8641")
    client.post("/pricing/level", data={"mpn": "SR8641", "family": "digital_isolator", "volume": "1000000",
                                        "price": mark, "whose": "ours", "cross": "SYNLEAKX"})  # fmt: skip
    assert pm.points(session)
    keys = [e.key for e in sr.REGISTRY]
    texts = {u: client.get(u).text for u in ["/shareable", *(e.url for e in sr.REGISTRY), "/shareable/presentation"]}
    texts["PDF"] = "\n".join(spdf.texts(client.get("/shareable/pdf?r=" + ",".join(keys)).content))
    texts["PPTX"] = "\n".join(t for s in pp.texts(client.get("/shareable/pptx?r=" + ",".join(keys)).content) for t in s)
    for fmt in ("csv", "xlsx"):
        r = client.get(f"/parts/{pid}/replacements.{fmt}")
        assert r.status_code == 200
        if fmt == "csv":
            texts["replacements.csv"] = r.text
        else:
            import io

            from openpyxl import load_workbook

            wb = load_workbook(io.BytesIO(r.content))
            texts["replacements.xlsx"] = "\n".join(str(c) for ws in wb for row in ws.iter_rows(values_only=True)
                                                   for c in row if c is not None)
    for name, t in texts.items():
        assert mark not in t and "8.64" not in t and "SYNLEAKX" not in t, name


def _level(client, page_mpn, part_id, price, whose="ours", cross="", volume="100000"):
    html = client.get(f"/pricing/{part_id}/model").text
    data = {"mpn": page_mpn, "family": "digital_isolator", "volume": volume, "price": price, "whose": whose,
            "cross": cross, "bases": _bases(html), "back": f"/parts/{part_id}?price=open",
            "unit_cost": re.search(r'name="unit_cost" value="([^"]*)"', html).group(1),
            "maker": re.search(r'name="maker" value="([^"]*)"', html).group(1)}  # fmt: skip
    assert client.post("/pricing/level", data=data, follow_redirects=False).status_code == 303


def test_levels_raise_the_cost_per_maker_and_family(client, session, part):
    """Owner, 9 Nov 2026: a level read at 60 % gross margin sets the cost; "different companies have different
    costs": our levels calibrate our maker, the cross's level its maker, in that family only."""
    cfg = pm.config()
    assert cfg["calibration_margin"] == 0.60 and "correction" not in str(list(cfg))  # nothing calibrated on file
    p, pq = _setup(client, session, part)  # SR8641 by SynRef (stands in for us)
    plain = pm.model(session, p, pq, owner=True)
    c0 = plain["model_cost"]
    assert plain["correction"]["n"] == 0 and plain["scale"]["maker"] == "SynRef"
    level = round(c0 * 5, 4)  # implies a cost of 2 x the model's at 60 %
    _level(client, "SR8641", p.id, f"{level}")
    m = pm.model(session, p, pq, owner=True)
    assert m["correction"]["n"] == 1 and m["correction"]["k"] == pytest.approx(2.0, rel=1e-3)
    implied = 1 - m["cost"]["levels"]["mid"]["total"] / level
    assert implied == pytest.approx(0.60, abs=0.005)  # the level now sits at 60 % margin on the model's cost
    assert "SynRef's cost raised ×2.00 from your price levels (1 part" in client.get(f"/pricing/{p.id}/model").text
    # the family's other SynRef part rises too; another maker's part (SynGamma) does not
    other = pm.model(session, part("SR8640N"), None, owner=True)
    assert other["correction"]["k"] == pytest.approx(2.0, rel=1e-3) and other["correction"]["scope"] == "family"
    gamma = pm.model(session, part("SC142"), None, owner=True)
    assert gamma["correction"]["n"] == 0
    # SynRef in another family: the weaker guide from other families
    gd = pm.model(session, part("SR8233"), None, owner=True)
    assert gd["correction"]["scope"] == "other families" and gd["correction"]["k"] == pytest.approx(2.0, rel=1e-3)
    # the competitor's cross level calibrates the competitor: a different correction in the same family
    _level(client, "SR8641", p.id, f"{round(c0 * 1.5, 4)}", whose="theirs", cross="SC141")
    lv = pm.points(session)
    sc141 = next(x for x in lv if x["key"] == "SC141")
    assert sc141["maker"] == "SynGamma" and sc141["cost"] > 0
    gamma = pm.model(session, part("SC142"), None, owner=True)
    assert gamma["correction"]["n"] == 1 and gamma["correction"]["k"] != pytest.approx(2.0, rel=0.05)
    assert gamma["cost"]["levels"]["mid"]["total"] != pytest.approx(other["cost"]["levels"]["mid"]["total"], rel=0.05)
    # the differentiator: price gap = cost gap x margin gap, shown to the owner next to the parity
    gap = pm.cost_gap(session, lv, "digital_isolator")
    assert len(gap) == 1 and gap[0]["maker"] == "SynGamma" and gap[0]["ours"] == "SynRef"
    g = gap[0]
    assert g["price"] == pytest.approx(g["cost"] * g["margin_ratio"])
    page = client.get(f"/pricing/{p.id}/model").text
    assert "<b>SynRef vs SynGamma</b>" in page and "cost ours ≈" in page and "Price gap = cost gap × margin gap" in page
    # guests and every non-owner model: the bottom-up cost, untouched
    assert pm.model(session, p, pq)["cost"]["levels"]["mid"]["total"] == pytest.approx(c0)
    assert pm.model(session, p, pq)["correction"]["n"] == 0


def test_guests_never_get_the_cost_correction(owner, make_guest, session, part):
    p, pq = _setup(owner, session, part)
    html = owner.get(f"/pricing/{p.id}/model").text
    c0 = float(re.search(r'name="unit_cost" value="([^"]*)"', html).group(1))
    owner.post("/pricing/level", data={"mpn": "SR8641", "family": "digital_isolator", "volume": "100000",
                                       "price": f"{c0 * 5:.4f}", "whose": "ours", "unit_cost": f"{c0}",
                                       "maker": "SynRef"})  # fmt: skip
    assert "cost raised" in owner.get(f"/pricing/{p.id}/model").text
    guest, _ = make_guest()
    g = guest.get(f"/pricing/{p.id}/model").text
    assert "cost raised" not in g and "vs SynGamma" not in g and 'name="unit_cost"' not in g
