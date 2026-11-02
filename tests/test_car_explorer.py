"""Car explorer (Systems & applications; owner, 2 Nov 2026): the area -> application mapping, the letters live from
the Automotive map (rejected calls hidden), the seat row from its block diagram, the links, the vendored three.js and
the page."""

import re

from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT
from app.db import get_engine
from app.services import automotive as au
from app.services import blocks
from app.services import car_explorer as ce
from app.services import systems as sy

STATIC = PROJECT_ROOT / "app" / "web" / "static"
VENDOR = STATIC / "vendor" / "three"


def _fns(areas, area: str, app: str) -> dict[str, str]:
    """{function: letter} of one application in one area, the "+N more" ones included."""
    row = next(a for z in areas if z["id"] == area for a in z["apps"] if a["id"] == app)
    return {c["fn"]: r["level"] for r in row["rows"] for c in r["shown"] + r["more"]}


def test_mapping_is_the_approved_one():
    """The mockup the owner approved, area by area, with its three notes."""
    got = {z["id"]: z["apps"] for z in ce.config()["areas"]}
    assert got == {"seat": ["seat", "incabin"], "rear-seats": ["incabin"], "dashboard": ["infotainment"],
                   "roof": ["telematics", "v2x", "satellite"], "front": ["adas"], "lights": [],
                   "battery": ["bms"], "motor": ["traction"], "charge-port": ["onboard", "charging"],
                   "doors": ["access", "body"]}  # fmt: skip
    assert {z["id"] for z in ce.config()["areas"] if z.get("note")} == {"seat", "lights", "charge-port"}


def test_every_id_is_known():
    apps = {a["id"] for a in au.applications()}
    rows = {d["id"] for d in ce.config()["diagram_rows"]}
    assert not apps & rows  # a diagram row never stands in for a map application
    ids = [z["id"] for z in ce.config()["areas"]]
    assert len(ids) == len(set(ids))
    for z in ce.config()["areas"]:
        assert set(z["apps"]) <= apps | rows, z["id"]
    for d in ce.config()["diagram_rows"]:
        assert ce.diagram_index(d["diagram"]) is not None, d["diagram"]  # renamed in data/blocks/templates.yaml?
        assert d["letters_from"] in apps
    for app, sub in ce.config()["subs"].items():
        assert app in apps and sy.sub(ce.SYSTEM, sub), (app, sub)


def test_the_3d_car_has_every_area_and_no_other():
    js = (STATIC / "car_explorer.js").read_text()
    in_js = set(re.findall(r'zone\("([a-z-]+)"', js)) | set(re.findall(r'seat\([^()]*"([a-z-]+)"\)', js))
    assert in_js == {z["id"] for z in ce.config()["areas"]}


def test_areas_show_the_map_letters_six_at_a_time(session):
    m = au.build(session)
    apps = {a["id"]: a for a in m["apps"]}
    zs = ce.areas(session)
    assert [z["id"] for z in zs] == [z["id"] for z in ce.config()["areas"]]
    seen = 0
    for z in zs:
        assert z["n_diagrams"] == sum(a["n_diagrams"] for a in z["apps"])
        for a in z["apps"]:
            if a["id"] not in apps:
                continue
            want = au.by_level(m, a["id"], m["columns"])  # what the map holds, rejected calls left out
            assert [r["level"] for r in a["rows"]] == [lv for lv in au.LEVELS if lv in want]
            assert a["n_diagrams"] == len(apps[a["id"]]["car"])  # car diagrams only
            for r in a["rows"]:
                chips = r["shown"] + r["more"]
                assert [c["fn"] for c in chips] == [c["fn"] for c in want[r["level"]]]
                assert r["n"] == len(chips) and len(r["shown"]) == min(ce.SHOWN, r["n"])
                assert all(c["href"].startswith("/business/automotive?view=apps&cell=") for c in chips)
                seen += len(r["more"])
        assert z["counts"] == {lv: sum(r["n"] for a in z["apps"] for r in a["rows"] if r["level"] == lv)
                               for lv in au.LEVELS}  # fmt: skip
    assert seen  # some letter has more than six functions: "+N more"


def test_lights_say_there_is_no_lighting_application(client, session):
    lights = next(z for z in ce.areas(session) if z["id"] == "lights")
    assert lights["apps"] == [] and "no lighting application" in lights["note"]
    html = client.get("/business/car-explorer?area=lights").text
    panel = html[html.index('id="ce-area-lights"') :]
    panel = panel[: panel.index("</section>")]
    assert "no lighting application" in panel and "lv-tabs" not in panel and "Body" not in panel


def test_a_rejected_call_leaves_the_explorer_too(client, session):
    c = next(c for c in au.build(session)["cells"].values() if c["app"] == "bms" and c["status"] == "proposed")
    assert c["fn"] in _fns(ce.areas(session), "battery", "bms")
    client.post("/business/automotive/review", data={"cell": c["key"], "verdict": "reject"})
    with Session(get_engine()) as s:
        assert c["fn"] not in _fns(ce.areas(s), "battery", "bms")
    client.post("/business/automotive/review", data={"cell": c["key"], "verdict": "reset"})
    with Session(get_engine()) as s:
        assert c["fn"] in _fns(ce.areas(s), "battery", "bms")


def test_seat_row_is_the_seat_diagram_with_the_body_letters(session):
    i = ce.diagram_index("Automotive seat adjustment and comfort actuators")
    fns = blocks.template_functions(blocks.templates()[i])
    want = {fn: c["level"] for fn, c in au.cells_for(session, "body", fns).items() if c["status"] != "rejected"}
    got = _fns(ce.areas(session), "seat", "seat")
    assert got == want
    assert {"lin_transceiver", "motor_controller", "hall_switch", "tvs_esd"} <= set(got)  # the seat module's blocks
    assert "mcu" not in got  # the customer's own parts are left out, as on the map
    body = au.build(session)["cells"]
    seat = next(a for z in ce.areas(session) if z["id"] == "seat" for a in z["apps"] if a["id"] == "seat")
    chips = {c["fn"]: c for r in seat["rows"] for c in r["shown"] + r["more"]}
    for fn, c in chips.items():  # a function links to its cell only where the map's Body row has it
        assert bool(c["href"]) == (("body", fn) in body), fn
    assert seat["n_diagrams"] == 1
    assert seat["links"]["blocks"] == "/blocks?system=automotive&sub=cockpit"
    assert seat["links"]["cross_sell"] == f"/blocks/cross-sell?system=automotive&sub=cockpit&template={i}"
    assert seat["links"]["map"] == "/business/automotive?view=apps#app-body"


def test_links_follow_the_application_diagrams(client, session):
    rows = {a["id"]: a for z in ce.areas(session) for a in z["apps"]}
    assert rows["bms"]["links"]["blocks"] == "/blocks?system=automotive&sub=battery-power"
    assert rows["telematics"]["links"]["cross_sell"] == "/blocks/cross-sell?system=automotive&sub=telematics-v2x"
    assert rows["satellite"]["links"]["blocks"] == "/blocks?system=automotive&sub=telematics-v2x"  # no diagram
    assert rows["adas"]["links"]["map"] == "/business/automotive?view=apps#app-adas"
    assert rows["bms"]["links"]["sub_title"] == "Battery and power distribution"
    for url in (rows["bms"]["links"]["blocks"], rows["bms"]["links"]["cross_sell"], rows["bms"]["links"]["map"]):
        assert client.get(url).status_code == 200, url
    assert 'id="app-adas"' in client.get(rows["adas"]["links"]["map"]).text


def test_page_lists_the_areas_and_loads_three_from_this_site(client):
    html = client.get("/business/car-explorer").text
    assert html.count('class="lv-tabs"') == sum(1 for z in ce.config()["areas"] if z["apps"])  # letter tabs per area
    assert "/static/lv_tabs.js" in html and 'data-lv="gap"' in html
    assert "<title>Car explorer – Systems &amp; applications – BizDev</title>" in html
    assert '{"imports": {"three": "/static/vendor/three/three.module.min.js"}}' in html
    assert "/static/car_explorer.js" in html and "jsdelivr" not in html and "unpkg" not in html
    assert html.count(" data-area=") == len(ce.config()["areas"])
    assert '<section class="ce-panel" data-lv-scope id="ce-area-battery" aria-labelledby="ce-h-battery" hidden>' in html
    opened = client.get("/business/car-explorer?area=battery").text  # also without JavaScript
    assert '<section class="ce-panel" data-lv-scope id="ce-area-battery" aria-labelledby="ce-h-battery">' in opened
    assert 'aria-current="true">High-voltage battery</a>' in opened
    assert client.get("/business/car-explorer?area=nowhere").status_code == 200
    assert 'href="/business/car-explorer"' in client.get("/business/automotive").text  # the map links here


def test_menu_entry_next_to_the_automotive_map():
    from app.web import nav

    hrefs = [href for key, _, items in nav.NAV if key == "systems" for _, href, _ in items]
    assert hrefs[hrefs.index("/business/automotive") + 1] == "/business/car-explorer"
    assert nav.place("/business/car-explorer") == ("systems", "/business/car-explorer")


def test_three_js_is_served_from_this_site_with_its_licence(client):
    lic = (VENDOR / "LICENSE").read_text()
    assert "The MIT License" in lic and "three.js authors" in lic
    assert 'const t="160"' in (VENDOR / "three.module.min.js").read_text()[:400]  # REVISION 160 = three@0.160.0
    assert "} from 'three';" in (VENDOR / "OrbitControls.js").read_text()  # resolved by the page's import map
    for path in ("/static/vendor/three/three.module.min.js", "/static/vendor/three/OrbitControls.js",
                 "/static/car_explorer.js"):  # fmt: skip
        r = client.get(path)
        assert r.status_code == 200 and "javascript" in r.headers["content-type"], path  # module scripts need it
    assert "http" not in (STATIC / "car_explorer.js").read_text()  # nothing from another site at runtime
