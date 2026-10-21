"""Guided path: part (with or without a cross) → application → parts in the design → numbers → prelim case (sent to
the review queue) or the lines into an existing business case."""

import re
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import Case, VolumeRequest
from app.services.seed import load_file

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def real(session):
    for f in ("ti_digital_isolators", "skyworks_si86"):
        load_file(session, ROOT / "data" / "real" / f"{f}.yaml")
    session.commit()


def ids(client, mpn):
    r = client.get(f"/find?q={mpn}", follow_redirects=False)
    return int(r.headers["location"].rsplit("/", 1)[1])


def new_case(session, title="Existing case"):
    c = Case(title=title, fn="digital_isolator", inputs={})
    session.add(c)
    session.commit()
    return c.id


def run_to_case(client, part, our, volume="100000", target=None, customers=("Bosch",), markets=("Automotive",)):
    # a GET only shows the start button (prefetchers must not create drafts); the POST creates the draft
    assert "Start the prelim case" in client.get(f"/pipeline/new?part={part}").text
    r = client.post("/pipeline/new", data={"part": part, **({"our": our} if our else {})}, follow_redirects=False)
    draft = r.headers["location"].split("?")[0]
    assert r.headers["location"].endswith("?step=part")
    page = client.get(draft + "?step=part").text
    client.post(draft, data={"act": "ours", "our": str(our or "")})
    apps = client.get(draft + "?step=application").text
    i = re.search(r'name="act" value="template"><input type="hidden" name="i" value="(\d+)"', apps).group(1)
    client.post(draft, data={"act": "template", "i": i, "description": "isolated industrial drive"})
    client.post(draft, data={"act": "pick_all"})
    design = client.get(draft + "?step=design").text
    client.post(draft, data={"act": "design_done"})
    numbers = client.get(draft + "?step=numbers").text
    keys = re.findall(r'name="inc:([^"]+)"', numbers)
    form = {"act": "numbers", "volume_all": volume, **{f"inc:{k}": "on" for k in keys}}
    form["price:cross"] = "1.50"
    client.post(draft, data=form)
    fin = {
        "act": "finish",
        "target": "existing" if target else "new",
        "existing": str(target or ""),
        "title": "Test case",
        "customer": list(customers),
        "market": list(markets),
    }
    r = client.post(draft, data=fin, follow_redirects=False)
    return page, design, r.headers["location"]


def test_lines_into_an_existing_business_case(client, session, real):
    comp, ours = ids(client, "ISO7741DBQR"), ids(client, "SI86S641EC-IS1")
    case_id = new_case(session)
    page, design, loc = run_to_case(client, comp, ours, target=case_id)
    assert loc == f"/business/cases/{case_id}"
    assert "SI86S641EC-IS1" in page and "No Skyworks part" in page
    assert "this part" in design and "Parts in the design" in design
    case = client.get(loc).text
    assert "Parts in this business case" in case and "SI86S641EC-IS1" in case and "ISO7741DBQR" in case
    assert "$150,000" in case  # 100,000 systems × 1 × $1.50
    assert "Parts in this business case (volumes and prices are assumptions)" in client.get(loc + "/brief.md").text


def test_prelim_case_goes_to_the_review_queue(client, session, real):
    comp, ours = ids(client, "ISO7741DBQR"), ids(client, "SI86S641EC-IS1")
    _, _, loc = run_to_case(client, comp, ours, customers=("Bosch", "Valeo", ""), markets=("Automotive", "Industrial"))
    draft = loc.split("?")[0]
    assert loc.endswith("?step=send") and draft.startswith("/pipeline/")
    case_step = client.get(draft + "?step=case").text
    assert "Create a prelim case" in case_step and "real market" in case_step
    assert "Create business case" not in case_step and 'data-add="customer"' in case_step
    assert 'data-add="market"' in case_step
    send = client.get(loc).text
    assert 'action="/business/schedule"' in send and 'data-autosend="1"' in send
    did = draft.rsplit("/", 1)[1]
    for field, value in (("source", f"prelim:{did}"), ("part", "ISO7741DBQR"), ("volume", "100000"),
                         ("next", f"/pipeline/{did}?step=case&amp;sent=1"), ("title", "Test case")):  # fmt: skip
        assert f'name="{field}" value="{value}"' in send
    assert "Bosch, Valeo" in send and "real market" in send
    assert 'data-autosend="1"' not in client.get(loc).text  # sent by itself once; a button after that
    assert "Sent to the review queue" in client.get(draft + "?step=case&sent=1").text
    # every request is kept; the volume accrues on the part
    _, _, _ = run_to_case(client, comp, None, volume="50000", customers=("Bosch",))
    rows = session.scalars(select(VolumeRequest).where(VolumeRequest.mpn == "ISO7741DBQR")).all()
    assert [r.volume for r in rows] == [100000, 50000] and rows[0].customer == "Bosch; Valeo"
    assert rows[0].market == "Automotive; Industrial" and rows[0].source == f"prelim:{did}"
    assert "150,000 pieces a year" in client.get(f"/parts/{comp}").text
    assert "2 requests" in client.get(draft + "?step=numbers").text


def test_application_description_search(client, session, real):
    comp = ids(client, "ISO7741DBQR")
    r = client.post("/pipeline/new", data={"part": comp}, follow_redirects=False)
    draft = r.headers["location"].split("?")[0]
    html = client.get(draft + "?step=application").text
    assert 'id="pl-desc"' in html and "top 10" in html and "/static/pipeline.js" in html
    found = client.get("/pipeline/apps.json?q=traction inverter&fn=digital_isolator").json()
    assert 0 < len(found) <= 10 and "traction inverter" in found[0]["name"].lower()
    assert len(client.get("/pipeline/apps.json?q=power&fn=digital_isolator").json()) == 10
    hvac = client.get("/pipeline/apps.json?q=heat pump for an HVAC system").json()
    assert hvac and any("HVAC" in t for t in hvac[0]["tags"])
    assert client.get("/pipeline/apps.json?q=zzqx").json() == []
    # the description is kept with the chosen design
    i = re.search(r'name="act" value="template"><input type="hidden" name="i" value="(\d+)"', html).group(1)
    client.post(draft, data={"act": "template", "i": i, "description": "Heat pump for homes"})
    assert "Heat pump for homes" in client.get(draft + "?step=application").text


def test_design_suggests_our_parts_per_block(client, session, real):
    comp, ours = ids(client, "ISO7741DBQR"), ids(client, "SI86S641EC-IS1")
    r = client.post("/pipeline/new", data={"part": comp, "our": ours}, follow_redirects=False)
    draft = r.headers["location"].split("?")[0]
    client.post(draft, data={"act": "ours", "our": str(ours)})
    apps = client.get(draft + "?step=application").text
    i = re.search(r'name="act" value="template"><input type="hidden" name="i" value="(\d+)"', apps).group(1)
    client.post(draft, data={"act": "template", "i": i})
    design = client.get(draft + "?step=design").text
    assert "Suggested from Skyworks / Qorvo" in design and "Why:" in design
    m = re.search(r'name="act" value="use"><input type="hidden" name="block" value="([^"]+)">'
                  r'<input type="hidden" name="mpn" value="([^"]+)">', design)  # fmt: skip
    client.post(draft, data={"act": "use", "block": m.group(1), "mpn": m.group(2)})
    assert f"<b>{m.group(2)}</b>" in client.get(draft + "?step=design").text


def test_merge_cases(client, session, real):
    comp, ours = ids(client, "ISO7741DBQR"), ids(client, "SI86S641EC-IS1")
    a = f"/business/cases/{new_case(session, 'Case A')}"
    b = f"/business/cases/{new_case(session, 'Case B')}"
    run_to_case(client, comp, ours, target=int(a.rsplit("/", 1)[1]))
    run_to_case(client, comp, None, target=int(b.rsplit("/", 1)[1]))
    na, nb = (client.get(x).text.count('name="vol:') for x in (a, b))
    assert na and nb
    r = client.post(b, data={"act": "merge", "target": a.rsplit("/", 1)[1]}, follow_redirects=False)
    assert r.headers["location"].startswith(a)
    assert client.get(a).text.count('name="vol:') == na + nb
    merged = client.get(b).text
    assert "Merged into" in merged and 'name="vol:' not in merged
    assert "Merged" in client.get("/business/cases").text
