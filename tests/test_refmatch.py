"""Public reference designs as a knowledge base behind the diagrams, gaps and parts (owner, 25 Oct 2026): the page
is out of the menu but reachable by precise links; one diagram per application informed by all matched designs;
"Found in N" on gaps; anchors (design parts we cross)."""

import importlib.util
import re
import time
from pathlib import Path

from app.services import blocks, refdesigns, refmatch
from app.web import nav
from tests.conftest import ids

ROOT = Path(__file__).resolve().parents[1]
TRACTION = "EV traction inverter"


def _n_designs(html: str) -> int:
    return html.count('class="rd-card"')


def test_menu_has_no_reference_designs_but_the_page_works(client):
    menu = [label for _, _, items in nav.NAV for label, _, _ in items]
    assert "Reference designs" not in menu
    assert nav.PLACES["/reference-designs"][0] == "systems"
    r = client.get("/reference-designs")
    assert r.status_code == 200 and 'name="q"' in r.text  # still searchable
    assert 'aria-current="page" class="on">Application library<' in r.text  # highlights Systems & applications


def test_filtered_lists_by_fn_diagram_and_part(client):
    fn = "gate_driver"
    r = client.get(f"/reference-designs?fn={fn}&view=list")
    assert "Reference designs where Isolated gate driver appears" in r.text
    n = refmatch.fn_count(fn)
    assert f"<b>{n:,}</b> public reference designs" in r.text
    e = refmatch.for_template(next(t for t in blocks.templates() if t["name"] == TRACTION))
    r = client.get(f"/reference-designs?diagram={e['key']}")
    assert "Reference designs used for the block diagram EV traction inverter" in r.text
    assert f"<b>{e['n']}</b> public reference designs" in r.text
    assert _n_designs(r.text) == min(e["n"], 50)
    first = refmatch.index()["by_key"][e["designs"][0]]
    assert first["id"] in r.text
    r = client.get("/reference-designs?part=ISO7741DBQR")  # an orderable number finds the designs' ISO7741
    name, keys = refmatch.part_designs("ISO7741DBQR")
    assert name == "ISO7741" and len(keys) >= 5
    assert "Reference designs that use ISO7741" in r.text and _n_designs(r.text) == min(len(keys), 50)
    assert all("ISO7741" in [refmatch.stem(p) for p in refmatch.index()["by_key"][k]["parts"]] for k in keys)


def test_library_diagram_is_based_on_matched_designs(client):
    i = next(i for i, t in enumerate(blocks.templates()) if t["name"] == TRACTION)
    e = refmatch.for_template(blocks.templates()[i])
    assert e["n"] >= 5 and len(e["designs"]) == e["n"]
    page = client.get(f"/blocks/new?template={i}").text
    assert f"Based on <a href=\"/reference-designs?diagram={e['key']}\">{e['n']} public reference designs</a>" in page
    assert "Confirmed by the designs" in page
    # one diagram per application: the designs never become diagrams of their own
    assert len(blocks.templates()) < 300 < len(refdesigns.designs())
    # the library card says it too
    assert f"Based on {e['n']} public reference designs" in client.get("/blocks?system=automotive").text


def test_suggestions_and_additions_follow_the_thresholds():
    data = refmatch.data()
    for e in data["diagrams"]:
        for s in e["suggested"]:
            assert e["n"] >= refmatch.MIN_DESIGNS_FOR_SUGGESTIONS and s["n"] / e["n"] >= refmatch.SUGGEST_SHARE
    added = [(t["name"], b["fn"]) for t in blocks.templates() for g in t["groups"] for b in g["blocks"]
             if isinstance(b, dict) and b.get("src") == "refdesigns"]  # fmt: skip
    # stricter since 25 Oct 2026 (>= 60 % and >= 8 designs): the two earlier additions no longer qualified and were
    # removed with their note; any addition left must still follow the thresholds
    assert not any(t["name"] == "USB-C power bank (TI)" and "power_fets" in blocks.template_functions(t)
                   for t in blocks.templates())  # fmt: skip
    for e in data["diagrams"]:
        t = next(t for t in blocks.templates() if refmatch.diagram_key(t) == e["key"])
        assert not refmatch.to_add(e, blocks.template_functions(t)), "the script added every qualifying block"
    for name, fn in added:
        t = next(t for t in blocks.templates() if t["name"] == name)
        e = refmatch.for_template(t)
        assert e["functions"][fn] >= refmatch.ADD_MIN and e["functions"][fn] / e["n"] >= refmatch.ADD_SHARE
        assert fn in t["refdesigns_added"]  # the source note on the template


def test_gaps_show_found_in_n_with_a_link(client):
    page = client.get("/business/opportunities").text
    m = re.search(r'Found in <a href="/reference-designs\?fn=([a-z_0-9]+)">(\d+) public reference design', page)
    assert m, "a gap card names the reference designs"
    fn, n = m.group(1), int(m.group(2))
    assert n == refmatch.fn_count(fn)
    assert _n_designs(client.get(f"/reference-designs?fn={fn}&view=list").text) == min(n, 50)
    assert "Found in" in client.get("/business/explorer/table").text
    # the block editor's gap list has the counts for every function
    assert '"counts": {' in client.get("/blocks/new").text.replace('{"counts":{', '"counts": {')


def test_reference_designs_page_is_fast(client):
    t = time.time()
    r = client.get("/reference-designs")  # first visit right after start-up (warm-up running alongside)
    assert r.status_code == 200 and time.time() - t < 3.0
    t = time.time()
    for u in ("/reference-designs?q=inverter", "/reference-designs?part=UCC21540", "/reference-designs?fn=adc"):
        assert client.get(u).status_code == 200
    assert time.time() - t < 6.0


def test_anchor_is_detected_for_a_crossed_competitor_part(session, real):
    a = refmatch.compute_anchors(session, [{"vendor": "TI", "id": "X", "parts": ["ISO7741-Q1", "NOPE123"]}])
    assert set(a) == {"ISO7741-Q1"}
    assert a["ISO7741-Q1"]["maker"] == "Skyworks" and a["ISO7741-Q1"]["fn"] == "digital_isolator"
    assert a["ISO7741-Q1"]["type"] in ("Drop-in", "Functional", "Package eq.")
    assert refmatch.stem("UCC21750-Q1") == "UCC21750"


def test_anchors_on_the_diagram_list_and_gaps_around_them(client):
    data = refmatch.data()
    assert data["anchors"]["ISO7741"]["maker"] == "Skyworks"
    e = next(e for e in data["diagrams"] if e["anchors"])
    a = e["anchors"][0]
    assert a["n"] == len(a["designs"]) and set(a["designs"]) <= set(e["designs"])
    i = next(i for i, t in enumerate(blocks.templates()) if refmatch.diagram_key(t) == e["key"])
    page = client.get(f"/blocks/new?template={i}").text
    assert 'class="anchor-badge">Anchor</span>' in page and f"use <b>{a['part']}</b> → we cross with" in page
    assert "Designs with this anchor also use:" in page  # the functions around the anchor (we have / no part)
    assert '"anchors": {"' in page.replace('"anchors":{"', '"anchors": {"')  # the diagram marks the anchor block
    lst = client.get(f"/reference-designs?diagram={e['key']}&anchor={a['part']}").text
    assert _n_designs(lst) == min(a["n"], 50) and "with an anchor for" in lst
    assert f"<b>{a['part']}" in lst or "rd-anchor" in lst
    around = refmatch.around(a["designs"], {a["fn"]})
    assert around and all(f != a["fn"] for f, _ in around)


def test_cross_sell_starts_from_the_anchors(client):
    from app.services import systems as sy

    s, x = next((s, x) for s in sy.systems() for x in s["subsystems"]
                if refmatch.anchors_for([blocks.templates()[i] for i in x["idx"]], {}))  # fmt: skip
    page = client.get(f"/blocks/cross-sell?system={s['key']}&sub={x['key']}").text
    assert "Anchors: where to start" in page and "Designs with this anchor also use:" in page


def test_part_page_names_reference_designs_and_anchor(client, real):
    r = client.get(f"/parts/{ids(client, 'ISO7741DBQR')}")
    n = len(refmatch.part_designs("ISO7741DBQR")[1])
    assert f'Used in <a href="/reference-designs?part=ISO7741">{n} public reference designs</a>' in r.text
    assert "Anchor</span> for SI86" in r.text


def test_match_script_runs_and_is_deterministic(tmp_path):
    spec = importlib.util.spec_from_file_location("match_refdesigns", ROOT / "scripts" / "match_refdesigns.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    a, b = tmp_path / "a.yaml", tmp_path / "b.yaml"
    assert mod.main(["--no-crosses", "--out", str(a)]) == 0
    assert mod.main(["--no-crosses", "--out", str(b)]) == 0
    assert a.read_text() == b.read_text()
    # the committed file has the same matches (anchors need the crosses, left out of this quick run)
    quick = {e["key"]: e["designs"] for e in refmatch.yamlio.load(a.read_text())["diagrams"]}
    assert quick == {e["key"]: e["designs"] for e in refmatch.data()["diagrams"]}
