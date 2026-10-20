"""Values from unofficial datasheet copies: merged from data/real/unofficial/ only while the setting is on, marked
in the pages, and gone from the database after a load with the setting off."""

from pathlib import Path

import yaml
from sqlalchemy import select

from app import yamlio
from app.models import Package, Part
from app.services.seed import UNOFFICIAL, is_unofficial, load_file, merge_unofficial, unofficial_keys

ROOT = Path(__file__).resolve().parents[1]

PKG = {"pin_count": 6, "body_length_mm": 2.0, "body_width_mm": 2.0, "span_mm": 2.0}
BASE = {
    "manufacturers": [{"name": "TestCo", "role": "competitor"}],
    "packages": [{"code": "U-6 (pitch n/s)", "name": "base", "pitch_mm": 0.0, **PKG}],
    "parts": [
        {
            "mpn": "SW1",
            "manufacturer": "TestCo",
            "family": "rf_switch",
            "package": "U-6 (pitch n/s)",
            "pinout": [],
            "notes": "store data only",
            "params": {"configuration": "SPDT", "max_input_power_dbm": 30},
            "param_sources": {"configuration": "store", "max_input_power_dbm": "store"},
        }
    ],
}
OVERLAY = {
    "base": "sw.yaml",
    "packages": [{"code": "U-6 p0.5", "name": "from the drawing", "pitch_mm": 0.5, "exposed_pad": True, **PKG}],
    "parts": [
        {
            "mpn": "SW1",
            "package": "U-6 p0.5",
            "pinout": ["RF2", "GND", "RF1", "V1", "RFC", "V2"],
            "params": {"control_interface": "GPIO", "termination": "reflective"},
            "param_sources": {"control_interface": "p.2 logic high 1.8 V", "pinout": "p.5 pin table"},
            "provenance": {"tier": "unofficial", "host": "mirror.example", "url": "https://mirror.example/sw1.pdf",
                           "sha256": "ab" * 32, "fetched": "2026-10-20", "note": "unofficial copy of the datasheet"},
        }
    ],
}  # fmt: skip


def write_files(root: Path, overlay: bool = True) -> Path:
    real = root / "data" / "real"
    (real / "unofficial").mkdir(parents=True, exist_ok=True)
    (real / "sw.yaml").write_text(yaml.safe_dump(BASE))
    if overlay:
        (real / "unofficial" / "sw.yaml").write_text(yaml.safe_dump(OVERLAY))
    return real / "sw.yaml"


def sw1(session) -> Part:
    session.expire_all()
    return session.scalars(select(Part).where(Part.mpn == "SW1")).unique().one()


def test_overlay_merges_when_on(session, tmp_path):
    load_file(session, write_files(tmp_path), unofficial=True)
    part = sw1(session)
    values = part.param_map()
    assert values["control_interface"] == "GPIO" and values["max_input_power_dbm"] == 30
    assert unofficial_keys(part) == {"control_interface", "termination", "pinout", "package"}
    src = {pv.key: pv.source for pv in part.params}
    assert src["control_interface"] == f"{UNOFFICIAL}mirror.example: p.2 logic high 1.8 V"
    assert not is_unofficial(src["max_input_power_dbm"])  # the base value stays official
    assert part.package.code == "U-6 p0.5" and part.package.pitch_mm == 0.5 and is_unofficial(part.package.name)
    assert part.pinout[3] == "V1" and is_unofficial(part.pinout_source)
    assert "https://mirror.example/sw1.pdf" in part.notes and part.notes.startswith("store data only")


def test_overlay_values_disappear_when_off(session, tmp_path):
    path = write_files(tmp_path)
    load_file(session, path, unofficial=True)
    load_file(session, path, unofficial=False)
    part = sw1(session)
    assert part.param_map() == {"configuration": "SPDT", "max_input_power_dbm": 30}
    assert unofficial_keys(part) == set()
    assert part.package.code == "U-6 (pitch n/s)" and part.pinout == [] and part.pinout_source is None
    assert part.notes == "store data only"


def test_setting_or_folder_change_reloads_without_overlay(session, tmp_path, monkeypatch):
    import app.main as main
    from app.config import get_settings

    write_files(tmp_path)
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path / "var")
    monkeypatch.setattr(get_settings(), "use_unofficial_data", True)
    assert main.load_real_if_changed(session) is True
    assert "control_interface" in sw1(session).param_map()
    assert main.load_real_if_changed(session) is False
    monkeypatch.setattr(get_settings(), "use_unofficial_data", False)  # the switch alone triggers a reload
    assert main.load_real_if_changed(session) is True
    assert unofficial_keys(sw1(session)) == set() and "control_interface" not in sw1(session).param_map()
    assert session.scalar(select(Package).where(Package.code == "U-6 p0.5")) is None  # unused overlay package removed
    monkeypatch.setattr(get_settings(), "use_unofficial_data", True)
    assert main.load_real_if_changed(session) is True and "control_interface" in sw1(session).param_map()
    (tmp_path / "data" / "real" / "unofficial" / "sw.yaml").unlink()  # deleting the overlay also reloads
    assert main.load_real_if_changed(session) is True and unofficial_keys(sw1(session)) == set()


def test_marker_renders(client, session, tmp_path):
    load_file(session, write_files(tmp_path), unofficial=True)
    session.commit()
    html = client.get(f"/parts/{sw1(session).id}").text
    assert 'class="unofficial" title="From an unofficial copy of the datasheet">†</sup>' in html
    assert "From an unofficial copy of the datasheet (a distributor" in html  # footnote
    quality = client.get("/business/quality").text
    assert "2 parameter values, 1 pinouts" in quality and "CROSSLIST_USE_UNOFFICIAL_DATA=false" in quality


def test_no_marker_without_overlay(client, session, tmp_path):
    load_file(session, write_files(tmp_path, overlay=False))
    session.commit()
    assert "†</sup>" not in client.get(f"/parts/{sw1(session).id}").text


def test_real_overlays_only_fill_and_name_their_copy():
    for path in sorted((ROOT / "data" / "real" / "unofficial").glob("*.yaml")):
        base, overlay = yamlio.load((path.parent.parent / path.name).read_text()), yamlio.load(path.read_text())
        parts = {p["mpn"]: p for p in base["parts"]}
        merge_unofficial(base, overlay)  # every overlay part exists in its base file
        for o in overlay["parts"]:
            prov = o["provenance"]
            assert prov["tier"] == "unofficial" and len(prov["sha256"]) == 64 and prov["url"].startswith("https://")
            assert not set(o["params"]) & set(parts[o["mpn"]]["params"]), f"{o['mpn']}: overlay overrides a base value"
            assert set(o["params"]) | {"pinout", "package"} >= set(o["param_sources"]) - {"package"}
