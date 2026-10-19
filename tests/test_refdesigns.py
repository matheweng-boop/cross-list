"""Reference designs page: public data in data/reference_designs (read as files, no network)."""

from app.services import refdesigns


def test_design_files_are_well_formed():
    rows = refdesigns.designs()
    assert rows
    ids = [(d["vendor"], d["id"]) for d in rows]
    assert len(ids) == len(set(ids))
    for d in rows:
        assert d["url"].startswith("https://")
        for v in (d.get("documents") or {}).values():
            for u in v if isinstance(v, list) else [v]:
                assert u.startswith("https://")


def test_search_and_filters():
    iso = refdesigns.search(isolation=True)
    assert iso and all(d.get("isolation") for d in iso)
    d = iso[0]
    assert d in refdesigns.search(d["id"].lower())
    fn = next(d["functions"][0] for d in refdesigns.designs() if d.get("functions"))
    assert all(fn in d["functions"] for d in refdesigns.search(fn=fn))


def test_page_renders_with_filters(client):
    r = client.get("/reference-designs?iso=1&page=2")
    assert r.status_code == 200
    assert "Reference designs" in r.text and "rd-card" in r.text
    assert client.get("/reference-designs?q=zzzz-no-such").text.count("rd-card") == 0
