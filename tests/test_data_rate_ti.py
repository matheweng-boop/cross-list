"""TI digital isolators: every data rate read from the part's own datasheet (2 Nov 2026).

Owner, 26 Oct 2026: a data rate decides a cross only when it comes from the datasheet pages. The 219 TI isolators
that still took data_rate_mbps from TI's product table, and the four ISO6441 with a page-less "corrected" note, were
re-read from their datasheets: recommended operating conditions, switching characteristics (ISO7421A-Q1) or the device
comparison table (ISO721-Q1, ISO722-Q1), per speed grade where the family has grades (ISO72x / ISO72xM, ISO722x
A/B/C/M, ISO723x and ISO724x C/M, ISO76x1 C/M). Only ISO6163 differed from the product table: 50 Mbps on its
high-speed channels (the table said 25; its control channels are 4 Mbps).
"""

from functools import cache
from pathlib import Path

import pytest
import yaml

from app.matching.engine import cross, from_datasheet, is_estimate_source
from app.matching.rules import get_rules
from app.services.seed import load_file

DATA = Path(__file__).resolve().parents[1] / "data" / "real"

# Datasheets whose data rate stays off a datasheet page, with the reason; every other TI isolator cites a page.
_CONTRADICTS = "contradicts itself: p.7 table DR max 50 Mbps; its note, p.1 and the device table 100 Mbps (26 Oct)"
EXCEPTIONS = {"iso7740.pdf": _CONTRADICTS, "iso7741.pdf": _CONTRADICTS, "iso7742.pdf": _CONTRADICTS}


@cache
def parts() -> dict[str, dict]:
    data = yaml.safe_load((DATA / "ti_digital_isolators.yaml").read_text())["parts"]
    return {p["mpn"]: p for p in data if p["family"] == "digital_isolator"}


def rate(mpn: str) -> tuple[float, str]:
    p = parts()[mpn]
    return p["params"].get("data_rate_mbps"), (p.get("param_sources") or {}).get("data_rate_mbps")


def test_no_ti_isolator_data_rate_from_the_product_table():
    assert len(parts()) > 300
    for mpn in parts():
        value, src = rate(mpn)
        assert value and src and "product table" not in src.lower(), (mpn, src)


def test_every_ti_isolator_data_rate_cites_a_page_of_its_own_datasheet():
    for mpn, p in parts().items():
        _, src = rate(mpn)
        if p["datasheet"] in EXCEPTIONS:
            assert is_estimate_source(src) and not from_datasheet(src), (mpn, src)
        else:
            assert from_datasheet(src) and src.startswith(f"{p['datasheet']} p."), (mpn, src)


def test_every_exception_is_still_open():
    """An exception whose parts now cite a page is removed from the list."""
    assert {p["datasheet"] for m, p in parts().items() if not from_datasheet(rate(m)[1])} == set(EXCEPTIONS)


@pytest.mark.parametrize(
    "mpn, value, page",
    [
        ("ISO6163DWR", 50.0, "iso6163.pdf p.5"),  # the product table said 25; control channels C and D: 4 Mbps
        ("ISO6041LDWR", 200.0, "iso6041.pdf p.7"),
        ("ISO6441FDWR", 150.0, "iso6441.pdf p.7"),  # was "datasheet: up to 150 Mbps; corrected" (no page)
        ("ISO6421DRQ1", 150.0, "iso6421-q1.pdf p.6"),
        ("ISO6520DR", 50.0, "iso6520.pdf p.5"),
        ("ISO7041DBQ", 4.0, "iso7041.pdf p.7"),
        ("ISO7140CCDBQ", 50.0, "iso7140cc.pdf p.5"),  # 40 Mbps below 4.5 V
        ("ISO721QDRQ1", 100.0, "iso721-q1.pdf p.2"),  # device comparison table
        ("ISO721DR", 100.0, "iso721.pdf p.5"),
        ("ISO722MDR", 150.0, "iso722m.pdf p.5"),
        ("ISO7220ADR", 1.0, "iso7220a.pdf p.5"),  # 1000 kbps
        ("ISO7221BDR", 5.0, "iso7221b.pdf p.5"),
        ("ISO7220CDR", 25.0, "iso7220c.pdf p.5"),
        ("ISO7221MDR", 150.0, "iso7221m.pdf p.5"),
        ("ISO7221AQDRQ1", 1.0, "iso7221a-q1.pdf p.4"),
        ("ISO7221CQDRQ1", 25.0, "iso7221c-q1.pdf p.4"),
        ("ISO7231CDWR", 25.0, "iso7231c.pdf p.5"),
        ("ISO7231MDWR", 150.0, "iso7231m.pdf p.5"),
        ("ISO7240CFDWR", 25.0, "iso7240cf.pdf p.5"),
        ("ISO7242MDWR", 150.0, "iso7242m.pdf p.5"),
        ("ISO7342FCDW", 25.0, "iso7342fc.pdf p.7"),
        ("ISO7421D", 1.0, "iso7421.pdf p.7"),
        ("ISO7421ED", 50.0, "iso7421e.pdf p.5"),
        ("ISO7421AQDRQ1", 50.0, "iso7421a-q1.pdf p.3"),  # switching characteristics
        ("ISO7520CDW", 1.0, "iso7520c.pdf p.5"),
        ("ISO7631FMDW", 150.0, "iso7631fm.pdf p.5"),  # M grade; 100 Mbps below 3 V
        ("ISO7641FCDW", 25.0, "iso7641fc.pdf p.5"),  # C grade
        ("ISO7841DW", 100.0, "iso7841.pdf p.3"),
        ("ISOS141FDBQSEP", 100.0, "isos141-sep.pdf p.5"),
        ("ISOW6442DWERQ1", 150.0, "isow6442-q1.pdf p.6"),  # 100 Mbps at VDDL 2.5 V
        ("ISOW7841FAQDWEQ1", 100.0, "isow7841a-q1.pdf p.5"),
        ("ISOW7821DWE", 100.0, "isow7821.pdf p.6"),  # was the p.1 feature line
    ],
)
def test_ti_data_rate_from_its_datasheet(mpn, value, page):
    got, src = rate(mpn)
    assert got == value and src.startswith(page + " ("), (mpn, got, src)


def test_speed_grades_keep_their_own_rate():
    """A grade letter in the part number picks its row of the datasheet table, never the family's top rate."""
    by_grade = {"ISO7220ADR": 1.0, "ISO7220BDR": 5.0, "ISO7220CDR": 25.0, "ISO7220MDR": 150.0, "ISO7230CDWR": 25.0,
                "ISO7231MDWR": 150.0, "ISO7241CDWR": 25.0, "ISO7241MDWR": 150.0, "ISO7631FCDW": 25.0,
                "ISO7631FMDW": 150.0}  # fmt: skip
    assert {m: rate(m)[0] for m in by_grade} == by_grade


@pytest.fixture
def loaded(session):
    for f in ("ti_digital_isolators", "skyworks_si86"):
        load_file(session, DATA / f"{f}.yaml")
    session.commit()
    return session


def test_ti_data_rate_now_decides_the_cross(loaded, part):
    """ISO7221MDR (150 Mbps, iso7221m.pdf p.5) against a 1 Mbps Si86xx code: a deviation, no longer only "check
    datasheet"."""
    r = cross(part("ISO7221MDR"), part("SI8621AB-IS"), get_rules("digital_isolator"))
    d = next(d for d in r.diffs if d.key == "data_rate_mbps")
    assert d.status == "worse" and not d.unverified and d in r.deviations
