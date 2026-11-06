"""One function in many bands is one row (owner, 3 Nov 2026): the bands of one function fold into a parent row on Gaps &
new technology, its detailed table and RF coverage; counts and rankings are by function; keep / set aside on the
group applies to every band without its own decision."""

import re

from app.services import variants

FM = "frequency_multiplier"


def _row(fn, band, score, reach=3, **kw):
    return {"fn": fn, "key": f"{fn}@{band}" if band else fn, "label": f"{fn} · {band}" if band else fn,
            "base_label": fn.title(), "band_id": band, "variant": band, "priority": {"score": score},
            "reach": reach, "tam": 0.0, "tam_apps": 0, **kw}  # fmt: skip


def test_two_bands_make_one_parent_with_two_subs_and_a_single_row_stays_plain():
    rows = [_row("mult", "X", 80, reach=5), _row("ldo", None, 70), _row("mult", "L", 60, reach=2)]
    out = variants.group(rows)
    assert [e["fn"] for e in out] == ["mult", "ldo"]  # the parent sits where its best band sits
    p, plain = out
    assert [s["key"] for s in p["subs"]] == ["mult@X", "mult@L"] and p["n_variants"] == 2
    assert p["label"] == "Mult" and p["key"] == "mult" and p["priority"]["score"] == 80
    assert p["variant_kind"] == "bands" and p["span"] == "L–X (1–12 GHz)" and p["reach_range"] == (2, 5)
    assert variants.summary(p) == "Mult · 2 bands · L–X (1–12 GHz)"
    assert plain is rows[1] and "subs" not in plain
    assert variants.count(rows) == 2


def test_power_classes_and_span_words():
    pa = [_row("pa", "mmw", 70, power_label="up to 1 W"), _row("pa", "mmw", 60, power_label="1–10 W")]
    assert variants.kind(pa) == "power classes" and variants.span(pa) == "V / E / W > 40 GHz"
    assert variants.span([_row("f", "sub1", 1), _row("f", "Ka", 1)]) == "sub-1 GHz–Ka (0.003–40 GHz)"
    assert variants.span([_row("f", "Ka", 1), _row("f", "mmw", 1)]) == "K–W (18–110 GHz)"
    assert variants.span([_row("f", None, 1)]) == ""


def test_a_band_follows_its_function_unless_it_has_its_own_decision():
    decisions = {"mult": "set_aside", "mult@L": "keep"}
    assert variants.decision_of(_row("mult", "X", 1), decisions) == ("set_aside", True)
    assert variants.decision_of(_row("mult", "L", 1), decisions) == ("keep", False)
    assert variants.decision_of(_row("mult", None, 1), decisions) == ("set_aside", False)
    assert variants.decision_of(_row("other", "X", 1), decisions) == (None, False)


def _heads(html: str) -> list[str]:
    return re.findall(r'<tr class="vg-head[^"]*" data-fn="(\w+)"', html)


def test_detailed_table_groups_bands_counts_functions_and_sorts_by_the_best_band(client):
    html = client.get("/business/explorer/table").text
    assert FM in _heads(html) and _heads(html).count(FM) == 1
    head = html.split(f'data-fn="{FM}"')[1].split('<tr class="vg-row">')[0]
    assert "6 bands" in head and "L–Ka (1–40 GHz)" in head and "Set aside all" in head
    subs = html.split(f'data-fn="{FM}"')[1].split("</details></td></tr>")[0].split('<tr class="vg-row">')[1]
    assert subs.count("/business/rf-coverage?fn=frequency_multiplier&amp;band=") == 6
    best = max(int(x) for x in re.findall(r'<b class="pr-num">(\d+)</b>', subs))
    assert f'<b class="pr-num">{best}</b>' in head  # the parent shows its best band's priority
    # the RF category counts functions: 8, not the 17 rows of before
    rf = re.search(r'RF &amp; radio <small class="muted">· (\d+)', html).group(1)
    chip = re.search(r"RF &amp; radio <small>(\d+)</small>", html).group(1)
    assert rf == chip
    rows_before = len(re.findall(r"/business/rf-coverage\?fn=\w+&amp;band=\w+\">RF coverage", html))
    assert int(rf) < rows_before
    # ascending by label still keeps each function once
    asc = client.get("/business/explorer/table?sort=label&dir=asc").text
    assert _heads(asc).count(FM) == 1


def test_detailed_table_filters_still_work_on_groups(client):
    html = client.get("/business/explorer/table?t=band_gap").text
    assert FM in _heads(html)
    chip = re.search(r'class="fchip gt-band_gap on"[^>]*>[^<]*<small>(\d+)</small>', html)
    assert chip and int(chip.group(1)) == len(set(re.findall(r'href="/business/evidence/(\w+)\?', html.split(
        'class="h-aside"')[0].split("<tbody>", 1)[1])))  # fmt: skip
    # a type filter counts functions too: the Opportunity score types of the band rows, one per function
    s = client.get("/business/explorer/table?t=band_gap&s=quick_win").text
    assert all(h in _heads(html) for h in _heads(s))


def test_set_aside_the_group_then_one_band(client):
    client.post("/business/decision", data={"fn": FM, "status": "set_aside", "note": "not now"})
    html = client.get("/business/explorer/table").text
    main, aside = html.split('class="h-aside"')
    assert FM not in _heads(main) and "1 not pursued" in aside
    assert "6 bands" in aside and "not now" in aside and f'name="fn" value="{FM}"' in aside and "Restore all" in aside
    page = client.get("/business/opportunities?show=all").text
    assert f'data-fn="{FM}"' not in page and "and 1 set aside" in page
    client.post("/business/decision", data={"fn": FM, "status": "clear"})
    # one band on its own: the group shows the other five, the band waits under Set aside
    client.post("/business/decision", data={"fn": f"{FM}@L", "status": "set_aside", "note": ""})
    html = client.get("/business/explorer/table").text
    main, aside = html.split('class="h-aside"')
    assert "5 bands" in main.split(f'data-fn="{FM}"')[1].split("</tr>")[0]
    assert f'name="fn" value="{FM}@L"' in aside and ">Restore<" in aside
    client.post("/business/decision", data={"fn": f"{FM}@L", "status": "clear"})


def test_keep_the_group_keeps_every_band_and_the_kept_filter_shows_it(client):
    client.post("/business/decision", data={"fn": FM, "status": "keep"})
    html = client.get("/business/explorer/table?f=kept").text
    assert _heads(html) == [FM] or FM in _heads(html)
    head = html.split(f'data-fn="{FM}"')[1].split("</tr>")[0]
    assert "✓ kept (all)" in head and "Keep all" not in head
    assert html.count("✓ kept (with the group)") == 6
    card = client.get("/business/opportunities?show=all").text.split(f'data-fn="{FM}"')[1].split("</article>")[0]
    assert "✓ kept" in card
    client.post("/business/decision", data={"fn": FM, "status": "clear"})


def test_gaps_page_shows_one_card_per_function_and_counts_them(client):
    page = client.get("/business/opportunities?show=all").text
    cards = re.findall(r'<article class="csg-card[^"]*"', page)
    groups = re.findall(r'class="csg-card vg-card"[^>]*data-fn="(\w+)"', page)
    assert FM in groups and "rf_synthesizer" in groups and groups.count(FM) == 1
    n_gaps = int(re.search(r"1 · Gaps to fill <small>(\d+)", page).group(1))
    n_new = int(re.search(r"2 · New technology <small>(\d+)", page).group(1))
    assert n_gaps + n_new == len(cards)
    card = page.split(f'data-fn="{FM}"')[1].split("</article>")[0]
    assert "6 bands · L–Ka (1–40 GHz)" in card and "Show the 6 bands" in card and card.count("<li>") == 6
    # the focus view ranks the group by its best band, so it is among the first cards
    focus = client.get("/business/opportunities").text
    assert f'data-fn="{FM}"' in focus


def test_rf_coverage_gaps_one_row_per_function(client):
    html = client.get("/business/rf-coverage").text
    sec = html.split("Gaps and thin spots applications need")[1].split('class="small rf-method"')[0]
    assert re.search(r"<small class=\"muted\">6 functions · 22 bands</small>", sec)
    assert _heads(sec).count(FM) == 1 and "rf_limiter" not in _heads(sec)
    assert "Show the 6 bands" in sec


def test_the_group_set_aside_form_sent_blank_gives_a_page(client):
    """The parent row's "Set aside all" form, sent with the reason left blank as a browser would."""
    from tests.test_blank_forms import _Forms, browser_payload, send, submitters

    p = _Forms()
    p.feed(client.get("/business/explorer/table").text)
    p.close()
    form = next(f for f in p.forms if f["action"] == "/business/decision"
                and ("fn", FM) in [(x["name"], x.get("value")) for x in f["fields"]]
                and any(x.get("value") == "set_aside" for x in f["fields"]) and any(x["name"] == "note" and
                x.get("type") != "hidden" for x in f["fields"]))  # fmt: skip
    sub = submitters(form)[0]
    assert ("note", "") in browser_payload(form, sub)
    path, r = send(client, "/business/explorer/table", form, sub)
    assert r.status_code == 200 and "6 bands" in r.text.split('class="h-aside"')[1]
    client.post("/business/decision", data={"fn": FM, "status": "clear"})
