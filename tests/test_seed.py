import pytest
import yaml

from app.services.seed import load_file

BASE = {
    "manufacturers": [{"name": "TestCo", "role": "competitor"}],
    "packages": [
        {
            "code": "T-8",
            "name": "test",
            "pin_count": 8,
            "pitch_mm": 1.27,
            "body_length_mm": 4.9,
            "body_width_mm": 3.9,
            "span_mm": 6.0,
        }
    ],
}


def write(tmp_path, part):
    path = tmp_path / "d.yaml"
    path.write_text(yaml.safe_dump({**BASE, "parts": [part]}))
    return path


def test_unknown_parameter_rejected(session, tmp_path):
    path = write(
        tmp_path,
        {
            "mpn": "X1",
            "manufacturer": "TestCo",
            "family": "digital_isolator",
            "package": "T-8",
            "pinout": ["P"] * 8,
            "params": {"bogus": 1},
        },
    )
    with pytest.raises(ValueError, match="unknown parameters"):
        load_file(session, path)


def test_pinout_length_must_match_package(session, tmp_path):
    path = write(
        tmp_path,
        {"mpn": "X2", "manufacturer": "TestCo", "family": "digital_isolator", "package": "T-8", "pinout": ["P"] * 6},
    )
    with pytest.raises(ValueError, match="pinout has 6 pins"):
        load_file(session, path)


def test_real_data_reloads_only_when_files_change(session, tmp_path, monkeypatch):
    import shutil

    import app.main as main
    from app.config import get_settings

    (tmp_path / "data" / "real").mkdir(parents=True)
    shutil.copy(main.SYNTHETIC_FILE, tmp_path / "data" / "real" / "demo.yaml")
    monkeypatch.setattr(main, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path / "var")
    assert main.load_real_if_changed(session) is True
    assert main.load_real_if_changed(session) is False
    (tmp_path / "data" / "real" / "demo.yaml").write_text(main.SYNTHETIC_FILE.read_text() + "\n# changed\n")
    assert main.load_real_if_changed(session) is True


def test_reload_updates_package_and_manufacturer(session, tmp_path):
    # the server's database persists across deploys, so a corrected package or role must reach the existing row
    from sqlalchemy import select

    from app.models import Manufacturer, Package

    part = {"mpn": "X3", "manufacturer": "TestCo", "family": "digital_isolator", "package": "T-8", "pinout": ["P"] * 8}
    load_file(session, write(tmp_path, part))
    pkg = dict(BASE["packages"][0], name="corrected", pin_count=6, span_mm=6.2)
    data = {
        "manufacturers": [{"name": "TestCo", "role": "reference"}],
        "packages": [pkg],
        "parts": [{**part, "pinout": ["P"] * 6}],
    }
    path = tmp_path / "d2.yaml"
    path.write_text(yaml.safe_dump(data))
    load_file(session, path)  # the pinout check uses the corrected pin count
    row = session.scalar(select(Package).where(Package.code == "T-8"))
    assert (row.name, row.pin_count, row.span_mm) == ("corrected", 6, 6.2)
    assert session.scalar(select(Manufacturer).where(Manufacturer.name == "TestCo")).role == "reference"
