"""Automotive map: grade conventions, computed A/B levels, curated rows and the review round trip."""

from sqlalchemy.orm import Session

from app.db import get_engine
from app.services import autograde, vocab
from app.services import automotive as au


def test_grade_order_and_conventions():
    g = autograde.grade
    assert g({"mpn": "X1", "values": {"qualification": "automotive"}})[0] == autograde.AUTOMOTIVE
    assert g({"mpn": "SI8641BD-AM", "values": {"qualification": "industrial"}})[0] == autograde.NOT_AUTO  # stated wins
    assert g({"mpn": "X2", "description": "AEC-Q100 Grade 1 switch"})[1] == "description says AEC-Q"
    assert g({"mpn": "SI8234AB-AM"})[0] == autograde.AUTOMOTIVE
    assert g({"mpn": "SI8642ED-AU"})[0] == autograde.AUTOMOTIVE
    assert g({"mpn": "QPQ1035Q"})[1] == "part-number convention: Q suffix (Qorvo)"
    assert g({"mpn": "SKYA21024"})[0] == autograde.NOT_STATED  # the SKYA prefix is not used: not reliable
    assert g({"mpn": "QPQ1035"})[0] == autograde.NOT_STATED


def test_cell_levels():
    comp_a = {"level": "A", "why": "", "parts": []}
    comp_b = {"level": "B", "why": "", "parts": []}
    row_c = {"level": "C", "why": "a  variant", "sources": ["T, P, 2026, https://example.org/x.pdf (search only)"]}
    assert au._cell(None, comp_a)["level"] == "A"
    assert au._cell(None, comp_b)["level"] == "B"
    assert au._cell(None, {"level": None})["level"] == "gap"
    assert au._cell(None, None) is None  # the customer's own part
    c = au._cell(row_c, comp_a)  # we already sell it: the row is the next step
    assert c["level"] == "A" and c["next"]["level"] == "C" and c["next"]["why"] == "a variant"
    assert c["next"]["sources"][0] == {"text": "T, P, 2026 (search only)", "url": "https://example.org/x.pdf"}
    assert au._cell({**row_c, "override": True}, comp_a)["level"] == "C"
    assert au._cell(row_c, {"level": None})["level"] == "C"


def test_moves_rank_research_first():
    cells = [
        {"fn": "pmic", "label": "PMIC", "level": "B", "key": "a:pmic", "app_label": "A", "category": "power"},
        {"fn": "pmic", "label": "PMIC", "level": "B", "key": "b:pmic", "app_label": "B", "category": "power"},
        {"fn": "v2x_fem", "label": "V2X", "level": "A", "key": "v:v2x_fem", "app_label": "V", "category": "rf",
         "next": {"level": "C", "title": "Two-carrier", "demand": "high", "driver": "FCC 2026"}},
    ]  # fmt: skip
    moves = au._moves(cells)  # without scores: research demand first
    assert [m["label"] for m in moves] == ["Two-carrier", "PMIC"]
    assert moves[0]["now"] == "A" and moves[0]["driver"] == "FCC 2026" and len(moves[1]["apps"]) == 2
    assert [m["distance"] for m in moves] == [3, 1]  # C and B on the distance scale
    scored = au._moves(cells, lambda fn, step: {"score": {"pmic": 80, "v2x_fem": 60}[fn]})
    assert [m["label"] for m in scored] == ["PMIC", "Two-carrier"]  # the Opportunity score ranks; demand text stays
    assert scored[1]["driver"] == "FCC 2026" and scored[0]["opp"]["score"] == 80


def test_config_ids_are_known():
    fns = vocab.functions()
    apps = {a["id"] for a in au.config()["applications"]}
    for r in au.config()["rows"]:
        assert r["fn"] in fns, r["fn"]
        assert r["app"] == "*" or r["app"] in apps, r["app"]
        assert r.get("level", "C") in ("B", "C", "D", "gap")


def test_page_and_review_round_trip(client):
    r = client.get("/business/automotive")
    assert r.status_code == 200 and "Automotive map" in r.text and "Top moves" in r.text
    assert 'class="am-app"' in r.text  # the default view groups each application's functions by level
    assert client.get("/business/automotive?view=all").status_code == 200
    assert 'class="am-matrix"' in client.get("/business/automotive?view=rf").text
    with Session(get_engine()) as s:
        cells = au.build(s)["cells"]
    key = next(c["key"] for c in cells.values() if c["status"] == "proposed")
    page = client.get(f"/business/automotive?cell={key}")
    assert 'name="verdict" value="reject"' in page.text
    r = client.post("/business/automotive/review", data={"cell": key, "verdict": "reject"}, follow_redirects=False)
    assert r.status_code == 303
    with Session(get_engine()) as s:
        m = au.build(s)
    assert m["cells"][tuple(key.split(":", 1))]["status"] == "rejected"
    assert key in [c["key"] for c in m["rejected"]]
    client.post("/business/automotive/review", data={"cell": key, "verdict": "reset"})
    with Session(get_engine()) as s:
        assert au.build(s)["cells"][tuple(key.split(":", 1))]["status"] == "proposed"
    assert client.post("/business/automotive/review", data={"cell": "x:y", "verdict": "accept"}).status_code == 400
