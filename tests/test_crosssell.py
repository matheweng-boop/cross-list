"""Cross-sell from a part number, optionally narrowed by loosely described application words."""

from app.services import crosssell as cs
from app.services import opportunity as op


def test_application_words_are_loose():
    apps = op.applications()
    for q, want in [("dcdc", "dc/dc"), ("DC-DC", "dc/dc"), ("broadcst", "radio"), ("ev chargr", "charger")]:
        hits = cs.match_applications(apps, q)
        assert hits, q
        assert any(want in a.name.lower() for a, _, _ in hits[:15]), q
    assert cs.match_applications(apps, "zzqqxx") == []


def test_part_number_resolves_to_function(session):
    p = cs.resolve_part(session, "SKY87604")
    assert p and p["fns"][0] == "load_switch" and p["ours"]
    assert cs.resolve_part(session, "zz") is None


def test_suggestions_ordered_with_reasons(session):
    p = cs.resolve_part(session, "SKY87604")
    r = cs.suggest(session, p, "dcdc")
    assert 0 < r["n"] <= r["n_with_part"]
    scores = [e["score"] for e in r["ours"]]
    assert scores == sorted(scores, reverse=True)
    top = r["ours"][0]
    assert top["fn"] != "load_switch" and top["why"]["n"] and top["offer"]


def test_page(client):
    r = client.get("/business/attach?part=SKY87604&app=dcdc")
    assert r.status_code == 200 and "Offer with it" in r.text and "SKY87604" in r.text
    assert "No part number starting with" in client.get("/business/attach?part=zzzzzz").text
