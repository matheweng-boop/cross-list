"""Owner, 24-25 Oct 2026: "Many parts you suggest here are not automotive qualified ... don't remove the parts that are
not automotive but simply mark that they are not automotive and make the selection filterable", and "at the top of
each application-specific page a table for Skyworks and Qorvo parts". One AEC-Q test (autograde.is_aec) marks every
part chip on Cross-sell › By system and the portfolio synergy cards; the "Automotive-qualified only" filter (?aec=1)
is on by default for Automotive and says how many parts it hides. (The Technology overview's Automotive focus page
was removed on 25 Oct 2026; the Automotive report covers it.)"""

import re
from urllib.parse import unquote

from app.services import autograde
from app.services import systems as sy

URL = "/blocks/cross-sell"
CHIP = re.compile(
    r'<a class="badge ln-(skyworks|qorvo) aec-chip" href="/parts\?q=([^"]+)">[^<]+ '
    r'<small class="aec-mark (aec-yes|aec-no)"'
)


def _section(html: str, start: str, end: str) -> str:
    return html[html.index(start) : html.index(end, html.index(start))]


def test_one_aec_test_for_every_part_form():
    assert autograde.is_aec({"mpn": "X1", "values": {"qualification": "automotive"}})
    assert not autograde.is_aec({"mpn": "SI8641BD-AM", "values": {"qualification": "industrial"}})  # stated wins
    assert autograde.is_aec({"mpn": "X2", "implies": {"qualification": "automotive"}})  # parts_for's form
    assert autograde.is_aec({"mpn": "X3", "description": "LNA, AEC-Q101 qualified"})
    assert autograde.is_aec("SKY5A2105") and autograde.is_aec("QPF5100Q")  # a bare part number: from the catalogue
    assert not autograde.is_aec("QM35825") and not autograde.is_aec("UNKNOWN-1")  # not stated -> not automotive
    shown, hidden = autograde.marked(["SKY5A2105", "QM35825"], aec_only=True)
    assert [p["mpn"] for p in shown] == ["SKY5A2105"] and hidden == 1 and shown[0]["aec"] is True
    shown, hidden = autograde.marked(["SKY5A2105", "QM35825"])
    assert [p["aec"] for p in shown] == [True, False] and hidden == 0


def test_every_chip_on_by_system_is_marked_and_the_mark_matches_the_test(client):
    html = client.get(f"{URL}?system=automotive&sub=car-access&aec=0").text
    chips = CHIP.findall(html)
    assert len(chips) >= 4 and {m for _, _, m in chips} == {"aec-yes", "aec-no"}
    for _, mpn, mark in chips:
        assert (mark == "aec-yes") == autograde.is_aec(unquote(mpn)), mpn
    assert ">AEC-Q</small>" in html and ">not automotive</small>" in html
    # every chip carries one of the two marks: no part chip without a text label
    assert html.count('aec-chip"') == len(chips)


def test_filter_is_on_by_default_for_automotive_and_kept_in_the_url(client):
    auto = client.get(f"{URL}?system=automotive").text
    assert 'aria-pressed="true"' in _section(auto, 'class="chip-row aec-filter"', "</div>")
    assert 'href="/blocks/cross-sell?co=combined&amp;system=automotive&amp;aec=0"' in auto  # the toggle turns it off
    assert "aec-no" not in _section(auto, 'id="parts-here"', "</section>")  # only AEC-Q chips in the table
    assert "aec-no" not in _section(auto, 'id="together"', "</section>")
    off = client.get(f"{URL}?system=automotive&aec=0").text
    assert 'aria-pressed="false"' in _section(off, 'class="chip-row aec-filter"', "</div>")
    assert "aec-no" in _section(off, 'id="parts-here"', "</section>")
    dc = client.get(f"{URL}?system=datacenter").text
    assert 'aria-pressed="false"' in _section(dc, 'class="chip-row aec-filter"', "</div>")
    assert 'href="/blocks/cross-sell?co=combined&amp;system=datacenter&amp;aec=1"' in dc
    on = client.get(f"{URL}?system=datacenter&aec=1").text
    assert 'aria-pressed="true"' in _section(on, 'class="chip-row aec-filter"', "</div>")
    assert '<input type="hidden" name="aec" value="1">' in on  # the picker keeps the choice
    assert 'href="/portfolio?system=datacenter&amp;aec=1"' in on  # and so do the Cross-sell tabs


def test_filtered_out_parts_are_counted_not_dropped_silently(client):
    off = client.get(f"{URL}?system=datacenter&aec=0").text
    on = client.get(f"{URL}?system=datacenter&aec=1").text
    n_no = _section(off, 'id="parts-here"', "</section>").count("aec-no")
    assert n_no > 0
    m = re.search(r"(\d+) non-automotive parts? hidden", _section(on, 'id="parts-here"', "</section>"))
    assert m and int(m.group(1)) == n_no
    assert "non-automotive part" not in _section(off, 'id="parts-here"', "</section>")


def test_skyworks_and_qorvo_parts_table_tops_the_selection(client):
    html = client.get(f"{URL}?system=automotive&sub=powertrain&aec=0").text
    table = _section(html, 'id="parts-here"', "</section>")
    assert html.index('id="parts-here"') < html.index("Our parts that go together") < html.index('id="together"')
    assert "Skyworks and Qorvo parts here" in table
    head = _section(table, "<thead>", "</thead>")
    assert re.search(r"Skyworks <small[^>]*>· \d+ parts? in \d+ functions?", head)
    assert re.search(r"Qorvo <small[^>]*>· \d+ parts? in \d+ functions?", head)
    groups = re.findall(r'<th scope="rowgroup" colspan="2">([^<]+)<', table)
    assert len(groups) == len(set(groups)) >= 3  # one group per function
    # synergy pairs: a small link from the table to the card below, and the card has that anchor
    links = re.findall(r'href="#pair-(\d+)"', table)
    assert links and all(f'id="pair-{j}"' in _section(html, 'id="together"', "</section>") for j in links)
    # no duplication: the parts are listed in the table, not again in "Our parts that go together"
    ours = _section(html, "Our parts that go together", "</table>")
    assert "aec-chip" not in ours and "Our parts</th>" not in ours


def test_table_on_a_single_line_and_on_one_diagram(client):
    # one company (owner, 25 Oct 2026): an old ?co=skyworks link shows both lines
    html = client.get(f"{URL}?co=skyworks&system=automotive&sub=car-radio").text
    table = _section(html, 'id="parts-here"', "</section>")
    assert "Skyworks" in table and "Qorvo" in table
    i = sy.sub("automotive", "car-radio")["idx"][0]
    one = client.get(f"{URL}?system=automotive&sub=car-radio&template={i}").text
    assert 'id="parts-here"' in one
    assert f"template={i}&amp;aec=0" in _section(one, 'class="chip-row aec-filter"', "</div>")


def test_portfolio_synergy_cards_are_marked_and_filterable(client):
    html = client.get("/portfolio").text
    cards = _section(html, '<div class="pf-syn">', "</div>\n</div>")
    assert "aec-chip" in cards and "aec-no" in cards and "AEC-Q</small>" in cards
    assert 'aria-pressed="false"' in html and 'href="/portfolio?aec=1#synergies"' in html
    auto = client.get("/portfolio?system=automotive").text
    assert 'aria-pressed="true"' in auto and 'href="/portfolio?system=automotive&amp;aec=0#synergies"' in auto
    cards = _section(auto, '<div class="pf-syn">', "</div>\n</div>")
    assert "aec-no" not in cards and "aec-yes" in cards

