"""Off-schedule update 22 Oct 2026 (c): tuner TAM sorted by scope; the total radio market sets the size."""

from app.services import tam


def test_tuner_figures_labelled_by_scope():
    cov = {e["key"]: e["coverage"] for e in tam.researched() if e["fn"] == "am_fm_tuner"}
    assert cov == {"tuner-ic-mrfr": "full", "tuner-ic-datahorizzon": "full",
                   "digital-radio-tuner-marketintelo": "part", "tuner-ic-emergen": "not_stated"}
    for e in tam.researched():
        if e["coverage"]:
            assert e["coverage"] in ("full", "part", "not_stated") and e["coverage_note"], e["key"]


def test_total_radio_market_is_the_range_of_full_coverage_figures(session):
    t = tam.by_function(session)["am_fm_tuner"]
    assert (t["low"], t["high"], t["n"]) == (890000000, 2310000000, 2)  # digital-only and unchecked figures left out
    assert t["usd"] == (890000000 + 2310000000) / 2


def test_tam_page_shows_coverage(client):
    page = client.get("/business/tam").text
    assert "covers the whole market" in page and "covers less than the whole market" in page
    assert "Total radio market" in page
