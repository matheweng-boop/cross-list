"""No manufacturing site or fab names on the site (owner, 25 Oct 2026: "the fab must not be revealed").

Only capability wording is allowed ("in-house BAW wafer processing", "in-house assembly and test", "silicon from
foundry partners"). Manufacturer data (data/catalog, data/real, data/appnotes.jsonl) is outside this check."""

import re
import subprocess

from app.services import opportunity as op
from tests.conftest import ROOT

# Skyworks / Qorvo (and former Trans-Tech) fab, assembly and test sites; whole words, any case. "Richardson RFPD"
# and "Richardson Electronics" are distributors, not the fab.
SITES = (
    "osaka", "kadoma", r"richardson(?!\s*(?:rfpd|electronics))", "adamstown", "singapore", "mexicali", "woburn",
    "newbury park", "hillsboro", "greensboro", "apopka", "farmers branch", "beijing", "dezhou", "hiroshima", "lowell",
    "haverhill", "cedar rapids", "ottawa", "heredia", "costa rica", "nuremberg", "milpitas", "east fishkill",
)  # fmt: skip
SITE = re.compile(r"\b(?:" + "|".join(SITES) + r")\b", re.I)
# a place next to a fab word: "Texas fab", "fabs in NC, OR, TX", "assembly in Mexico"
_FAB = (r"(?i:fabs?|foundry|foundries|wafer (?:fab|processing|production)|assembly(?: and test)?|test sites?|plants?|"
        r"facilit(?:y|ies))")  # fmt: skip
_PLACE = (r"(?:Texas|Japan|Mexico|Oregon|North Carolina|Massachusetts|California|Maryland|Florida|Costa Rica|Germany|"
          r"Singapore|Malaysia|China|Taiwan|Korea|Philippines|TX|NC|OR|MA|CA|MD|FL)")  # fmt: skip
NEAR = re.compile(rf"\b{_PLACE}\s+{_FAB}\b|\b{_FAB}\b[^.;\n<]{{0,30}}?\b(?:in|at)\s+{_PLACE}\b")

SCOPE = ("data/business", "data/library", "app", "docs")
SKIP = ("data/catalog/", "data/real/", "data/appnotes.jsonl")
BINARY = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".woff", ".woff2", ".sqlite", ".db")


def hits(text: str) -> list[str]:
    return [m.group(0) for m in SITE.finditer(text)] + [m.group(0) for m in NEAR.finditer(text)]


def tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files", *SCOPE], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [f for f in out.split() if not f.startswith(SKIP) and not f.endswith(BINARY)]


def test_the_check_catches_site_wording():
    for bad in ("Skyworks BAW (Osaka)", "Qorvo's RICHARDSON BAW fab", "Trans-Tech, Adamstown, Maryland",
                "fabs in NC, OR, TX", "a Texas fab", "assembly and test in Mexico", "Newbury Park, CA"):  # fmt: skip
        assert hits(bad), bad
    for ok in ("in-house BAW wafer processing", "in-house GaAs HBT wafer fab", "in-house assembly and test",
               "silicon from foundry partners", "Richardson RFPD (distributor)", "richardsonrfpd.com",
               "China leads Wi-Fi 6 adoption",
               "DoD Trusted Source accreditation for its microwave foundry"):  # fmt: skip
        assert not hits(ok), ok


def test_no_site_names_in_site_files():
    files = tracked()
    assert any(f.startswith("data/business/capabilities") for f in files)
    found = {}
    for f in files:
        try:
            text = (ROOT / f).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        if h := hits(text):
            found[f] = sorted(set(h))
    assert not found, f"manufacturing sites named (use capability wording instead): {found}"


def _shareable_pages(client) -> list[str]:
    html = client.get("/shareable").text
    return sorted({"/shareable", *re.findall(r'href="(/shareable/[^"#?]+)"', html)} - {"/shareable/logo"})


def test_no_site_names_on_rendered_pages(client):
    pages = ["/business/capabilities", "/engineering", "/knowledge", "/business/automotive",
             "/business/reports/filters-1-11ghz", "/business/reports/filters-1-11ghz/background",
             *_shareable_pages(client)]  # fmt: skip
    assert "/shareable/technology-overview" in pages
    # evidence pages of every function a manufacturing or packaging platform serves (they list those platforms)
    fns = sorted({f for p in op.capabilities().values() if p.get("kind") in ("manufacturing", "packaging")
                  for f in p.get("functions") or []})  # fmt: skip
    assert "filter_saw_baw" in fns
    pages += [f"/business/evidence/{f}" for f in fns]
    found = {}
    for url in pages:
        r = client.get(url)
        assert r.status_code == 200, url
        if h := hits(r.text):
            found[url] = sorted(set(h))
    assert not found, f"manufacturing sites on pages: {found}"


def test_manufacturing_platforms_are_capabilities_not_sites():
    plats = {k: p for k, p in op.capabilities().items() if p.get("kind") == "manufacturing"}
    assert "inhouse_wafer_fabs" in plats and "inhouse_assembly_test" in plats
    assert not [k for k in op.capabilities() if k.startswith("site_")]
