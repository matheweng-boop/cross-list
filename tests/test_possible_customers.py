"""Possible customers per sub-system and region (owner, 9 Nov 2026): every company has a public source with its link
and read date, a company in several regions appears in each, the Systems library shows a folded section per
sub-system and system, the screen passes, and the data stays out of the Shareable reports."""

import re
from datetime import date
from pathlib import Path

import pytest

from app.config import PROJECT_ROOT
from app.services import possible_customers as pc
from app.services import systems as sy

SUBS = [(s["key"], x["key"]) for s in sy.systems() for x in s["subsystems"]]
TYPES = {"company page", "public annual report", "press release", "trade publication", "association list",
         "industry specification"}  # fmt: skip


def _all(g):
    return [c for v in g["regions"].values() for c in v] + g["unplaced"]


def test_every_sub_system_is_mapped_and_known():
    keys = set(pc.data().get("subsystems") or {})
    assert keys == {f"{a}/{b}" for a, b in SUBS}
    for spec in pc.data()["subsystems"].values():
        assert set(spec.get("segments") or []) <= set(pc.segments()), spec
        for x in spec.get("extra") or []:
            assert set(x["sources"]) <= set(pc.data()["sources"]), x
    for name, p in pc.data()["presence"].items():
        assert set(p["regions"]) <= set(pc.REGIONS) and p["where"] and p["sources"], name


@pytest.mark.parametrize(("system", "sub"), SUBS)
def test_every_company_has_a_source_url_date_and_type(system, sub):
    g = pc.for_sub(system, sub)
    assert g["n"] or g["few"], f"{system}/{sub}: no companies and no 'few public sources' line"
    for c in _all(g):
        assert c["sources"], c["name"]
        for s in c["sources"] + c["presence"]:
            assert re.match(r"https://\S+$", s["url"]), (c["name"], s)
            assert date.fromisoformat(s["date"]) <= date(2026, 11, 9), (c["name"], s)
            assert s["type"] in TYPES, (c["name"], s)
        assert c["note"], c["name"]


@pytest.mark.parametrize(("system", "sub"), SUBS)
def test_a_company_in_several_regions_is_in_each(system, sub):
    g = pc.for_sub(system, sub)
    shown = {r: {c["name"] for c in v} | set(g["more"][r]) for r, v in g["regions"].items()}
    for c in _all(g):
        assert set(c["regions"]) <= set(pc.REGIONS)
        for r in c["regions"]:
            assert c["name"] in shown[r], (c["name"], r)
        for r in set(pc.REGIONS) - set(c["regions"]):
            assert c["name"] not in shown[r], (c["name"], r)
        if len(c["regions"]) > 1:
            assert c["where"], c["name"]  # one line saying where
    assert all(len(v) <= pc.data()["max_per_region"] for v in g["regions"].values())


def test_presence_adds_regions_beyond_the_headquarters():
    bosch = next(c for c in _all(pc.for_sub("automotive", "car-access")) if c["name"] == "Bosch")
    assert bosch["regions"] == ["EMEA", "Americas", "Asia"] and bosch["presence"]
    assert bosch["presence"][0]["url"].startswith("https://www.bosch.com/")
    system = pc.for_system("automotive")
    for r in pc.REGIONS:  # once per region list, not once per sub-system
        assert sum(1 for c in system["regions"][r] if c["name"] == "Bosch") == 1, r


def test_the_screen_passes_and_wording_never_claims_a_customer():
    assert pc.screen() == []
    for t in pc.all_texts():
        low = t.lower()
        assert not re.search(r"\b(buys?|bought|customer of|design[- ]win|uses (skyworks|qorvo))\b", low), t
        assert "skyworks" not in low and "qorvo" not in low, t
    assert pc.NOTE == pc.data()["note"]


def test_hosts_never_requested_are_not_sources():
    banned = ("qorvo.com", "qualcomm.com", "nxp.com", "analog.com", "mouser", "digikey", "arrow.com")
    for s in pc.data()["sources"].values():
        assert not any(b in s["url"] for b in banned), s


def test_library_shows_the_folded_section(client):
    html = client.get("/library").text
    assert 'id="pc-automotive-car-access"' in html and 'id="pc-datacenter"' in html
    box = html.split('id="pc-automotive-car-access"', 1)[1].split("</details>", 1)[0]
    assert "Possible customers" in html and pc.NOTE in html
    for r in pc.REGIONS:
        assert f'aria-label="{r}"' in box
    assert "carconnectivity.org/our-members/member-list/" in box and "read 2026-11-09" in box
    assert "Possible customers" not in client.get("/blocks").text  # Systems library only
    assert 'href="/library"' in client.get("/business/customers").text


def test_guests_see_it_like_the_customers_page(owner, make_guest):
    guest, _ = make_guest("Anna Guest")
    assert guest.get("/business/customers").status_code == 200  # public company names are shown to guests there
    assert 'id="pc-automotive-car-access"' in guest.get("/library").text


def test_kept_out_of_the_shareables(client):
    app = Path(PROJECT_ROOT) / "app"
    for p in [*app.glob("services/share_*.py"), app / "services" / "presentation.py",
              *app.glob("web/templates/shareable/**/*.html")]:  # fmt: skip
        text = p.read_text()
        assert "possible_customers" not in text and "pc_box" not in text, p
    html = client.get("/shareable/v2x").text
    assert "Possible customers" not in html and "carconnectivity.org/our-members" not in html
