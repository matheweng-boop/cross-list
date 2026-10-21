"""Verify next: small batches that stand for many items, refilled per kind only when that kind is done."""

from sqlalchemy import select

from app.models import DataReview, SiteFeedback, VerifyTask
from app.services import verify
from tests.test_pipeline import real  # noqa: F401  (fixture)


def _open(session, kind):
    session.expire_all()
    return session.scalars(select(VerifyTask).where(VerifyTask.kind == kind, VerifyTask.status == "open")).all()


def test_batches_refill_per_kind(client, session, real):  # noqa: F811
    html = client.get("/manage/verify").text
    assert "Verify next" in html and "Crosses" in html and "Block diagrams" in html
    crosses, diagrams, data = _open(session, "cross"), _open(session, "diagram"), _open(session, "data")
    assert 1 <= len(crosses) <= verify.BATCH["cross"] and len(diagrams) == verify.BATCH["diagram"]
    assert 1 <= len(data) <= verify.BATCH["data"] and len({t.detail["fn"] for t in data}) == len(data)
    assert all(t.covers >= 1 and " | " in t.key for t in crosses)
    first_diagrams = {t.id for t in diagrams}
    for i, t in enumerate(crosses):  # finish the crosses only
        r = client.post(f"/manage/verify/{t.id}", data={"result": "wrong" if i == 0 else "ok", "note": "pin 4"},
                        follow_redirects=False)  # fmt: skip
        assert r.status_code == 303
    client.get("/manage/verify")
    assert {t.id for t in _open(session, "diagram")} == first_diagrams  # untouched kind keeps its batch
    new = _open(session, "cross")
    assert not new or not {t.key for t in new} & {t.key for t in crosses}  # new crosses, never the same pair
    assert session.scalar(select(SiteFeedback).where(SiteFeedback.author == verify.AUTHOR)) is not None


def test_data_answer_feeds_the_score_reviews(client, session, real):  # noqa: F811
    client.get("/manage/verify")
    t = _open(session, "data")[0]
    client.post(f"/manage/verify/{t.id}", data={"result": "ok"})
    row = session.scalar(select(DataReview).where(DataReview.dataset == t.detail["topic"],
                                                  DataReview.key == t.detail["fn"]))  # fmt: skip
    assert row is not None and row.verdict == "correct"
    assert client.post(f"/manage/verify/{t.id}", data={"result": "ok"}).status_code == 404  # done once


def test_data_batch_includes_a_library_rule(client, session, real):  # noqa: F811
    client.get("/manage/verify")
    rule = next(t for t in _open(session, "data") if t.detail["topic"] == "library")
    assert rule.key.startswith("library:") and rule.detail["claim"]
    client.post(f"/manage/verify/{rule.id}", data={"result": "ok"})
    row = session.scalar(select(DataReview).where(DataReview.dataset == f"library:{rule.detail['library']}",
                                                  DataReview.key == rule.detail["item"]))  # fmt: skip
    assert row is not None and row.verdict == "correct"
