import csv
import io
import json

from openpyxl import load_workbook


def ids(client, *mpns):
    out = []
    for m in mpns:
        out.append(next(p["id"] for p in client.get(f"/api/parts?q={m}").json() if p["mpn"] == m))
    return out


def test_pages_render(client):
    for url in ["/parts", "/parts?role=&q=SA", "/compare", "/lifecycle", "/rules"]:
        r = client.get(url)
        assert r.status_code == 200, url
        assert "synthetic" in r.text.lower()


def test_part_page_shows_cross_types_and_top5(client):
    (ref,) = ids(client, "SR8641")
    html = client.get(f"/parts/{ref}").text
    for label in ["Drop-in", "Functional", "Package eq.", "P2P", "Top 5 differences", "Download Excel"]:
        assert label in html


def test_hide_eol_filter(client):
    (ref,) = ids(client, "SR8641")
    assert "SA7741X" in client.get(f"/parts/{ref}?all=true").text
    assert "SA7741X" not in client.get(f"/parts/{ref}?hide_eol=true&all=true").text


def test_missing_part_404(client):
    assert client.get("/parts/99999").status_code == 404


def test_cross_excel_highlights_differences(client):
    ref, cand = ids(client, "SR8641", "SB8441")
    r = client.get(f"/cross/{ref}/{cand}.xlsx")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    ws = load_workbook(io.BytesIO(r.content)).active
    rows = {row[1].value: row for row in ws.iter_rows() if len(row) >= 5 and row[1].value}
    default_out = rows["Output type (default state)"]
    assert default_out[4].value == "different"
    assert default_out[3].fill.fgColor.rgb.endswith("FFEB9C")


def test_cross_csv(client):
    ref, cand = ids(client, "SR8641", "SA7741")
    rows = list(csv.reader(io.StringIO(client.get(f"/cross/{ref}/{cand}.csv").text)))
    assert rows[0][0] == "Priority"
    iso = next(r for r in rows if r[1] == "Isolation rating")
    assert iso[2:] == ["5 kVrms", "5.7 kVrms", "better"]


def test_compare_selected_parts_priority_1_and_2_only(client):
    a, b, c = ids(client, "SR8641", "SA7741", "SC141")
    html = client.get(f"/compare?pick={a}&pick={b}&pick={c}&baseline={a}").text
    assert "CMTI" in html and "Data rate" in html  # P1 / P2
    assert "Pulse width distortion" not in html  # P3 excluded
    data = client.get(f"/api/compare?ids={a},{b},{c}").json()
    assert {r["priority"] for r in data["rows"]} == {1, 2}


def test_compare_downloads(client):
    a, b = ids(client, "SR8233", "SA21520")
    x = client.get(f"/compare.xlsx?ids={a},{b}&baseline={a}")
    ws = load_workbook(io.BytesIO(x.content)).active
    assert any(c.value == "Propagation delay (max)" for row in ws.iter_rows() for c in row)
    text = client.get(f"/compare.csv?ids={a},{b}").text
    assert "SynAlpha SA21520" in text
    assert client.get("/compare.csv?ids=").status_code == 400


def test_api_crosses(client):
    (ref,) = ids(client, "SR8286")
    data = client.get(f"/api/parts/{ref}/crosses").json()
    assert set(data) == {"fff", "functional", "package"}
    assert len(data["fff"][0]["top_differences"]) <= 5


def test_reject_fff_and_undo(client):
    ref, cand = ids(client, "SR8641", "SC141")
    html = client.get(f"/parts/{ref}").text
    row = html.split(f'id="row-{cand}"')[1].split("</tr>")[0]
    assert "FFF" in row and "Reject as FFF" in html
    r = client.post(
        "/feedback", data={"reference_id": ref, "candidate_id": cand, "verdict": "reject", "note": "too slow"}
    )
    assert r.status_code == 200  # redirect followed back to the part page
    html = client.get(f"/parts/{ref}").text
    row = html.split(f'id="row-{cand}"')[1].split("</tr>")[0]
    assert "Package equivalent" in row and "FFF rejected in review" in row
    assert "too slow" in html and "Local user" in html
    data = client.get(f"/api/parts/{ref}/crosses").json()
    sc141 = next(x for x in data["package"] if x["candidate"]["label"].endswith("SC141"))
    assert sc141["fff_status"] == "rejected" and sc141["feedback"]["note"] == "too slow"
    client.post("/feedback", data={"reference_id": ref, "candidate_id": cand, "verdict": "clear"})
    data = client.get(f"/api/parts/{ref}/crosses").json()
    assert any(x["candidate"]["label"].endswith("SC141") for x in data["fff"])


def test_feedback_reject_moves_out_of_fff(client):
    ref, cand = ids(client, "SR8641", "SC141")
    client.post("/feedback", data={"reference_id": ref, "candidate_id": cand, "verdict": "reject", "note": "too slow"})
    data = client.get(f"/api/parts/{ref}/crosses").json()
    assert all(not x["candidate"]["label"].endswith("SC141") for x in data["fff"])
    assert "Rejected as FFF (1)" in client.get(f"/parts/{ref}").text
    for verdict in ("maybe", "accept"):
        r = client.post("/feedback", data={"reference_id": ref, "candidate_id": cand, "verdict": verdict})
        assert r.status_code == 400


def test_partial_part_numbers(client):
    from app.services.queries import normalize_pn

    assert normalize_pn(" si-86 41 ") == "SI8641"
    rows = client.get("/api/parts?q=8641").json()
    mpns = [p["mpn"] for p in rows]
    assert "SR8641" in mpns and "SD8641A" in mpns and "SB8641N" in mpns
    assert [p["mpn"] for p in client.get("/api/parts?q=sr86*41").json()][:1] == ["SR8641"]  # wildcard, prefix first
    assert {p["mpn"] for p in client.get("/api/parts?q=sa-77").json()} >= {"SA7741", "SA7740N", "SA7721"}


def test_search_page_covers_all_companies(client):
    html = client.get("/parts?q=7741").text
    assert "SA7741" in html  # competitor part found without changing the filter
    assert "SR8641" in client.get("/parts").text and "SA7741X" not in client.get("/parts").text


def test_suggestions_fragment(client):
    html = client.get("/suggest?q=864").text
    assert "SR8641" in html and "suggest-list" in html and "<html" not in html
    assert client.get("/suggest?q=8").text.strip() == ""  # at least two characters
    assert "No part numbers contain" in client.get("/suggest?q=zzzz").text


def test_result_table_filters_by_company(client):
    (ref,) = ids(client, "SR8641")
    html = client.get(f"/parts/{ref}").text
    assert 'class="company-filter"' in html and "SynAlpha (" in html
    table = (
        client.get(f"/parts/{ref}?company=SynBeta")
        .text.split('<table class="results">')[1]
        .split('<details class="category-view">')[0]
    )
    assert "SB8441" in table and "SA7741" not in table


def test_result_table_cross_types(client):
    ref, exact, better, info_worse, other_out, other_pins = ids(
        client, "SR8641", "SA7741X", "SD8641A", "SC141", "SB8441", "SB8641N"
    )
    def table(query):
        html = client.get(f"/parts/{ref}?all=true{query}").text
        return html, html.split('<table class="results">')[1].split('<details class="category-view">')[0]

    _, t = table("")  # non-automotive crosses of a non-automotive reference

    def row(pid, t=t):
        return t.split(f'id="row-{pid}"')[1].split("</tr>")[0]

    assert "Drop-in" in row(exact) and "spec-exact" in row(exact) and "p2p yes" in row(exact)
    assert "Drop-in" in row(info_worse) and "spec-exact" in row(info_worse)  # only priority 2 worse
    assert "Package eq." in row(other_out) and "p2p yes" in row(other_out)
    assert "Functional" in row(other_pins) and "p2p no" in row(other_pins)
    assert t.index(f'id="row-{info_worse}"') < t.index(f'id="row-{other_pins}"') < t.index(f'id="row-{other_out}"')
    _, auto = table("&grade=automotive")
    assert "Drop-in" in row(better, auto) and "spec-over" in row(better, auto)
    page = client.get(f"/parts/{ref}?type=functional").text
    only = page.split('<table class="results">')[1].split('<details class="category-view">')[0]
    assert f'id="row-{other_pins}"' in only and f'id="row-{other_out}"' not in only and f'id="row-{exact}"' not in only
    assert "Functional (1)" in page and "Drop-in (3)" in page


def test_deviation_setting(client):
    ref, cand = ids(client, "SR8640N", "SB8441")  # other package, one priority 1 deviation
    assert f'id="row-{cand}"' in client.get(f"/parts/{ref}?all=true").text
    assert f'id="row-{cand}"' not in client.get(f"/parts/{ref}?dev=0&all=true").text
    assert "SB8441" not in client.get(f"/parts/{ref}/replacements.csv?dev=0").text


def test_competitor_part_finds_reference_replacements(client):
    (comp,) = ids(client, "SA7741X")  # identical to SR8641, but obsolete
    html = client.get(f"/parts/{comp}").text
    assert "Suitable Skyworks parts" in html and "Include other competitors" in html
    data = client.get(f"/api/parts/{comp}/crosses").json()
    fff = [x["candidate"]["label"] for x in data["fff"]]
    assert fff == ["SynRef SR8641"]
    every = {x["candidate"]["label"] for cat in data.values() for x in cat}
    assert all(label.startswith("SynRef") for label in every)  # only reference parts by default
    wide = client.get(f"/parts/{comp}?scope=all").text
    assert "Replacements" in wide and "SB8441" in wide


def test_reference_part_page_unchanged(client):
    (ref,) = ids(client, "SR8641")
    html = client.get(f"/parts/{ref}").text
    assert "<h2>Replacements</h2>" in html and "Suitable Skyworks parts" not in html


def test_suggestions_mark_competitor_parts(client):
    html = client.get("/suggest?q=7741").text
    assert "find Skyworks part" in html


def test_finder_start_page(client):
    html = client.get("/").text
    assert "Find a Skyworks part" in html and 'action="/find"' in html


def test_find_full_part_number_opens_its_page(client):
    (comp,) = ids(client, "SA7741X")
    r = client.get("/find?q=sa-7741x", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/parts/{comp}"


def test_find_partial_lists_competitors_first(client):
    html = client.get("/find?q=7741").text
    assert "Tap a part to see suitable Skyworks parts" in html and "SA7741X" in html
    assert "No part numbers contain" in client.get("/find?q=ADUM1401").text
    assert client.get("/find?q=", follow_redirects=False).status_code == 303


def test_result_table_download(client):
    (ref,) = ids(client, "SR8641")
    r = client.get(f"/parts/{ref}/replacements.xlsx")
    ws = load_workbook(io.BytesIO(r.content)).active
    rows = [[c.value for c in row] for row in ws.iter_rows()]
    header = next(i for i, row in enumerate(rows) if row[0] == "Part")
    verdicts = {row[0]: row[2] for row in rows[header + 1 :]}
    assert verdicts["SA7741"] == "Drop-in (FFF)" and verdicts["SB8441"].startswith("Package equivalent")
    assert verdicts["SB8641N"].startswith("Functional equivalent")
    text = client.get(f"/parts/{ref}/replacements.csv?type=fff").text
    assert "SA7741" in text and "SB8641N" not in text


def test_cmti_explorer_page(client):
    ref, cand = ids(client, "SR8641", "SA7741")
    html = client.get(f"/engineering/cmti_kv_us?ids={ref},{cand}").text
    assert "CMTI" in html and "Datasheet guaranteed" in html and "Engineering estimate" in html
    devices = json.loads(html.split("data-devices='")[1].split("'")[0])
    assert [d["mpn"] for d in devices] == ["SR8641", "SA7741"]  # reference first
    assert all(isinstance(d["values"]["cmti_kv_us"], int | float) for d in devices)
    assert f'href="/engineering/cmti_kv_us?ids={ref},' in client.get(f"/parts/{ref}").text
    r = client.get(f"/impact?ids={ref},{cand}", follow_redirects=False)  # old address
    assert r.headers["location"] == f"/engineering/cmti_kv_us?ids={ref},{cand}"


def test_engineering_notes(client):
    html = client.get("/engineering").text
    assert "Engineering notes" in html and "/engineering/creepage_mm" in html
    for key in ("isolation_rating_kvrms", "viorm_vpk", "prop_delay_ns", "peak_sink_a", "enable_pins"):
        assert client.get(f"/engineering/{key}").status_code == 200, key
    assert client.get("/engineering/no_such_thing").status_code == 404


def test_deviation_links_open_the_note_with_both_parts(client):
    ref, cand = ids(client, "SR8640N", "SB8441")  # default output deviates
    page = client.get(f"/parts/{ref}?all=true").text
    link = f"/engineering/default_output?ref={ref}&amp;cand={cand}"
    assert link in page
    note = client.get(link.replace("&amp;", "&")).text
    assert "Your comparison" in note and "SR8640N" in note and "SB8441" in note and "different" in note


def test_grade_badges_and_filter(client):
    (ref,) = ids(client, "SR8641")
    html = client.get(f"/parts/{ref}").text
    assert "Non-automotive reference" in html and "All grades" not in html
    assert "SD8641A" not in html.split('<details class="category-view">')[0]  # non-automotive by default
    auto = client.get(f"/parts/{ref}?grade=automotive").text
    assert 'class="badge grade-auto"' in auto
    assert "SD8641A" in auto and "SC141" not in auto.split('<details class="category-view">')[0]
    ind = client.get(f"/parts/{ref}?grade=industrial").text
    assert "SD8641A" not in ind.split('<details class="category-view">')[0]


def test_automotive_reference_banner(client):
    (ref,) = ids(client, "SD8641A")
    html = client.get(f"/parts/{ref}").text
    assert "Automotive reference" in html and "Filter by grade" not in html


def test_sections_and_subheaders(client):
    for url, section, sub in [("/", "Crosses", "Find"), ("/parts", "Crosses", "Parts"),
                              ("/technical", "Technical discussions", "Technical"),
                              ("/engineering/cmti_kv_us", "Technical discussions", "Engineering notes"),
                              ("/broadcast", "Broadcast", "Overview"),
                              ("/broadcast/configurations", "Broadcast", "Configurations")]:  # fmt: skip
        html = client.get(url).text
        assert f'class="section-tab on" aria-current="true">{section}<' in html, url
        assert f'aria-current="page">{sub}<' in html, url
    assert 'id="global-search"' in client.get("/parts").text
    assert 'id="global-search"' not in client.get("/broadcast").text


def test_best_and_next_best_options_are_flagged(client):
    (ref,) = ids(client, "SR8641")
    html = client.get(f"/parts/{ref}").text.split('<details class="category-view">')[0]
    # best and next best per cross type, nothing else until "show all"
    assert html.count("Best drop-in</span>") == 1 and html.count("Next best drop-in</span>") == 1
    assert html.count('class="result-row') <= 6 and "Show all results (" in html and "Other options (" not in html
    full = client.get(f"/parts/{ref}?all=true").text.split('<details class="category-view">')[0]
    assert "Other options (" in full and full.count('class="result-row') > html.count('class="result-row')


def test_compare_page_layout_and_typed_parts(client):
    html = client.get("/compare?add=SR8641,SA7741").text
    assert html.index('name="add"') < html.index("compare-table") < html.index("Pick from the list")
    assert "SR864x" in html  # parts grouped by series
    assert "Not found" in client.get("/compare?add=NOSUCHPART").text


def test_series_and_sister_family_prefixes():
    from app.services.alternates import sister_prefix
    from app.web.routes import series_of

    assert series_of("SI86S641BE-IS2") == "SI86S64x" and series_of("NSI8241W1-DSWR") == "NSI824x"
    assert sister_prefix("SI8641BD-IS")[0] == "SI86S641" and sister_prefix("SI86S641BE-IS2")[0] == "SI8641"
    assert sister_prefix("SI8234AB-AM") is None
