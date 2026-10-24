"""Part walk-through: one step at a time from the cross result, gaps recorded once as site feedback, links back."""

import json
import re

from sqlalchemy import func, select

from app.models import BlockDiagram, SiteFeedback
from app.services import blocks, walk
from app.services.seed import load_file
from tests.conftest import ROOT, ids


def test_steps_only_when_asked(client, real):
    comp = ids(client, "ISO7741DBQR")
    page = client.get(f"/parts/{comp}").text
    assert f"/parts/{comp}/walk?upto=2" in page and "Next: 2 Sell around it" in page
    two = client.get(f"/parts/{comp}/walk").text
    assert 'id="step-2"' in two and 'id="step-3"' not in two and "Next: 3 Best of ours around it" in two
    five = client.get(f"/parts/{comp}/walk?upto=5").text
    assert all(f'id="step-{n}"' in five for n in range(1, 6)) and "Next:" not in five
    assert any(v in five for v in walk.VERDICTS.values())


def test_gaps_go_to_site_feedback_once(client, session, real):
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


def test_function_page_links_back(client, real):
    html = client.get("/business/evidence/digital_isolator").text
    assert "Walk through from a competitor part" in html and "/walk" in html


def test_sell_around_it_from_the_customer_view(client, real):
    comp = ids(client, "ISO7741DBQR")
    html = client.get(f"/parts/{comp}/walk").text
    assert "You want ISO7741DBQR in this application" in html and "we also have" in html
    assert html.count('class="walk-card"') > 9 and "/static/walk.js" in html and 'id="walk-q"' in html
    assert "/blocks/new?template=" in html and "place=ISO7741DBQR&amp;fn=digital_isolator" in html
    assert "Add ISO7741DBQR to an application" in html and "New block diagram from ISO7741DBQR" in html
    assert 'class="walk-mini"' in html and 'class="mb-mine"' in html
    assert 'data-q="motor"' in html  # quick picks: general categories over the cards


def test_applications_searchable_by_general_category(client, real):
    comp = ids(client, "ISO7741DBQR")

    def shown(q):
        html = client.get(f"/parts/{comp}/walk", params={"q": q}).text
        card = r'<article class="walk-card"[^>]*?( hidden)?>\s*<h3>(?:<button[^>]*data-full="([^"]+)"|([^<]+))'
        cards = re.findall(card, html)
        return [full or name for hid, full, name in cards if not hid], html

    trac, _ = shown("traction inverter")
    assert trac and all("traction" in n.lower() for n in trac)
    hvac, _ = shown("HVAC")
    assert hvac and all(n not in trac for n in hvac)
    none, html = shown("zzqx")
    assert none == [] and '<p id="walk-none" class="small muted">' in html


def test_search_rules():
    idx = blocks.search_index("HVAC motor control (AC input, PFC + 3-phase inverter)", "Industrial", "gate driver")
    assert {"hvac", "motor"} <= set(idx["tags"])
    assert blocks.search_all(idx, "HVAC") and blocks.search_all(idx, "motor drive") and blocks.search_all(idx, "gate")
    assert not blocks.search_all(idx, "BMS") and not blocks.search_all(idx, "traction inverter")
    assert blocks.query_units("traction inverter for a forklift")[0][0] == "traction inverter"
    assert blocks.search_score(idx, "heat pump with a compressor") == 2


def _design(html):
    return json.loads(re.search(r'id="bk-design">(.*?)</script>', html, re.S).group(1))


def test_add_part_to_an_application(client, session, real):
    tpl = next(i for i, t in enumerate(blocks.templates()) if "digital_isolator" in blocks.template_functions(t))
    design = _design(client.get(f"/blocks/new?template={tpl}&place=ISO7741DBQR&fn=digital_isolator").text)
    assert design["id"] is None and "placed in" in design["prefill"]
    parts = [b.get("part") for g in design["data"]["groups"] for b in g["blocks"] if b["fn"] == "digital_isolator"]
    assert parts and all(p == "ISO7741DBQR" for p in parts)
    # a new diagram from the part
    new = _design(client.get("/blocks/new?place=ISO7741DBQR&fn=digital_isolator&name=Heat pump").text)
    assert new["name"] == "Heat pump" and new["data"]["groups"][0]["blocks"][0]["part"] == "ISO7741DBQR"
    # a saved diagram without the function gets a frame with the part; the saved one is unchanged until Save
    d = BlockDiagram(name="My design", data={"groups": [{"id": "g1", "label": "Power", "col": 0, "row": 0, "w": 1,
                                                         "blocks": [{"id": "b1", "fn": "pol_buck", "qty": 1}]}],
                                             "links": []})  # fmt: skip
    session.add(d)
    session.commit()
    ext = _design(client.get(f"/blocks/{d.id}?place=ISO7741DBQR&fn=digital_isolator").text)
    assert ext["id"] == d.id and ext["data"]["groups"][-1]["label"] == "Added: ISO7741DBQR"
    session.refresh(d)
    assert len(d.data["groups"]) == 1
    comp = ids(client, "ISO7741DBQR")
    assert f"/blocks/{d.id}?place=ISO7741DBQR" in client.get(f"/parts/{comp}/walk").text


def test_case_only_for_a_part_we_cannot_cross(client, session):
    load_file(session, ROOT / "data" / "real" / "ti_digital_isolators.yaml")  # no part of ours: nothing crosses
    session.commit()
    comp = ids(client, "ISO7741DBQR")
    page = client.get(f"/parts/{comp}").text
    assert "Start a prelim case" in page and "No case needed" not in page
    assert 'action="/pipeline/new"' in client.get(f"/parts/{comp}/walk").text


def test_no_case_when_we_can_cross_it(client, real):
    """Owner, 22 Oct 2026: a part counts as crossed only with a drop-in; our own parts never get the button."""
    dropin = ids(client, "SC141")  # SR8641 (ours) is a drop-in
    for html in (client.get(f"/parts/{dropin}").text, client.get(f"/parts/{dropin}/walk?upto=5").text):
        assert "No case needed" in html and "Start a prelim case" not in html
    functional = ids(client, "ISO7741DBQR")  # only functional crosses (other package): not crossed
    page = client.get(f"/parts/{functional}").text
    assert "Start a prelim case" in page and "No drop-in of ours" in page and "closest" in page
    walk = client.get(f"/parts/{functional}/walk?upto=5").text
    assert "Start a prelim case" in walk and "No drop-in of ours" in walk
    ours = ids(client, "SR8641")
    for html in (client.get(f"/parts/{ours}").text, client.get(f"/parts/{ours}/walk?upto=5").text):
        assert "Start a prelim case" not in html
