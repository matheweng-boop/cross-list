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
    """By part was retired (owner, 2 Nov 2026); an old part link lands in the part box of By system."""
    r = client.get("/business/attach?part=SKY87604&app=dcdc")
    assert r.status_code == 200 and str(r.url).endswith("/blocks/cross-sell?part=SKY87604")
    assert "SKY87604" in r.text and 'class="xs-sys-list"' in r.text and "Offer with it" not in r.text
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
    groups = re.findall(r'<th scope="row">([^<]+)<', table)
    assert len(groups) == len(set(groups)) >= 3  # one row per function
    # synergy pairs: a small link from the table to the card below, and the card has that anchor
    links = re.findall(r'href="#pair-(\d+)"', table)
    assert links and all(f'id="pair-{j}"' in _section(html, 'id="together"', "</section>") for j in links)
    # no duplication: the parts are listed in the table, not again in "Our parts that go together"
    ours = _section(html, "Our parts that go together", "</table>")
    assert "aec-chip" not in ours and "Our parts</th>" not in ours


# ---- compact parts table and system chooser (owner, 2 Nov 2026) ------------------------------------------------------
# "After picking a system, the table uses two rows per function: with 30-40 functions a very long page." One compact row
# per function (Function | Skyworks | Qorvo | Used in), at most three chips per cell and the rest under "+N more" (a
# <details>, no script), the synergy markers kept in the row; one line only: three columns. The "Pick a system" chooser
# is a grid of system buttons; the sub-systems appear as chips once a system is picked.

ROW = re.compile(r'<tr id="fn-([a-z0-9_]+)" class="xs-row([^"]*)">(.*?)</tr>', re.S)


def _cells(row: str) -> list[str]:
    return re.findall(r'<td class="ln-(?:skyworks|qorvo)" data-label="[^"]+">(.*?)</td>', row, re.S)


def test_compact_table_one_row_per_function_three_chips_then_more(client):
    html = client.get(f"{URL}?system=cellular&aec=0").text
    table = _section(html, 'id="parts-here"', "</section>")
    head = _section(table, "<thead>", "</thead>")
    assert re.findall(r"<th scope=\"col\"[^>]*>(Function|Skyworks|Qorvo|Used in)\b", head) == [
        "Function", "Skyworks", "Qorvo", "Used in"]  # fmt: skip
    rows = ROW.findall(table)
    n_all = len(sy.selection("cellular")["idx"])
    assert len(rows) >= 20 and table.count("<tr id=") == len(rows) and "rowgroup" not in table
    folded = 0
    for fn, _cls, row in rows:
        assert row.count('<th scope="row">') == 1, fn
        used = re.search(r'<td class="xs-used">(\d+) of (\d+) diagrams?</td>', row)
        assert used and int(used.group(2)) == n_all and 1 <= int(used.group(1)) <= n_all, fn
        for cell in _cells(row):
            before, _, more = cell.partition('<details class="xs-more">')
            assert before.count('aec-chip"') <= 3, fn
            if more:  # "+N more": the chips folded away plus the series not listed
                folded += 1
                n = int(re.search(r"<summary>\+(\d+) more</summary>", more).group(1))
                rest = re.search(r"and (\d+) more in Browse products", more)
                assert n == more.count('aec-chip"') + (int(rest.group(1)) if rest else 0) > 0, fn
                assert before.count('aec-chip"') == 3, fn
    assert folded >= 5
    # the rows keep the order of "most used first"
    counts = [int(re.search(r'<td class="xs-used">(\d+) of', r).group(1)) for _, _, r in rows]
    assert counts == sorted(counts, reverse=True)


def test_compact_table_keeps_the_pair_markers_and_the_filter(client):
    html = client.get(f"{URL}?system=automotive&sub=powertrain&aec=0").text
    rows = ROW.findall(_section(html, 'id="parts-here"', "</section>"))
    marked = [(cls, row) for _, cls, row in rows if 'class="xs-pair small"' in row]
    assert marked
    for cls, row in marked:  # the marker sits in the row's own function cell, and the row says it is a synergy pair
        assert re.search(r'<th scope="row">[^<]+ <a class="xs-pair small" href="#pair-\d+"', row)
        assert cls == " xs-syn"
    on = client.get(f"{URL}?system=automotive&sub=powertrain").text  # the AEC-Q filter is on for Automotive
    table = _section(on, 'id="parts-here"', "</section>")
    assert "aec-no" not in table and "aec-yes" in table
    for _fn, _cls, row in ROW.findall(table):
        for cell in _cells(row):
            assert cell.partition("<details")[0].count('aec-chip"') <= 3


def test_compact_table_with_one_line_has_three_columns(client, session):
    mine = op.company("combined")[2]
    i = next(i for x in sy.systems() for s in x["subsystems"] for i in s["idx"]
             if len(sy.parts_table(session, sy.bottom_up(session, [i], mine)["ours"], mine)["lines"]) == 1)  # fmt: skip
    system, sub = sy.place_of(i)[0]
    html = client.get(f"{URL}?system={system}&sub={sub}&template={i}&aec=0").text
    table = _section(html, 'id="parts-here"', "</section>")
    head = _section(table, "<thead>", "</thead>")
    assert head.count('<th scope="col"') == 3 and "xs-one" in table
    line = re.findall(r'<th scope="col" class="ln-(skyworks|qorvo)">', head)
    assert len(line) == 1
    other = "qorvo" if line[0] == "skyworks" else "skyworks"
    assert f'class="ln-{other}"' not in table
    assert all(row.count("<td") == 2 for _, _, row in ROW.findall(table))  # one parts cell and "Used in"
    # the service keeps both lines when both have parts, and only the lines that have one
    t = sy.parts_table(session, sy.bottom_up(session, sy.selection("cellular")["idx"], mine)["ours"], mine)
    assert t["lines"] == ["Skyworks", "Qorvo"]
    assert sy.parts_table(session, [], mine)["lines"] == ["Skyworks", "Qorvo"]  # nothing here: nothing dropped


def test_system_chooser_is_a_grid_of_buttons_then_sub_system_chips(client):
    html = client.get(URL).text
    pick = _section(html, '<nav class="xs-pick"', "</nav>")
    buttons = re.findall(r'<a class="xs-sys" href="/blocks/cross-sell\?co=combined&amp;system=([\w-]+)">', pick)
    assert buttons == [s["key"] for s in sy.systems()]
    assert "xs-subs" not in pick and "sub=" not in pick  # no sub-system before a system is picked
    assert 'name="sel"' not in html  # the old drop-down is gone; ?sel= links still work
    auto = client.get(f"{URL}?system=automotive").text
    pick = _section(auto, '<nav class="xs-pick"', "</nav>")
    on = '<a class="xs-sys on" href="/blocks/cross-sell?co=combined&amp;system=automotive" aria-current="true">'
    assert on in pick
    chips = re.findall(r'href="/blocks/cross-sell\?co=combined&amp;system=automotive&amp;sub=([\w-]+)"', pick)
    assert chips == [x["key"] for x in sy.get("automotive")["subsystems"]]
    assert f"Automotive <small>{len(sy.selection('automotive')['idx'])}</small>" in pick
    one = client.get(f"{URL}?system=automotive&sub=car-radio&aec=1").text
    pick = _section(one, '<nav class="xs-pick"', "</nav>")
    chip = 'class="fchip on" href="/blocks/cross-sell?co=combined&amp;system=automotive&amp;sub=car-radio&amp;aec=1"'
    assert chip in pick
    assert 'href="/blocks/cross-sell?co=combined&amp;system=datacenter&amp;aec=1"' in pick  # the filter choice is kept
    old = _section(client.get(f"{URL}?sel=automotive:car-radio").text, '<nav class="xs-pick"', "</nav>")
    assert old.count(' on"') == 2 and "sub=car-radio\" aria-current" in old  # old picker links: system and sub


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
    assert [label for label, _ in tabs] == ["By system", "Skyworks + Qorvo portfolio"]  # By part retired, 2 Nov 2026
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
    assert "/business/attach" not in tabs and ">By part<" not in tabs  # retired (owner, 2 Nov 2026)
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


def test_old_function_links_land_on_the_systems_that_use_it(client):
    r = client.get("/business/attach?fn=am_fm_tuner")
    assert str(r.url).endswith("/blocks/cross-sell?fn=am_fm_tuner")
    assert 'href="/blocks/cross-sell?co=combined&amp;system=automotive&amp;sub=car-radio&amp;fn=am_fm_tuner"' in r.text
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


# ---- "Start from a part we already sell" (owner, 2 Nov 2026) ---------------------------------------------------------
# "Suggesting partner parts without the application is a guess": the By part tab is gone. By system has a part box: one
# of our part numbers shows the systems and sub-systems that use its function, with diagram counts; picking one opens
# the normal By system view with the part highlighted (its chip first and marked, its row marked, a short note).
# Unknown and competitor part numbers are answered plainly; old /business/attach links redirect.


def test_systems_of_a_function_count_each_diagram_once():
    fn = "digital_isolator"
    idx = sy.diagrams_of_function(fn)
    out = sy.systems_of_function(fn)
    assert out and [s["n"] for s in out] == sorted((s["n"] for s in out), reverse=True)
    for s in out:
        mine = idx & set(sy.selection(s["key"])["idx"])
        assert s["n"] == len(mine) and s["subs"] and all(p["system"] == s["key"] for p in s["subs"])
        assert max(p["n"] for p in s["subs"]) <= s["n"] <= sum(p["n"] for p in s["subs"])
    assert {p["sub"] for s in out for p in s["subs"]} == {p["sub"] for p in sy.places_of_function(fn)}
    assert sy.systems_of_function("no_such_function") == []


def test_part_box_lists_the_systems_that_use_our_part(client, session):
    html = client.get(f"{URL}?part=SKY87604").text
    p = cs.resolve_part(session, "SKY87604")
    box = _section(html, 'class="xs-places"', "</section>")
    assert f"{p['mpn']} <small" in box and "Skyworks" in box and "Closest match for “SKY87604”" in box
    systems = sy.systems_of_function("load_switch")
    n = len(sy.diagrams_of_function("load_switch"))
    assert f"is used in {n} diagrams of {len(systems)} systems" in box
    listed = re.findall(r'<li><a href="/blocks/cross-sell\?co=combined&amp;system=([\w-]+)&amp;part=([^"]+)"><b>([^<]+)'
                        r"</b> \((\d+) diagrams?\)</a>", box)  # fmt: skip
    assert [(k, int(c)) for k, _, _, c in listed] == [(s["key"], s["n"]) for s in systems]
    assert {unquote(m) for _, m, _, _ in listed} == {p["mpn"]}
    first = systems[0]["subs"][0]
    assert f"system={first['system']}&amp;sub={first['sub']}&amp;part=" in box and f"({first['n']})" in box
    assert "Sell what we have" in html  # the rest of the page as before
    exact = client.get(f"{URL}?part={p['mpn']}").text
    assert "Closest match" not in exact and f"{p['mpn']} <small" in exact


def test_picking_a_system_highlights_the_part(client, session):
    mpn = cs.resolve_part(session, "SKY87604")["mpn"]
    place = sy.places_of_function("load_switch")[0]
    html = client.get(f"{URL}?system={place['system']}&sub={place['sub']}&part={mpn}&aec=0").text
    note = _section(html, '<p class="xs-note small" role="status">', "</p>")
    assert f"<b>{mpn}</b> (Skyworks · " in note and "its chip and row are highlighted" in note
    assert 'href="#fn-load_switch"' in note and f"part={mpn}" in note and ">Clear</a>" in note
    rows = {fn: (cls, row) for fn, cls, row in ROW.findall(_section(html, 'id="parts-here"', "</section>"))}
    cls, row = rows["load_switch"]
    assert "xs-hl" in cls and sum("xs-hl" in c for c, _ in rows.values()) == 1
    sky = _cells(row)[0]
    you = '<div class="xs-chips"><span class="xs-you" title="The part you started from"><a class="badge'
    assert sky.startswith(you)
    assert sky.count(f'href="/parts?q={mpn}"') == 1  # listed once, first
    # the selection keeps the part: system buttons, sub-system chips, the filter toggle and the one-diagram form
    pick = _section(html, '<nav class="xs-pick"', "</nav>")
    assert pick.count(f"part={mpn}") == pick.count("<a ") and f'name="part" value="{mpn}"' in html
    assert f"part={mpn}&amp;aec=1" in _section(html, 'class="chip-row aec-filter"', "</div>")
    # a system that does not use the function says so
    used = sy.diagrams_of_function("load_switch")
    other = next(s for s in sy.systems() if not set(sy.selection(s["key"])["idx"]) & used)
    none = client.get(f"{URL}?system={other['key']}&part={mpn}").text
    assert "is not used in these diagrams" in none and "xs-hl" not in _section(none, "<main", "</main>")


def test_part_box_answers_unknown_and_competitor_parts_plainly(client, real):
    html = client.get(f"{URL}?part=zzzzzz").text
    assert "No part number starting with “zzzzzz” in BizDev" in html and 'class="xs-places"' not in html
    comp = client.get(f"{URL}?part=ISO7741").text
    m = re.search(r'<b>(ISO7741[^<]*)</b> is a TI part, not one of ours\. '
                  r'<a href="(/parts/\d+)">See its cross: our replacements</a>', comp)  # fmt: skip
    assert m and client.get(m.group(2)).status_code == 200
    assert 'class="xs-places"' not in comp and "xs-hl" not in comp
    blank = client.get(f"{URL}?part=").text  # the box sent empty: the chooser, no message
    assert "No part number" not in blank and "Pick a system" in blank


def test_old_by_part_links_redirect(client):
    for old, new in (("/business/attach", "/blocks/cross-sell"),
                     ("/business/attach?part=Si8641&app=dcdc", "/blocks/cross-sell?part=Si8641"),
                     ("/business/attach?fn=gate_driver&co=combined", "/blocks/cross-sell?fn=gate_driver"),
                     ("/business/attach?part=Si8641&fn=gate_driver", "/blocks/cross-sell?part=Si8641"),
                     ("/business/attach?system=automotive&sub=car-radio&aec=0",
                      "/blocks/cross-sell?system=automotive&sub=car-radio&aec=0")):  # fmt: skip
        r = client.get(old, follow_redirects=False)
        assert r.status_code == 307 and r.headers["location"] == new, old
    from app.services import vocab

    fn = client.get("/blocks/cross-sell?fn=gate_driver").text
    label = vocab.fn_label("gate_driver")
    assert f'<h3 id="xs-places-h">{label}</h3>' in fn and f"{label} is used in " in fn
    assert "No part number" not in client.get("/blocks/cross-sell?fn=no_such_function").text
