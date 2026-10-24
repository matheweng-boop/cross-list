"""Owner feedback 23 Oct 2026, Products > Price estimate: the part data fills in by itself (package, pins, release
year), no "our part" price, two help texts gone, and "Not Enough Data" wherever a number cannot be computed."""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import price_builder as pb
from app.services.seed import load_file

ROOT = Path(__file__).resolve().parent.parent
FILES = ("ti_digital_isolators", "ti_gate_drivers_more", "skyworks_switches", "macom_switches", "skyworks_si86")


@pytest.fixture
def lists(session):
    for f in FILES:
        load_file(session, ROOT / "data" / "real" / f"{f}.yaml")
    session.commit()


def test_pins_from_package_text():
    assert pb.pins_from("QFN, 16L (4 x 4 x 1.5 mm)") == 16
    assert pb.pins_from("MCM, 28-pin (6 x 6 x 0.9 mm)") == 28
    assert pb.pins_from("QFN-56") == 56 and pb.pins_from("SOIC-16W") == 16
    assert pb.pins_from("Ceramic SMT 8x5x2.5") == 0 and pb.pins_from("") == 0


def test_release_year_rule():
    def p(rel=None, rev=None, ds=None):
        return SimpleNamespace(release_date=rel, datasheet_revision=rev, datasheet_date=ds)

    assert pb.released_year(p(date(2016, 3, 1), "E", date(2024, 1, 1))) == 2016  # release date = first issue
    assert pb.released_year(p(None, "206709A", date(2023, 5, 1))) == 2023  # Skyworks document, first letter
    assert pb.released_year(p(None, "1.0", date(2019, 5, 1))) == 2019
    assert pb.released_year(p(None, "206326B", date(2024, 5, 1))) is None  # a later revision: unknown
    assert pb.released_year(p(None, "V1", None)) is None


@pytest.mark.parametrize("mpn, family, package, pins", [
    ("SKY12212-478LF", "rf_switch", "QFN-16 4x4", 16),  # Skyworks switch: cross list + catalogue
    ("SKY13453-385LF", "rf_switch", "QFN-6 1x1", 6),
    ("ISO7741DWR", "digital_isolator", "SOIC-16 (DW)", 16),  # TI isolator, full ordering code
    ("UCC21520", "gate_driver", "SOIC-16 (DW)", 16),  # TI gate driver, base number: its variants agree
    ("Si8641BD-B-IS", "digital_isolator", "SOIC-16W", 16),  # Buy-Now code with die revision
    ("MSW2030-203", "rf_switch", "Ceramic SMT 8x5x2.5", 0),  # MACOM: pins not published
])  # fmt: skip
def test_site_info_fills_package_and_pins(session, lists, mpn, family, package, pins):
    info = pb.site_info(session, mpn)
    assert (info["family"], info["package"], info["pins"]) == (family, package, pins)
    assert info["found"]


def test_site_info_release_year_and_radio_parts(session, lists):
    assert pb.site_info(session, "ISO7741DWR")["released"] == 2016  # first datasheet issue in the cross list
    assert pb.site_info(session, "ISO7741")["released"] == 2016  # base number: earliest of its variants
    radio = pb.site_info(session, "Si47962")
    assert (radio["package"], radio["pins"], radio["family"]) == ("QFN-56", 56, "am_fm_tuner")
    assert pb.site_info(session, "SKY65313-21")["pins"] == 28  # catalogue only: pins read from "28-pin"


def test_estimate_page_texts_and_no_our_part(client, lists):
    html = client.get("/pricing/estimate", params={"name": "UCC21520"}).text
    assert 'name="package" value="SOIC-16 (DW)"' in html
    assert 'name="pins" type="number" min="1" max="2000" value="16"' in html
    assert 'name="released" type="number" min="1980" max="2050" value="2016"' in html
    assert "a known part number sets package and channels" not in html
    assert "(assumed; the datasheet" not in html
    assert 'name="ours"' not in html and 'name="parity_lo"' not in html and "Our part priced" not in html
    blank = client.get("/pricing/estimate").text
    assert "a known part number sets package and channels" not in blank and "(assumed; the datasheet" not in blank


def test_not_enough_data_instead_of_blanks(client, session, lists):
    est = client.get("/pricing/estimate", params={"breaks": "1000 1.20"}).text  # no family
    assert "Not Enough Data" in est
    b = client.post("/pricing/builder", data={"mpn": "NO-SUCH-PART-9", "qty": "1", "do": "price"}).text
    assert b.count("Not Enough Data") >= 8  # the part's 4 prices and the 4 system totals
    assert "—" not in b.split('id="pb-result"')[1] and "nan" not in b.split('id="pb-result"')[1].lower()
    from tests.test_pipeline import ids

    panel = client.get(f"/pricing/{ids(client, 'SI86S641EC-IS1')}/model").text  # no prices cached
    assert panel.count("Not Enough Data") >= 1 + 3 * 3  # the note and low / target / high at 3 volumes


def test_picking_a_part_fills_the_form(client, lists):
    """Owner, 23 Oct 2026 (iPad): picking a part fills family, package and pins at once and locks them; overriding
    them is the second option."""
    d = client.get("/pricing/part-info", params={"name": "Si47962"}).json()
    assert (d["family"], d["package"], d["pins"]) == ("am_fm_tuner", "QFN-56", 56) and d["found"]
    assert client.get("/pricing/part-info", params={"name": ""}).json()["found"] == []
    html = client.get("/pricing/estimate", params={"name": "Si47962", "family": "digital_isolator"}).text
    assert '<option value="am_fm_tuner" selected' in html  # the part's data wins over a stale family
    assert 'value="QFN-56" placeholder="e.g. QFN-48, SOIC-16W, LGA" readonly class="pe-locked"' in html
    assert ">Override</button>" in html and 'fetch("/pricing/part-info?name="' in html
    own = client.get("/pricing/estimate", params={"name": "Si47962", "family": "digital_isolator", "package": "SOIC-8",
                                                  "pins": "8", "override": "true"}).text  # fmt: skip
    assert '<option value="digital_isolator" selected' in own and 'value="SOIC-8" placeholder' in own
    assert 'name="override" value="true"' in own and "pe-locked" not in own.split("Price breaks")[0]
    free = client.get("/pricing/estimate", params={"name": "XYZ123", "released": "2015"}).text
    assert 'name="released" type="number" min="1980" max="2050" value="2015"' in free


def test_blank_number_fields_are_no_error(client):
    """A blank pins / SOP / released / margin field, as the browser sends it, gives the page, not a 422."""
    r = client.get("/pricing/estimate", params={"name": "XYZ", "family": "digital_isolator", "pins": "", "sop": "",
                                                "gm": "", "released": "", "override": ""})  # fmt: skip
    assert r.status_code == 200 and 'name="pins" type="number" min="1" max="2000" value=""' in r.text
