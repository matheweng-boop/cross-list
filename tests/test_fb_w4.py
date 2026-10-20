"""Site feedback 2026-10-20, W4: verified applications, the editor in its own window, broad reference-design groups."""

from app.services import blocks, refdesigns


def test_application_verified_flag_and_filter(client):
    i = 0
    page = client.get(f"/blocks/new?template={i}").text
    assert "Entered, not verified" in page and "Mark technically verified" in page
    r = client.post("/blocks/verify", data={"i": i, "on": "1", "author": "Ana", "note": "checked vs datasheet"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    page = client.get(f"/blocks/new?template={i}").text
    assert "Technically verified" in page and "Ana" in page and "Back to entered" in page
    lib = client.get("/blocks?verified=yes").text
    assert "Technically verified" in lib and blocks.title_parts(blocks.templates()[i])[0] in lib
    client.post("/blocks/verify", data={"i": i, "on": "0"})
    assert "Entered, not verified" in client.get(f"/blocks/new?template={i}").text
    assert client.post("/blocks/verify", data={"i": 99999, "on": "1"}).status_code == 404


def test_editor_own_window(client):
    full = client.get("/blocks/new?template=0").text
    assert 'id="bk-window"' in full and 'class="shell"' in full
    bare = client.get("/blocks/new?template=0&bare=1").text
    assert 'class="shell bare"' in bare and "Full page" in bare and 'id="bk-window"' not in bare


def test_reference_design_types():
    rows = list(refdesigns.designs())
    tree = refdesigns.type_tree(rows)
    assert sum(t["n"] for t in tree) == len(rows)
    names = [t["type"] for t in tree]
    assert "RF & communications" in names and "Power conversion & energy" in names
    rf = next(t for t in tree if t["type"] == "RF & communications")
    assert all(k in refdesigns.BAND_CLASSES for k, _ in rf["subs"])
    assert refdesigns.sub_class({"title": "800 V traction inverter"}, "Motor drives & motion") == "Above 600 V"
    assert refdesigns.sub_class({"title": "28 GHz beamformer"}, "RF & communications") == "Above 6 GHz"


def test_reference_designs_page_groups(client):
    page = client.get("/reference-designs").text
    assert "rd-types" in page and "By application type" in page
    r = client.get("/reference-designs?atype=RF+%26+communications&view=list")
    assert r.status_code == 200 and "rd-card" in r.text and "Frequency band" in r.text
