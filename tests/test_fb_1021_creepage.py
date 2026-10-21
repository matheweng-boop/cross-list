"""Owner feedback 21 Oct ("especially pollution degrees and requirements"): the ISO7821DWW report answers its creepage
question, the creepage specification guide carries the pollution-degree / material-group explanation and the IEC 60664-1
table, the systems library states the 800 V requirement, and TI's public ISO7821 list prices are stored."""

import html
import re
from pathlib import Path

from app.config import PROJECT_ROOT
from app.services import library
from app.services import price_model as pm
from app.services import reports as rp

# basic insulation, material group I (mm): working voltage -> (PD1, PD2, PD3)
TABLE = {400: (1.0, 2.0, 5.0), 500: (1.3, 2.5, 6.3), 630: (1.8, 3.2, 8.0), 800: (2.4, 4.0, 10), 1000: (3.2, 5.0, 12.5)}


def _num(x: float) -> str:
    return f"{x:g}" if x >= 10 else f"{x:.1f}"


def test_creepage_guide_explains_pollution_degree_material_group_and_the_table(client):
    page = html.unescape(client.get("/engineering/creepage_mm").text)
    for term in ("PD1", "PD2", "PD3", "PD4", "CTI", "IIIa", "IIIb", "Reinforced = 2 × basic", "IEC 60747-17",
                 "ISO 6469-3", "IEC 61800-5-1", "IEC 62109-1", "SLUP419", "MINMAX"):  # fmt: skip
        assert term in page, term
    assert "Not modelled" not in page
    for v, (pd1, pd2, pd3) in TABLE.items():
        row = re.search(rf"<tr><td>{v}</td>(.*?)</tr>", page)
        assert row, v
        cells = re.findall(r"<td>([^<]*)</td>", row.group(1))
        assert cells[0] == _num(pd1) and cells[1] == _num(pd2) and cells[4] == _num(pd3), (v, cells)


def test_iso7821dww_report_answers_the_creepage_question(client):
    r = rp.report("iso7821dww-isolation")
    page = html.unescape(client.get("/business/reports/iso7821dww-isolation").text)
    heads = [page.index(h) for h in ("1. Adjacent products and technologies", "2. Where else we see opportunities",
                                     "3. Market trend", "4. Creepage, pollution degree and what 800 V systems need",
                                     "Open questions", "Sources")]  # fmt: skip
    assert heads == sorted(heads)
    assert "8.0 mm at 800 V and 10 mm at 1000 V" in page and "$2.60" in page and "$2.64" in page
    assert "not verified here" not in page and "No new web research" not in page
    opq = page[page.index("Open questions") : page.index("Sources", page.index("Open questions"))]
    assert "What creepage and working voltage do 800 V OEMs require" not in opq
    assert "pollution degree" in r["summary"] and "10 mm at 1000 V" in r["summary"]
    assert "not verified here" not in " ".join(x["text"] for x in rp.learn(r))


def test_library_topic_states_the_800v_requirement():
    t = library.topic("traction_asil_d")
    d11 = next(x for x in t["design_rules"] if x["id"] == "d11")
    assert "8.0 mm at 800 V" in d11["rule"] and "pollution degree 3" in d11["rule"]
    assert not any("not verified here" in q for q in t["open_questions"])
    assert "/engineering/creepage_mm" in {k["href"] for k in library.related_to(d11["rule"])["knowledge"]}
    ids = {s["id"] for s in library.sources()}
    assert {"creepageGuides", "creepageBlocked"} <= ids


def test_ti_iso7821_list_prices():
    lp = pm.list_prices()
    for mpn in ("ISO7821DW", "ISO7821DWR", "ISO7821DWW", "ISO7821DWWR"):
        p = lp[mpn]
        assert p["maker"] == "TI" and p["source"] == "TI store" and str(p["retrieved"]) == "2026-10-21", mpn
        qs = [q for q, _ in p["breaks"]]
        assert qs == [1, 100, 250, 1000] and all(b[1] > 0 for b in p["breaks"]), mpn
    assert lp["ISO7821DWWR"]["breaks"][-1][1] <= lp["ISO7821DWR"]["breaks"][-1][1]  # no premium on reels
    assert lp["ISO7821DWW"]["breaks"][-1][1] > lp["ISO7821DW"]["breaks"][-1][1]  # tubes: extra-wide costs more


def test_creepage_visual_has_pollution_degree():
    js = Path(PROJECT_ROOT / "app/web/static/visuals.js").read_text()
    block = js[js.index("const CREEP =") : js.index('id: "creep"')]
    assert "CREEP3" in block and "[800, 10, 11, 12.5]" in block and "[1000, 3.2]" in block
    assert 'k: "pd"' in js
