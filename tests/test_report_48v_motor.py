"""Owner, 27 and 28 Oct 2026: "48V Motor Control Applications in Cars. Actuators transitioning from 12V to 48V, Motor
Control SoCs", "Non safety critical actuator replacement using Qorvo Intelligent motor control" and "ACT72350
Automotive Block Diagram applications". A preliminary report in the standard layout, linked to the motor Part knowledge
page and the PAC5527 review; three library diagrams with the ACT72350 in its block, listed under "Used in"; the
automotive grade of the PAC / ACT parts stated honestly."""

import html
import urllib.parse

from app.services import autograde, blocks, digest, site_guard
from app.services import how_it_works as hw
from app.services import reports as rp

SLUG = "auto-48v-motor-control"
DIAGRAMS = (
    "Automotive 48 V coolant pump, oil pump and cooling fan drive",
    "Automotive 48 V HVAC blower and electric A/C compressor drive",
    "Automotive seat adjustment and comfort actuators",
)


def test_entry_is_a_complete_automotive_report_linked_to_part_knowledge():
    r = rp.report(SLUG)
    assert r and r["kind"] == "report" and r["app_type"] == "Automotive" and r["status"] == "draft"
    assert rp.story_problems(r) == [] and rp.has_background(SLUG) and r["answer"]["conf"] in rp.CONFIDENCE
    assert [x["age"] for x in rp.learn(r)] == list(rp.LEARN_AGES) and r["learn_links"]
    assert digest.words(r["gist"]) <= digest.MAX_WORDS and 2 <= len(r["abstract"]) <= 3
    hrefs = {s["href"] for s in r["see_also"] if isinstance(s, dict)}
    assert {"/reviews/how/motor", "/reviews/qorvo-pac5527-motor-driver"} <= hrefs
    assert rp.reports()[0]["date"] >= r["date"]  # newest first; at the top of reports.yaml


def test_page_follows_the_owners_order_and_shows_see_also_links(client):
    page = html.unescape(client.get(f"/business/reports/{SLUG}").text)
    assert 'class="rpt"' in page and "Bottom line" in page
    assert 'See also: <a href="/reviews/how/motor">' in page and 'href="/reviews/qorvo-pac5527-motor-driver"' in page
    order = ["1. Adjacent products and technologies", "What moves to 48 V", "What 48 V motor control needs",
             "Depth check", "2. The owner's angle", "3. Gaps and new technology", "4. Where else",
             "5. Market trend and who is doing it", "Risks"]  # fmt: skip
    assert [page.index(h) for h in order] == sorted(page.index(h) for h in order)
    for t in ("Cybertruck", "PAC5532AQX", "ACT72350", "PAC5527", "TLE9140EQW", "DRV8363-Q1", "L9908", "AMT49100",
              "GD3000", "E523.52", "MLX81350", "Si86xx", "Si88xx", "seat adjustment", "AEC-Q100", "ISO 26262",
              "nothing that fits", "Not enough data", "est"):  # fmt: skip
        assert t in page, t
    bg = html.unescape(client.get(f"/business/reports/{SLUG}/background").text)
    assert "Requests made for this report" in bg and "sprabq7a.pdf" in bg and "seat-adjustment application note" in bg


def test_no_site_names_no_qorvo_com_and_honest_grades():
    item = digest.by_key()[f"background:{SLUG}"]
    assert not item["auto"]
    for name in (f"{SLUG}.html", f"{SLUG}.background.html"):
        text = (rp.BODIES / name).read_text()
        assert not site_guard.hits(text), name
        assert "qorvo.com/" not in text  # never a qorvo.com source link
    for mpn in ("ACT72350", "PAC5532AQX", "PAC5527QM", "PAC5527AQM"):
        assert not autograde.is_aec(mpn), mpn  # grade not stated: the report must not call them automotive
    for mpn in ("ACT4751MQI101",):
        assert autograde.is_aec(mpn)


def test_act72350_diagrams_exist_link_and_are_listed_under_used_in(client):
    names = {t["name"]: t for t in blocks.templates()}
    body = (rp.BODIES / f"{SLUG}.html").read_text()
    for start in DIAGRAMS:
        name = next(n for n in names if n.startswith(start))
        t = names[name]
        labels = " ".join(b["label"] for g in t["groups"] for b in g["blocks"] if isinstance(b, dict))
        assert "ACT72350" in labels and "grade not stated" in " ".join(g["label"] for g in t["groups"]), name
        assert urllib.parse.quote(name) in body, name  # the report links each diagram by name
        assert client.get("/blocks/new", params={"diagram": name}).status_code == 200
    motor = next(g for g in hw.groups() if g["id"] == "motor")
    rows = hw.used_in(motor)  # same order as the data entries
    for start in DIAGRAMS:
        i = next(i for i, u in enumerate(motor["used_in"]) if (u.get("app") or "").startswith(start))
        assert rows[i]["href"].startswith("/business/applications/"), rows[i]
    assert any(u["href"] == f"/business/reports/{SLUG}" for u in rows)
    page = client.get("/reviews/how/motor").text
    assert "Automotive seat adjustment and comfort actuators" in html.unescape(page)
