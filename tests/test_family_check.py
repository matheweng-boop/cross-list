"""Datasheet families: check the whole family, then batch confirm (owner, 26 Oct 2026: "Do we have a system when
enough crosses are flagged or confirmed that we will check the whole product family and therefore batch confirm?" –
"Build it"). See app/services/families.py."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import DataReview, Part
from app.services import crosslist, digest, families, inbox

THEIRS = ["ISO7740DWR", "ISO7741DWR", "ISO7742DWR", "ISO7720DR", "ISO7721DR"]


@pytest.fixture
def checks(tmp_path, monkeypatch):
    """A family_checks.yaml of the test's own: write(sheet, when) records a re-read (a UTC time as reread_at, or an
    old date-only entry)."""
    path = tmp_path / "family_checks.yaml"
    path.write_text("checks: []\n")
    monkeypatch.setattr(families, "CHECKS_FILE", path)
    rows = []

    def write(sheet: str, when: date | datetime):
        at = (f"reread_at: {when.astimezone(UTC):%Y-%m-%dT%H:%M:%SZ}" if isinstance(when, datetime)
              else f"date: {when.isoformat()}")  # fmt: skip
        rows.append(f"  - {{family: {families.family_name(sheet)}, datasheet: {sheet}, {at}, done: x}}\n")
        path.write_text("checks:\n" + "".join(rows))

    return write


def _codes(session, sheet: str) -> list[str]:
    ids = sorted(i for i, s in families.sheets(session).items() if s == sheet)
    return [session.get(Part, i).mpn for i in ids]


def _theirs(session) -> list[str]:
    have = set(session.scalars(select(Part.mpn).where(Part.mpn.in_(THEIRS))))
    return [m for m in THEIRS if m in have]


def _answer(session, their, ours, verdict, comment="", when=None):
    r = crosslist.record(session, their, ours, verdict, comment, "owner")
    if when is not None:
        r.created_at = when
        session.commit()
    return r


def test_family_names_are_short_and_readable():
    assert families.family_name("si861x-2x-datasheet.pdf") == "Si861x/2x"
    assert families.family_name("iso776x-q1.pdf") == "ISO776x-Q1"
    assert families.family_name("NSI822x_Datasheet_2.0_EN.pdf") == "NSI822x"
    assert families.family_name("si8941-46-47-datasheet.pdf") == "Si8941/46/47"
    assert families.family_name("SKY13317-373LF_200914L.pdf") == "SKY13317-373LF"
    assert families.family_name("CAIS372xdatasheetVersion1.08.pdf") == "CAIS372x"
    assert families.WRONG_TO_FLAG == 2 and families.RIGHT_TO_OFFER == 3  # stricter at first


def test_two_wrong_flag_the_family_one_does_not(client, session, real, checks):
    ours = _codes(session, "si864x-datasheet.pdf")
    their = _theirs(session)
    _answer(session, their[0], ours[0], "wrong", "channel count differs")
    f = families.status(session)["si864x-datasheet.pdf"]
    assert f.name == "Si864x" and len(f.wrong) == 1 and not f.flagged  # one Wrong is not a pattern
    assert "Si864x" not in "\n".join(families.inbox_lines(session, datetime(2026, 1, 1, tzinfo=UTC)))
    _answer(session, their[1], ours[1], "wrong", "default output differs")
    f = families.status(session)["si864x-datasheet.pdf"]
    assert f.flagged and len(f.part_ids) == len(ours)
    # their parts' own families count too (either side)
    assert any(s != "si864x-datasheet.pdf" for s in families.status(session))
    # a later Right on the same pair replaces the Wrong (the latest answer wins)
    _answer(session, their[1], ours[1], "right")
    assert not families.status(session)["si864x-datasheet.pdf"].flagged


def test_inbox_lists_the_flagged_family(client, session, real, checks):
    ours = _codes(session, "si864x-datasheet.pdf")
    their = _theirs(session)
    _answer(session, their[0], ours[0], "wrong", "channel count differs")
    _answer(session, their[1], ours[1], "wrong")
    text = inbox.collect(session, date.today() - timedelta(days=1))
    sec = text.split("## Cross list: datasheet families to re-read")[1].split("\n## ")[0]
    assert f"- Si864x · datasheet si864x-datasheet.pdf · {len(ours)} codes · 2 Wrong" in sec
    assert f"{their[0]} → {ours[0]} · channel count differs" in sec and f"{their[1]} → {ours[1]}" in sec
    assert "family_checks.yaml" in sec
    assert "Nothing new since the last pull." not in text


def test_candidate_after_reread_and_three_right(client, session, real, checks):
    ours = _codes(session, "si864x-datasheet.pdf")
    their = _theirs(session)
    old = datetime.now(UTC) - timedelta(days=3)
    _answer(session, their[0], ours[0], "wrong", when=old)
    _answer(session, their[1], ours[1], "wrong", when=old)
    for i in range(2, 5):
        _answer(session, their[i], ours[i], "right")
    f = families.status(session)["si864x-datasheet.pdf"]
    assert not f.candidate  # open Wrongs and not re-read
    checks("si864x-datasheet.pdf", (old + timedelta(days=1)).date())
    f = families.status(session)["si864x-datasheet.pdf"]
    assert f.candidate and not f.flagged and not f.open_wrong
    item = next(r for r in families.digest_items(session) if r["id"] == "si864x-datasheet.pdf")
    assert item["type"] == "family" and item["key"] == "family:si864x-datasheet.pdf"
    assert item["gist"].startswith(f"Si864x: {len(ours)} codes, re-read ") and "3 crosses confirmed" in item["gist"]
    assert item["gist"].endswith("Confirm the family?")
    assert digest.words(item["gist"]) <= digest.MAX_WORDS and len(item["abstract"]) <= 3
    # two Rights are not enough
    session.delete(session.scalars(select(DataReview).where(DataReview.key.startswith(their[4]))).first())
    session.commit()
    assert not families.status(session)["si864x-datasheet.pdf"].candidate


def _verified_row(session, mpn):
    rows = crosslist.cross_list(session, crosslist.parse(mpn)[0])
    return rows[0]


def test_confirm_sets_verified_and_a_later_wrong_reopens(client, session, real, checks):
    row = _verified_row(session, "ISO7741DWR")
    cand = row.drop_in or row.functional
    assert cand is not None and not row.verified
    sheet = families.sheets(session)[cand.part.id]
    ours = [m for m in _codes(session, sheet) if m != cand.part.mpn]
    their = [m for m in _theirs(session) if m != "ISO7741DWR"]
    for i in range(3):
        _answer(session, their[i], ours[i % len(ours)] if len(ours) > 2 else cand.part.mpn, "right")
    checks(sheet, date.today() - timedelta(days=1))
    key = f"family:{sheet}"
    f = digest.feed(session)
    card = next(c for c in f["cards"] if c["key"] == key)
    assert card["type_label"] == "Datasheet family"
    assert client.post("/manage/to-confirm/act", data={"key": key, "action": "confirm"}).status_code in (200, 303)
    v = session.scalars(select(DataReview).where(DataReview.dataset == families.DATASET)).all()
    assert [(r.key, r.verdict) for r in v] == [(sheet, "confirmed")]
    assert key in {c["key"] for c in digest.feed(session, "confirmed")["cards"]}
    assert key not in {c["key"] for c in digest.feed(session)["cards"]}
    # Verified on Cross a list, the Excel export and the part page
    row = _verified_row(session, "ISO7741DWR")
    assert row.verified and crosslist.export_cells(row)[-2] == "✓ Verified"
    ref = session.scalars(select(Part).where(Part.mpn == "ISO7741DWR")).one()
    assert (ref.id, cand.part.id) in crosslist.Verified(session)
    assert "✓ Verified" in client.get(f"/parts/{ref.id}").text
    # a later Wrong on any cross of the family reopens it
    later = datetime.now(UTC) + timedelta(seconds=5)
    _answer(session, their[3], cand.part.mpn, "wrong", "pinout differs", when=later)
    f = families.status(session)[sheet]
    assert f.reopened and not f.confirmed and f.flagged
    assert not _verified_row(session, "ISO7741DWR").verified
    assert key not in {c["key"] for c in digest.feed(session, "confirmed")["cards"]}
    assert "reopened" in "\n".join(families.inbox_lines(session, datetime(2026, 1, 1, tzinfo=UTC)))


def test_undo_takes_the_family_verdict_back(client, session, real, checks):
    ours = _codes(session, "si864x-datasheet.pdf")
    their = _theirs(session)
    for i in range(3):
        _answer(session, their[i], ours[i], "right")
    checks("si864x-datasheet.pdf", date.today() - timedelta(days=1))
    key = "family:si864x-datasheet.pdf"
    digest.act(session, key, "confirm")
    assert families.status(session)["si864x-datasheet.pdf"].confirmed
    digest.act(session, key, "undo")
    assert not families.status(session)["si864x-datasheet.pdf"].confirmed
    assert key in {c["key"] for c in digest.feed(session)["cards"]}
    with pytest.raises(ValueError):
        digest.act(session, "family:nope.pdf", "confirm")


def test_guests_cannot_confirm_a_family(make_guest, session):
    guest, _ = make_guest()
    r = guest.post("/manage/to-confirm/act", data={"key": "family:si864x-datasheet.pdf", "action": "confirm"})
    assert r.status_code == 403
    assert session.scalar(select(DataReview.id).where(DataReview.dataset == families.DATASET)) is None


def test_reread_time_counts_same_day_wrongs_after_it_as_open(client, session, real, checks):
    """A re-read is a UTC time: a Wrong is handled only when it is older than it (a Wrong left after the 18:42 run on
    the same day stays open). An old date-only entry counts as the start of that day."""
    assert families.reread_time("2026-10-27T18:55:00Z") == datetime(2026, 10, 27, 18, 55, tzinfo=UTC)
    assert families.reread_time("2026-10-27") == datetime(2026, 10, 27, tzinfo=UTC)
    assert families.reread_time(date(2026, 10, 27)) == datetime(2026, 10, 27, tzinfo=UTC)
    ours = _codes(session, "si864x-datasheet.pdf")
    their = _theirs(session)
    day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    _answer(session, their[0], ours[0], "wrong", when=day + timedelta(hours=10))
    _answer(session, their[1], ours[1], "wrong", when=day + timedelta(hours=20))
    _answer(session, their[2], ours[2], "wrong", when=day + timedelta(hours=21))
    checks("si864x-datasheet.pdf", day.date())  # date only: start of the day, all three stay open
    f = families.status(session)["si864x-datasheet.pdf"]
    assert len(f.open_wrong) == 3 and f.flagged
    checks("si864x-datasheet.pdf", day + timedelta(hours=18, minutes=55))  # the run finished at 18:55 UTC
    f = families.status(session)["si864x-datasheet.pdf"]
    assert f.reread == day + timedelta(hours=18, minutes=55)
    assert {w.key.split("|")[0] for w in f.open_wrong} == {their[1], their[2]} and f.flagged
    checks("si864x-datasheet.pdf", day + timedelta(hours=22))
    f = families.status(session)["si864x-datasheet.pdf"]
    assert not f.open_wrong and not f.flagged
