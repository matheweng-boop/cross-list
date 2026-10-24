"""Owner comments of 22 Oct 2026 (daily update): precision fixes, layout changes and new sections."""

from pathlib import Path

from tests.conftest import ids

ROOT = Path(__file__).resolve().parents[1]


def test_sso8_creepage_is_at_least_not_measured():
    files = [
        ROOT / "data/business/cases/hv-extra-wide-isolation.yaml",
        ROOT / "app/web/templates/business/reports/iso7821dww-isolation.html",
        ROOT / "app/web/templates/business/reports/hv-extra-wide-isolation.background.html",
        ROOT / "data/business/reports.yaml",
    ]
    for f in files:
        text = f.read_text()
        assert "measured 8.5" not in text and "measures 8.5" not in text and "8.5 mm measured" not in text, f
    bg = files[2].read_text()
    assert "7. Summary and Future Outlook" in bg
    assert "Skyworks is currently developing a new ultra-wide-body (UWB) SOIC package" in bg


def test_walk_market_size_points_to_tam_and_is_not_logged(client, session, real):
    from sqlalchemy import select

    from app.models import SiteFeedback
    from app.services import walk

    comp = ids(client, "ISO7741DBQR")
    html = client.get(f"/parts/{comp}/walk?upto=5").text
    assert "ASP and application volumes" not in html
    assert "no public market-size estimate yet" in html or "public estimate" in html
    texts = session.scalars(select(SiteFeedback.text).where(SiteFeedback.author == walk.AUTHOR)).all()
    assert not any("market size" in t or "market-size" in t for t in texts)


def test_no_feedback_sections_at_the_bottom(client):
    caps = client.get("/business/capabilities").text
    assert 'action="/business/capabilities/feedback"' not in caps and 'id="feedback"' not in caps
    rep = client.get("/business/reports/filters-1-11ghz").text
    assert "/ask" not in rep and 'class="fb-open"' in rep  # only the floating button
    # old form targets still answer
    r = client.post("/business/capabilities/feedback", data={"kind": "idea", "text": "x"}, follow_redirects=False)
    assert r.status_code == 303


def test_walk_cards_short_heading_full_text_and_next_on_top(client, real):
    from app.services import walk

    tws = "True-wireless (TWS) earbuds with charging case"
    assert walk.short_name(tws) == "True-wireless earbuds with charging case"
    assert walk.short_name("AC solid-state circuit breaker (SSCB) with air-gap relay, AC/DC current sensing") == (
        "AC solid-state circuit breaker"
    )
    comp = ids(client, "ISO7741DBQR")
    html = client.get(f"/parts/{comp}/walk").text
    assert html.index("Next: 3 Best of ours around it") < html.index('id="step-1"')  # with the step buttons on top
    assert html.count("Next: 3") == 1
    assert 'class="link-btn walk-name"' in html and 'id="walk-full"' in html
    assert "more</li>" not in html  # nothing cut off
    css = (ROOT / "app/web/static/app.css").read_text()
    assert "text-overflow: ellipsis; white-space: nowrap; }\n.walk-also" not in css


def test_band_tables_do_not_scroll(client):
    rf = client.get("/business/rf-coverage").text
    assert '<div class="fit-wrap"><table class="rf-matrix stack-table rf-small">' in rf and 'data-label="' in rf
    pf = client.get("/portfolio").text
    assert 'class="pf-band small stack-table"' in pf
    css = (ROOT / "app/web/static/app.css").read_text()
    assert ".stack-table thead { display: none; }" in css


def test_agree_disagree_shown_without_react_click(client):
    html = client.get("/library/v2x_frontend").text
    assert 'class="pc-react pc-inline"' in html and ">Agree</button>" in html and ">Disagree</button>" in html
    assert '<details class="pc-react"' not in html and ">react<" not in html
    for path in ("app/web/templates/business/_prelim.html", "app/web/templates/reviews/detail.html"):
        src = (ROOT / path).read_text()
        assert '<details class="pc-react"' not in src and "pc-inline" in src
    r = client.post("/library/v2x_frontend/react", data={"item": "x", "verdict": "agree"}, follow_redirects=False)
    assert r.status_code in (303, 400, 404)


def test_markets_filters_compact_with_more_filters(client):
    html = client.get("/business/markets").text
    assert 'class="more-filters"><summary class="small">More filters' in html
    head, more = html.split('class="more-filters"', 1)
    assert ">Leap</span>" in head and "Qualify for automotive" in more.split("</details>")[0]
    assert 'class="more-filters" open' in client.get("/business/markets?view=multi").text


def test_feedback_window_has_dictation(client):
    html = client.get("/").text
    assert '<p class="fb-dict small" hidden>' in html and "fb-mic" in html  # shown by the script only if supported
    js = (ROOT / "app/web/static/feedback.js").read_text()
    assert "window.SpeechRecognition || window.webkitSpeechRecognition" in js and "if (!SR || !root) return;" in js


def test_research_lists_product_ideas_as_feasibility_studies(client):
    html = client.get("/business/reports").text
    assert "Product idea" in html and "Feasibility study" in html
    assert ">Report</span>" not in html and ">Type</span>" not in html  # no report / idea split
    assert ">Application</a>" in html and ">Feasibility</a>" in html
    assert "Reports <small" not in client.get("/business/reports?view=feasibility").text
    page = client.get("/business/reports/filters-1-11ghz").text
    assert "Feasibility study" in page and ">Report</span>" not in page
    r = client.post("/business/schedule", data={"title": "Filters", "source": "research:filters-1-11ghz"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    assert "Business case review (scheduled)" in client.get("/business/reports/filters-1-11ghz").text


def test_business_case_asks_feasibility_price_manufacturing_markets_competition(client):
    import re

    from app.services import cases

    keys = [k for k, *_ in cases.FIELDS]
    for k in ("feasibility", "price", "manufacturing", "inhouse", "markets", "market_size", "competitors",
              "competitor_prices", "competitor_share", "anything_else"):  # fmt: skip
        assert k in keys, k
    page = client.get("/business/cases/new?fn=pol_ldo").text
    assert "Is the technology feasible?" in page and "Anything else to add?" in page
    assert 'data-field="market_size"' in page and "Manufacturing locations" in page
    r = client.post("/business/cases", data={"title": "LDO case", "fn": "pol_ldo", "feasibility": "Existing die",
                                              "manufacturing": "Open: not public", "anything_else": "Add export"})
    assert r.status_code in (200, 303)
    cid = int(re.search(r"/business/cases/(\d+)", client.get("/business/cases").text).group(1))
    brief = client.get(f"/business/cases/{cid}/brief.md").text
    assert "Existing die" in brief and "Manufacturing" in brief and "Anything else to add?" in brief
    assert "public prices" in brief and "share of the" in brief
    sg = re.search(r'<script type="application/json" id="sg-data">(.*?)</script>', page, re.S)
    assert sg and "market_size" in sg.group(1)  # a hint for market size (estimate or "add one on TAM estimates")


def test_price_estimate_variants_sop_and_break_rows(client, session, real, part):
    from datetime import date

    html = client.get("/pricing/estimate", params={"name": "ISO7741"}).text
    assert 'class="pe-variants"' in html and "ISO7741DBQR" in html and "ISO7741DWR" in html
    assert 'class="outline small-btn pe-add"' in html and ">or</span>" in html and 'name="bq"' in html
    p = part("ISO7741DWR")
    p.release_date = date(2016, 3, 1)
    session.commit()
    html = client.get("/pricing/estimate", params={"name": "ISO7741DWR"}).text
    assert 'name="sop" type="number" min="1980" max="2050" value="2016"' in html
    assert "year of the datasheet&#39;s first revision" in html or "year of the datasheet's first revision" in html
    # rows and pasted text together make the breaks
    q = [("family", "digital_isolator"), ("name", "X1"), ("bq", "1"), ("bp", "3.10"), ("bq", "1000"), ("bp", "1.90"),
         ("breaks", "100 2.50")]  # fmt: skip
    html = client.get("/pricing/estimate", params=q).text
    assert 'id="price-model"' in html and 'value="1000"' in html and "100 2.50" in html


def test_library_focus_areas_and_area_requests(client, session):
    from datetime import date

    from app.services import blocks, inbox

    assert blocks.focus_of("Quadcopter drone flight controller", "", "Consumer") == ["drones"]
    assert blocks.focus_of("5G smartphone modem-to-antenna", "", "Consumer") == ["cellular"]
    assert "automotive" in blocks.focus_of("Body controller", "", "Automotive")
    assert blocks.focus_of("Cell site gateway router", "Communications equipment", "Industrial") == ["cellular"]
    assert blocks.focus_of("Smart thermostat", "Appliances & building", "Consumer") == []
    html = client.get("/blocks").text
    order = [html.index(f'id="area-{k}"') for k in ("automotive", "datacenter", "drones", "cellular")]
    assert order == sorted(order) and order[-1] < html.index('id="other-areas"')
    assert '<details class="lib-other" id="other-areas">' in html and 'action="/blocks/area-request"' in html
    r = client.post("/blocks/area-request", data={"area": "Robotics", "why": "Humanoid robots"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.post("/blocks/area-request", data={"area": " "}).status_code == 400
    assert "Robotics" in client.get("/manage/reviews?type=area").text
    page = client.get("/blocks/area-requests").text
    assert "Robotics" in page and "Humanoid robots" in page
    text = inbox.collect(session, date.today())
    assert "## Application area requests" in text and "Robotics" in text and "why: Humanoid robots" in text
    rid = int(page.split('action="/blocks/area-requests/')[1].split('"')[0])
    r = client.post(f"/blocks/area-requests/{rid}", data={"status": "planned"}, follow_redirects=False)
    assert r.status_code == 303
    assert client.post(f"/blocks/area-requests/{rid}", data={"status": "x"}).status_code == 400
    daily = (ROOT / "docs/daily_update.md").read_text()
    assert ("Deep dives for data centres and drones (main areas outside automotive and cellular): a few documents per "
            "run") in daily
