"""Opportunity pages: explorer sorting and decisions, cross-sell parts, market chips, business-case candidates."""

import re

KEEP = r'name="fn" value="([a-z0-9_]+)"><input type="hidden" name="status" value="keep"'  # a function row's Keep


def test_explorer_sorts_and_old_views(client):
    for sort in ("label", "path", "reach", "competition", "score", "tam"):
        for d in ("asc", "desc"):
            r = client.get(f"/business/explorer?sort={sort}&dir={d}")
            assert r.status_code == 200 and 'class="sortable sorted"' in r.text, (sort, d)
    html = client.get("/business/explorer?view=feasibility").text  # old links land on the matching sort
    assert 'aria-sort="descending"' in html and "Fit score</a>" not in html
    assert "higher is better" in html and "Evidence" not in html.split("<thead>")[1].split("</thead>")[0]
    assert "How the score works" in html and any(f">{b}</span>" in html for b in ("High", "Medium", "Low"))


def test_keep_set_aside_and_restore(client):
    first = re.search(KEEP, client.get("/business/explorer").text).group(1)
    r = client.post("/business/decision", data={"fn": first, "status": "keep", "back": "/business/explorer"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"] == "/business/explorer"
    assert "✓ kept" in client.get("/business/explorer").text
    client.post("/business/decision", data={"fn": first, "status": "set_aside", "note": "revisit 2027"})
    html = client.get("/business/explorer").text
    aside = html.split('class="h-aside"')[1]
    assert "revisit 2027" in aside and "1 not pursued" in aside
    client.post("/business/decision", data={"fn": first, "status": "clear"})
    assert "0 not pursued" in client.get("/business/explorer").text
    assert client.post("/business/decision", data={"fn": "nope", "status": "keep"}).status_code == 400


def test_cross_sell_names_parts_and_bundles(client):
    html = client.get("/business/attach").text
    assert "Best bundles" in html
    fn = re.search(r'<option value="([a-z0-9_]+)"', html).group(1)
    html = client.get(f"/business/attach?fn={fn}").text
    assert "Offer with it" in html and "New products next to it" in html


def test_markets_chips_and_groups(client):
    html = client.get("/business/markets").text
    assert all(h in html for h in ("Existing portfolio", "Portfolio gap", "New technology"))
    assert "<span>Markets</span>" in html and "Needed in" not in html
    market = re.search(r'href="/business/markets\?co=combined&amp;m=([^"&]+)&amp;', html).group(1)
    one = client.get(f"/business/markets?m={market}").text
    assert one.count('class="bo-mk"') < html.count('class="bo-mk"')


def test_candidates_to_business_case(client):
    page = client.get("/business/explorer").text
    fn = re.search(KEEP, page).group(1)
    form = {"origin": "explorer", "key": fn, "title": "Candidate one", "fn": fn, "back": "/business/explorer"}
    assert client.post("/business/shortlist", data=form, follow_redirects=False).status_code == 303
    client.post("/business/shortlist", data=form)  # pushing twice keeps one
    client.post("/business/shortlist", data={"origin": "idea", "key": "Wireless audio for e-bikes"})
    html = client.get("/business/shortlist").text
    assert (
        html.count("Candidate one") == 1
        and "Wireless audio for e-bikes" in html
        and "★ on the shortlist" in client.get("/business/explorer").text
    )
    # the button's script posts for JSON and stays on the page; the count feeds the badge on the tab
    count = client.get("/api/shortlist/count").json()["count"]
    r = client.post(
        "/business/shortlist", data={"origin": "idea", "key": "Second idea"}, headers={"Accept": "application/json"}
    )
    assert r.status_code == 200 and r.json() == {"count": count + 1}
    item = re.search(r"shortlist=(\d+)", html).group(1)
    new = client.get(f"/business/cases/new?shortlist={item}").text
    assert f'name="shortlist" value="{item}"' in new
    r = client.post("/business/cases", data={"title": "Analysed", "shortlist": item}, follow_redirects=False)
    assert r.status_code == 303
    assert "Open case: Analysed" in client.get("/business/shortlist").text
    assert client.post("/business/shortlist", data={"origin": "bogus", "key": "x"}).status_code == 400


def test_overview_retired_explorer_grouped_with_rf_band_gaps(client):
    r = client.get("/business?co=skyworks", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/business/explorer?co=skyworks"
    from app.services import opportunity as op

    bands = op.rf_band_rows()
    assert all(b["gap_type"] == "band_gap" and b["group"] == "RF & radio" and "@" in b["key"] for b in bands)
    html = client.get("/business/explorer").text
    assert 'class="ex-group"' in html and "Category" in html
    if bands:  # an RF band gap can be kept like a function
        r = client.post("/business/decision", data={"fn": bands[0]["key"], "status": "keep"}, follow_redirects=False)
        assert r.status_code == 303
    assert client.post("/business/decision", data={"fn": "nope@X", "status": "keep"}).status_code == 400


def test_cross_sell_explains_each_pairing(client):
    from app.services import opportunity as op

    w = op.pair_reasons(op.applications(), "load_switch", "pol_buck")
    assert w["n"] and w["rows"] and w["summary"]
    r = w["rows"][0]
    assert r["same"] or r["links"] or (r["a_blocks"] and r["b_blocks"])
    page = client.get("/business/attach?fn=load_switch")
    assert page.status_code == 200 and '<details class="why small"><summary>Why?</summary>' in page.text
    assert '<details class="why small" open' not in page.text  # collapsed by default
