import pytest
from sqlalchemy.orm import Session

from app.db import get_engine
from app.services import prelim
from app.services import reports as rp

SLUG = "radio-tuner-next"


SLUGS = sorted(p.stem for p in prelim.FOLDER.glob("*.yaml") if not p.stem.startswith("_"))


@pytest.mark.parametrize("slug", SLUGS)
def test_case_file_is_consistent(slug):
    """Every case: ids unique, distances known, prices ordered, scenarios priced, listed in reports.yaml with a body."""
    c = prelim.raw(slug)
    assert c and c.get("title") and c.get("brief")
    pos = c.get("position") or {}
    rows = [x for k in prelim.LISTS for x in pos.get(k) or []]
    rows += [*(c.get("outlook") or []), *(c.get("features") or []), *(c.get("attach") or []), *c["prices"]["items"]]
    ids = [str(x["id"]) for x in rows]
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]
    assert all(f["distance"] in prelim.DISTANCE for f in c["features"])
    prices = {p["id"] for p in c["prices"]["items"]}
    assert all(p["entry"] <= p["target"] <= p["premium"] for p in c["prices"]["items"])
    assert all(v["price"] in prices for v in c.get("volumes") or [])
    assert rp.report(slug) is not None, "missing from reports.yaml or no body template"


def test_case_page_feedback_and_real_asp(client):
    r = client.get(f"/business/reports/{SLUG}")
    assert r.status_code == 200 and "Advantages" in r.text and "Real ASP" in r.text
    assert 'id="pc-dialog"' in r.text and "prelim.js" in r.text and 'class="fz fz-' in r.text
    assert client.get("/business/reports/method").status_code == 200
    data = {"key": "f-node", "verdict": "further", "comment": "Two dies"}
    r = client.post(f"/business/reports/{SLUG}/react", data=data, follow_redirects=False)
    assert r.status_code == 303
    assert client.post(f"/business/reports/{SLUG}/react", data={"key": "nope", "verdict": "agree"}).status_code == 400
    assert client.post(f"/business/reports/{SLUG}/price", data={"key": "p-rn4", "value": "15.25"},
                       follow_redirects=False).status_code == 303  # fmt: skip
    with Session(get_engine()) as s:
        c = prelim.case(s, SLUG)
    node = next(f for f in c["features"] if f["id"] == "f-node")
    assert node["fb"]["verdict"] == "further" and node["fb"]["comments"][0]["text"] == "Two dies"
    rn4 = next(p for p in c["prices"]["items"] if p["id"] == "p-rn4")
    assert rn4["real"] == 15.25
    assert any(v["real"] and v["unit"] == 15.25 for v in c["revenue"])
    page = client.get(f"/business/reports/{SLUG}").text
    assert "move further" in page and "your ASP" in page
