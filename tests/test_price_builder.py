"""Solution price builder: parts priced from their own prices or a sibling's, the system total, presets, no storage."""

from starlette.datastructures import ImmutableMultiDict

from app.services import price_builder as pb

EUR = "1 25,10\n10 22,37\n100 19,80"  # made-up test numbers
FIELDS = ("qty", "breaks", "cur", "anchor", "plo", "phi", "fam", "pkg", "pins", "auto", "rel")


def _form(*rows, **glob):
    items = [(k, str(v)) for k, v in glob.items()]
    for r in rows:
        items += [("mpn", r["mpn"])] + [(k, str(r.get(k, ""))) for k in FIELDS]
    return items


def _post(*rows, **glob):
    data: dict[str, list[str]] = {}
    for k, v in _form(*rows, **glob):
        data.setdefault(k, []).append(v)
    return data


def test_site_data_fills_in_and_siblings_price_parts_without_prices(session):
    info = pb.site_info(session, "Si47961")
    assert info["family"] == "am_fm_tuner" and info["package"] == "QFN-56" and info["pins"] == 56 and info["automotive"]
    assert pb.site_info(session, "Si46922")["family"] == "radio_coprocessor"
    assert pb.sibling("Si47961") == "Si47962" and pb.sibling("Si47981") == "Si47972" and pb.sibling("Si46922") is None
    rows = pb.rows_from_form(ImmutableMultiDict(_form(
        {"mpn": "Si47961", "qty": 2, "plo": 80, "phi": 90},
        {"mpn": "Si46922", "breaks": EUR, "cur": "EUR"},
        {"mpn": "Si47981", "anchor": "Si47972", "plo": 55, "phi": 75},
        {"mpn": ""},  # an empty row is dropped
    )))
    assert [r.mpn for r in rows] == ["Si47961", "Si46922", "Si47981"] and rows[0].parity_lo == 0.8
    sol = pb.solution(session, rows, 1_000_000, 0.4, 1.0, 2028)
    first, cop, single = sol["parts"]
    assert first["anchor"]["mpn"] == "Si47962" and first["anchor"]["auto"] and cop["basis"] == "own prices (pasted)"
    assert single["anchor"] == {**single["anchor"], "mpn": "Si47972", "lo": 0.55, "hi": 0.75, "auto": False}
    fab, tot = sol["totals"][0]
    assert tot["n"] == 3
    expect = sum(p["row"].qty * p["scenarios"][0][1]["at"]["target"] for p in sol["parts"])
    assert abs(tot["target"] - expect) < 1e-9 and tot["low"] < tot["target"] < tot["high"]
    lower = pb.solution(session, rows, 1_000_000, 0.4, 0.8, 2028)["totals"][0][1]
    assert abs(lower["target"] - 0.8 * tot["target"]) < 1e-6  # the market-level slider moves every band


def test_missing_prices_and_unknown_family_are_explained(session):
    rows = [pb.Row(mpn="Si46922"), pb.Row(mpn="XYZ123")]
    a, b = pb.solution(session, rows, 100_000, 0.4, 1.0, 2028)["parts"]
    assert "paste DigiKey prices" in a["error"] and "pick a family" in b["error"]


def test_page_add_load_and_nothing_in_the_link(client):
    page = client.get("/pricing/builder").text
    assert 'method="post"' in page and 'id="pb-add"' in page and 'name="breaks"' in page and "Radio preset:" in page
    r = client.post("/pricing/builder", data=_post({"mpn": "Si47961"}, {"mpn": "Si46922", "breaks": EUR, "cur": "EUR"},
                                                   vol=1000000, gm=40, adj=100, sop=2028, do="price"))  # fmt: skip
    assert r.status_code == 200 and "System (2 of 2 parts priced)" in r.text and 'data-fab="in_house" hidden>' in r.text
    preset = "radio:AM/FM, dual tuner, no demod"
    r = client.post("/pricing/builder", data=_post({"mpn": "Si46922"}, load=preset, do="load"))
    assert r.text.count('name="mpn" list="pb-mpns" value="Si4') == 2  # the kept row and the preset's tuner
