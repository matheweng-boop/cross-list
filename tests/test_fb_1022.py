"""Owner comments of 22 Oct 2026 (daily update): precision fixes, layout changes and new sections."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_sso8_creepage_is_at_least_not_measured():
    files = [
        ROOT / "data/business/cases/hv-extra-wide-isolation.yaml",
        ROOT / "app/web/templates/business/reports/iso7821dww-isolation.html",
        ROOT / "app/web/templates/business/reports/hv-extra-wide-isolation.background.html",
        ROOT / "data/business/reports.yaml",
    ]
    for f in files:
        text = f.read_text()
        assert "measured 8.5" not in text and "measures 8.5" not in text and "8.5 mm measured" not in text, f
    bg = files[2].read_text()
    assert "7. Summary and Future Outlook" in bg
    assert "Skyworks is currently developing a new ultra-wide-body (UWB) SOIC package" in bg
