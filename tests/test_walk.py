"""Part walk-through: one step at a time from the cross result, gaps recorded once as site feedback, links back."""

from sqlalchemy import func, select

from app.models import SiteFeedback
from app.services import walk
from tests.test_pipeline import ids, real  # noqa: F401  (fixture)


def test_steps_only_when_asked(client, real):  # noqa: F811
    comp = ids(client, "ISO7741DBQR")
    page = client.get(f"/parts/{comp}").text
    assert f"/parts/{comp}/walk?upto=2" in page and "Next: 2 Sell around it" in page
    two = client.get(f"/parts/{comp}/walk").text
    assert 'id="step-2"' in two and 'id="step-3"' not in two and "Next: 3 Best of ours around it" in two
    five = client.get(f"/parts/{comp}/walk?upto=5").text
    assert all(f'id="step-{n}"' in five for n in range(1, 6)) and "Next:" not in five
    assert any(v in five for v in walk.VERDICTS.values())


def test_gaps_go_to_site_feedback_once(client, session, real):  # noqa: F811
    comp = ids(client, "ISO7741DBQR")

    def n():
        return session.scalar(select(func.count(SiteFeedback.id)).where(SiteFeedback.author == walk.AUTHOR))

    client.get(f"/parts/{comp}/walk?upto=2")
    after2 = n()
    client.get(f"/parts/{comp}/walk?upto=5")
    after5 = n()
    assert after5 >= after2  # later steps add their own gaps only when they are opened
    client.get(f"/parts/{comp}/walk?upto=5")
    client.get(f"/parts/{ids(client, 'ISO7741DWR')}/walk?upto=5")  # same function: same gaps, not again
    assert n() == after5
    rows = session.scalars(select(SiteFeedback).where(SiteFeedback.author == walk.AUTHOR)).all()
    assert all(r.kind == "data" and "/walk#step-" in r.path for r in rows)
    assert "found walking through" in client.get("/manage/feedback").text or rows == []


def test_function_page_links_back(client, real):  # noqa: F811
    html = client.get("/business/evidence/digital_isolator").text
    assert "Walk through from a competitor part" in html and "/walk" in html
