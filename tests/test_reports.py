"""Pre-lim product ideas and reports: the list, a report page, filters and unknown slugs."""

from app.services import reports as rp


def test_registry_entries_have_a_body():
    items = rp.reports()
    assert items and all(r["kind"] in rp.KINDS and r["status"] in rp.STATUSES for r in items)
    assert [r["date"] for r in items] == sorted((r["date"] for r in items), reverse=True)


def test_list_links_to_each_report(client):
    page = client.get("/business/reports")
    assert page.status_code == 200
    for r in rp.reports():
        assert f'href="/business/reports/{r["slug"]}"' in page.text
    assert client.get("/business/reports?kind=idea").status_code == 200


def test_report_page_and_unknown_slug(client):
    page = client.get("/business/reports/filters-1-11ghz")
    assert page.status_code == 200 and 'class="rpt"' in page.text and "Standalone filter" in page.text
    assert client.get("/business/reports/no-such-report").status_code == 404


def test_question_is_saved_reviewed_and_answered(client):
    url = "/business/reports/filters-1-11ghz"
    r = client.post(f"{url}/ask", data={"text": "Which Trans-Tech ceramic filters cover the S band?"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"].endswith("#questions")
    assert "Which Trans-Tech ceramic filters" in client.get(url).text
    assert client.post(f"{url}/ask", data={"text": "  "}).status_code == 400
    assert client.post("/business/reports/no-such-report/ask", data={"text": "x"}).status_code == 404

    client.post(f"{url}/ask", data={"text": "What Trans-Tech ceramic filters cover S band?"})
    page = client.get("/business/reports/questions")
    assert page.status_code == 200 and "Possible duplicate of" in page.text
    assert "like #" in client.get("/business/reports/questions.txt").text

    qid = int(page.text.split('id="q', 2)[1].split('"')[0])
    r = client.post(f"/business/reports/questions/{qid}", data={"status": "good", "answer": "Two, both 2.4 GHz."},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    assert "Two, both 2.4 GHz." in client.get(url).text
    assert client.post(f"/business/reports/questions/{qid}", data={"status": "bogus"}).status_code == 400
    assert client.post("/business/reports/questions/99999", data={"status": "good"}).status_code == 404


def test_background_page_only_when_present(client):
    has = rp.has_background("filters-1-11ghz")
    assert client.get("/business/reports/filters-1-11ghz/background").status_code == (200 if has else 404)


def test_reports_grouped_by_type_and_feasibility(client):
    from app.services import reports as rp

    ideas = [r for r in rp.reports() if r["kind"] == "idea"]
    assert ideas and all(r["feasibility"] in rp.FEASIBILITY and r.get("feasibility_why") for r in ideas)
    page = client.get("/business/reports").text
    assert "Group by" in page and "Suggested next topics" in page
    assert all(f'<h2 class="rp-group">{t} ' in page for t in {r["app_type"] for r in rp.reports()})
    page = client.get("/business/reports?view=feasibility").text
    assert "Close to the portfolio" in page and "Reports" in page
