"""One rule each for lifecycle status and part-number matching, used by every page."""

import pytest

from app.partnumbers import normalize_pn
from app.services.lifecycle import is_risk, status_class


@pytest.mark.parametrize(
    "status,cls",
    [
        ("Active", "active"), ("Standard", "active"), ("Featured", "active"), ("In Production", "active"),
        ("Preview", "preview"), ("Pre Release", "preview"), ("Samples Only", "preview"),
        ("NRND", "nrnd"), ("No new designs", "nrnd"), ("Last Time Buy", "nrnd"), ("last_time_buy", "nrnd"),
        ("Discontinued", "obsolete"), ("Obsolete", "obsolete"),
        (None, "unknown"), ("unknown", "unknown"), ("Contact sales (ND)", "nrnd"),
    ],
)  # fmt: skip
def test_status_class(status, cls):
    assert status_class(status) == cls
    assert is_risk(status) == (cls in ("nrnd", "obsolete"))


def test_part_numbers_match_without_separators():
    assert normalize_pn("Si8641BD-IS") == normalize_pn("si8641bd is") == normalize_pn("SI8641BD–IS") == "SI8641BDIS"
    assert normalize_pn("JSW2-63DR+") == "JSW263DR+" and normalize_pn("SKY13*") == "SKY13*"
    assert normalize_pn(None) == ""


def test_search_finds_a_part_typed_with_other_separators(client):
    # the database search strips the same characters as normalize_pn
    page = client.get("/find?q=SI8641BD%E2%80%93IS")
    assert page.status_code in (200, 303)
