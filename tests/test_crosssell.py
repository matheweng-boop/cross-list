"""Cross-sell from a part number, optionally narrowed by loosely described application words."""

import re
from collections import Counter
from urllib.parse import unquote

from app.services import autograde, blocks
from app.services import crosssell as cs
from app.services import opportunity as op
from app.services import portfolio as pf
from app.services import systems as sy
from app.web import nav


def test_application_words_are_loose():
    apps = op.applications()
    for q, want in [("dcdc", "dc/dc"), ("DC-DC", "dc/dc"), ("broadcst", "radio"), ("ev chargr", "charger")]:
        hits = cs.match_applications(apps, q)
        assert hits, q
        assert any(want in a.name.lower() for a, _, _ in hits[:15]), q
    assert cs.match_applications(apps, "zzqqxx") == []


def test_part_number_resolves_to_function(session):
    p = cs.resolve_part(session, "SKY87604")
    assert p and p["fns"][0] == "load_switch" and p["ours"]
    assert cs.resolve_part(session, "zz") is None


def test_suggestions_ordered_with_reasons(session):
    p = cs.resolve_part(session, "SKY87604")
    r = cs.suggest(session, p, "dcdc")
    assert 0 < r["n"] <= r["n_with_part"]
    scores = [e["score"] for e in r["ours"]]
    assert scores == sorted(scores, reverse=True)
    top = r["ours"][0]
    assert top["fn"] != "load_switch" and top["why"]["n"] and top["offer"]


def test_page(client):
    r = client.get("/business/attach?part=SKY87604&app=dcdc")
    assert r.status_code == 200 and "Offer with it" in r.text and "SKY87604" in r.text
    assert "No part number starting with" in client.get("/business/attach?part=zzzzzz").text


# ---- from tests/test_aec_crosssell_1025.py ---------------------------------------------------------------------------
# Owner, 24-25 Oct 2026: "Many parts you suggest here are not automotive qualified ... don't remove the parts that are
# not automotive but simply mark that they are not automotive and make the selection filterable", and "at the top of
# each application-specific page a table for Skyworks and Qorvo parts". One AEC-Q test (autograde.is_aec) marks every
# part chip on Cross-sell › By system and the portfolio synergy cards; the "Automotive-qualified only" filter (?aec=1)
# is on by default for Automotive and says how many parts it hides. (The Technology overview's Automotive focus page
# was removed on 25 Oct 2026; the Automotive report covers it.)

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


# ---- from tests/test_crosssell_portfolio_1025.py ---------------------------------------------------------------------
# Owner, 25 Oct 2026: the Skyworks + Qorvo portfolio moved from Products to Systems & applications › Cross-sell
# (third tab, URL kept); By system shows "Skyworks + Qorvo together here" for the picked system, each pair once; the
# automotive synergies per sub-system with a reason, real active parts and the design-effort mark; the selected system
# carries over between the Cross-sell tabs.

AUTO_SUBS = ("car-access", "car-radio", "telematics-v2x", "adas", "powertrain", "battery-power", "charging", "cockpit")


def _cards(html: str) -> list[tuple[str, str]]:
    """(Skyworks label, Qorvo label) of every synergy card on a page."""
    return re.findall(r'<span class="ln-skyworks"><b>([^<]+)</b>.*?<span class="ln-qorvo"><b>([^<]+)</b>', html)


def test_portfolio_moved_from_products_to_cross_sell():
    products = next(s for s in nav.NAV if s[0] == "products")
    assert all(href != "/portfolio" for _, href, _ in products[2])
    systems = next(s for s in nav.NAV if s[0] == "systems")
    desc = next(d for label, href, d in systems[2] if href == "/blocks/cross-sell")
    assert "portfolio" in desc
    tabs = next(g for g in nav.TABS if g[0][1] == "/blocks/cross-sell")
    assert [label for label, _ in tabs] == ["By system", "By part", "Skyworks + Qorvo portfolio"]
    st = nav.state("/portfolio")
    assert (st["section"], st["item"], st["active_tab"]) == ("systems", "/blocks/cross-sell", "/portfolio")
    assert st["crumbs"] == [("Systems & applications", "/library"), ("Cross-sell", "/blocks/cross-sell")]
    assert nav.page_label("/portfolio") == "Skyworks + Qorvo portfolio"


def test_portfolio_page_keeps_every_section_and_shows_the_tab_row(client):
    html = client.get("/portfolio").text
    for anchor in (
        "categories",
        "rf",
        "synergies",
        "competence",
        "pick",
        "overlap",
        "competitors",
        "crosssell",
        "tech",
    ):
        assert f'id="{anchor}"' in html
    assert "Further design effort required" in html and "pf-syn-card" in html
    tabs = _section(html, 'class="page-tabs"', "</nav>")
    assert 'href="/portfolio" aria-current="page"' in tabs and 'href="/blocks/cross-sell"' in tabs
    # each synergy card names the systems where the pair applies, with a link to By system
    assert 'class="pf-syn-places">Systems: <a href="/blocks/cross-sell?system=' in html
    assert len(_cards(html)) == len(set(_cards(html))) == len(pf.synergies())


def test_tab_links_keep_the_selected_system(client):
    html = client.get("/blocks/cross-sell?system=automotive&sub=car-radio").text
    tabs = _section(html, 'class="page-tabs"', "</nav>")
    assert 'href="/business/attach?system=automotive&amp;sub=car-radio"' in tabs
    assert 'href="/portfolio?system=automotive&amp;sub=car-radio"' in tabs
    back = _section(client.get("/portfolio?system=automotive").text, 'class="page-tabs"', "</nav>")
    assert 'href="/blocks/cross-sell?system=automotive"' in back
    assert nav.tab_href(None, "/blocks", {"system": "x"}) == "/blocks"
    picker = _section(client.get("/blocks/cross-sell?sel=automotive:car-radio").text, 'class="page-tabs"', "</nav>")
    assert (
        'href="/portfolio?system=automotive&amp;sub=car-radio"' in picker
    )  # the picker's form carries over too  # groups without carry keep plain links


def test_portfolio_marks_the_pairs_of_the_system_it_came_from(client):
    html = client.get("/portfolio?system=automotive").text
    assert "From Cross-sell › By system, <b>Automotive</b>" in html
    here = {
        (x["skyworks"], x["qorvo"]) for x in pf.synergies() if set(sy.selection("automotive")["idx"]) & set(x["idx"])
    }
    assert html.count("pf-syn-card small pf-here") == len(here) > 0


def test_automotive_and_its_sub_systems_show_pairs(client):
    with_pairs = [k for k in AUTO_SUBS if pf.together_in(sy.sub("automotive", k)["idx"])["synergies"]]
    assert len(with_pairs) >= 5, with_pairs
    html = client.get("/blocks/cross-sell?system=automotive").text
    assert "Skyworks + Qorvo together here" in html
    block = _section(html, 'id="together"', "</section>")
    assert len(_cards(block)) >= 5


def test_every_part_named_in_a_pair_exists_and_is_active():
    cp = blocks.catalog_parts()
    for k in AUTO_SUBS:
        for x in pf.together_in(sy.sub("automotive", k)["idx"])["synergies"]:
            for side, fn in (("skyworks", x["skyworks"]), ("qorvo", x["qorvo"])):
                assert x[f"{side}_parts"], (k, fn)
                for p in x[f"{side}_parts"]:
                    rows = [r for r in cp[fn] if r["mpn"] == p["mpn"]]
                    assert rows and not rows[0]["risk"] and rows[0]["manufacturer"].lower() == side
                # automotive grade first: no non-automotive part before an automotive one
                q = [p["values"]["qualification"] == "automotive" for p in x[f"{side}_parts"]]
                assert q == sorted(q, reverse=True)
            for m in x["marks"]:
                assert m["mpn"] in {r["mpn"] for r in cp[m["fn"]] if not r["risk"]}


def test_curated_reasons_cover_the_automotive_pairs_and_name_real_diagrams():
    notes = pf.synergy_notes()
    names = " ".join(t.get("name", "") for t in blocks.templates())
    for k in AUTO_SUBS:
        for x in pf.together_in(sy.sub("automotive", k)["idx"])["synergies"]:
            assert x["reason"], (k, x["skyworks"], x["qorvo"])
    for key, n in notes.items():
        assert n["reason"] and n["source"].startswith("Library diagram")
        first = n["source"].split(": ", 1)[1].split(" (")[0].split(";")[0].split(", ")[0].strip()
        assert first[:25] in names, (key, first)


def test_a_pair_is_rendered_once_and_counts_match(client):
    for k in ("car-radio", "telematics-v2x", "battery-power"):
        html = client.get(f"/blocks/cross-sell?system=automotive&sub={k}").text
        cards = _cards(html)
        assert cards and len(cards) == len(set(cards))
        n_apps = int(re.search(r"<h2>[^<]+<small class=\"muted\">· (\d+) diagram", html).group(1))
        # the Bundles table no longer lists a Skyworks + Qorvo pair shown in the block
        table = (
            _section(html, "<h3>Bundles", "</table>")
            if "xs-table" in _section(html, "<h3>Bundles", "</section>")
            else ""
        )
        for s, q in cards:
            assert not re.search(rf"<td>{re.escape(s)}</td><td>{re.escape(q)}", table)
            assert not re.search(rf"<td>{re.escape(q)}</td><td>{re.escape(s)}", table)
        # the count on each card is "of N diagrams here", N = the diagrams of the selection in the heading
        assert all(int(m) == n_apps for m in re.findall(r"together in \d+ of (\d+) diagrams? here", html))
        tog = pf.together_in(sy.sub("automotive", k)["idx"])
        assert f"in {tog['n_both']} of {n_apps} diagram" in html


def test_no_together_block_when_nothing_matches(client):
    html = client.get("/blocks/cross-sell?system=automotive&sub=cockpit").text
    assert not pf.together_in(sy.sub("automotive", "cockpit")["idx"])["synergies"]
    assert 'id="together"' not in html and "Skyworks + Qorvo together here" not in html
    one_line = client.get("/blocks/cross-sell?co=skyworks&system=automotive&sub=car-radio").text
    assert 'id="together"' in one_line  # one company now: an old ?co=skyworks link shows the combined view


def test_by_part_links_a_function_to_its_systems(client):
    html = client.get("/business/attach?fn=am_fm_tuner").text
    assert 'href="/blocks/cross-sell?system=automotive&amp;sub=car-radio"' in html
    places = sy.places_of_function("am_fm_tuner")
    assert places and places[0]["n"] >= places[-1]["n"]


def test_synergy_pairs_stay_one_per_function_pair():
    syn = pf.synergies(limit=8, min_diagrams=1, within=frozenset(sy.selection("automotive")["idx"]))
    assert Counter((x["skyworks"], x["qorvo"]) for x in syn).most_common(1)[0][1] == 1


def test_bundle_table_count_matches_the_diagrams_where_both_lines_supply_blocks(client):
    html = client.get("/portfolio").text
    total = len(pf.bundles(limit=10_000))
    shown = len(pf.bundles())
    assert f"The {shown} most complementary of {total} block diagrams where both lines supply blocks" in html
    auto = sy.selection("automotive")["idx"]
    assert pf.together_in(auto)["n_both"] == sum(1 for b in pf.bundles(limit=10_000) if b["i"] in set(auto))
