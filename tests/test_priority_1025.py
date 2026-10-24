"""Priority score on Opportunities > Gaps & new technology (owner, 25 Oct 2026): "we really need to focus on things we
can do that are RF-related or power-related ... a mathematical weighting based on number of diagrams, likeliness and
technology relation, and then sort the list of gaps to fill and the list of new technology by that."""

import math
import re

import pytest

from app.services import blocks
from app.services import priority as pr

try:  # the browser fixture (a tab on the live app, checked at 390 px afterwards); skipped without Playwright
    from tests.test_browser import page  # noqa: F401
except pytest.skip.Exception:
    pass

FOCUS = ("rf_core", "power_core", "timing_ms", "power_near")


def row(fn, reach, feas=None, background=0, key=None, gap_type="true_gap"):
    return {"fn": fn, "key": key or fn, "label": fn, "reach": reach, "background": background,
            "feasibility": feas, "distance": None, "gap_type": gap_type}  # fmt: skip


def test_formula_and_rf_above_ldo_and_mcu():
    rows = pr.annotate([row("power_amplifier", 12, 2), row("pol_ldo", 128, 1), row("mcu", 100, 3)])
    pa, ldo, mcu = (e["priority"] for e in rows)
    w = pr.default_weights()
    assert w == pytest.approx({"technology": 0.45, "likeliness": 0.30, "diagrams": 0.25})
    # power amplifier: RF core 1.0; feasibility 2 -> 0.6, + 0.1 for a platform of ours (GaAs HBT); 12 of 128 diagrams
    d = math.log(13) / math.log(129)
    assert (pa["T"], pa["L"], pa["D"]) == (1.0, 0.7, pytest.approx(d, abs=1e-3))
    assert pa["score"] == pytest.approx(100 * (0.45 * 1.0 + 0.30 * 0.7 + 0.25 * d), abs=0.05)
    # the LDO is in the most diagrams and likely, yet general power: 100 × (0.45 × 0.4 + 0.30 × 1 + 0.25 × 1) = 73
    assert (ldo["T"], ldo["L"], ldo["D"]) == (0.4, 1.0, 1.0) and ldo["score"] == pytest.approx(73.0)
    assert mcu["T"] == 0.2 and mcu["L"] == 0.3 and mcu["outside"] and not mcu["focus"]
    assert pa["score"] > ldo["score"] > mcu["score"]
    # with the same diagrams and likeliness, the technology relation decides: RF, then LDO, then MCU
    same = pr.annotate([row("lna", 40, 1), row("pol_ldo", 40, 1), row("mcu", 40, 1)])
    assert [e["fn"] for e in pr.ranked(same)] == ["lna", "pol_ldo", "mcu"]
    assert pr.chips(same[0]) == ["RF core", "40 diagrams", "likely"]
    assert pr.example(same[1]) == "100 × (0.45 × 0.40 + 0.30 × 1.00 + 0.25 × 1.00) = 73.0"


def test_diagrams_on_a_log_scale_and_owner_answers():
    assert pr.diagrams(4, 40) == pytest.approx(math.log(5) / math.log(41))
    assert pr.diagrams(40, 40) == 1.0 and pr.diagrams(0, 40) == 0.0 and pr.diagrams(3, 0) == 0.0
    assert pr.diagrams(40, 128) / pr.diagrams(4, 128) < 3  # 40 diagrams is not 10 × better than 4
    rows = pr.annotate([row("temperature_sensor", 118, 1), row("tvs_esd", 101, 2), row("pcie_switch", 1)])
    temp, tvs, unknown = (e["priority"] for e in rows)
    assert temp["L"] == 0.3 and temp["l_owner"] and "ASP" in temp["l_basis"]
    assert tvs["L"] == 0.2 and tvs["l_owner"]
    assert unknown["L"] == 0.45 and unknown["l_label"] == "unlikely"  # not assessed
    assert pr.annotate([row("x", 3, background=2)])[0]["priority"]["n"] == 3  # background counts in full by default


def test_weights_from_the_sliders():
    base = pr.default_weights()
    assert pr.weights() == (base, False)
    assert pr.weights("", "", "") == (base, False) and pr.weights("abc", "", "") == (base, False)
    assert pr.weights("0", "0", "0") == (base, False)
    w, custom = pr.weights("20", "40", "40")
    assert custom and w == pytest.approx({"technology": 0.2, "likeliness": 0.4, "diagrams": 0.4})
    w, custom = pr.weights("90", "90", "20")  # scaled to add up to 1
    assert sum(w.values()) == pytest.approx(1) and w["technology"] == pytest.approx(0.45)
    assert pr.weights("10", "10", "80", allowed=False) == (base, False)  # guests always see the default
    assert pr.percent(base) == {"technology": 45, "likeliness": 30, "diagrams": 25}


def test_yaml_validates_and_every_function_is_mapped():
    cfg = pr.config()
    assert sum(cfg["weights"].values()) == pytest.approx(1)
    t = cfg["technology"]
    assert all(0 <= lv["value"] <= 1 and lv["label"] and lv["help"] for lv in t["levels"].values())
    values = {k: lv["value"] for k, lv in t["levels"].items()}
    assert values["rf_core"] == 1.0 and values["power_core"] == 0.9 and values["timing_ms"] == 0.7
    assert values["power_commodity"] == 0.4 and values["outside"] == 0.2 and t["default"] == 0.3
    cat = blocks.catalogue()["functions"]
    cats = {f.get("category") for f in cat.values()}
    assert set(t["categories"]) <= cats and set(t["categories"].values()) <= set(t["levels"])
    assert set(t["functions"]) <= set(cat), set(t["functions"]) - set(cat)
    assert set(t["functions"].values()) <= set(t["levels"])
    assert set(cfg["likeliness"]["owner"]) <= set(cat)
    assert {1, 2, 3} == set(cfg["likeliness"]["feasibility"])
    assert 0 < cfg["outside_below"] < cfg["focus_from"] <= 1
    # every function of the catalogue maps to a level, so nothing on the page falls back to the default
    assert pr.unmapped([{"fn": fn} for fn in cat]) == []
    assert pr.unmapped([{"fn": "no_such_function"}]) == ["no_such_function"]
    assert pr.relation("no_such_function")["value"] == 0.3
    # the brief's examples
    lv = {fn: pr.relation(fn)["level"] for fn in cat}
    for fn in ("power_amplifier", "lna", "filter_saw_baw", "rf_switch", "antenna_tuner", "uwb_fem", "gnss_lna",
               "beamformer_ic", "uwb_soc", "ble_soc"):  # fmt: skip
        assert lv[fn] == "rf_core", fn
    for fn in ("gate_driver", "digital_isolator", "current_sensor", "isolated_dcdc", "efuse_hotswap",
               "motor_controller"):  # fmt: skip
        assert lv[fn] == "power_core", fn
    for fn in ("clock_generator", "crystal_oscillator", "am_fm_tuner"):
        assert lv[fn] == "timing_ms", fn
    for fn in ("pol_ldo", "termination_ldo", "ldo_tracker", "pol_buck", "buck_boost", "load_switch", "supervisor"):
        assert lv[fn] == "power_commodity", fn
    for fn in ("mcu", "flash", "soc", "temperature_sensor", "tvs_esd", "can_transceiver"):
        assert lv[fn] == "outside", fn


CARD = (r'<article class="csg-card" data-t="([\w]+)"><b><a [^>]*>([^<]+)</a></b>\s*<span class="pr-bar".*?'
        r'<b class="pr-num">([\d.]+)</b>')  # fmt: skip
# a Markets row: label, then the priority cell (its fill colour names the technology level)
MROW = r'<td class="bo-fn"><b>([^<]+)</b>.*?<span class="pr-fill pr-t-(\w+)".*?<b class="pr-num">([\d.]+)</b>'


def _section(html: str, section: str) -> str:
    part = html[html.index(f'id="{section}"') :]
    return part[: part.index("</section>")]


def _found(part: str, pattern: str) -> list[tuple[str, float, str]]:
    """(label, priority, technology level) in page order."""
    if pattern == CARD:
        return [(m[1], float(m[2]), m[0]) for m in re.findall(pattern, part, re.S)]
    return [(m[0], float(m[2]), m[1]) for m in re.findall(pattern, part, re.S)]


def _cards(html: str, section: str, pattern: str = CARD) -> list[tuple[str, float, str]]:
    return _found(_section(html, section), pattern)


def _groups(html: str, section: str, pattern: str = CARD):
    """(RF & power, general power and adjacent, outside our technology focus) of one section under "All"."""
    part = _section(html, section)
    cuts = [part.find(m) for m in ('<details class="pr-middle"', '<details class="pr-outside"')]
    ends = [c if c >= 0 else len(part) for c in cuts]
    main = part[: min(ends)]
    middle = part[cuts[0] : ends[1]] if cuts[0] >= 0 else ""
    outside = part[cuts[1] :] if cuts[1] >= 0 else ""
    return _found(main, pattern), _found(middle, pattern), _found(outside, pattern)


def _check_all(focus_html: str, all_html: str, section: str, pattern: str = CARD):
    shown = _cards(focus_html, section, pattern)
    assert all(t in FOCUS for _, _, t in shown), shown
    main, middle, outside = _groups(all_html, section, pattern)
    for group in (shown, main, middle, outside):
        scores = [s for _, s, _ in group]
        assert scores == sorted(scores, reverse=True), (section, scores)
    assert all(t in FOCUS for _, _, t in main)
    assert all(t in ("adjacent", "power_commodity") for _, _, t in middle)
    assert all(t == "outside" for _, _, t in outside)
    # nothing dropped: the focus rows are the first group under "All", and All lists every item once
    assert shown == main
    labels = [lab for lab, _, _ in main + middle + outside]
    assert len(labels) == len(set(labels))
    return main, middle, outside


def test_both_lists_sorted_by_priority_and_filtered(client):
    focus = client.get("/business/opportunities").text
    every = client.get("/business/opportunities?show=all").text
    assert 'class="fchip on" href="/business/opportunities?co=combined" aria-current="true"' in focus  # on by default
    assert "RF &amp; power only" in every and 'aria-current="true">All' in every
    for section in ("gaps", "new"):
        _check_all(focus, every, section)
    assert html_count(every) == html_count(every.split('id="how"')[0])
    assert "General power and adjacent technology" in every
    assert html_count(every) > html_count(focus) > 5
    assert "How the score works" in focus and "Outside our technology focus" in every
    assert "None: every function here is mapped." in focus
    assert "Top item:" in focus and "100 × (0.45 ×" in focus


def html_count(html: str) -> int:
    return html.count('class="csg-card"')


def test_all_lists_every_open_item(client, session):
    from app.services import opportunity as op
    from app.services import scoring

    apps = op.with_status(op.applications(), op.makers(session), op.COMPANIES["combined"][1])
    asp, vol = op.inputs(session)
    rows = op.explorer(apps, asp, vol, scoring.for_session(session, apps, asp, vol))
    open_rows = [e for e in rows if e["gap_type"] != "not_ours"]
    every = client.get("/business/opportunities?show=all").text
    assert html_count(every) == len(open_rows)
    assert pr.unmapped(open_rows) == []


def test_detailed_table_sorts_by_priority_by_default(client):
    html = client.get("/business/explorer/table").text
    head = 'class="sortable sorted" data-n aria-sort="descending"><a href="/business/explorer/table?co=combined'
    assert head + "&amp;dir=asc&amp;scope=all&amp;sort=priority" in html
    assert ">Priority<" in html and 'class="pr-bar"' in html and "how the score works" in html
    for sort in ("label", "path", "reach", "score", "competition"):  # the other sorts stay
        assert client.get(f"/business/explorer/table?sort={sort}").status_code == 200
    # the same number on the cards and in the table
    cards = dict((lab, s) for lab, s, _ in _cards(client.get("/business/opportunities?show=all").text, "gaps"))
    cell = r'<td><a href="/business/evidence/[^"]+"><b>([^<]+)</b></a>.*?<b class="pr-num">([\d.]+)</b>'
    table = dict(re.findall(cell, html, re.S))
    common = set(cards) & set(table)
    assert common and all(cards[k] == float(table[k]) for k in common)


def test_owner_weights_in_the_url(client):
    html = client.get("/business/opportunities?wt=20&wl=40&wd=40").text
    assert "(your weights)" in html and "100 × (0.20 ×" in html
    assert 'href="/business/explorer/table?co=combined&amp;wt=20&amp;wl=40&amp;wd=40"' in html
    assert 'name="wt"' in html and 'type="range"' in html
    table = client.get("/business/explorer/table?wt=20&wl=40&wd=40").text
    assert "wt=20" in table  # the sort links keep the weights
    assert client.get("/business/opportunities?wt=&wl=&wd=").status_code == 200


def test_guest_sees_the_default_weights_and_no_sliders(make_guest, owner):
    g, _ = make_guest()
    url = "/business/opportunities?wt=10&wl=10&wd=80"
    page = g.get(url).text
    assert "Gaps to fill" in page and "100 × (0.45 ×" in page and "(your weights)" not in page
    assert 'type="range"' not in page and "TAM $" not in page
    mine = owner.get(url).text
    assert "(your weights)" in mine and 'type="range"' in mine
    assert "TAM / year" not in g.get("/business/explorer/table?wt=10&wl=10&wd=80").text


# --- Markets & customers: the same score (owner, 25 Oct 2026: "the topics weighted just like in the other") ----------
MK_GROUPS = ("portfolio", "gap", "new_tech")


def test_markets_in_priority_order_commodity_below_rf_and_power(client):
    focus = client.get("/business/markets").text
    every = client.get("/business/markets?show=all").text
    assert "RF &amp; power only" in focus
    assert 'href="/business/opportunities?co=combined#how">how the score works' in focus
    n_rows = 0
    for k in MK_GROUPS:
        main, middle, outside = _check_all(focus, every, f"mk-{k}", MROW)
        order = [t for _, _, t in main + middle + outside]
        n_rows += len(order)
        commodity = [i for i, t in enumerate(order) if t == "power_commodity"]
        rf_power = [i for i, t in enumerate(order) if t in ("rf_core", "power_core")]
        if commodity and rf_power:  # every LDO-like row below every RF and power row
            assert min(commodity) > max(rf_power), k
    # nothing dropped under "All": every function of the three tables is there once
    assert n_rows == every.count('<td class="bo-fn"><b>') > focus.count('<td class="bo-fn"><b>')
    assert "Outside our technology focus" in every and "General power and adjacent technology" in every


def test_markets_all_lists_every_function(client, session):
    from app.services import opportunity as op

    apps = op.with_status(op.applications(), op.makers(session), op.COMPANIES["combined"][1])
    rows = op.markets(session, apps, op.COMPANIES["combined"][1])["rows"]
    every = client.get("/business/markets?show=all").text
    for k in MK_GROUPS:
        found = sum(len(x) for x in _groups(every, f"mk-{k}", MROW))
        assert found == sum(e["group"] == k for e in rows), k


def test_same_function_same_technology_and_likeliness_on_both_pages(session):
    from app.services import opportunity as op
    from app.services import scoring

    apps = op.with_status(op.applications(), op.makers(session), op.COMPANIES["combined"][1])
    asp, vol = op.inputs(session)
    tab = scoring.for_session(session, apps, asp, vol)
    gaps = {e["key"]: e for e in pr.annotate(op.explorer(apps, asp, vol, tab))}
    rows = [dict(e) for e in op.markets(session, apps, op.COMPANIES["combined"][1])["rows"]]
    mk = pr.annotate(pr.with_feasibility(rows, tab), count=lambda e: e["n_apps"])
    common = [e for e in mk if e["fn"] in gaps and gaps[e["fn"]]["gap_type"] != "not_ours"]
    assert len(common) > 5
    for e in common:
        a, b = e["priority"], gaps[e["fn"]]["priority"]
        assert (a["T"], a["L"], a["t_level"]) == (b["T"], b["L"], b["t_level"]), e["fn"]
    # with every market chosen the count is the same as "Needed in", so the whole score matches when n_max does
    for e in common:
        assert e["priority"]["n"] == gaps[e["fn"]]["priority"]["n"], e["fn"]


def test_markets_weights_and_guests(make_guest, owner):
    url = "/business/markets?show=all&wt=20&wl=40&wd=40"
    mine = owner.get(url).text
    assert "(your weights)" in mine and 'type="range"' in mine and 'action="/business/markets"' in mine
    assert "wt=20" in mine and "100 × (0.20 ×" in mine  # the tooltips use the weights from the URL
    g, _ = make_guest()
    page = g.get(url).text
    assert "(your weights)" not in page and 'type="range"' not in page and "Outside our technology focus" in page
    assert "100 × (0.45 ×" in page and "100 × (0.20 ×" not in page


# --- in a real browser ------------------------------------------------------------------------------------------------
@pytest.mark.browser
def test_browser_filter_and_how_the_score_works(page):  # noqa: F811
    """Open the page, switch "RF & power only" to "All", open "How the score works", try the owner's sliders; the
    page fixture also opens every visited page at 390 px and fails on sideways scrolling or a console error."""
    pytest.importorskip("playwright.sync_api")
    from tests.test_browser import go

    go(page, "/business/opportunities")
    on = page.locator(".pr-filter a.fchip.on")
    assert on.inner_text().strip() == "RF & power only"
    n_focus = page.locator("article.csg-card").count()
    with page.expect_navigation():
        page.locator(".pr-filter a.fchip", has_text="All").click()
    assert "show=all" in page.url
    assert page.locator(".pr-filter a.fchip.on").inner_text().startswith("All")
    assert page.locator("article.csg-card").count() > n_focus
    assert page.get_by_text("Outside our technology focus").first.is_visible()
    how = page.locator("details#how")
    assert not how.evaluate("d => d.open")
    how.locator("summary").click()
    assert how.evaluate("d => d.open") and page.get_by_text("Top item:").is_visible()
    slider = page.locator("#pr-wt")
    slider.fill("80")
    assert page.locator('output[for="pr-wt"]').inner_text() == "80"
    with page.expect_navigation():
        page.locator("#pr-weights button[type=submit]").click()
    assert "wt=80" in page.url and "show=all" in page.url
    # Markets: the same filter and groups
    go(page, "/business/markets")
    assert page.locator(".pr-filter a.fchip.on").inner_text().strip() == "RF & power only"
    with page.expect_navigation():
        page.locator(".pr-filter a.fchip", has_text="All").click()
    assert "show=all" in page.url and page.get_by_text("General power and adjacent technology").first.is_visible()
