"""General knowledge by product and "Why it matters to the customer" on the spec guides (owner, 22 Oct 2026)."""

from app.services import knowledge


def test_data_points_somewhere():
    assert knowledge.problems() == []


def test_isolation_guides_have_customer_points():
    for key in ("cmti_kv_us", "creepage_mm", "isolation_rating_kvrms", "prop_delay_ns", "uvlo_v", "peak_source_a"):
        groups = knowledge.why(key)
        assert groups and all(pt["kind"] in knowledge.KINDS for g in groups for pt in g["points"]), key
    assert any(g["heading"] == "Material group (CTI)" for g in knowledge.why("creepage_mm"))


def test_by_product_page_and_guide_box(client):
    html = client.get("/knowledge").text
    for key in ("digital_isolators", "gate_drivers", "isolated_analog", "rf_switches", "tuners"):
        assert f'id="p-{key}"' in html
    assert "Why it matters to the customer" in html and 'href="/engineering/cmti_kv_us"' in html
    note = client.get("/engineering/cmti_kv_us").text
    assert 'class="kn-why kn-why-note small"' in note and "shoot-through" in note
    assert note.index("Why it matters to the customer") < note.index("What it is")
    assert 'class="kn-est"' in client.get("/engineering/creepage_mm").text
    gd = next(p for p in knowledge.by_product() if p["key"] == "gate_drivers")
    assert gd["guides"] and gd["visuals"] and gd["topics"] and gd["points"]
