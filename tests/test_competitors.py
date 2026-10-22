"""Competitive analytics: profiles load from data, every figure has a source, the pages show them."""

from app.services import competitors as cp


def test_profiles_are_valid_and_sourced():
    assert not cp.problems()
    s = cp.get("sitime")
    assert s and s["name"] == "SiTime" and all(f["source"] for f in s["figures"])
    assert any(o["level"] == "direct" for o in s["overlap"]) and s["strengths"] and s["weaknesses"]


def test_bad_profile_is_reported(tmp_path):
    (tmp_path / "x.yaml").write_text("name: X\nsummary: s\nfigures:\n  - {label: Revenue, value: 1}\n"
                                     "overlap:\n  - {area: a, level: maybe}\n")
    (tmp_path / "_format.yaml").write_text("name: skipped\n")
    assert cp.all_profiles(tmp_path) == [] and len(cp.problems(tmp_path)) == 2


def test_pages(client):
    page = client.get("/business/competitors").text
    assert "Competitive analytics" in page and 'href="/business/competitors/sitime"' in page
    one = client.get("/business/competitors/sitime").text
    assert "Where they compete with Skyworks and Qorvo" in one and "$326.7 M" in one and "Renesas" in one
    assert client.get("/business/competitors/nobody").status_code == 404
