"""UWB positioning on one page (owner, 2 Nov 2026: "interactive visuals for the engineering knowledge on
ultra-wideband, specifically two-way ranging, time difference of arrival, lightweight time difference of arrival, and
phase difference of arrival ... packed into a single page, along with visuals"): the page, its four visuals and the
physics behind them."""

import json
import math
import re
import shutil
import subprocess

import pytest

from app.config import PROJECT_ROOT
from app.services import engineering, knowledge, library, visuals

JS = PROJECT_ROOT / "app" / "web" / "static" / "vz" / "uwb_positioning.js"
VIS = ("uwbtwr", "uwbtdoa", "uwbltdoa", "uwbpdoa")
C0 = 299792458


def _page(client) -> str:
    """The page with every run of whitespace as one space (the template wraps its sentences)."""
    page = client.get("/engineering/uwb_positioning")
    assert page.status_code == 200
    return " ".join(page.text.split())


def test_page_has_every_method_a_visual_each_and_the_when_to_use_boxes(client):
    html = _page(client)
    for vid in VIS:
        assert f'data-uwp="{vid}"' in html, vid
    for anchor in ('id="twr"', 'id="tdoa"', 'id="ltdoa"', 'id="pdoa"', 'id="compare"', 'id="parts"', 'id="sources"'):
        assert anchor in html, anchor
    assert html.count("When to use it") == 4
    assert "/static/vz/uwb_positioning.js" in html and "/static/vz/uwb_positioning.css" in html
    for s in ("Two-way ranging", "poll", "response", "final", "T<sub>round1</sub>·T<sub>round2</sub>", "±20 ppm",
              "UL-TDoA", "DL-TDoA", "hyperbola", "backhaul", "Privacy", "Δφ = 2π·d·sin θ / λ", "46.2 mm",
              "37.5 mm", "λ/2", "±90°", "Why it matters to the customer", "kn-est"):
        assert s in html, s
    # comparison table: the methods across, the owner's rows down
    table = html.split('id="compare"', 1)[1].split("</table>", 1)[0]
    for s in ("TWR", "UL-TDoA", "DL-TDoA", "Lightweight TDoA", "PDoA", "Messages per fix", "Tag power",
              "Number of tags", "Infrastructure", "Accuracy", "Privacy", "Typical uses", "Car access",
              "Indoor navigation", "Asset tracking", "Item finding"):
        assert s in table, s


def test_lightweight_tdoa_finding_is_stated_with_the_open_question(client):
    html = _page(client)
    sec = html.split('id="ltdoa"', 1)[1].split('id="pdoa"', 1)[0]
    assert "not a defined method name" in sec and "lightweight uplink message" in sec
    assert "Which document or product used" in sec and "Our reading" in sec and "kn-est" in sec
    assert 'data-uwp="uwbltdoa"' in sec and "Classic TDoA tag" in sec and "Lightweight TDoA tag" in sec


def test_sources_are_linked_and_no_qorvo_page_is(client):
    html = _page(client)
    src = html.split('id="sources"', 1)[1]
    for url in ("https://www.firaconsortium.org/news/press-releases/2025/12/",
                "https://research.samsung.com/blog/FiRa-4-0-Specification-Release-and-Certification-Program-launching",
                "https://arxiv.org/abs/2008.04248", "https://arxiv.org/abs/2211.00538", "https://arxiv.org/abs/2312.13672",
                "https://www.themobileknowledge.com/product/mk-uwb-kit-rtls-2-0/"):  # fmt: skip
        assert f'href="{url}' in src, url
    assert "qorvo.com" not in html
    internal = {h for h in re.findall(r'href="(/[^"#]*)', html) if not h.startswith("/static")}
    assert {"/reviews/how/uwb", "/engineering/uwb_signal_path", "/engineering/uwb_wifi_coexistence"} <= internal
    assert not [h for h in sorted(internal) if client.get(h).status_code >= 400]


def test_parts_section_names_the_pdoa_parts_from_our_data(client):
    html = _page(client)
    parts = html.split('id="parts"', 1)[1].split('id="sources"', 1)[0]
    for mpn in ("QM33120W", "DW3120", "DW3220", "DW3110", "SKY5A2108", "QM14068"):
        assert mpn in parts, mpn
    from app import yamlio

    data = yamlio.load((PROJECT_ROOT / "data" / "catalog" / "qorvo_parts.yaml").read_text())
    cat = {p["mpn"]: p for p in (data if isinstance(data, list) else data["parts"])}
    assert "Dual RF Port" in cat["QM33120W"]["description"] and "2 Antenna Ports" in cat["DW3120"]["description"]
    assert "1 Antenna Port" in cat["DW3110"]["description"]
    for mpn in ("QM33120W", "DW3120", "DW3220"):  # status as shown on the page
        assert re.search(rf"{mpn}</a></td>.*?<td>{cat[mpn]['status']}</td>", parts, re.S), mpn


def test_page_is_registered_like_the_gnss_note(client):
    assert "uwb_positioning" in engineering.NOTES and engineering.has_body("uwb_positioning")
    assert "/engineering/uwb_positioning" in client.get("/engineering").text
    assert knowledge.why("uwb_positioning") and not knowledge.problems()
    card = next(p for p in knowledge.by_product() if p["key"] == "uwb")
    assert "/engineering/uwb_positioning" in {g["href"] for g in card["guides"]}
    assert {f"/visuals#{v}" for v in VIS} <= {x["href"] for x in card["visuals"]}
    assert "uwb_positioning" in library.SPEC_GUIDES
    assert "/engineering/uwb_positioning" in client.get("/reviews/how/uwb").text
    from app.services import how_it_works as hw

    assert "uwb_positioning" in {p["id"] for p in hw.knowledge_pages()}


def test_visuals_are_registered_under_uwb_with_explanations(client):
    js = JS.read_text()
    ex = visuals.explanations()
    html = client.get("/visuals").text
    assert "/static/vz/uwb_positioning.js" in html
    assert html.index("/static/vz/uwb_positioning.js") < html.index('src="/static/visuals.js"')
    for vid in VIS:
        assert f'id: "{vid}", group: "UWB"' in js and library.VISUALS[vid][1] == f"/visuals#{vid}"
        assert vid in ex and f'data-for="{vid}"' in html, vid
    # the existing UWB visual links to the page (the one change allowed in vz/uwb.js)
    assert '"/engineering/uwb_positioning"' in (JS.parent / "uwb.js").read_text()


# ---------------------------------------------------------------- the physics, run in node
def _run(expr: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("node not installed")
    code = ("global.window={};global.document={readyState:'complete',querySelectorAll:()=>[]};"
            f"require({json.dumps(str(JS))});const U=window.VZ_UWBPOS;console.log(JSON.stringify({expr}))")  # fmt: skip
    return json.loads(subprocess.run([node, "-e", code], capture_output=True, text=True, check=True).stdout)


def test_twr_single_sided_error_grows_with_reply_time_and_double_sided_cancels_it():
    out = _run("[[400e-6,900e-6],[4000e-6,200e-6],[400e-6,400e-6]].map(([a,b])=>U.twr({d:10,reply1:a,reply2:b,"
               "ppmTag:10,ppmAnchor:-5}))")  # fmt: skip
    r, long_reply, equal = out
    tof = 10 / C0
    assert abs(r["tof"] - tof) < 1e-18
    # single-sided: c·(e_tag·ToF + (e_tag − e_anchor)·T_reply1 / 2) = 0.9 m for 15 ppm and 400 µs
    assert abs(r["errSS"] - r["approxSS"]) < 1e-6 and abs(r["errSS"] - 0.9) < 1e-3
    # the reply-time part grows with the reply time: 15 ppm × (4000 − 400) µs / 2 more
    assert abs((long_reply["errSS"] - r["errSS"]) - 15e-6 * 3600e-6 / 2 * C0) < 1e-6
    # asymmetric double-sided: exactly ToF·(2·kA·kB / (kA + kB) − 1), whatever the reply times
    exact = tof * (2 * (1 + 10e-6) * (1 - 5e-6) / (2 + 5e-6) - 1) * C0
    for x in (r, long_reply, equal):
        assert abs(x["errDS"] - exact) < 1e-8 and abs(x["exactDS"] - exact) < 1e-12
    assert abs(r["errDS"]) < 1e-4  # 25 µm
    # the plain average only cancels with equal reply times
    assert abs(r["errAvg"] - r["approxAvg"]) < 1e-6 and abs(r["errAvg"]) > 0.5 and abs(equal["errAvg"]) < 1e-3
    assert _run("U.twrMessages(4)") == {"ss": 8, "ds": 12, "oneToMany": 6}


def test_tdoa_time_differences_hyperbolas_solver_and_spread():
    out = _run("(()=>{const A=[[2,2],[22,2],[22,12],[2,12]],p=[9,6],dd=U.rangeDiffs(p,A);"
               "const h=U.hyperbola(A[0],A[2],dd[1]);"
               "return {dd,dt:U.timeDiffs(p,A),sol:U.tdoaSolve(A,dd,[12,7]),"
               "hyp:h.map(q=>Math.hypot(q[0]-22,q[1]-12)-Math.hypot(q[0]-2,q[1]-2)),n:h.length,"
               "c1:U.tdoaCov(p,A,0.1),c2:U.tdoaCov(p,A,0.2),out:U.tdoaCov([23.5,13.5],A.slice(0,3),0.1),"
               "line:U.tdoaCov([12,2],[[2,2],[22,2],[32,2]],0.1)}})()")  # fmt: skip
    d = lambda a, b: math.dist(a, b)  # noqa: E731
    p, A = (9, 6), ((2, 2), (22, 2), (22, 12), (2, 12))
    want = [d(p, a) - d(p, A[0]) for a in A[1:]]
    assert all(abs(x - w) < 1e-12 for x, w in zip(out["dd"], want, strict=True))
    assert all(abs(t * C0 - w) < 1e-9 for t, w in zip(out["dt"], want, strict=True))
    assert abs(out["dt"][0] * 1e9 - want[0] / C0 * 1e9) < 1e-9  # range difference / c, in ns
    assert abs(out["sol"]["x"] - 9) < 1e-6 and abs(out["sol"]["y"] - 6) < 1e-6
    assert out["n"] > 50 and max(abs(x - want[1]) for x in out["hyp"]) < 1e-9  # every point on the hyperbola
    tr = lambda c: c[0][0] + c[1][1]  # noqa: E731
    assert abs(tr(out["c2"]) / tr(out["c1"]) - 4) < 1e-9  # spread scales with the sync error
    assert tr(out["out"]) > 4 * tr(out["c1"])  # outside the anchors the spread grows
    assert out["line"] is None  # tag in line with the anchors: no fix


def test_pdoa_angle_wavelength_and_ambiguity():
    out = _run("{l65:U.lambda(6.5e9),l8:U.lambda(8e9),c5:U.lambda(U.FC['5']),c9:U.lambda(U.FC['9']),"
               "half:U.pdoa(30,U.lambda(U.FC['9'])*500,U.FC['9'],10),"
               "amb:U.pdoa(40,U.lambda(U.FC['9'])*1000,U.FC['9']),"
               "side:U.pdoa(80,U.lambda(U.FC['9'])*500,U.FC['9'],10),"
               "sweep:[-89,-60,-30,0,30,60,89].map(a=>U.pdoa(a,18,U.FC['9']).ambiguous),"
               "wide:[-60,0,60].map(a=>U.pdoa(a,40,U.FC['9']).candidates.length),"
               "fix:U.polarFix(5,30,0.1,5)}")  # fmt: skip
    assert abs(out["l65"] * 1000 - 46.12) < 0.01 and abs(out["l8"] * 1000 - 37.47) < 0.01
    assert abs(out["c5"] * 1000 - 46.20) < 0.01 and abs(out["c9"] * 1000 - 37.53) < 0.01
    h = out["half"]  # d = λ/2, θ = 30°: Δφ = π·sin 30° = 90°
    assert abs(math.degrees(h["dphi"]) - 90) < 1e-9 and abs(h["est"] - 30) < 1e-9
    assert h["candidates"] == [pytest.approx(30)]
    assert abs(h["sigmaTheta"] - math.degrees(math.radians(10) / (math.pi * math.cos(math.radians(30))))) < 1e-9
    a = out["amb"]  # d = λ, θ = 40°: the phase wraps and two angles fit
    assert a["ambiguous"] and abs(a["meas"] - (2 * math.pi * math.sin(math.radians(40)) - 2 * math.pi)) < 1e-9
    other = math.degrees(math.asin(math.sin(math.radians(40)) - 1))  # the same wrapped phase, one turn less
    assert [round(x, 2) for x in a["candidates"]] == [round(other, 2), 40.0]
    assert out["side"]["sigmaTheta"] > 4 * h["sigmaTheta"]  # accuracy falls off towards ±90°
    assert not any(out["sweep"])  # 18 mm < λ/2 on channel 9: always unique
    assert all(n >= 2 for n in out["wide"])  # 40 mm > λ/2: ambiguous
    f = out["fix"]
    assert abs(f["x"] - 2.5) < 1e-9 and abs(f["y"] - 5 * math.cos(math.radians(30))) < 1e-9
    assert abs(f["across"] - 5 * math.radians(5)) < 1e-12


def test_lightweight_tag_model_and_random_access():
    out = _run("(()=>{const o={ch:'9',msg:150e-6,anchors:4,listen:1e-3};"
               "const f=Object.fromEntries(['twr','classic','light','dl'].map(k=>[k,U.tagFix(k,o)]));"
               "return {f,h:Object.fromEntries(Object.entries(f).map(([k,v])=>[k,U.batteryHours(v.charge,1)])),"
               "zero:U.tagFix('classic',{...o,listen:0}),a:U.aloha(500,1,150e-6),s:U.scheduledTags(1),R:U.RADIO}})()")
    f, h, R = out["f"], out["h"], out["R"]
    assert f["light"]["rx"] == 0 and f["light"]["tx"] == pytest.approx(150e-6)
    assert abs(f["light"]["charge"] - (R["wake"] * R["tWake"] + R["tx"] * 150e-6)) < 1e-15
    assert abs(f["classic"]["charge"] - f["light"]["charge"] - R["rx"]["9"] * 1e-3) < 1e-15
    assert out["zero"]["charge"] == pytest.approx(f["light"]["charge"])  # no listen window: the light tag
    assert h["light"] > 5 * max(h["twr"], h["classic"], h["dl"])  # listening is what empties the coin cell
    assert abs(h["light"] - 0.22 / (f["light"]["charge"] + R["sleep"])) < 1e-6
    a = out["a"]  # pure ALOHA: P = e^(−2G), G = 500 × 1 × 150 µs
    assert abs(a["G"] - 0.075) < 1e-12 and abs(a["success"] - math.exp(-0.15)) < 1e-12
    assert abs(a["tags90"] - math.log(1 / 0.9) / (2 * 150e-6)) < 1e-6 and out["s"] == pytest.approx(1000)
