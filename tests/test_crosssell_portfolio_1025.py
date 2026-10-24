"""Owner, 25 Oct 2026: the Skyworks + Qorvo portfolio moved from Products to Systems & applications › Cross-sell
(third tab, URL kept); By system shows "Skyworks + Qorvo together here" for the picked system, each pair once; the
automotive synergies per sub-system with a reason, real active parts and the design-effort mark; the selected system
carries over between the Cross-sell tabs."""

import re
from collections import Counter

from app.services import blocks
from app.services import portfolio as pf
from app.services import systems as sy
from app.web import nav

AUTO_SUBS = ("car-access", "car-radio", "telematics-v2x", "adas", "powertrain", "battery-power", "charging", "cockpit")


def _cards(html: str) -> list[tuple[str, str]]:
    """(Skyworks label, Qorvo label) of every synergy card on a page."""
    return re.findall(r'<span class="ln-skyworks"><b>([^<]+)</b>.*?<span class="ln-qorvo"><b>([^<]+)</b>', html)


def _section(html: str, start: str, end: str) -> str:
    return html[html.index(start) : html.index(end, html.index(start))]


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
    assert 'id="together"' not in one_line  # only for the combined company


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
