"""Data rate read from each part's own datasheet (owner, 26 Oct 2026: "The 10Mbps spec is often times wrong, and
stated differently in the datasheet - so it should at least be better researched from the datasheet").

- Every Skyworks isolator's data rate comes from its datasheet, with the page and how it is stated.
- The web product table was wrong for the Si86xx 1 Mbps codes (150) and the Si86S60x (3.4); Novosense's table for
  the NSI8266 (150, datasheet 30) and the NSI823x/824x 2.0 and -DSWVR codes (150, datasheet 100).
- AW's reading holds: the Si86S F/H codes (36 ns deglitch) are 10 Mbps max, the B/E codes 150 Mbps.
- A data rate decides the cross only when both values come from a datasheet page; a product-table or estimated value
  is shown amber with "check datasheet" and only breaks ties (rules/digital_isolator.yaml, datasheet_only).
"""

from functools import cache
from pathlib import Path

import pytest
import yaml

from app.matching.engine import cross, from_datasheet
from app.matching.rules import get_rules
from app.services import crosslist as cl
from app.services.seed import load_file

DATA = Path(__file__).resolve().parents[1] / "data" / "real"


@cache
def rates(name: str) -> dict:
    """mpn -> (data rate, source) of one data file."""
    parts = yaml.safe_load((DATA / f"{name}.yaml").read_text())["parts"]
    return {p["mpn"]: (p["params"].get("data_rate_mbps"), (p.get("param_sources") or {}).get("data_rate_mbps"))
            for p in parts if "data_rate_mbps" in (p.get("params") or {})}  # fmt: skip


# ---------------------------------------------------------------- the stored values


def test_every_skyworks_isolator_data_rate_has_a_datasheet_page():
    for name in ("skyworks_si86", "skyworks_isolators_more"):
        for mpn, (_, src) in rates(name).items():
            assert from_datasheet(src), (mpn, src)


@pytest.mark.parametrize(
    "mpn, rate, page",
    [
        ("SI86S620HE-AS4", 10.0, "si86s61x_2x_Ox-datasheet.pdf p.9"),  # 36 ns deglitch: AW's reading holds
        ("SI86S620FC-AS", 10.0, "si86s61x_2x_Ox-datasheet.pdf p.9"),
        ("SI86S620EE-AS4", 150.0, "si86s61x_2x_Ox-datasheet.pdf p.9"),
        ("SI86S640FC-AS1", 10.0, "si86s6xx-datasheet.pdf p.22"),
        ("SI86SL40BC-AS1", 150.0, "si86s6xx-datasheet.pdf p.22"),
        ("SI8620BC-AS", 150.0, "si861x-2x-datasheet.pdf p.12"),
        ("SI8641BD-IS", 150.0, "si864x-datasheet.pdf p.14"),
        ("SI8610AB-AS", 1.0, "si86xx-1Mbps-datasheet.pdf p.13"),  # the product table said 150
        ("SI8641AB-IS", 1.0, "si86xx-1Mbps-datasheet.pdf p.13"),
        ("SI86S600AC-AS", 1.7, "si86s60x-datasheet.pdf p.14"),  # I2C: 1.7 MHz; the product table said 3.4
        ("SI8600AB-AS", 1.7, "si860x.pdf p.15"),
        ("SI86P341EC-IS", 150.0, "Si86Px-datasheet.pdf p.22"),
    ],
)
def test_skyworks_data_rate_from_its_datasheet(mpn, rate, page):
    value, src = rates("skyworks_si86")[mpn]
    assert value == rate and src.startswith(page), (mpn, value, src)


def test_deglitch_note_says_how_the_datasheet_states_it():
    _, src = rates("skyworks_si86")["SI86S620HE-AS4"]
    assert "max 10 Mbps" in src and "36 ns deglitch" in src and "min pulse width 100 ns" in src


def test_si84_one_mbps_grade_cites_its_own_table():
    more = rates("skyworks_isolators_more")
    assert more["SI8410AB-IS"] == (1.0, "Si8410.pdf p.6") and more["SI8410BB-IS"] == (150.0, "Si8410.pdf p.7")
    assert more["SI8620EB-IS"][1].startswith("si861x-2x-datasheet.pdf p.12")


@pytest.mark.parametrize(
    "mpn, rate, page",
    [
        ("NSI8240S0-Q1SSR", 150.0, "NSI824x-Q1_Datasheet_Rev1.4_EN.pdf p.8"),
        ("NSI8266W0-DSWR", 30.0, "NSI8266x0_Datasheet_1.3_EN.pdf p.4"),  # the product table said 150
        ("NSI8240W0-DSWR", 100.0, "NSI824x_Datasheet_2.0_EN.pdf p.11"),  # the product table said 150
        ("NSI8230W0-DSWR", 100.0, "NSI823x_Datasheet_2.0_EN.pdf p.9"),
        ("NSI8220W0-DSWVR", 100.0, "NSI822x_Datasheet_2.0_EN.pdf p.12"),  # the -DSWVR row: 100 Mbps
        ("NSI8220N0-DSPR", 150.0, "NSI822x_Datasheet_2.0_EN.pdf p.12"),
    ],
)
def test_novosense_data_rate_from_its_datasheet(mpn, rate, page):
    value, src = rates("novosense_digital_isolators")[mpn]
    assert value == rate and src.startswith(page), (mpn, value, src)


def test_novosense_without_a_readable_datasheet_stays_unverified():
    value, src = rates("novosense_digital_isolators")["NSI8320N0-Q1SPR"]  # served encrypted: product table only
    assert value == 150.0 and not from_datasheet(src)


def test_chipanalog_ca_is3720hg_q1_from_its_datasheet():
    value, src = rates("chipanalog_isolation")["CA-IS3720HG-Q1"]
    assert value == 150.0 and src.startswith("CAIS372xQ1datasheetVersion1.05.pdf p.6") and "p.14" in src


def test_ti_iso77xx_and_iso67xx_from_the_datasheet():
    ti = rates("ti_digital_isolators")
    assert ti["ISO7761QDWRQ1"][0] == 100.0 and ti["ISO7761QDWRQ1"][1].startswith("iso7761-q1.pdf p.7")
    assert ti["ISO7741QDWRQ1"][1].startswith("iso7741-q1.pdf p.6")
    assert ti["ISO6721BDR"][0] == 50.0 and ti["ISO6721BDR"][1].startswith("iso6721.pdf p.6")


def test_ti_iso774x_contradiction_is_marked_est():
    """iso7741.pdf p.7: DR max 50 Mbps in the table, 100 Mbps in its own note and on p.1: not guessed."""
    value, src = rates("ti_digital_isolators")["ISO7741DWR"]
    assert value == 100.0 and src.startswith("est:") and "50 Mbps" in src and not from_datasheet(src)


# ---------------------------------------------------------------- the cross


def test_from_datasheet_needs_a_page_and_no_estimate():
    assert from_datasheet("si86s6xx-datasheet.pdf p.22 (max 150 Mbps)")
    assert not from_datasheet("TI product table")
    assert not from_datasheet("Novosense product table")
    assert not from_datasheet("est: iso7741.pdf p.7 contradicts itself")


@pytest.fixture
def loaded(session):
    for f in ("ti_digital_isolators", "skyworks_si86", "novosense_digital_isolators", "chipanalog_isolation"):
        load_file(session, DATA / f"{f}.yaml")
    session.commit()
    return session


def _row(session, mpn):
    entries, _ = cl.parse(mpn)
    return cl.cross_list(session, entries)[0]


def test_unverified_data_rate_is_never_a_deviation(loaded, part):
    rules = get_rules("digital_isolator")
    r = cross(part("NSI8320N0-Q1SPR"), part("SI86S620FC-AS"), rules)  # 150 (product table) vs 10 (datasheet)
    d = next(d for d in r.diffs if d.key == "data_rate_mbps")
    assert d.status == "worse" and d.unverified and d.score == 0
    assert d not in r.deviations and r.unverified_worse == 1
    assert any("check datasheet" in g for g in cl.data_gaps(r))
    verified = cross(part("CA-IS3720HG-Q1"), part("SI86S620HE-AS4"), rules)  # both from datasheet pages
    assert "data_rate_mbps" in [d.key for d in verified.deviations]


def test_unverified_data_rate_only_breaks_ties(loaded):
    """NSI8320N0-Q1SPR: its 150 Mbps is from the product table; the 10 Mbps deglitch code does not win on CMTI."""
    r = _row(loaded, "NSI8320N0-Q1SPR")
    assert r.functional.result.candidate.mpn == "SI86S620BC-AS"
    assert r.light == "amber" and "Data rate not from their datasheet: check datasheet" in r.functional.comment


def test_flagged_crosses_after_the_datasheet_pass(loaded):
    ca = _row(loaded, "CA-IS3720HG-Q1").functional.result
    assert ca.candidate.mpn == "SI86S620EE-AS4"  # the B/E code (150 Mbps), not the F/H deglitch code
    nsi = _row(loaded, "NSI8240S0-Q1SSR").functional.result
    assert nsi.candidate.param_map()["data_rate_mbps"] >= 150
    iso7741 = _row(loaded, "ISO7741DW")  # their 100 Mbps is "est": amber with check datasheet
    assert iso7741.light == "amber" and "Data rate estimated (theirs): check datasheet" in iso7741.drop_in.comment
    iso7761 = _row(loaded, "ISO7761QDWRQ1")  # both values from datasheet pages
    assert iso7761.light == "green" and iso7761.drop_in.result.candidate.mpn == "SI86S661EE-AS2"
