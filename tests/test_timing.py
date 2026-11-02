"""Timing crosses (owner, 22 Oct 2026): Skyworks clocks, buffers and oscillators against TI, SiTime and Renesas, one
rules family (rules/timing.yaml) whose function_type keeps clock generators, jitter attenuators, buffers and
oscillators apart."""

import re

import pytest
from sqlalchemy import select

from app import yamlio
from app.matching.engine import pins_compatible, ranked
from app.matching.rules import get_rules, load_all_rules
from app.models import Part
from app.services import blocks, runs, text
from app.services.cross_notes import notes_for
from app.services.pipeline import fn_for_part
from app.services.queries import crosses_for
from tests.conftest import ROOT, ids

FILES = ("skyworks_timing", "ti_timing", "sitime_timing")
FUNCTIONS = {"clock_generator", "jitter_attenuator", "clock_buffer", "pcie_buffer", "crystal_oscillator"}


PRELOAD = {"timing": (FILES, False)}


@pytest.fixture
def timing(session):
    """The FILES (without unofficial values) in the test database; loaded through PRELOAD (tests/conftest.py)."""


def _get(session, mpn) -> Part:
    return session.scalars(select(Part).where(Part.mpn == mpn)).unique().one()


def _crosses(session, mpn) -> dict[str, object]:
    return {r.candidate.mpn: r for r in ranked(crosses_for(session, _get(session, mpn)))}


# ---------------------------------------------------------------- rules and data


def test_timing_rules_priorities():
    rules = get_rules("timing")
    assert "timing" in load_all_rules()
    p1 = {p.key for p in rules.by_priority(1)}
    # owner, 22 Oct 2026: function, jitter and outputs first; package never decides; supply is priority 2
    assert p1 == {"function_type", "outputs", "output_formats", "freq_range_mhz", "jitter_fs"}
    assert rules.functional_focus and rules.get("vdd_range_v").priority == 2
    assert rules.get("function_type").hard
    p2 = {p.key for p in rules.by_priority(2)}
    assert p2 == {"vdd_range_v", "core_rails", "qualification", "temp_range_c", "pcie_gen"}
    assert rules.get("qualification").must_meet and rules.get("jitter_fs").direction == "lower"


def test_every_timing_part_states_its_must_match_values_and_source():
    rules = get_rules("timing")
    p1 = [p.key for p in rules.by_priority(1)]
    for f in FILES:
        data = yamlio.load((ROOT / "data" / "real" / f"{f}.yaml").read_text())
        assert all(d["url"].startswith("https://") and len(d["sha256"]) == 64 for d in data["datasheets"])
        resolved = {}
        for raw in data["parts"]:
            spec = {**resolved.get(raw.get("like"), {}), **raw}
            spec["params"] = {**resolved.get(raw.get("like"), {}).get("params", {}), **raw.get("params", {})}
            resolved[spec["mpn"]] = spec
            assert spec["params"]["function_type"] in FUNCTIONS, spec["mpn"]
            missing = [k for k in p1 if spec["params"].get(k) in (None, [], "")]
            assert not missing, (spec["mpn"], missing)
            assert spec.get("datasheet_url"), spec["mpn"]


# ---------------------------------------------------------------- crosses


def test_pcie_buffer_crosses_both_ways(session, timing):
    to_ours = _crosses(session, "LMKDB1104")
    assert {"Si53204-A01", "Si53204-A02"} <= set(to_ours)
    r = to_ours["Si53204-A01"]
    assert r.category == "functional" and [d.key for d in r.deviations] == ["freq_range_mhz", "jitter_fs"]
    # not a drop-in: different package, pinout not read
    assert not r.fit.same_package and r.category != "fff"
    to_ti = _crosses(session, "Si53204-A01")
    assert set(to_ti) == {"LMKDB1102", "LMKDB1104", "LMKDB1108", "LMKDB1112", "LMKDB1120"}
    assert [d.key for d in to_ti["LMKDB1104"].deviations] == []  # supply is priority 2 now
    assert [d.key for d in to_ti["LMKDB1102"].deviations] == ["outputs"]  # 2 outputs for our 4


def test_twelve_output_pcie_buffers_and_the_20_output_gap(session, timing):
    # timing backlog, 2 Nov 2026: Si53212 (12 outputs) against TI's LMKDB1112 (12) and LMKDB1120 (20)
    ours = _get(session, "Si53212-A01").param_map()
    assert ours["outputs"] == 12 and ours["pcie_gen"] == "gen6" and ours["jitter_fs"] == 20
    assert _get(session, "Si53212-A01").package.code == "QFN-64 9x9 p0.5 EP"
    to_ti = _crosses(session, "Si53212-A01")
    assert [d.key for d in to_ti["LMKDB1112"].deviations] == [] and "LMKDB1104" in to_ti
    assert [d.key for d in to_ti["LMKDB1104"].deviations] == ["outputs"]
    assert _get(session, "LMKDB1112").param_map()["jitter_fs"] == 3.3  # its own jitter table (p28)
    # 2 Nov 2026: the PCIe Gen 7 SKY535x2 buffers (10 / 8 / 4 outputs) are candidates too
    assert {"Si53212-A01", "Si53212-A02", "SKY53512"} <= set(_crosses(session, "LMKDB1112"))
    to_20 = _crosses(session, "LMKDB1120")  # no Skyworks PCIe buffer has 20 outputs: any candidate falls short
    assert set(to_20) <= {"SKY53512", "SKY53582", "SKY53542"} and all("outputs" in [d.key for d in r.deviations] for r in to_20.values())
    assert _get(session, "LMKDB1102").param_map()["control"] == ["pin"]  # no SMBus


def test_grades_from_the_same_datasheets(session, timing):
    # timing backlog, 2 Nov 2026: grades B / D stop at 200 MHz (Si5332) or 350 MHz (Si534x); C / D are integer only
    def p(mpn):
        return _get(session, mpn).param_map()

    assert p("Si5332B-GM1")["freq_range_mhz"] == [5, 200] and p("Si5332C-GM3")["freq_range_mhz"] == [5, 333.33]
    assert p("Si5332D-AM2")["qualification"] == "automotive" and p("Si5332D-AM2")["freq_range_mhz"] == [5, 200]
    assert p("Si5332B-GM3")["outputs"] == 12 and _get(session, "Si5332C-AM3").package.code == "QFN-48 7x7 p0.5 EP"
    assert p("Si5341C")["freq_range_mhz"] == [0.0001, 1028] and p("Si5340D")["freq_range_mhz"] == [0.0001, 350]
    assert p("Si5340B")["outputs"] == 4 and p("Si5341D")["outputs"] == 10
    assert (p("Si5394")["outputs"], p("Si5392")["outputs"], p("Si5396")["outputs"]) == (4, 2, 4)
    assert p("Si5396")["freq_range_mhz"] == [0.0001, 720] and p("Si5394")["function_type"] == "jitter_attenuator"
    auto = _crosses(session, "Si5332D-AM2").values()
    assert all(r.candidate.param_map()["qualification"] == "automotive" for r in auto)


def test_function_type_keeps_kinds_apart(session, timing):
    # a jitter attenuator is never listed for a clock generator, a buffer never for an oscillator
    for mpn in ("Si5341A", "Si5345", "Si53204-A01", "Si545"):
        ref = _get(session, mpn)
        kind = ref.param_map()["function_type"]
        assert all(r.candidate.param_map()["function_type"] == kind for r in ranked(crosses_for(session, ref)))
    assert "LMK04832" in _crosses(session, "Si5345") and "LMK04832" not in _crosses(session, "Si5341A")
    assert "SiT95211" in _crosses(session, "Si5341A")


def test_automotive_reference_only_gets_automotive_candidates(session, timing):
    ours = _crosses(session, "Si5332A-AM1")
    assert all(r.candidate.param_map()["qualification"] == "automotive" for r in ours.values())
    to_ours = _crosses(session, "CDCE6214-Q1")
    assert to_ours and all(r.candidate.param_map()["qualification"] == "automotive" for r in to_ours.values())
    assert "Si5332A-GM1" not in to_ours


def test_jitter_and_pcie_are_priority_2_only(session, timing):
    r = _crosses(session, "5P49V6965")["Si5332A-GM1"]
    diffs = {d.key: d for d in r.diffs}
    assert diffs["jitter_fs"].status == "better" and diffs["pcie_gen"].status == "better"
    assert [d.key for d in r.deviations] == ["freq_range_mhz"]  # Si5332 starts at 5 MHz, VersaClock 6E at 1 kHz


def test_oscillator_pinout_matches_across_vendors(session, timing):
    assert pins_compatible("CLK+", "OUT+", "timing") and not pins_compatible("CLK+", "OUT-", "timing")
    r = _crosses(session, "SiT9365")["Si545"]
    assert r.fit.same_pinout and not r.fit.same_package  # centre pad on the SiTime part only
    assert r.category == "functional"


def test_cross_notes_cover_timing_pairs():
    assert notes_for("LMKDB1104", "Si53204-A01")[0]["verdict"] == "best"
    assert notes_for("CDCE6214-Q1", "Si5332A-AM1")
    assert notes_for("Si5332A-AM2", "LMK3H0102-Q1")[0]["verdict"] == "not_recommended"


# ---------------------------------------------------------------- functions, pages, walk-through


def test_function_from_the_part_and_block_candidates(session, timing):
    assert fn_for_part(_get(session, "Si53208-A01")) == "pcie_buffer"
    assert fn_for_part(_get(session, "LMK04832")) == "jitter_attenuator"
    blocks._CAND_CACHE.clear()
    pcie = {c["mpn"] for c in blocks._candidates(session, "pcie_buffer") if c.get("full")}
    assert "Si53204-A01" in pcie and "Si5345" not in pcie
    osc = {c["mpn"] for c in blocks._candidates(session, "crystal_oscillator") if c.get("full")}
    assert {"Si545", "Si549"} <= osc and "Si5332A-GM1" not in osc


def test_summary_names_the_function():
    s = text.short_description("timing", "TI REX 28-pin VQFN 4x4", "not_automotive",
                               params={"function_type": "pcie_buffer", "outputs": 4, "freq_range_mhz": [1, 400],
                                       "jitter_fs": 3})  # fmt: skip
    assert s.startswith("PCIe clock buffer · 4 outputs · 1–400 MHz · 3 fs")
    osc = text.short_description("timing", params={"function_type": "crystal_oscillator", "outputs": 1,
                                                   "freq_range_mhz": [0.2, 1500]})  # fmt: skip
    assert osc == "Crystal / oscillator · 200 kHz–1500 MHz"


def test_part_page_and_walk_through(client, session, timing):
    comp = ids(client, "LMKDB1104")
    page = client.get(f"/parts/{comp}").text
    assert "SKY53542" in page and "PCIe clock buffer" in page  # 4 outputs, PCIe Gen 7 like LMKDB1104
    assert "Function" in page and "Output formats" in page
    walk = client.get(f"/parts/{comp}/walk").text
    assert 'id="step-2"' in walk and "PCIe clock buffer" in walk
    assert "is not mapped to a block-diagram function" not in walk
    ours = client.get(f"/parts/{ids(client, 'Si5345')}").text
    assert "LMK04832" in ours and "8A34001" in ours


def test_timing_backlog_and_daily_run():
    backlog = (ROOT / "docs" / "timing_backlog.md").read_text()
    assert re.search(r"^- \[ \]", backlog, flags=re.M) and re.search(r"^- \[x\]", backlog, flags=re.M)
    daily = (ROOT / "docs" / "daily_update.md").read_text()
    assert "Timing crosses: the next 2–3 datasheets from `docs/timing_backlog.md`" in daily
    job = next(j for j in runs.jobs() if j["name"] == "Timing crosses")
    assert job["frequency"] == "daily" and job["tonight"] == 6
    steps = [j["tonight"] for j in runs.tonight()]
    assert steps == list(range(1, len(steps) + 1))


def test_schedule_page_counts_timing_datasheets(client, session):
    q = runs.queue(session)
    assert q["timing_left"] > 0 and q["timing_done"] > 0
    assert f"<b>{q['timing_left']}</b> timing datasheets left" in client.get("/manage/schedule").text


def test_pcie_gen7_parts_only_where_the_datasheet_states_it(session, timing):
    """Owner, 2 Nov 2026 ("Yes to all"): our PCIe Gen 7 parts from their datasheets; older parts keep their stated gen."""
    p = lambda m: _get(session, m).param_map()  # noqa: E731
    assert p("SKY62101")["pcie_gen"] == "gen7" and p("SKY62101")["function_type"] == "clock_generator"
    for m, n in (("SKY53582", 8), ("SKY53512", 10), ("SKY53542", 4)):
        assert p(m)["pcie_gen"] == "gen7" and p(m)["outputs"] == n and p(m)["function_type"] == "pcie_buffer"
    assert (p("Si5332A-GM1")["pcie_gen"], p("Si53204-A01")["pcie_gen"]) == ("gen6", "gen6")
