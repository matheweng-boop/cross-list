"""Cross-sell > Skyworks + Qorvo portfolio: the comparison loads, names real parts and renders."""

from app.services import blocks
from app.services import portfolio as pf


def test_curated_parts_exist_in_the_catalogue():
    known = {p["mpn"].upper() for parts in blocks.catalog_parts().values() for p in parts}
    for s in pf.curated().get("segments") or []:
        for k in ("pick_skyworks", "pick_qorvo"):
            for mpn in (s.get(k) or {}).get("parts") or []:
                assert mpn.upper() in known, (s["id"], mpn)


def test_overlap_and_bundles_have_both_lines():
    ov = pf.overlap()
    assert ov["both"] and all(r["Skyworks"] and r["Qorvo"] for r in ov["both"])
    assert all(b["skyworks"] and b["qorvo"] for b in pf.bundles())


def test_page_renders(client):
    page = client.get("/portfolio")
    assert page.status_code == 200 and "Which line to offer" in page.text and "Against each competitor" in page.text


def test_product_categories_cover_both_lines():
    pc = pf.product_categories()
    labels = {r["label"]: r for r in pc["rows"]}
    assert labels["Isolated gate drivers"]["Skyworks"] > 0
    assert labels["Filters, duplexers and multiplexers"]["Qorvo"] > 0
    assert pc["totals"]["Skyworks"] == sum(r["Skyworks"] for r in pc["rows"])
    assert pf.category_of("Isolation", "Isolated Gate Drivers") == "Isolated gate drivers"
    assert pf.category_of("TV and Video", "Digital TV and Satellite Demodulators") == "Broadcast radio, TV and audio"
    assert pf.category_of("Something new") == pf.OTHER_CATEGORY


def test_synergies_pair_the_two_lines_only():
    syn = pf.synergies()
    assert syn
    for x in syn:
        assert x["skyworks_parts"] and all(p["manufacturer"] == "Skyworks" for p in x["skyworks_parts"])
        assert x["qorvo_parts"] and all(p["manufacturer"] == "Qorvo" for p in x["qorvo_parts"])
        assert x["same"] or x["linked"] or "companion" in x["summary"]
        assert "gap" not in x["summary"].lower()


def test_page_has_categories_synergies_and_section_links(client):
    html = client.get("/portfolio").text
    for anchor in ("categories", "rf", "synergies"):
        assert f'href="#{anchor}"' in html and f'id="{anchor}"' in html
    assert 'class="pf-cat small"' in html and "pf-syn-card" in html
    assert "Skyworks + Qorvo portfolio" in html
