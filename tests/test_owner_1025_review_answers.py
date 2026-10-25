"""Owner's review answers of 25 Oct 2026: TPSI3050-Q1 technology review, integrated temperature sensing as the path
to product, owner's view on LDO trends, and the elaborated current-sensor TAM estimate (figure unchanged)."""

from app import yamlio
from app.config import PROJECT_ROOT
from app.services import reviews as rv
from app.services import tam
from app.services.opportunity import evidence


def test_tpsi3050_review_loads_and_answers_the_request():
    _, errors, warnings = rv.load_dir(rv.FOLDER)
    assert errors == [] and warnings == []
    r = rv.get("ti-tpsi3050-q1-isolated-switch")
    assert r is not None and r["maker"] == "TI" and r["family"] == "isolated_switch_driver"
    assert [x["slug"] for x in rv.for_part("TPSI3050-Q1")] == ["ti-tpsi3050-q1-isolated-switch"]
    names = " ".join(b["name"] for b in r["concept"]["blocks"])
    assert "transformer" in names and "gate driver" in names  # block diagram walked through
    assert any("Si875" in c["parts"] for c in r["competitors"])  # Skyworks competitive view


def test_temperature_sensor_path_is_integrated_sensing():
    p = evidence("path")["temperature_sensor"]
    assert p["path"] == "variant"
    assert "integrated" in p["base"].lower() and "standalone" in p["base"].lower()
    assert any("sky5a2105" in s.lower() for s in p["sources"]) and "owner" in " ".join(p["sources"]).lower()
    assert any("not pursued" in m for m in p["missing"])


def test_pol_ldo_trend_carries_owner_view_and_keeps_outlook():
    t = evidence("trends")["pol_ldo"]
    assert t["outlook"] == "stable"
    text = " ".join(t["drivers"]) + t["note"]
    assert "owner, 25 oct 2026" in text.lower() and "dissipation" in text and "accuracy" in text


def test_current_sensor_tam_elaborated_figure_unchanged():
    e = next(
        x
        for x in yamlio.load((PROJECT_ROOT / "data/business/tam.yaml").read_text())["estimates"]
        if x["id"] == "current-sensor-mm"
    )
    assert e["usd"] == 3350000000 and e["value"] == "$3.35 B" and e["year"] == 2026
    assert tam.parse_cagr(e["scope"]) == 11.4
    assert "contact-based" in e["scope"] and "not given" in e["scope"]
