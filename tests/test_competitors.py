"""Competitive analytics: profiles load from data, every figure has a source, the pages show them."""

from app.services import competitors as cp


def test_profiles_are_valid_and_sourced():
    assert not cp.problems()
    s = cp.get("sitime")
    assert s and s["name"] == "SiTime" and all(f["source"] for f in s["figures"])
    assert any(o["level"] == "direct" for o in s["overlap"]) and s["strengths"] and s["weaknesses"]


def test_every_number_has_source_and_date():
    """Owner, 23 Oct 2026: a financial stability section for every profile; every number with its source and date."""
    profiles = cp.all_profiles()
    assert {"sitime", "novosense"} <= {p["slug"] for p in profiles}
    for p in profiles:
        fin = p["financials"]
        items = [*p["figures"], *fin["table"], *fin["notes"], fin["ownership"]]
        assert all(x.get("source") and x.get("date") for x in items), p["slug"]
        keys = {r["key"] for r in fin["table"]} | {n["key"] for n in fin["notes"]}
        assert {"revenue", "rnd", "rnd_pct", "opex", "op_result", "cash", "debt", "fcf"} <= keys, p["slug"]
        assert len(fin["years"]) == 3 and fin["supplier_verdict"]["text"]


def test_bad_financials_are_reported():
    good = {"name": "X", "ticker": "T", "summary": "s", "figures": [{"label": "R", "value": 1, "source": "s",
                                                                       "date": "2026-01-01"}]}  # fmt: skip
    assert any("financials is missing" in e for e in cp.validate(good, "x"))
    fin = {"years": ["a", "b"], "table": [{"key": "revenue", "values": ["1"], "source": "s"}],
           "notes": [{"key": "cash", "value": "v", "source": "s", "date": "d"}],
           "supplier_verdict": {"longevity": "great", "supply": "solid", "text": ["t"]}}  # fmt: skip
    errs = cp.validate({**good, "financials": fin}, "x")
    for bit in ("3 fiscal years", "one value per year", "source and a date", "needs debt", "needs fcf",
                "ownership", "supplier_verdict"):  # fmt: skip
        assert any(bit in e for e in errs), bit


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
    assert "Financial stability" in one and "$808.4 M" in one and "convertible" in one
    assert "What it means as a supplier" in one and ">est<" in one
    assert client.get("/business/competitors/nobody").status_code == 404


def test_novosense_page(client):
    assert 'href="/business/competitors/novosense"' in client.get("/business/competitors").text
    html = client.get("/business/competitors/novosense").text
    assert "688052" in html and "3,367.8" in html and "Not Enough Data" in html
    assert 'href="/parts?company=Novosense"' in html and "Diodes" in html and "What it means for us" in html
