"""Future growth (owner feedback 21 Oct): the first question to the business unit, the "Learn about this" tab with
knowledge-base links, the schedule-for-business-case-review queue (shared POST /business/schedule contract) and the
per-field hints on business case pages."""

import glob
import html
import json
import re

from sqlalchemy import func, select

from app.models import ScheduledReview
from app.services import prelim, rf_notes
from app.services import reports as rp


def test_every_report_has_an_opener_and_learn_levels():
    for r in rp.reports():
        o = r.get("bu_opener") or {}
        assert o.get("question") and o.get("pros") and o.get("cons"), r["slug"]
        assert [x["age"] for x in rp.learn(r)] == list(rp.LEARN_AGES), r["slug"]
        assert all(x["text"] and x["title"] for x in rp.learn(r))
        assert r.get("learn_links"), r["slug"]


def test_learn_links_point_to_real_knowledge_pages(client):
    notes = {t["id"] for _, _, ts in rf_notes.by_category() for t in ts}
    js = "".join(open(f).read() for f in ["app/web/static/visuals.js", *sorted(glob.glob("app/web/static/vz/*.js"))])
    visuals = set(re.findall(r'id: "([a-z0-9]+)", group:', js))
    for r in rp.reports():
        for k in r["learn_links"]:
            path, _, anchor = k["href"].partition("#")
            assert path.startswith(("/library", "/rf-notes", "/engineering", "/visuals")), k
            assert client.get(path).status_code == 200, k
            if path == "/rf-notes":
                assert f'id="{anchor}"' in client.get(path).text, k
                assert anchor in notes
            if path == "/visuals":
                assert anchor in visuals, k


def test_report_page_shows_learn_tab_and_opener_first(client):
    page = client.get("/business/reports/auto-ntn-pa").text
    r = rp.report("auto-ntn-pa")
    q = html.escape(r["bu_opener"]["question"], quote=False).replace("'", "&#39;")
    assert "Learn about this" in page and "Age 25" in page and 'href="/library/tcu_rf"' in page
    assert "First question for the business unit" in page
    section = page.split('id="questions-to-ask"', 1)[1]
    first_bu = html.escape(prelim.raw("auto-ntn-pa")["questions"]["bu"][0]["text"], quote=False)
    assert "Start here:" in section and section.index("Start here:") < section.index(first_bu.replace("'", "&#39;"))
    assert q[:60] in page
    # a report without a case records the opener's answer too
    url = "/business/reports/filters-1-11ghz"
    assert "First question for the business unit" in client.get(url).text
    resp = client.post(f"{url}/react", data={"key": rp.OPENER_ID, "verdict": "answer", "comment": "Yes, BU likes it"},
                       follow_redirects=False)  # fmt: skip
    assert resp.status_code == 303
    assert "Yes, BU likes it" in client.get(url).text


def test_iso7821dww_research_idea_follows_the_layout(client):
    r = rp.report("iso7821dww-isolation")
    assert r and "ISO7821DWW" in r["tags"] and r["kind"] == "report"
    page = client.get("/business/reports/iso7821dww-isolation").text
    heads = [page.index(h) for h in ("1. Adjacent products and technologies", "2. Where else we see opportunities",
                                     "3. Market trend", "Open questions")]  # fmt: skip
    assert heads == sorted(heads)
    assert "/engineering/creepage_mm" in page and "/visuals#creep" in page


def test_schedule_contract(client, session):
    data = {"title": "ISO7821DWW in HEV/EV on-board charger", "source": "prelim:42", "note": "from the walk",
            "part": "ISO7821DWW", "volume": "200000", "next": "/parts?x=1"}  # fmt: skip
    r = client.post("/business/schedule", data=data, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/parts?x=1"
    r = client.post("/business/schedule", data={**data, "note": "updated", "next": "//evil.example"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"] == "/business/cases#scheduled"
    assert session.scalar(select(func.count(ScheduledReview.id))) == 1
    item = session.scalar(select(ScheduledReview))
    assert (item.note, item.part, item.volume) == ("updated", "ISO7821DWW", "200000")
    assert client.post("/business/schedule", data={"title": " "}).status_code == 400
    assert client.post("/business/schedule", data={"title": "x"}, headers={"accept": "application/json"}).json()["id"]
    for page in ("/business/cases", "/business/shortlist"):
        assert "ISO7821DWW in HEV/EV on-board charger" in client.get(page).text


def test_research_to_schedule_to_case(client, session):
    reports = client.get("/business/reports").text
    assert reports.count("Schedule business case review") >= len(rp.reports())
    client.post("/business/schedule", data={"title": "NTN", "source": "research:auto-ntn-pa",
                                            "next": "/business/reports"})  # fmt: skip
    assert "✓ scheduled for business case review" in client.get("/business/reports/auto-ntn-pa").text
    item = session.scalar(select(ScheduledReview).where(ScheduledReview.source == "research:auto-ntn-pa"))
    new = client.get(f"/business/cases/new?schedule={item.id}").text
    assert 'name="schedule"' in new and "Scheduled from Research &amp; ideas: NTN" in new
    r = client.post("/business/cases", data={"title": "NTN case", "schedule": str(item.id)}, follow_redirects=False)
    case_id = int(r.headers["location"].rsplit("/", 1)[1])
    session.expire_all()
    item = session.get(ScheduledReview, item.id)
    assert (item.case_id, item.status) == (case_id, "started")
    assert f'href="/business/cases/{case_id}">Open business case' in client.get("/business/cases").text
    client.post(f"/business/cases/{case_id}", data={"act": "delete"})
    session.expire_all()
    assert session.get(ScheduledReview, item.id).status == "scheduled"
    item_id = item.id
    client.post(f"/business/schedule/{item_id}", data={"act": "remove"})
    session.expire_all()
    assert session.get(ScheduledReview, item_id) is None


def _hints(page: str) -> dict:
    m = re.search(r'<script type="application/json" id="sg-data">(.*?)</script>', page, re.S)
    return json.loads(html.unescape(m.group(1)))


def test_case_fields_get_hints_from_parts_crosses_and_research(client):
    title = "ISO7821DWW%20in%20HEV%2FEV%20on-board%20charger"
    page = client.get(f"/business/cases/new?fn=digital_isolator&title={title}").text
    assert "/static/suggest.js" in page and 'data-field="specs"' in page
    hints = _hints(page)
    assert hints["applications"] and hints["markets"] and hints["competitors"]
    assert any("iso7821dww-isolation" in json.dumps(v) or "ISO7821DWW" in json.dumps(v) for v in hints.values())
    research = [x for x in hints.get("question", []) if "ISO7821DWW" in x["text"]]
    assert research, "the ISO7821DWW research idea should be suggested for the decision"
