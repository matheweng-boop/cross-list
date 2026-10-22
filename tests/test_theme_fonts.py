"""Pastel theme: fonts are self-hosted, declared with @font-face and never loaded from a font host."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "app/web/static"
FONTS = ("manrope-latin.woff2", "space-grotesk-latin.woff2", "jetbrains-mono-500-latin.woff2")


def test_font_files_are_woff2_and_small():
    total = 0
    for name in FONTS:
        data = (STATIC / "fonts" / name).read_bytes()
        assert data[:4] == b"wOF2", name
        total += len(data)
    assert total < 400_000
    assert "SIL Open Font License" in (STATIC / "fonts/OFL.txt").read_text()


def test_font_face_declared():
    css = (STATIC / "app.css").read_text()
    for family, name in zip(("Manrope", "Space Grotesk", "JetBrains Mono"), FONTS, strict=True):
        assert f'@font-face {{ font-family: "{family}";' in css
        assert f'url("/static/fonts/{name}")' in css
    assert css.count("font-display: swap") >= 3


def test_no_external_font_host():
    for text in ((ROOT / "app/web/templates/base.html").read_text(), (STATIC / "app.css").read_text()):
        for host in ("fonts.googleapis.com", "fonts.gstatic.com", "use.typekit", "fonts.bunny.net"):
            assert host not in text
