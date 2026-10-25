"""Data quality questions take a comment and Submit, no yes / no (owner, 25 Oct 2026: "yes and no Feedback is
misplaced here as well as undecided. It should be a comment with submit and reviewed again in a second round after
checking"). The daily run checks each comment and records it in data/business/quality_checked.yaml; the item then
comes back in a second round."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.models import DataReview
from app.services import inbox, quality, tam


def _item() -> tuple[str, str]:
    """A competition item that has a question."""
    ds = quality.datasets()["competition"][1]
    key = next(k for k, e in ds.items() if isinstance(e, dict) and quality.ask("competition", k, k, e))
    return "competition", key


def _questions(html: str) -> str:
    return html.split('id="questions"', 1)[1].split('id="research"', 1)[0]


def _card(html: str, dataset: str, key: str) -> str:
    part = html[html.index(f'id="q-{dataset}-{key}"') :]
    return part[: part.index("</li>")]


def _check(path, ds: str, key: str, at: str, note: str) -> None:
    path.write_text(f'checked:\n  - dataset: {ds}\n    key: {key}\n    date: {date.today()}\n'
                    f'    comment_at: "{at}"\n    note: "{note}"\n')  # fmt: skip


@pytest.fixture
def checked_file(tmp_path, monkeypatch):
    path = tmp_path / "quality_checked.yaml"
    path.write_text("checked: []\n")
    monkeypatch.setattr(quality, "CHECKED_FILE", path)
    return path


def test_questions_show_comment_and_submit_no_yes_no(client):
    queue = _questions(client.get("/business/quality").text)
    assert 'class="qa-item"' in queue and 'name="comment"' in queue and ">Submit<" in queue
    assert 'name="answer"' not in queue and ">Yes<" not in queue and ">No<" not in queue
    assert "Undecided" not in queue and "Looks right now" not in queue  # the confirm is for the second round only


def test_comment_is_stored_and_shows_being_checked_and_reaches_the_inbox(client, session, checked_file):
    ds, key = _item()
    r = client.post("/business/quality/answer", data={"dataset": ds, "key": key, "comment": "  TI sells one too "},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"].endswith(f"#q-{ds}-{key}")
    row = session.scalar(select(DataReview).where(DataReview.dataset == ds, DataReview.key == key))
    assert row.verdict == "comment" and row.comment == "TI sells one too"
    card = _card(client.get("/business/quality").text, ds, key)
    assert "Comment received – being checked" in card and "TI sells one too" in card and 'name="comment"' not in card
    # the inbox lists it with the item, its current value and the comment
    lines = quality.inbox_lines(session)
    line = next(x for x in lines if f"/ {key} ·" in x)
    assert "[round 1] Competition" in line and "now: " in line and "comment: TI sells one too" in line
    text = inbox.collect(session, date(2026, 1, 1))
    assert "## Data quality comments (being checked)" in text and "comment: TI sells one too" in text
    assert "quality_checked.yaml" in text
    # an empty comment is not stored
    n = session.query(DataReview).count()
    blank = {"dataset": ds, "key": key, "comment": " "}
    r = client.post("/business/quality/answer", data=blank, follow_redirects=False)
    assert r.status_code == 303 and "empty=1" in r.headers["location"] and session.query(DataReview).count() == n


def test_checked_item_comes_back_in_round_two(client, session, checked_file):
    ds, key = _item()
    assert client.post("/business/quality/answer", data={"dataset": ds, "key": key, "comment": "TI missing"},
                       follow_redirects=False).status_code == 303  # fmt: skip
    # confirming before the check is refused
    r = client.post("/business/quality/answer", data={"dataset": ds, "key": key, "action": "confirm"})
    assert r.status_code == 400
    first = session.scalar(select(DataReview).where(DataReview.key == key))
    first.created_at = datetime(2026, 10, 20, 10, 0, 40, tzinfo=UTC)  # the comment as the inbox printed it: 10:00
    session.commit()
    _check(checked_file, ds, key, "2026-10-20 10:00", "Added TI to the list")
    assert quality.threads(session)[(ds, key)]["status"] == "round2"
    card = _card(client.get("/business/quality").text, ds, key)
    assert "Checked: Added TI to the list – OK now?" in card and "TI missing" in card
    assert 'name="comment"' in card and ">Submit<" in card and ">Looks right now<" in card
    assert not any(f"/ {key} ·" in x for x in quality.inbox_lines(session))  # checked: off the inbox list
    # a second-round comment goes back to being checked
    client.post("/business/quality/answer", data={"dataset": ds, "key": key, "comment": "and ADI"})
    rows = session.scalars(select(DataReview).where(DataReview.key == key).order_by(DataReview.id)).all()
    assert [r.verdict for r in rows] == ["comment", "comment2"]
    card = _card(client.get("/business/quality").text, ds, key)
    assert "being checked" in card and "and ADI" in card
    assert any("[round 2]" in x and f"/ {key} ·" in x for x in quality.inbox_lines(session))
    # the run checks again; "Looks right now" closes the item
    _check(checked_file, ds, key, datetime.now(UTC).strftime("%Y-%m-%d %H:%M"), "Added ADI too")
    assert quality.threads(session)[(ds, key)]["status"] == "round2"
    r = client.post("/business/quality/answer", data={"dataset": ds, "key": key, "action": "confirm"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    assert session.scalars(select(DataReview.verdict).where(DataReview.key == key)).all()[-1] == "correct"
    assert quality.threads(session)[(ds, key)]["status"] == "closed"
    assert f'id="q-{ds}-{key}"' not in client.get("/business/quality").text


def test_tam_comment_is_not_a_verdict_and_applied_items_stay_locked(client, session, checked_file):
    key = next(e["key"] for e in tam.researched() if e["key"] not in tam.applied())
    assert client.post("/business/quality/answer", data={"dataset": "tam", "key": key, "comment": "figure is 2023"},
                       follow_redirects=False).status_code == 303  # fmt: skip
    assert {e["key"]: e for e in tam.estimates(session)}[key]["review"] is None  # the TAM page is unchanged
    assert "being checked" in _card(client.get("/business/quality").text, "tam", key)
    n = session.query(DataReview).count()
    for data in ({"comment": "no"}, {"action": "confirm"}):
        r = client.post("/business/quality/answer", data={"dataset": "tam", "key": "tuner-ic-mrfr", **data})
        assert r.status_code == 409
    assert session.query(DataReview).count() == n


def test_earlier_yes_no_answers_stay_readable(client, session):
    ds, key = _item()
    session.add(DataReview(dataset=ds, key=key, verdict="wrong", comment="older answer", author="Mat"))
    session.commit()
    html = client.get("/business/quality").text
    recent = html.split("Recent reviews and comments", 1)[1]
    assert "older answer" in recent and "Wrong" in recent
