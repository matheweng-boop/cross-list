"""Lifetime demand seen (owner, 26 Oct 2026): volume steps on Cross a list › Update cross-lists for unknown and gap
parts, totals per part and function on owner pages only, Part review + Research & ideas entries, the business case
line and the owner-only scoring switch. Every safeguard of the owner's approval is checked here."""

import io
import re
from datetime import date, timedelta

import pytest
from openpyxl import load_workbook
from sqlalchemy import inspect, select

from app.config import get_settings
from app.models import Case, CrossListLookup, DemandEntry, TechReviewRequest
from app.services import crosslist_lookups as lk
from app.services import demand, inbox, scoring

LIST = "SC141\nSC142\nZZZ999"  # row 1 has a cross, row 2 is a gap part (digital isolator, no cross), row 3 unknown
FN = "digital_isolator"


@pytest.fixture(autouse=True)
def _answers(tmp_path, monkeypatch):
    f = tmp_path / "crosslist_lookups.yaml"
    f.write_text("parts: []\n")
    monkeypatch.setattr(lk, "_file", lambda: f)


def gap_fn(c, session) -> str:
    """A function on Opportunities › Gaps, with a 400k entry of its own (the isolator is not a gap there)."""
    page = c.get("/business/opportunities?show=all").text
    fn = re.search(r'/business/evidence/(\w+)', page.split('id="gaps"')[1]).group(1)
    session.add(DemandEntry(part="GAP123", fn=fn, volume=400_000, day=date.today(), lookup_id=0))
    session.commit()
    return fn


def send(c, **vols):
    return c.post("/cross-list/lookup", data={"parts": LIST, **vols}, follow_redirects=False)


def test_steps_are_the_documented_list_and_validated():
    assert demand.STEPS[:10] == tuple(range(100_000, 1_000_001, 100_000))
    assert demand.STEPS[10:] == (1_500_000, 2_000_000, 3_000_000, 5_000_000, 10_000_000, 20_000_000)
    assert [label for _, label in demand.CHOICES][9:12] == ["1M", "1.5M", "2M"]
    assert demand.parse_step("") is None and demand.parse_step("300000") == 300_000
    for bad in ("150000", "0", "-100000", "1e6", "100k", "30000000", "200000 ACME"):
        with pytest.raises(ValueError):
            demand.parse_step(bad)


def test_unknown_and_gap_rows_get_a_select_owner_only(owner, make_guest):
    page = owner.post("/cross-list", data={"parts": LIST}).text
    assert 'name="v2"' in page and 'name="v3"' in page and 'name="v1"' not in page  # the crossed part gets none
    assert 'form="cx-lookup-form"' in page and '<option value="">—</option>' in page
    assert all(f'<option value="{v}">' in page for v in demand.STEPS)
    assert "<textarea" in page and 'name="note"' not in page  # no free-text field for volumes
    guest, _ = make_guest()
    g = guest.post("/cross-list", data={"parts": LIST}).text
    assert 'name="v2"' not in g and "Lifetime volume" not in g


def test_send_stores_only_the_five_fields(client, session):
    r = send(client, v2="200000", v3="1500000")
    assert r.status_code == 303
    assert "recorded 2 lifetime volumes" in client.get(r.headers["location"]).text
    cols = {c["name"] for c in inspect(session.get_bind()).get_columns("demand_entries")}
    assert cols == {"id", "part", "fn", "volume", "day", "lookup_id"}
    look = session.scalar(select(CrossListLookup))
    assert [p["part"] for p in look.unknown_parts] == ["ZZZ999"]  # the gap part is not queued for lookup
    rows = session.scalars(select(DemandEntry).order_by(DemandEntry.id)).all()
    assert [(e.part, e.fn, e.volume, e.day, e.lookup_id) for e in rows] == [
        ("SC142", FN, 200_000, date.today(), look.id), ("ZZZ999", None, 1_500_000, date.today(), look.id)]


def test_server_refuses_other_fields_and_values(client, session):
    for extra in ({"v2": "150000"}, {"v2": "abc"}, {"v2": "200000", "note": "ACME"},
                  {"v2": "200000", "customer": "ACME"}, {"v2": "200000", "price": "0.85"}, {"v1": "200000"},
                  {"v9": "200000"}):  # fmt: skip
        assert send(client, **extra).status_code == 400, extra
    assert session.scalar(select(DemandEntry.id)) is None and session.scalar(select(CrossListLookup.id)) is None
    # a gap-only list with nothing chosen sends nothing
    assert client.post("/cross-list/lookup", data={"parts": "SC142"}).status_code == 400


def test_guest_cannot_send_and_sees_no_volumes(owner, make_guest, session, part):
    assert send(owner, v2="500000").status_code == 303
    guest, _ = make_guest()
    assert send(guest, v2="500000").status_code == 403
    assert session.scalar(select(CrossListLookup.id).where(CrossListLookup.id > 1)) is None
    pid = part("SC142").id
    gap_fn(owner, session)
    pages = [f"/parts/{pid}", f"/business/evidence/{FN}", "/business/opportunities?show=all", "/business/reports",
             "/reviews"]  # fmt: skip
    for url in pages:
        o, g = owner.get(url), guest.get(url)
        assert o.status_code == g.status_code == 200, url
        assert ("500k" in o.text or "400k" in o.text) and "Owner only" in o.text, url
        assert "400k" not in g.text, url
        assert "500k" not in g.text and "Owner only" not in g.text and "demand seen" not in g.text.lower(), url
    assert guest.get("/manage/requests?kind=lookup").status_code in (303, 403)
    assert guest.post("/manage/demand/scoring", data={"on": "1"}).status_code in (303, 403)
    assert not demand.scoring_on(session)


def test_totals_over_two_lookups_on_owner_pages(client, session, part):
    send(client, v2="200000")
    send(client, v2="1000000", v3="300000")
    t = demand.totals(session)
    assert (t.part("SC142").volume, t.part("SC142").n) == (1_200_000, 2)
    assert (t.fn(FN).volume, t.fn(FN).n) == (1_200_000, 2)
    assert t.no_fn["ZZZ999"].volume == 300_000
    assert "Lifetime demand seen: <b>1.2M</b> over 2 requests" in client.get(f"/parts/{part('SC142').id}").text
    assert "Demand seen (owner estimates): <b>1.2M</b> lifetime over 2 requests" in client.get(
        f"/business/evidence/{FN}").text  # fmt: skip
    gap_fn(client, session)
    assert "Demand seen: <b>400k</b> over 1 request" in client.get("/business/opportunities?show=all").text
    req = client.get("/manage/requests?kind=lookup&show=all").text
    assert "Lifetime volumes · 2" in req and "SC142" in req and "all requests: 1.2M lifetime over 2 requests" in req


def test_part_review_and_idea_entries(client, session):
    send(client, v2="200000")
    send(client, v2="1000000")
    reqs = session.scalars(select(TechReviewRequest)).all()
    assert [(r.mpn, r.question) for r in reqs] == [("SC142", demand.REVIEW_QUESTION)]  # once, on the first entry
    assert "000" not in reqs[0].question and "k" not in reqs[0].question.split()
    page = client.get("/reviews").text
    assert "Demand: <b>1.2M</b> over 2 requests" in page
    ideas = client.get("/business/reports").text
    assert 'id="demand-seen"' in ideas and "Digital isolator: lifetime demand seen" in ideas
    assert "<b>1.2M</b> lifetime demand over 2 requests" in ideas and "/find?q=SC142" in ideas


def test_business_case_line_owner_only_and_scores_unchanged(owner, make_guest, session):
    before = {fn: s["score"] for fn, s in scoring.combined(session)["rows"].items()}
    case = Case(title="Isolator case", fn=FN)
    session.add(case)
    session.commit()
    send(owner, v2="2000000")
    page = owner.get(f"/business/cases/{case.id}").text
    assert "Demand seen (owner estimates): <b>2M</b> lifetime over 1 request" in page
    assert "score with demand seen" not in page  # switch off by default
    guest, _ = make_guest()
    assert "Demand seen" not in guest.get(f"/business/cases/{case.id}").text
    scoring._CACHE.clear()
    assert {fn: s["score"] for fn, s in scoring.combined(session)["rows"].items()} == before
    owner.post("/manage/demand/scoring", data={"on": "1"})
    page = owner.get(f"/business/cases/{case.id}").text
    shared = before[FN]
    assert "score with demand seen <b>" in page and f"(shared score {shared}, unchanged)" in page
    scoring._CACHE.clear()
    assert {fn: s["score"] for fn, s in scoring.combined(session)["rows"].items()} == before  # shared: unchanged


def test_not_in_excel_copy_shareable_inbox_or_api(client, session, monkeypatch):
    send(client, v2="700000", v3="1500000")
    look = session.scalar(select(CrossListLookup))
    page = client.get(f"/cross-list?lookup={look.id}").text
    export = page.split('id="cx-export"')[1].split("</table>")[0]  # the Copy table's cells
    assert "700" not in export and "1.5M" not in export and "1500000" not in export
    x = client.post("/cross-list.xlsx", data={"parts": LIST, "v2": "700000"})
    wb = load_workbook(io.BytesIO(x.content))
    cells = [str(c.value) for ws in wb for row in ws.iter_rows() for c in row if c.value is not None]
    assert not any("700000" in v or "700k" in v or "1.5M" in v for v in cells)
    for url in ("/shareable", "/shareable/technology-overview", "/shareable/synergies", "/shareable/automotive"):
        t = client.get(url).text
        assert "700k" not in t and "Owner only" not in t, url
    text = inbox.collect(session, date.today() - timedelta(days=1))
    assert "2 new volume entries" in text
    assert "700k" not in text and "700000" not in text and "1.5M" not in text and "1500000" not in text
    monkeypatch.setattr(get_settings(), "inbox_token", "k" * 40)
    api = client.get("/api/inbox", headers={"Authorization": "Bearer " + "k" * 40}).text
    assert "2 new volume entries" in api and "700" not in api.replace("2026", "") and "1.5M" not in api
    q = client.get("/api/inbox/crosslist-lookups", headers={"Authorization": "Bearer " + "k" * 40}).json()
    assert "700000" not in repr(q) and "SC142" not in repr(q)


def test_retention_12_months(client, session):
    send(client, v2="200000")
    look = session.scalar(select(CrossListLookup))
    session.add(DemandEntry(part="SC142", fn=FN, volume=900_000, day=date.today() - timedelta(days=370),
                            lookup_id=look.id))  # fmt: skip
    session.add(DemandEntry(part="SC142", fn=FN, volume=100_000, day=date.today() - timedelta(days=300),
                            lookup_id=look.id))  # fmt: skip
    session.commit()
    t = demand.totals(session)
    assert t.part("SC142").volume == 300_000  # the 13-month-old entry is dropped
    assert session.scalar(select(DemandEntry.id).where(DemandEntry.volume == 900_000)) is None  # and deleted
    assert demand.cutoff(date(2028, 2, 29)) == date(2027, 2, 28)


def test_deleting_the_lookup_deletes_its_volumes(client, session):
    send(client, v2="200000")
    look = session.scalar(select(CrossListLookup))
    client.post(f"/manage/crosslist-lookups/{look.id}/delete")
    session.expire_all()
    assert session.scalar(select(DemandEntry.id)) is None
