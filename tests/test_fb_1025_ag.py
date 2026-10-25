"""Owner's site comments of 25 Oct 2026 (worker AG): block-diagram indicator and one-click links in the libraries,
a shorter key-applications table on the eFuse bigger picture, and what Euro NCAP is."""

import html as h

from app.services import key_apps, opportunity
from app.services import systems as sy


def _card(page: str, system: str, sub: str) -> str:
    return page.split(f'id="card-{system}-{sub}"')[1].split("</article>")[0]


def _with_and_without():
    subs = [(s["key"], x) for s in sy.systems() for x in s["subsystems"]]
    has = next((k, x) for k, x in subs if x["idx"])
    none = next(((k, x) for k, x in subs if not x["idx"]), None)
    return has, none


def test_application_library_shows_diagram_indicator_and_one_click_links(client):
    page = client.get("/blocks").text
    (sk, x), missing = _with_and_without()
    card = _card(page, sk, x["key"])
    assert f"Block diagram ✓ ({len(x['idx'])})" in card
    assert f'href="/blocks/new?template={x["idx"][0]}"' in card  # one click opens the diagram
    if missing:
        assert "No diagram yet" in _card(page, missing[0], missing[1]["key"])
    assert 'id="diagrams"' in page and "block diagrams</b>" in page.split('id="area-')[0]  # summary near the top
    one = client.get(f"/blocks?system={sk}&sub={x['key']}").text
    assert f'id="diagrams-{sk}"' in one and "Block diagrams in" in one


def test_new_systems_have_indicators_in_both_libraries(client):
    blocks_page, library_page = client.get("/blocks").text, client.get("/library").text
    for key in ("industrial", "aerospace", "consumer", "home", "medical"):
        s = sy.get(key)
        assert s, key
        for x in s["subsystems"]:
            for page in (blocks_page, library_page):
                card = _card(page, key, x["key"])
                assert ("Block diagram ✓" in card) == bool(x["idx"]) and ("No diagram yet" in card) != bool(x["idx"])
                if x["idx"]:
                    assert f'href="/blocks/new?template={x["idx"][0]}"' in card


def test_efuse_key_applications_table_has_short_cells_and_a_more_line(client):
    d = key_apps.for_function("efuse_hotswap")
    for a in d["applications"]:
        assert a["where"] and len(a["where"]) <= 50 and len(a["v"]) <= 20 and len(a["a"]) <= 20, a["key"]
    page = h.unescape(client.get("/business/evidence/efuse_hotswap").text)
    table = page.split('class="small ka-table"')[1].split("</table>")[0]
    assert table.count('class="ka-more"') == len(d["applications"]) and "More: uses, full ranges" in table
    assert 'data-label="Voltage"' in table and "12 V · 48 V" in table


def test_euro_ncap_is_explained_where_it_is_first_mentioned(client):
    t = opportunity.explanations()["terms"]["euro_ncap"]
    assert "European New Car Assessment Programme" in t["short"] and "euroncap.com" in t["href"]
    page = h.unescape(client.get("/business/reports/auto-uwb-cpd").text)
    box = page.index("What is Euro NCAP?")
    assert page.index("Euro NCAP") < box < page.index('class="rpt"')
    assert 'href="https://www.euroncap.com/"' in page and 'href="/business/method#t-euro_ncap"' in page
    method = client.get("/business/method").text
    assert 'id="t-euro_ncap"' in method and "Source: euroncap.com" in method
