"""The single price at 1M a year everywhere it fits (owner, 9 Nov 2026: "1M price should appear everywhere possible"):
the part page's cross results, Cross a list, State of the art, the solution builder, the radio market and the Excel
downloads. Synthetic parts and invented prices; the Excel downloads use public data only, never the owner's levels."""

import io

import pytest
from openpyxl import load_workbook

from app.services import export
from app.services import price_model as pm
from tests.conftest import ids


def test_singles_only_for_parts_with_a_model(session, part):
    s = pm.Singles(session)
    one = s(part("SR8641"))  # digital isolator: a cost-only band without a curve
    assert one and one["price"] >= one["floor"] > 0 and not one["by_level"]
    assert s(part("SR8501")) is None  # current sensor: no cost model, so nothing rather than a guess
    assert s(None) is None
    assert pm.single_text(one, short=True).startswith("≈ $") and pm.single_text(one, short=True).endswith("at 1M")
    assert "floor $" in pm.single_text(one) and pm.single_text(None) == ""
    assert s(part("SR8641")) == one  # cached, same value


def test_part_page_and_cross_list_show_it(client, part):
    pid = ids(client, "SR8641")
    page = client.get(f"/parts/{pid}").text
    assert page.count('class="p1m"') >= 2  # several candidates
    cx = client.post("/cross-list", data={"parts": "SC141\nSR8501"}).text
    assert 'p1m"' in cx and "at 1M" in cx


def test_builder_part_and_system_at_1m(client):
    data = {"mpn": ["SR8641", "SC141"], "qty": ["2", "1"], "family": ["digital_isolator", "digital_isolator"],
            "breaks": ["1000 1.25\n2500 1.05", "1000 0.95\n2500 0.85"], "cur": ["USD", "USD"],
            "do": "price"}  # fmt: skip
    html = client.post("/pricing/builder", data=data).text
    assert html.count('class="p1m"') >= 2 and "System at 1M a year" in html


def test_radio_market_rows_carry_it(session):
    from app.services import radio_market as rm

    r = rm.price(session, "SI47962A0GE1AMR", "tuner", 100000)  # the owner's public DigiKey table (list_prices.yaml)
    assert r["ok"] and r["single"]["price"] > 0
    assert "Not Enough Data" not in pm.single_text(r["single"])


def test_excel_downloads_have_the_public_1m_price_only(client, session, part):
    pid = ids(client, "SR8641")
    ws = load_workbook(io.BytesIO(client.get(f"/parts/{pid}/replacements.xlsx").content)).active
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    head = next(r for r in rows if r and export.P1M_NOTE in r)
    col = head.index(export.P1M_NOTE)
    vals = [r[col] for r in rows[rows.index(head) + 1:] if len(r) > col and r[col] not in (None, "")]
    assert vals and all(isinstance(v, float) and v > 0 for v in vals)
    # an owner level does not reach the download
    before = sorted(vals)
    client.post("/pricing/level", data={"mpn": "SC141", "family": "digital_isolator", "volume": "1000000",
                                        "price": "9.999", "whose": "ours"})  # fmt: skip
    ws = load_workbook(io.BytesIO(client.get(f"/parts/{pid}/replacements.xlsx").content)).active
    rows = [[c.value for c in r] for r in ws.iter_rows()]
    after = sorted(r[col] for r in rows[rows.index(head) + 1:] if len(r) > col and r[col] not in (None, ""))
    assert after == before and 9.999 not in after
    # Cross a list: three columns before the owner's comment column
    r = client.post("/cross-list.xlsx", data={"parts": "SC141"})
    ws = load_workbook(io.BytesIO(r.content))["Cross list"]
    head = [c.value for c in ws[1]]
    assert head[-4:-1] == export.CROSS_LIST_1M and head[-1] == "Your comment"
    row = [c.value for c in ws[2]]
    assert isinstance(row[-4], float) and row[-4] > 0  # SC141 itself


@pytest.mark.parametrize("path", ["/state-of-the-art"])
def test_state_of_the_art_opens(client, path):
    assert client.get(path).status_code == 200
