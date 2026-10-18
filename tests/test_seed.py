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
