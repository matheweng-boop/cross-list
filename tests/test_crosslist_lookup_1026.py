"""Cross-list lookup 1 (owner, 26 Oct 2026: 49 TI parts sent with "Update cross-lists"): the answers file is valid,
every part found resolves on Products › Cross a list as a known part, and parts of functions without crossing rules
get the honest red reason "Function known (…), no Skyworks/Qorvo part in our data."."""

from app import yamlio
from app.matching.rules import load_all_rules
from app.services import crosslist as cl
from app.services import crosslist_lookups as lk
from app.services import vocab
from app.services.seed import load_file
from tests.conftest import ROOT

ANSWERS = ROOT / "data" / "manage" / "crosslist_lookups.yaml"
DATA = ROOT / "data" / "real" / "ti_other_known.yaml"


def _rows():
    return [r for r in yamlio.load(ANSWERS.read_text())["parts"] if r["lookup"] == 1]


def test_lookup_answers_file_is_valid():
    rows = _rows()
    assert len(rows) == 49 and len({r["part"] for r in rows}) == 49
    for r in rows:
        assert r["status"] in ("found", "not_found") and str(r["date"]) == "2026-10-26", r
        assert str(r["source"]).startswith("https://www.ti.com/"), r
        assert r["status"] == "found" or r["note"], r  # a not-found part says why
    assert {r["part"] for r in rows if r["status"] == "not_found"} == {"PTPLD1201DGSRQ1", "1P1G126QDBVRQ1"}
    assert len(lk.results()) >= 49  # the site reads every answer


def test_other_known_family_has_no_crossing_rules():
    fam = load_all_rules()["other_known"]
    assert {p.priority for p in fam.params} == {3}
    fns = vocab.functions()
    for p in yamlio.load(DATA.read_text())["parts"]:
        assert p["params"]["function_type"] in fns, p["mpn"]
        assert p["params"]["qualification"] == "automotive", p["mpn"]


def test_every_found_part_is_known_on_cross_a_list(session, real):
    load_file(session, DATA)
    session.commit()
    found = [r["part"] for r in _rows() if r["status"] == "found"]
    entries, _ = cl.parse("\n".join(found))
    rows = {r.text: r for r in cl.cross_list(session, entries)}
    assert set(rows) == set(found)
    for text, r in rows.items():
        assert r.part is not None and "Not in our data" not in r.reason, (text, r.reason)
        assert r.light == "red" and r.drop_in is None and r.functional is None, text
        label = vocab.fn_label(r.part.param_map()["function_type"])
        assert r.reason == f"Function known ({label}), no Skyworks/Qorvo part in our data.", (text, r.reason)
    assert rows["ADS131B02Q1"].part.mpn == "ADS131B02QPWRQ1" and rows["ADS131B02Q1"].how == "variant"
    assert rows["TLV9002QDRQ1"].reason == "Function known (Amplifier), no Skyworks/Qorvo part in our data."
    assert rows["SN74HCS08QDYYRQ1"].reason.startswith("Function known (Logic")
    assert rows["TPSI2140QDWQRQ1"].reason == ("Function known (Isolated switch driver), no Skyworks/Qorvo part in our "
                                              "data.")  # fmt: skip
    assert rows["TPSI2140QDWQRQ1"].reason_link == "/business/evidence/isolated_switch_driver"


def test_not_found_parts_stay_unknown(session):
    load_file(session, DATA)
    session.commit()
    entries, _ = cl.parse("PTPLD1201DGSRQ1\n1P1G126QDBVRQ1")
    assert all(r.part is None for r in cl.cross_list(session, entries))
