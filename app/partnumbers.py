"""Part numbers compare without case and without separators: "Si8641BD-IS", "SI8641BD IS" and "si8641bd–is" are the
same part. The database search strips the same characters in SQL (app/services/queries.py), so a part number matches
the same way on every page. ``*`` stays (a wildcard in searches)."""

import re

SEPARATORS = (" ", "-", "–", "_", "/", ".", ",", "#")
_SEP = re.compile("[" + re.escape("".join(SEPARATORS)) + r"\s]")


def normalize_pn(text: str | None) -> str:
    return _SEP.sub("", text or "").upper()
