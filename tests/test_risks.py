"""Opportunities > Risks: the data validates, every risk has public sources and est markings, the page renders and its
internal links open."""

import re

from app.services import risks


def test_risks_data_is_valid_and_sourced():
    d = risks.load()
    assert not d["errors"]
    ids = {g["id"] for g in d["groups"]}
    assert {"isolation", "timing", "rf", "radio", "power"} <= ids  # owner's families
    for g in d["groups"]:
        for r in g["risks"]:
            assert r["sources"] and r["signs"] and r["who"] and r["impact"], r["id"]
    assert any(r["id"] == "iso-low-cost-capacitive" for r in risks.urgent(d))


def test_bad_risk_is_reported():
    bad = {"groups": [{"id": "x", "name": "X", "ours": "o", "risks": [
        {"id": "a", "threat": "t", "who": ["W"], "impact": "i", "signs": ["s"], "sources": ["s"],
         "likelihood": "maybe", "when": "soon", "kind": "technology", "links": [{"label": "l", "href": "ftp://x"}]},
        {"id": "a", "threat": "t", "kind": "technology", "likelihood": "low", "when": "now"}]}]}  # fmt: skip
    errs = risks.validate(bad)
    assert any("likelihood" in e for e in errs) and any("when must" in e for e in errs)
    assert any("link" in e for e in errs) and any("twice" in e for e in errs) and any("sources" in e for e in errs)


def test_risks_page_and_links(client):
    from app.web import nav

    opp = dict((k, items) for k, _, items in nav.NAV)["opportunities"]
    assert "/business/risks" in [i[1] for i in opp]
    html = client.get("/business/risks").text
    for g in risks.load()["groups"]:
        assert f'id="{g["id"]}"' in html and g["name"] in html
    assert "(est)" in html and 'href="/business/competitors/novosense"' in html
    for href in sorted(set(re.findall(r'href="(/[^"#]*)"', html.split("<h1>", 1)[1]))):
        assert client.get(href.replace("&amp;", "&")).status_code == 200, href
