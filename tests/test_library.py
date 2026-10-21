"""Systems library: topic files are consistent (six references, valid functions, rules cite references) and the pages
and the workspace open them."""

import pytest

from app.services import library, vocab

KEYS = sorted(p.stem for p in (library.FOLDER / "topics").glob("*.yaml"))


def test_sources_page(client):
    assert len(library.sources()) >= 20
    assert all(s["feasibility"] in library.FEASIBILITY for s in library.sources())
    html = client.get("/library/sources").text
    assert "OpenAlex" in html and "Blocked" in html
    assert client.get("/library").status_code == 200


@pytest.mark.parametrize("key", KEYS)
def test_topic_file_is_consistent(key):
    t = library.topic(key)
    refs = library.refs_by_id(t)
    assert t.get("title") and t.get("summary") and len(t["references"]) == 6 and len(refs) == 6
    assert all(r.get("url") and r.get("licence") for r in t["references"])
    fns = vocab.functions()
    d = t["block_diagram"]
    gids = {g["id"] for g in d["groups"]}
    for g in d["groups"]:
        for b in g["blocks"]:
            fn = b["fn"] if isinstance(b, dict) else b
            assert vocab.canonical(fn) in fns, fn
    assert all(lk[0] in gids and lk[1] in gids for lk in d.get("links") or [])
    for x in [*t["design_rules"], *t["trends"]]:
        assert x.get("refs") and set(x["refs"]) <= set(refs), x
    assert all(vocab.canonical(s["fn"]) in fns for s in t.get("skyworks_fit") or [])


@pytest.mark.parametrize("key", KEYS)
def test_topic_pages(client, key):
    t = library.topic(key)
    html = client.get(f"/library/{key}").text
    assert t["title"].replace("&", "&amp;") in html or t["title"] in html
    assert client.get(f"/blocks/new?library={key}").status_code == 200


def test_library_feeds_the_decision_pages(client):
    ev = client.get("/business/evidence/digital_isolator").text
    assert "From the systems library" in ev and "/library/traction_asil_d" in ev
    case = client.get("/business/reports/auto-cv2x-fe").text
    assert "From the systems library" in case and "/library/v2x_frontend" in case
    topic = client.get("/library/v2x_frontend").text
    assert "/business/reports/auto-cv2x-fe" in topic and "Full research notes" in topic
    hits = client.get("/technical?q=DESAT blanking").text
    assert "/library/traction_asil_d#" in hits
    assert {c["slug"] for c in library.cases_using("auto_uwb")} == {"auto-uwb-15-4ab", "auto-uwb-cpd"}
    assert library.for_function("digital_isolator")[0]["ours"]


def test_disagree_lowers_a_rule_confidence(client, session):
    t = library.topic("traction_asil_d")
    rule = next(r for r in t["design_rules"] if r.get("conf") in ("high", "med"))
    r = client.post("/library/traction_asil_d/react", data={"item": rule["id"], "verdict": "disagree",
                                                            "comment": "datasheet says otherwise"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    got = next(x for x in library.reviewed(session, "traction_asil_d")["design_rules"] if x["id"] == rule["id"])
    assert got["conf_was"] == rule["conf"] and got["conf"] != rule["conf"] and got["fb"]["verdict"] == "wrong"
    assert "/library/traction_asil_d#i-" in client.get("/manage/reviews").text
    assert client.post("/library/traction_asil_d/react", data={"item": "nope", "verdict": "agree"}).status_code == 400
