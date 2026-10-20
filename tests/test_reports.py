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
