"""Guided path: part (with or without a cross) → application → parts in the design → numbers → business case."""

import re
from pathlib import Path

import pytest

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


def run_to_case(client, part, our, volume="100000", target=None):
    # a GET only shows the start button (prefetchers must not create drafts); the POST creates the draft
    assert "Start the business case" in client.get(f"/pipeline/new?part={part}").text
    r = client.post("/pipeline/new", data={"part": part, **({"our": our} if our else {})}, follow_redirects=False)
    draft = r.headers["location"].split("?")[0]
    assert r.headers["location"].endswith("?step=part")
    page = client.get(draft + "?step=part").text
    client.post(draft, data={"act": "ours", "our": str(our or "")})
    apps = client.get(draft + "?step=application").text
    i = re.search(r'name="act" value="template"><input type="hidden" name="i" value="(\d+)"', apps).group(1)
    client.post(draft, data={"act": "template", "i": i})
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
    }
    r = client.post(draft, data=fin, follow_redirects=False)
    return page, design, r.headers["location"]


def test_cross_to_business_case(client, real):
    comp, ours = ids(client, "ISO7741DBQR"), ids(client, "SI86S641EC-IS1")
    assert "Start a business case" in client.get(f"/parts/{comp}").text
    page, design, loc = run_to_case(client, comp, ours)
    assert "SI86S641EC-IS1" in page and "No Skyworks part" in page
    assert "this part" in design and "Parts in the design" in design
    case = client.get(loc).text
    assert "Parts in this business case" in case and "SI86S641EC-IS1" in case and "ISO7741DBQR" in case
    assert "$150,000" in case  # 100,000 systems × 1 × $1.50
    assert "Parts in this business case (volumes and prices are assumptions)" in client.get(loc + "/brief.md").text


def test_no_cross_is_a_gap_and_adds_to_existing_case(client, real):
    comp, ours = ids(client, "ISO7741DBQR"), ids(client, "SI86S641EC-IS1")
    _, _, loc = run_to_case(client, comp, ours)
    case_id = int(loc.rsplit("/", 1)[1])
    n = client.get(loc).text.count('name="vol:')
    _, _, loc2 = run_to_case(client, comp, None, target=case_id)
    assert loc2 == loc
    html = client.get(loc).text
    assert html.count('name="vol:') > n and "Gap: no part of ours" in html


def test_merge_cases(client, real):
    comp, ours = ids(client, "ISO7741DBQR"), ids(client, "SI86S641EC-IS1")
    _, _, a = run_to_case(client, comp, ours)
    _, _, b = run_to_case(client, comp, None)
    na, nb = (client.get(x).text.count('name="vol:') for x in (a, b))
    r = client.post(b, data={"act": "merge", "target": a.rsplit("/", 1)[1]}, follow_redirects=False)
    assert r.headers["location"].startswith(a)
    assert client.get(a).text.count('name="vol:') == na + nb
    merged = client.get(b).text
    assert "Merged into" in merged and 'name="vol:' not in merged
    assert "Merged" in client.get("/business/cases").text
