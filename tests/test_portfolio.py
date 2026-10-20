"""Products > Skyworks + Qorvo: the comparison loads, names real parts and renders."""

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
