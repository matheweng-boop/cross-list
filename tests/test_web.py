import csv
import io

from openpyxl import load_workbook


def ids(client, *mpns):
    out = []
    for m in mpns:
        out.append(next(p["id"] for p in client.get(f"/api/parts?q={m}").json() if p["mpn"] == m))
    return out


def test_pages_render(client):
    for url in ["/", "/?role=&q=SA", "/compare", "/lifecycle", "/rules"]:
        r = client.get(url)
        assert r.status_code == 200, url
        assert "synthetic" in r.text.lower()


def test_part_page_shows_four_categories_and_top5(client):
    (ref,) = ids(client, "SR8641")
    html = client.get(f"/parts/{ref}").text
    for label in ["FFF", "Pin-to-pin", "Upgrade", "Downgrade", "Top 5 differences", "Download Excel"]:
        assert label in html


def test_hide_eol_filter(client):
    (ref,) = ids(client, "SR8641")
    assert "SA7741X" in client.get(f"/parts/{ref}").text
    assert "SA7741X" not in client.get(f"/parts/{ref}?hide_eol=true").text


def test_missing_part_404(client):
    assert client.get("/parts/99999").status_code == 404


def test_cross_excel_highlights_differences(client):
    ref, cand = ids(client, "SR8641", "SB8441")
    r = client.get(f"/cross/{ref}/{cand}.xlsx")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    ws = load_workbook(io.BytesIO(r.content)).active
    rows = {row[1].value: row for row in ws.iter_rows() if len(row) >= 5 and row[1].value}
    default_out = rows["Default output"]
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
    assert set(data) == {"fff", "p2p", "upgrade", "downgrade"}
    assert len(data["fff"][0]["top_differences"]) <= 5


def test_feedback_accept_and_undo(client):
    ref, cand = ids(client, "SR8641", "SC141")
    html = client.get(f"/parts/{ref}").text
    assert "FFF – needs review" in html and "Accept as FFF" in html
    r = client.post(
        "/feedback", data={"reference_id": ref, "candidate_id": cand, "verdict": "accept", "note": "OK at 100 Mbps"}
    )
    assert r.status_code == 200  # redirect followed back to the part page
    html = client.get(f"/parts/{ref}").text
    assert "FFF – accepted" in html and "OK at 100 Mbps" in html and "Local user" in html
    data = client.get(f"/api/parts/{ref}/crosses").json()
    sc141 = next(x for x in data["fff"] if x["candidate"]["label"].endswith("SC141"))
    assert sc141["fff_status"] == "accepted" and sc141["feedback"]["note"] == "OK at 100 Mbps"
    client.post("/feedback", data={"reference_id": ref, "candidate_id": cand, "verdict": "clear"})
    assert "FFF – needs review" in client.get(f"/parts/{ref}").text


def test_feedback_reject_moves_out_of_fff(client):
    ref, cand = ids(client, "SR8641", "SC141")
    client.post("/feedback", data={"reference_id": ref, "candidate_id": cand, "verdict": "reject", "note": "too slow"})
    data = client.get(f"/api/parts/{ref}/crosses").json()
    assert all(not x["candidate"]["label"].endswith("SC141") for x in data["fff"])
    assert "Rejected as FFF (1)" in client.get(f"/parts/{ref}").text
    assert (
        client.post("/feedback", data={"reference_id": ref, "candidate_id": cand, "verdict": "maybe"}).status_code
        == 400
    )


def test_partial_part_numbers(client):
    from app.services.queries import normalize_pn

    assert normalize_pn(" si-86 41 ") == "SI8641"
    rows = client.get("/api/parts?q=8641").json()
    mpns = [p["mpn"] for p in rows]
    assert "SR8641" in mpns and "SD8641A" in mpns and "SB8641N" in mpns
    assert [p["mpn"] for p in client.get("/api/parts?q=sr86*41").json()][:1] == ["SR8641"]  # wildcard, prefix first
    assert {p["mpn"] for p in client.get("/api/parts?q=sa-77").json()} >= {"SA7741", "SA7740N", "SA7721"}


def test_search_page_covers_all_companies(client):
    html = client.get("/?q=7741").text
    assert "SA7741" in html  # competitor part found without changing the filter
    assert "SR8641" in client.get("/").text and "SA7741X" not in client.get("/").text  # no query: references only


def test_suggestions_fragment(client):
    html = client.get("/suggest?q=864").text
    assert "SR8641" in html and "suggest-list" in html and "<html" not in html
    assert client.get("/suggest?q=8").text.strip() == ""  # at least two characters
    assert "No part numbers contain" in client.get("/suggest?q=zzzz").text


def test_part_page_groups_suggestions_by_company(client):
    (ref,) = ids(client, "SR8641")
    html = client.get(f"/parts/{ref}").text
    assert "By company" in html and "SynAlpha" in html and 'class="strip"' in html
    only = client.get(f"/parts/{ref}?company=SynBeta").text
    section = only.split('id="cat-fff"')[1]
    assert "SynBeta SB8441" in section and "SynAlpha SA7741" not in section


def test_competitor_part_finds_reference_replacements(client):
    (comp,) = ids(client, "SA7741X")  # identical to SR8641, but obsolete
    html = client.get(f"/parts/{comp}").text
    assert "Skyworks replacements" in html and "Include other competitors" in html
    data = client.get(f"/api/parts/{comp}/crosses").json()
    fff = [x["candidate"]["label"] for x in data["fff"]]
    assert fff == ["SynRef SR8641"]
    every = {x["candidate"]["label"] for cat in data.values() for x in cat}
    assert all(label.startswith("SynRef") for label in every)  # only reference parts by default
    wide = client.get(f"/parts/{comp}?scope=all").text
    assert "Crosses with all manufacturers" in wide and "SynBeta SB8441" in wide


def test_reference_part_page_unchanged(client):
    (ref,) = ids(client, "SR8641")
    html = client.get(f"/parts/{ref}").text
    assert "<h2>Crosses</h2>" in html and "Skyworks replacements" not in html


def test_suggestions_mark_competitor_parts(client):
    html = client.get("/suggest?q=7741").text
    assert "find Skyworks part" in html
