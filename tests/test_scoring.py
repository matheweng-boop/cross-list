"""Opportunity score: weights, mappings, neutral values, suggestion types, the TAM switch and reviewer feedback."""

from sqlalchemy.orm import Session

from app.db import get_engine
from app.services import opportunity as op
from app.services import prelim, scoring


def _apps(ours: frozenset = frozenset({"load_switch"})) -> list[op.Application]:
    """Every diagram with a fixed portfolio, so the tests do not depend on the parts database."""
    apps = op.applications()
    for a in apps:
        for p in a.positions:
            p.status = "supported" if p.fn in ours else "gap"
    return apps


def test_weights_and_mappings():
    assert sum(scoring.weights().values()) == 100
    cfg = scoring.config()
    assert set(cfg["weights"]) == set(cfg["labels"])
    d = scoring.distance
    assert [d({"path": p})[0] for p in ("exists", "variant", "new_design", "new_capability")] == [0, 1, 3, 4]
    assert [d(proximity=p)[0] for p in (3, 2, 1, 0)] == [1, 3, 4, 4]
    assert d({"path": "variant"}, proximity=0)[0] == 1  # the path wins over the technology rating
    assert d(status="supported")[0] == 0 and d() == (None, "no path or technology rating yet", "low", "")
    assert d({"path": "new_design", "confidence": "high"})[2] == "high"
    assert [scoring.ladder_distance(x) for x in "ABCD"] == [0, 1, 3, 4] and scoring.ladder_distance("C", 2) == 2
    assert [scoring.feasibility(x) for x in range(5)] == [1, 1, 2, 2, 3] and scoring.feasibility(None) is None
    assert cfg["distance"]["points"] == {0: 100, 1: 85, 2: 65, 3: 40, 4: 15}
    assert cfg["competition"]["values"] == {"low": 100, "medium": 60, "high": 30}


def test_neutral_for_missing_data_and_suggestion_types():
    f = scoring._factor("competition", None, "not assessed", "high")
    assert f["value"] == scoring.config()["neutral"] == 50 and f["confidence"] == "low"
    assert scoring._competition(None) == (None, "not assessed", "low")
    assert scoring._trend({})[0] is None and scoring._trend({"regulation": "NG-eCall 2026"})[0] == 100
    # the type comes from distance and how many diagrams need it, not from the score
    cases = [(0, 50), (2, 10), (3, 10), (1, 9), (3, 1), (4, 200), (None, 50)]
    assert [scoring.suggestion(d, n) for d, n in cases] == ["quick_win", "quick_win", "new_chip", "niche", "niche",
                                                            "partner", "unknown"]  # fmt: skip
    neutral = [scoring._factor(k, None, "", "low") for k in scoring.weights()]
    r = scoring.result(neutral)
    assert r["score"] == 50 and r["suggestion"] == "unknown" and r["suggestion_label"] == "Not assessed yet"
    assert r["confidence"] == "low"


def test_confidence_steps():
    assert scoring.lower("high") == "medium" and scoring.lower("medium") == "low" and scoring.lower("low") == "low"
    assert scoring.conf("med") == "medium" and scoring.conf(None) == "low"
    confs = ("high", "medium", "low", "high", "low")
    fs = [scoring._factor(k, 80, "", c) for k, c in zip(scoring.weights(), confs, strict=True)]
    assert scoring.result(fs)["confidence"] == "medium"  # demand / distance / competition only; trend does not count


def test_table_scores_every_function_and_tam_switch():
    apps = _apps()
    tab = scoring.table(apps)
    rows = tab["rows"]
    assert rows and all(0 <= r["score"] <= 100 and r["suggestion_label"] for r in rows.values())
    assert max(f["value"] for r in rows.values() for f in r["factors"] if f["key"] == "demand") == 100
    assert all(not scoring.scorable(fn, tab["usage"][fn]) for fn in op._NOT_CHIPS if fn in tab["usage"])
    fn = "pol_ldo"
    assert rows[fn]["demand_basis"] == "diagrams"
    app = next(a for a in apps if any(p.fn == fn for p in a.positions))
    with_tam = scoring.table(apps, {fn: 0.5}, {app.name: 10_000_000})
    demand = next(f for f in with_tam["rows"][fn]["factors"] if f["key"] == "demand")
    assert with_tam["rows"][fn]["demand_basis"] == "tam" and demand["basis"].startswith("TAM")
    assert demand["confidence"] == scoring.config()["demand"]["tam_confidence"]
    assert scoring.table(apps, {fn: 0.5}, {})["rows"][fn]["demand_basis"] == "diagrams"  # ASP alone is not enough


def test_disagree_lowers_confidence_and_agree_does_not():
    apps = _apps()
    fn = next(f for f, c in op.competition().items() if (c.get("check") or {}).get("status") == "confirmed"
              and f in scoring.table(apps)["rows"])  # fmt: skip

    def comp(verdicts):
        r = scoring.table(apps, verdicts=verdicts)["rows"][fn]
        return next(f for f in r["factors"] if f["key"] == "competition")

    assert comp({})["confidence"] == "high"
    assert comp({("competition", fn): "correct"})["confidence"] == "high"
    wrong = comp({("competition", fn): "wrong"})
    assert wrong["confidence"] == "medium" and "disputed" in wrong["basis"] and wrong["value"] == comp({})["value"]


def test_rescore_band_row_and_bundle():
    tab = scoring.table(_apps())
    a = scoring.rescore(tab, "pol_ldo", 0, "today", "high")
    b = scoring.rescore(tab, "pol_ldo", 4, "new technology", "high")
    # both scores are rounded, so their difference is within 1 of the weighted distance step
    assert abs(a["score"] - b["score"] - (100 - 15) * scoring.weights()["distance"] / 100) < 1
    assert scoring.rescore(tab, "not_a_function", 0, "", "high") is None
    row = {"fn": "lna", "reach": 3, "rf_kind": "none", "band_note": "no part of ours", "competition": None}
    r = scoring.band_row(tab, row)
    arch, comp = (next(f for f in r["factors"] if f["key"] == k) for k in ("architecture", "competition"))
    assert r["distance"] == 3 and arch["value"] == comp["value"] == 50 and comp["confidence"] == "low"
    assert scoring.bundle(1, 1, 1) == 100 and scoring.bundle(0.5, 0, 0) == 30 and scoring.bundle(0, 0, 0) == 0


def test_case_score_feasibility_and_disagree(client):
    slug = "auto-gnss-l1l5"
    with Session(get_engine()) as s:
        before = prelim.case(s, slug)
    o = before["opportunity"]
    assert o["fn"] == "gnss_lna" and o["headline"]["id"] == "f-l2" and o["derived"] == 2
    assert o["curated"] == 1 and o["mismatch"] and o["feasibility"] == 1  # curated kept, flagged
    item = next(x for k in prelim.LISTS for x in before["position"][k] if x.get("conf") == "high")
    client.post(f"/business/reports/{slug}/react", data={"key": item["id"], "verdict": "agree"})
    with Session(get_engine()) as s:
        assert prelim.case(s, slug)["opportunity"]["confidence"] == o["confidence"]  # agree changes nothing
    client.post(f"/business/reports/{slug}/react", data={"key": item["id"], "verdict": "disagree"})
    with Session(get_engine()) as s:
        after = prelim.case(s, slug)
    x = next(x for k in prelim.LISTS for x in after["position"][k] if x["id"] == item["id"])
    assert x["conf"] == "med" and x["conf_was"] == "high"
    assert after["opportunity"]["confidence"] == scoring.lower(o["confidence"])
    assert item["id"] in after["opportunity"]["disputed"]
    page = client.get(f"/business/reports/{slug}").text
    assert "Opportunity score" in page and "derived feasibility is 2" in page


def test_every_case_names_a_scored_function():
    for p in prelim.FOLDER.glob("[a-z]*.yaml"):
        c = prelim.raw(p.stem)
        assert c.get("fn") and prelim.headline(c)["id"] == c.get("headline"), p.stem
        assert prelim.derived_feasibility(p.stem) in (1, 2, 3)


def test_pages_show_the_score(client):
    html = client.get("/business/explorer?sort=score").text
    assert "Opportunity score" in html and "of 100" in html
    method = client.get("/business/method").text
    assert all(w in method for w in ("Portfolio distance", "Architecture fit", "Engineering rules", "Bundle strength"))
    assert 'id="research"' in client.get("/business/quality").text
    assert "Level · distance" in client.get("/business/automotive").text
