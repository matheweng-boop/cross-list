"""Convert to schematic: design-rule check, questions, drawing and the typical-application data."""

import sys
from pathlib import Path

import pytest

from app.services.seed import load_file

ROOT = Path(__file__).resolve().parents[1]

DIAGRAM = {
    "groups": [
        {"id": "g1", "label": "Controller", "col": 0, "row": 0, "w": 1,
         "blocks": [{"id": "b1", "fn": "mcu", "label": "", "qty": 1, "part": None}]},
        {"id": "g2", "label": "Isolation & drive", "col": 1, "row": 0, "w": 2,
         "blocks": [{"id": "b2", "fn": "digital_isolator", "label": "", "qty": 1, "part": "ISO7741DBQR"},
                    {"id": "b3", "fn": "gate_driver", "label": "", "qty": 3, "part": "SI8233BB-D-IS1"}]},
        {"id": "g3", "label": "RF", "col": 0, "row": 1, "w": 1,
         "blocks": [{"id": "b4", "fn": "rf_switch", "label": "", "qty": 1, "part": "SKY13317-373LF"}]},
    ],
    "links": [["g1", "g2", "SPI"], ["g1", "g3", "control"]],
}  # fmt: skip


@pytest.fixture
def real(session):
    """The real parts the diagram uses (test databases start with synthetic parts only)."""
    for f in ("ti_digital_isolators", "skyworks_si823x", "skyworks_switches"):
        load_file(session, ROOT / "data" / "real" / f"{f}.yaml")
    session.commit()


def post(client, **kw):
    r = client.post("/api/blocks/schematic", json={"data": DIAGRAM, **kw})
    assert r.status_code == 200, r.text
    return r.json()


def test_check_lists_devices_rules_and_questions(client, real):
    out = post(client, scope={"kind": "all"})
    devs = {d["ref"]: d for d in out["devices"]}
    assert devs["U1"]["placeholder"] and devs["U2"]["mpn"] == "ISO7741DBQR"
    texts = " ".join(i["text"] for i in out["issues"])
    assert "no part chosen" in texts and "quantity 3" in texts
    q = {x["id"]: x for x in out["questions"]}
    assert q["gnd:U2:GND2"]["default"] == "ISO_U2_GND2"  # isolated side keeps its own ground
    assert q["vdd:U3:VDDA"]["default"] == "15 V"  # gate-driver output side defaults inside its range
    # inside the frame: isolator outputs drive the gate-driver inputs, letter to letter, no pin twice
    assert set(q["in:g2:0"]["default"]) == {"U2.OUTA|U3.VIA", "U2.OUTB|U3.VIB"}
    # the controller link does not offer the already-driven gate-driver inputs as suggestions
    assert all("U3." not in p for p in q["link:0"]["default"])
    assert any(p.endswith("U4.V1") for p in q["link:1"]["default"])  # control link -> switch control lines


def test_rules_flag_bridged_isolation_and_out_of_range_supply(client, real):
    out = post(client, scope={"kind": "all"}, answers={"gnd:U2:GND2": "GND", "vdd:U3:VDDI": "12 V"})
    errors = [i["text"] for i in out["issues"] if i["level"] == "error"]
    assert any("bridges the isolation barrier" in e for e in errors)
    assert any("VDDI at 12 V is outside" in e for e in errors)
    assert out["errors"] == len(errors)


def test_draw_sheets_and_external_parts_from_datasheets(client, real):
    out = post(client, scope={"kind": "all"}, draw=True, title="Test")
    assert [s["title"] for s in out["sheets"]] == ["Controller", "Isolation & drive", "RF"]
    assert all(s["svg"].startswith("<svg") for s in out["sheets"])
    bom = out["bom"]
    iso = [b for b in bom if b["device"] == "U2"]
    assert {b["pin"] for b in iso} == {"VDD1", "VDD2"} and all(b["value"] == "0.1 µF" and b["quote"] for b in iso)
    assert any(b["device"] == "U2" and b["to"] == "ISO_U2_GND2" for b in bom)  # side 2 decoupled to its own ground
    assert not any("bootstrap" in b["note"].lower() for b in bom)  # topology parts are not ticked by default
    # the placeholder gets one pin per confirmed connection, named after the far end
    assert "U2 INA" in out["sheets"][0]["svg"]


def test_scope_one_frame_and_open_values(client, real):
    out = post(client, scope={"kind": "group", "group": "g3"}, draw=True)
    assert [s["title"] for s in out["sheets"]] == ["RF"]
    vq = next(q for q in out["questions"] if q["id"].startswith("val:U1:"))  # numbered within the selection
    assert any("no value" in i["text"] for i in out["issues"])
    out = post(client, scope={"kind": "group", "group": "g3"}, draw=True, answers={vq["id"]: "100 pF"})
    assert not any("no value" in i["text"] for i in out["issues"])
    assert {b["value"] for b in out["bom"] if b["series"]} == {"100 pF"}


def test_typical_application_data_is_consistent():
    sys.path.insert(0, str(ROOT / "tools"))
    from check_typical import check

    for f in sorted((ROOT / "data" / "schematic").glob("*.yaml")):
        # datasheet text lives under var/ (not committed): without it only the structure is checked
        errs = [e for e in check(f) if "datasheet text not found" not in e]
        assert not errs, errs[:5]
