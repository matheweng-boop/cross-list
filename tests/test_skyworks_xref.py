"""Skyworks' public cross reference against our engine (owner, 10 Nov 2026; docs/cross_reference_check_2026-11-10.md):
the official table and its check mark behind our part, and the data fixes the comparison found."""

import re
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from app.models import Part
from app.services import crosslist as cl
from app.services import skyworks_xref as sx
from app.services.seed import load_file
from app.sources.novosense import by_part_number

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "real"


@pytest.fixture
def load(session):
    def go(*files):
        for f in files:
            load_file(session, DATA / f"{f}.yaml")
        session.commit()
        return lambda mpn: session.scalars(select(Part).where(Part.mpn == mpn)).unique().one()

    return go


def _shown(session, get, their: str) -> tuple[list[str], str | None]:
    ref = get(their)
    crosses = cl.Crosser(session).crosses(ref)
    c1, c2 = cl.columns(ref, crosses)
    alt = cl.other_family([c1, c2], cl._pool(ref, crosses))
    shown = [r.candidate.mpn for r in (c1, c2, alt[1] if alt else None) if r is not None]
    return shown, (c1.candidate.mpn if c1 else None)


# ---------------------------------------------------------------- the official table


def test_table_has_source_licence_and_rows():
    text = sx.FILE.read_text()
    assert "https://www.skyworksinc.com/cross-reference" in text and "facts used with a link" in text
    data = yaml.safe_load(text)
    assert data["read"] and len(data["rows"]) > 300
    assert {"maker", "part", "ours", "match", "note"} <= set(data["rows"][0])
    keys = [(r["maker"], r["part"].upper(), r["ours"].upper(), r["match"]) for r in data["rows"]]
    assert len(keys) == len(set(keys))  # de-duplicated
    assert not re.search(r"qorvo\.com", text, re.I)


def test_mark_exact_base_number_q1_device_and_reel():
    m = sx.mark("ISO7741DWR", "SI86S641EE-IS2")
    assert m["match"] == "Drop-In Replacement" and m["url"].endswith("PartNumber=ISO7741DWR")
    assert sx.mark("ISO7741DWR", "SI8641ET-IS") is None  # not in their list for this part
    assert sx.mark("ISO7720DWR", "SI8620ED-IS")["part"] == "ISO7720"  # base number, no package
    assert sx.mark("ISO7730QDWRQ1", "SI86S630EE-AS2")["part"] == "ISO7730-Q1"  # TI device name
    assert sx.mark("ISO7730QDWRQ1", "SI8630ET-AS")["part"] == "ISO7730QDWRQ1"  # and its own row
    assert sx.mark("ISO7740FQDBQRQ1", "SI8640BB-AU")["match"] == "Pin-to-Pin Replacement"
    assert sx.mark("ISO7720FDR", "SI8620ED-IS") is None  # its own row wins over the base number
    assert sx.mark("ADUM1400ARWZ", "SI8640AB-IS")["part"] == "ADUM1400A"
    assert sx.mark(None, "SI86S641EE-IS2") is None and sx.mark("UNKNOWN123", "SI86S641EE-IS2") is None


def test_check_mark_on_the_part_page(client, real, session):
    pid = session.scalar(select(Part.id).where(Part.mpn == "ISO7720DR"))
    page = client.get(f"/parts/{pid}").text
    assert 'class="sky-check"' in page and "✓" in page
    assert re.search(r"title=\"In Skyworks(&#39;|&#x27;|')s? cross reference \(Drop-In Replacement\)\"", page)
    assert "https://www.skyworksinc.com/cross-reference?PartNumber=ISO7720DR" in page


def test_check_mark_on_cross_a_list(client, real):
    page = client.post("/cross-list", data={"parts": "ISO7731DWR"}).text  # other family: SI86S631EE-IS2, official
    assert page.count('class="sky-check"') == 1
    assert "PartNumber=ISO7731DWR" in page
    plain = client.post("/cross-list", data={"parts": "ISO1050DUBR"}).text  # not in the official table
    assert 'class="sky-check"' not in plain


# ---------------------------------------------------------------- data fixes the comparison found


def test_novosense_channels_and_default_follow_the_part_number():
    """The Novosense product table had NSI8221 as 2/1 and swapped defaults; the datasheets' order information
    (NSI822x p.28) gives 1/1, and the last digit 0 = default low, 1 = high."""
    parts = yaml.safe_load((DATA / "novosense_digital_isolators.yaml").read_text())["parts"]
    checked = 0
    for p in parts:
        rule = by_part_number(p["mpn"])
        if rule:
            checked += 1
            assert p["params"]["channel_config"] == rule["channel_config"], p["mpn"]
            assert p["params"]["default_output"] == rule["default_output"], p["mpn"]
    assert checked > 250
    assert by_part_number("NSI8221N0-DSPR") == {"channel_config": "1/1", "default_output": "low"}
    assert by_part_number("NSI8266W1-DSWR") == {"channel_config": "6/0", "default_output": "high"}
    assert by_part_number("NSI8241BW1-DSWR") is None


def test_novosense_822x_pinouts_from_the_datasheet():
    parts = {p["mpn"]: p for p in yaml.safe_load((DATA / "novosense_digital_isolators.yaml").read_text())["parts"]}
    assert parts["NSI8221N0-DSPR"]["pinout"][:3] == ["VDD1", "OUTA", "INB"]  # NSI822x Figure 1.2
    assert parts["NSI8222N0-DSPR"]["pinout"][:3] == ["VDD1", "INA", "OUTB"]
    assert parts["NSI8241N0-DSPNR"]["pinout"][5] == "OUTD"


def test_iso6760l_defaults_low():
    parts = {p["mpn"]: p for p in yaml.safe_load((DATA / "ti_digital_isolators.yaml").read_text())["parts"]}
    assert parts["ISO6760LDWR"]["params"]["default_output"] == "low"  # iso6760l.pdf function table
    assert parts["ISO7730QDWRQ1"]["pinout"] == parts["ISO7730DWR"]["pinout"]  # iso7730-q1.pdf Figure 4-1


def test_nsi8221_gets_the_si86s622_drop_in(session, load):
    """NSI8221 pin 2 is OUTA like Si86S622 (the official table says Si86S621 for the N0 code: reversed)."""
    get = load("novosense_digital_isolators", "skyworks_si86")
    shown, drop_in = _shown(session, get, "NSI8221N0-DSPR")
    assert drop_in == "SI86S622BC-IS"
    assert "SI86S621BC-IS" not in shown


def test_kept_ours_where_the_official_row_is_reversed(session, real, part):
    """ISO7721 pin 2 is OUTA (iso7721.pdf Figure 5-4): Si86S622, not the official Si86S621."""
    shown, drop_in = _shown(session, part, "ISO7721DR")
    assert drop_in == "SI86S622EC-IS" and "SI86S621EC-IS" not in shown


def test_known_pairs_from_the_official_table():
    pairs = [p for p in cl.known_pairs() if p["source"] == "skyworks_xref"]
    assert len(pairs) >= 10
    assert {"their": "ISO7721DR", "ours": "SI86S621EC-IS", "expect": "wrong", "source": "skyworks_xref"} in pairs
