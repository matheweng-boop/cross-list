"""The one list of manufacturing site and fab names that must never appear on the site (owner, 25 Oct 2026: "the fab
must not be revealed"; capability wording only, "in-house is fine"). Used by the Shareable reports' word check and by
tests/test_no_sites.py; this file is the only place the names are written down."""

import re

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


def hits(text: str) -> list[str]:
    """Site names and place-next-to-fab phrases found in a text."""
    return [m.group(0) for m in SITE.finditer(text)] + [m.group(0) for m in NEAR.finditer(text)]
