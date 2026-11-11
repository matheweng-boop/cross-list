"""Car radio deep dive (weekly deep dive, 11 Nov 2026): Automotive > Car radio has its Systems library topic in the
full format (customer, competitors, market), it names catalogue parts only, renders with its research notes and links
to the radio-tuner-next case and the broadcast pages."""

from app.services import blocks, library
from app.services import systems as sy


def test_car_radio_topic_sits_in_its_sub_system():
    assert sy.topic_place("car_radio") == ("automotive", "car-radio")
    assert "car_radio" in sy.sub("automotive", "car-radio")["topics"]


def test_car_radio_topic_has_the_full_format():
    t = library.topic("car_radio")
    refs = set(library.refs_by_id(t))
    assert len(t["design_rules"]) >= 12 and len(t["trends"]) >= 5 and t["open_questions"]
    assert all(r.get("retrieved") for r in t["references"])
    assert t["why_customer"] and t["competitors"] and t["market"]
    for m in t["market"]:
        assert set(m.get("refs") or []) <= refs, m
        assert m.get("refs") or "est" in m["text"], m
    catalogue = {r["mpn"] for r in blocks.catalog_rows()}
    named = [p for s in t["skyworks_fit"] for p in s["parts"]]
    assert named and set(named) <= catalogue, set(named) - catalogue
    assert "data centre" not in str(t)


def test_car_radio_topic_page_renders_and_links(client):
    html = client.get("/library/car_radio").text
    for anchor in ('id="customer"', 'id="competitors"', 'id="market"', 'id="rules"', 'id="ours"',
                   "Full research notes", 'href="/broadcast"', "EN 303 345-3"):  # fmt: skip
        assert anchor in html, anchor
    assert client.get("/blocks/new?library=car_radio").status_code == 200
    assert "/library/car_radio" in client.get("/business/reports/radio-tuner-next").text
    assert 'href="/library/car_radio"' in client.get("/library").text
