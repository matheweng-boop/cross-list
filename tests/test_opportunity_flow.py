"""Opportunity pages: explorer sorting and decisions, cross-sell parts, market chips, business-case candidates."""

import re

KEEP = r'name="fn" value="([a-z0-9_]+)"><input type="hidden" name="status" value="keep"'  # a function row's Keep


def test_explorer_sorts_and_old_views(client):
    for sort in ("label", "path", "reach", "competition", "score", "tam"):
        for d in ("asc", "desc"):
            r = client.get(f"/business/explorer/table?sort={sort}&dir={d}")
            assert r.status_code == 200 and 'class="sortable sorted"' in r.text, (sort, d)
    html = client.get("/business/explorer/table?view=feasibility").text  # old links land on the matching sort
    assert 'aria-sort="descending"' in html and "Fit score</a>" not in html
    assert "higher is better" in html and "Evidence" not in html.split("<thead>")[1].split("</thead>")[0]
    assert "How the type and score work" in html
    assert any(f">{b}</span>" in html for b in ("Quick win", "New chip", "Niche"))
    assert client.get("/business/explorer/table?s=niche").status_code == 200


def test_keep_set_aside_and_restore(client):
    first = re.search(KEEP, client.get("/business/explorer/table").text).group(1)
    r = client.post("/business/decision", data={"fn": first, "status": "keep", "back": "/business/explorer"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"] == "/business/explorer"
    assert "✓ kept" in client.get("/business/explorer/table").text
    client.post("/business/decision", data={"fn": first, "status": "set_aside", "note": "revisit 2027"})
    html = client.get("/business/explorer/table").text
    aside = html.split('class="h-aside"')[1]
    assert "revisit 2027" in aside and "1 not pursued" in aside
    client.post("/business/decision", data={"fn": first, "status": "clear"})
    assert "0 not pursued" in client.get("/business/explorer/table").text
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
    page = client.get("/business/explorer/table").text
    fn = re.search(KEEP, page).group(1)
    form = {"origin": "explorer", "key": fn, "title": "Candidate one", "fn": fn, "back": "/business/explorer"}
    assert client.post("/business/shortlist", data=form, follow_redirects=False).status_code == 303
    client.post("/business/shortlist", data=form)  # pushing twice keeps one
    client.post("/business/shortlist", data={"origin": "idea", "key": "Wireless audio for e-bikes"})
    html = client.get("/business/shortlist").text
    assert (
        html.count("<b>Candidate one</b>") == 1
        and "Wireless audio for e-bikes" in html
        and "★ on the shortlist" in client.get("/business/explorer/table").text
    )
    # the button's script posts for JSON and stays on the page; the count feeds the badge on the tab
    count = client.get("/api/shortlist/count").json()["count"]
    r = client.post(
        "/business/shortlist", data={"origin": "idea", "key": "Second idea"}, headers={"Accept": "application/json"}
    )
    assert r.status_code == 200 and r.json() == {"count": count + 1}
    item = re.search(r'value="shortlist:(\d+)"', html).group(1)  # candidates are scheduled for a case review
    new = client.get(f"/business/cases/new?shortlist={item}").text
    assert f'name="shortlist" value="{item}"' in new
    r = client.post("/business/cases", data={"title": "Analysed", "shortlist": item}, follow_redirects=False)
    assert r.status_code == 303
    assert "Open case: Analysed" in client.get("/business/shortlist").text
    assert client.post("/business/shortlist", data={"origin": "bogus", "key": "x"}).status_code == 400


def test_overview_retired_explorer_grouped_with_rf_band_gaps(client):
    r = client.get("/business?co=skyworks", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/business/opportunities?co=skyworks"  # one hop
    r = client.get("/business?sort=reach&co=qorvo", follow_redirects=False)
    assert r.headers["location"] == "/business/explorer/table?sort=reach&co=qorvo"
    from app.services import opportunity as op

    bands = op.rf_band_rows()
    assert all(b["gap_type"] == "band_gap" and b["group"] == "RF & radio" and "@" in b["key"] for b in bands)
    html = client.get("/business/explorer/table").text
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


def test_gaps_and_new_technology_under_opportunities(client):
    """Owner, 23 Oct 2026: gaps and new technology moved out of Cross-sell into Opportunities; the old explorer URL
    lands there, sorted links keep landing on the detailed table."""
    r = client.get("/business/explorer", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"].startswith("/business/opportunities")
    r = client.get("/business/explorer?sort=score", follow_redirects=False)
    assert r.headers["location"] == "/business/explorer/table?sort=score"
    html = client.get("/business/opportunities").text
    for anchor, title in (("gaps", "Gaps to fill"), ("new", "New technology")):
        assert f'id="{anchor}"' in html and title in html
    assert 'id="sell"' not in html and html.count('class="csg-card"') > 5
    assert 'href="/business/explorer/table?co=combined"' in html
    from app.web import nav

    assert nav.place("/business/opportunities") == ("opportunities", "/business/opportunities")
    assert nav.place("/business/explorer/table") == ("opportunities", "/business/opportunities")
    assert nav.place("/business/evidence/rf_switch") == ("opportunities", "/business/opportunities")
    opp = dict((k, items) for k, _, items in nav.NAV)["opportunities"]
    assert [i[1] for i in opp] == ["/business/opportunities", "/business/competitors", "/business/risks"]


def test_cross_sell_is_bottom_up_per_system(client):
    """Owner, 23 Oct 2026: Cross-sell shows which of our parts go together in the selected system, sub-system or
    diagram; without a selection it offers the systems and what we sell across the library."""
    from app.services import systems as sy
    from app.web import nav

    html = client.get("/blocks/cross-sell").text
    assert "Pick a system" in html and 'id="gaps"' not in html and 'href="/business/opportunities"' in html
    assert 'href="/blocks/cross-sell?co=combined&amp;system=automotive&amp;sub=car-radio"' in html
    page = client.get("/blocks/cross-sell?system=automotive&sub=car-radio").text
    assert "Automotive › Car radio" in page and "Our parts that go together" in page
    assert f"{len(sy.sub('automotive', 'car-radio')['idx'])} diagrams" in page
    same = client.get("/blocks/cross-sell?sel=automotive:car-radio").text  # the picker's form
    assert "Automotive › Car radio" in same
    i = sy.sub("automotive", "car-radio")["idx"][0]
    one = client.get(f"/blocks/cross-sell?system=automotive&sub=car-radio&template={i}").text
    assert "1 diagram<" in one and "Open the diagram" in one
    assert client.get("/blocks/cross-sell?sel=automotive:car-radio&template=").status_code == 200  # "all diagrams"
    assert nav.place("/blocks/cross-sell") == ("systems", "/blocks/cross-sell")
    assert nav.place("/business/attach") == ("systems", "/blocks/cross-sell")
    assert 'aria-current="page" class="on">By part<' in client.get("/business/attach").text
    assert 'aria-current="page" class="on">Skyworks + Qorvo portfolio<' in client.get("/portfolio").text
