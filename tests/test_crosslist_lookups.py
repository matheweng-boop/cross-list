"""Products › Cross a list › "Update cross-lists" (owner, 26 Oct 2026): unknown parts sent for an hourly datasheet
lookup, the list kept to cross it again, the Requests entry with progress, and the inbox / API hand-off."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import CrossListLookup
from app.services import crosslist_lookups as lk
from app.services import inbox

PASTE = ("Part\tQty\tPrice\tCustomer\nSC141\t2000\t$0.85\tACME Motors\nZZZ999\t500\t1.20\tACME\n"
         "SC142, 10k\nqq-777x\nZZZ999\n")


@pytest.fixture
def answers(tmp_path, monkeypatch):
    f = tmp_path / "crosslist_lookups.yaml"
    f.write_text("parts: []\n")
    monkeypatch.setattr(lk, "_file", lambda: f)
    return f


def test_button_only_with_unknown_rows_and_only_for_the_owner(owner, make_guest):
    client = owner
    page = client.post("/cross-list", data={"parts": PASTE}).text
    assert "Update cross-lists" in page and "Too many unknown?" in page and 'action="/cross-list/lookup"' in page
    known = client.post("/cross-list", data={"parts": "SC141\nSC142"}).text  # known, one without a cross
    assert 'action="/cross-list/lookup"' not in known
    guest, _ = make_guest()
    assert 'action="/cross-list/lookup"' not in guest.post("/cross-list", data={"parts": PASTE}).text


def test_guest_gets_403(make_guest, session):
    guest, _ = make_guest()
    assert guest.post("/cross-list/lookup", data={"parts": PASTE}).status_code == 403
    assert session.scalar(select(CrossListLookup.id)) is None


def test_send_stores_part_numbers_only(client, session, answers):
    r = client.post("/cross-list/lookup", data={"parts": PASTE}, follow_redirects=False)
    assert r.status_code == 303  # a reload of the result does not send twice
    r = client.get(r.headers["location"])
    assert "Sent 2 unknown parts for lookup (checked hourly)" in r.text and 'action="/cross-list/lookup"' not in r.text
    row = session.scalar(select(CrossListLookup))
    assert row.list_parts == ["SC141", "ZZZ999", "SC142", "qq-777x"]
    assert [p["part"] for p in row.unknown_parts] == ["ZZZ999", "QQ777X"]  # normalised, once each, no known parts
    assert all(p["status"] == "queued" for p in row.unknown_parts)
    stored = repr((row.list_parts, row.unknown_parts))
    for private in ("ACME", "2000", "0.85", "10k", "Qty", "Customer"):
        assert private not in stored
    assert client.post("/cross-list/lookup", data={"parts": "SC141"}).status_code == 400  # nothing unknown


def test_requests_page_progress_from_the_repo_file_and_delete(client, session, answers):
    row = lk.create(session, ["SC141", "AA111", "BB222", "CC333"], ["AA111", "BB222", "CC333"], "Owner")
    answers.write_text(f"parts:\n- {{lookup: {row.id}, part: AA111, status: found, source: https://example.com/aa.pdf,"
                       " date: 2026-10-27}\n- {part: bb-222, status: not_found, note: no public datasheet}\n")
    page = client.get("/manage/requests?kind=lookup").text
    assert "Cross-list lookup" in page and "1 of 3 found, 1 not found, 1 queued" in page
    assert f'href="/cross-list?lookup={row.id}"' in page and "Cross this list again" in page
    assert "no public datasheet" in page and "https://example.com/aa.pdf" in page
    assert [q["part"] for q in lk.queued(session)] == ["CC333"]
    answers.write_text(answers.read_text() + "- {part: CC333, status: found}\n")
    assert "2 of 3 found, 1 not found" in client.get("/manage/requests?kind=lookup&show=all").text
    assert "Nothing open here" in client.get("/manage/requests?kind=lookup").text  # done: no longer open
    lid = row.id
    r = client.post(f"/manage/crosslist-lookups/{lid}/delete", follow_redirects=False)
    session.expire_all()
    assert r.status_code == 303 and session.get(CrossListLookup, lid) is None


def test_cross_this_list_again_prefills_and_runs(owner, session, make_guest):
    client = owner
    row = lk.create(session, ["SC141", "ZZZ999"], ["ZZZ999"], None)
    page = client.get(f"/cross-list?lookup={row.id}").text
    assert "SC141\nZZZ999</textarea>" in page and "2 parts:" in page and "Not in our data" in page
    assert client.get("/cross-list?lookup=9999").status_code == 404
    guest, _ = make_guest()
    assert guest.get(f"/cross-list?lookup={row.id}").status_code == 403


def test_inbox_lists_only_queued_parts(client, session, answers, monkeypatch):
    a = lk.create(session, ["AA111", "BB222"], ["AA111", "BB222"], None)
    answers.write_text(f"parts:\n- {{lookup: {a.id}, part: AA111, status: found}}\n")
    text = inbox.collect(session, date.today() - timedelta(days=1))
    sec = text.split("## Cross-list lookups (queued parts)")[1].split("\n## ")[0]
    assert f"- BB222 · lookup {a.id} · " in sec and "AA111" not in sec
    monkeypatch.setattr(get_settings(), "inbox_token", "k" * 40)
    assert client.get("/api/inbox/crosslist-lookups").status_code == 401
    r = client.get("/api/inbox/crosslist-lookups", headers={"Authorization": "Bearer " + "k" * 40})
    assert r.status_code == 200
    assert [(q["part"], q["lookup"]) for q in r.json()["queued"]] == [("BB222", a.id)]


def test_repo_file_parses():
    assert lk.results() == {} or all(v["status"] in ("found", "not_found") for v in lk.results().values())
