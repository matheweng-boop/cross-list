"""Case "isolated current sensing for EV charging", In depth part (owner's comment "Look more into it", 27 Oct 2026;
added 2 Nov 2026): where isolated current sensing sits, shunt versus Hall and other magnetic sensors, the requirements,
our Si89xx parts from data/real, competitors and the sockets, shown after section 1 on the case page."""

import html

from app import yamlio
from app.config import PROJECT_ROOT
from app.services import prelim, quality, site_guard

SLUG = "iso-current-sense-charging"
TITLES = ("Where isolated current sensing sits", "Shunt with an isolated amplifier or modulator, Hall",
          "What it must meet, and where we stand", "Our parts: the Si89xx family", "Competitors (public sources)",
          "Market and sockets")  # fmt: skip


def _parts(name: str) -> list[dict]:
    return yamlio.load((PROJECT_ROOT / "data" / "real" / name).read_text())["parts"]


def test_depth_tables_are_complete_and_public_safe():
    d = prelim.raw(SLUG)["depth"]
    assert [t["id"] for t in d["tables"]] == ["where", "how", "needs", "ours", "rivals", "market"]
    for t in d["tables"]:
        assert t["rows"] and all(len(r) == len(t["columns"]) for r in t["rows"]), t["id"]
    where = {r[0].split(" (")[0] for r in d["tables"][0]["rows"]}
    assert {"On-board charger", "HV-to-LV DC-DC", "DC fast charger", "AC wallbox", "Battery"} <= where
    text = " ".join(str(c) for t in d["tables"] for r in t["rows"] for c in r)
    for t in ("Hall", "TMR", "fluxgate", "CMTI", "Offset drift", "Gain drift", "AEC-Q100", "Reinforced", "ADuM3195",
              "BQ79631-Q1", "TMCS1123", "Infineon", "est"):  # fmt: skip
        assert t in text, t
    assert not site_guard.hits(text + " " + d["intro"] + " " + " ".join(d["points"]))
    assert 10 < len(d["thread"]) < 200


def test_our_part_counts_match_the_parts_data():
    """The depth tables quote our and TI's OPN counts and CMTI from data/real; keep them in step."""
    sky = _parts("skyworks_isolated_amplifiers.yaml")
    auto = [p for p in sky if p["params"].get("qualification") == "automotive"]
    assert (len(sky), len(auto)) == (60, 30)
    assert {p["params"]["cmti_kv_us"] for p in sky} == {50.0}
    ti = _parts("ti_isolated_amplifiers.yaml")
    ti_auto = [p for p in ti if p["params"].get("qualification") == "automotive"]
    d = prelim.raw(SLUG)["depth"]
    ours = next(t for t in d["tables"] if t["id"] == "ours")
    assert f"{len(sky)} Si89xx OPNs" in ours["note"] and f"{len(auto)} of them AEC-Q100" in ours["note"]
    rivals = next(t for t in d["tables"] if t["id"] == "rivals")
    assert f"{len(ti)} OPNs in our data, {len(ti_auto)} automotive" in rivals["rows"][0][1]
    assert any(p["params"].get("cmti_kv_us") == 150.0 for p in ti_auto)


def test_case_page_shows_in_depth_after_section_one(client):
    page = html.unescape(client.get(f"/business/reports/{SLUG}").text)
    start = page.index('id="in-depth"')
    assert page.index("1. Position against the competition") < start < page.index("2. The market today")
    end = page.index("</section>", start)
    sec = page[start:end]
    assert [sec.index(t) for t in TITLES] == sorted(sec.index(t) for t in TITLES)
    assert 'data-label="How it is done"' in sec and "For the decision:" in sec and "Next step" in sec
    assert "150 kV/µs" in page and "BQ79631-Q1" in page  # also in the position items
    other = client.get("/business/reports/radio-tuner-next").text
    assert 'id="in-depth"' not in other  # only cases with a depth block
    bg = html.unescape(client.get(f"/business/reports/{SLUG}/background").text)
    assert "6. In depth (2 Nov 2026)" in bg and "www.infineon.com/products/sensor/current-sensors" in bg


def test_comment_is_recorded_as_checked():
    chk = quality.checked()[("digest", f"case:{SLUG}")]
    assert chk["comment_at"] == "2026-10-27 09:14" and "In depth" in chk["note"]
