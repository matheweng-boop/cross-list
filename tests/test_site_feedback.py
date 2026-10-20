"""Floating feedback button: sending with page context, daily digest with grouping, one response per group."""

import re
from datetime import UTC, datetime, timedelta

from app.models import SiteFeedback
from app.services import feedback as fb


def _send(client, text, path="/business/rf-coverage", **kw):
    r = client.post("/site-feedback", json={"text": text, "path": path, "client": "c1", **kw})
    assert r.status_code == 200
    return r.json()


def test_send_records_where_it_came_from(client):
    out = _send(client, "Matrix needs a maker split", heading="RF coverage by band", selection="LNA row")
    assert out["page"] == "Opportunities › RF coverage › RF coverage by band"
    assert client.post("/site-feedback", json={"text": "  "}).status_code == 400
    assert client.get("/site-feedback/context?path=/blocks").json()["page"].startswith("Systems & applications")


def test_digest_groups_similar_points_and_response_reaches_sender(client):
    _send(client, "Show Skyworks versus Qorvo split in every RF coverage cell")
    _send(client, "Please split each RF coverage cell by Skyworks and Qorvo", path="/business/rf-coverage?fn=lna")
    _send(client, "Library cards are too tall on a laptop", path="/blocks", kind="problem")
    page = client.get("/manage/feedback")
    assert page.status_code == 200 and page.text.count('class="fb-group') == 2
    text = client.get("/manage/feedback/digest.txt").text
    group = next(line for line in text.splitlines() if "split" in line)
    assert group.startswith("- [New]")
    ids = re.search(r'name="ids" value="(\d+,\d+)"', page.text).group(1)  # the grouped pair
    r = client.post("/manage/feedback/respond", data={"ids": ids, "status": "planned", "response": "Next RF update."},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    mine = client.get("/site-feedback/mine?client=c1").json()
    assert sum(m["response"] == "Next RF update." for m in mine) == 2


def test_similarity_rules():
    a = SiteFeedback(text="Show Skyworks versus Qorvo split per cell", path="/x")
    b = SiteFeedback(text="split per cell: Skyworks and Qorvo", path="/x?y=1")
    c = SiteFeedback(text="Library cards too tall", path="/x")
    assert fb.similar(a, b) and not fb.similar(a, c)


def test_earlier_open_point_is_flagged(client, session):
    old = SiteFeedback(text="Export the RF coverage matrix to Excel", path="/business/rf-coverage", status="new",
                       created_at=datetime.now(UTC) - timedelta(days=2))  # fmt: skip
    session.add(old)
    session.commit()
    _send(client, "Can I export the RF coverage matrix to Excel?")
    d = fb.digest(session, datetime.now(UTC).date())
    assert any(g["repeats"] and g["repeats"].id == old.id for g in d["groups"])
