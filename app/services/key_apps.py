"""Key applications of a function (data/business/key_applications.yaml), shown on its bigger-picture page: per
application the voltage and current class, why the function is used, links, and the library diagrams that use the
function there (by system / sub-system from data/blocks/systems.yaml, or by diagram category)."""

from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT
from app.services import blocks
from app.services import systems as sy

FILE = PROJECT_ROOT / "data" / "business" / "key_applications.yaml"


@lru_cache
def _data() -> dict:
    return yamlio.load(FILE.read_text()) or {}


def _idx(spec: str) -> set[int]:
    """Library diagram indexes of a system ("drones") or a sub-system ("cellular/transport")."""
    system, _, sub = spec.partition("/")
    s = sy.get(system)
    if s is None:
        return set()
    return {i for x in s["subsystems"] if not sub or x["key"] == sub for i in x["idx"]}


def for_function(fn: str) -> dict | None:
    """{intro, applications: [... with diagrams [{i, name, href}] and n], other: diagrams in no application}."""
    from app.services import opportunity as op

    entry = _data().get(fn)
    if not entry:
        return None
    lib = blocks.templates()
    using = sorted({a.i for a in op.applications()
                    if not a.background and any(p.fn == fn for p in a.positions)})  # fmt: skip
    placed: set[int] = set()
    rows = []
    for a in entry.get("applications") or []:
        keep = set().union(*(_idx(s) for s in a.get("systems") or [])) if a.get("systems") else set()
        cats = set(a.get("categories") or [])
        # a category counts only for diagrams outside the systems (those are already counted by their system)
        mine = [i for i in using if i in keep or (lib[i].get("category") in cats and sy.place_of(i)[0][0] == sy.OTHER)]
        placed.update(mine)
        rows.append({**a, "links": [tuple(x) for x in a.get("links") or []], "n": len(mine),
                     "diagrams": [{"i": i, "name": blocks.display_name(lib[i]), "href": f"/blocks/new?template={i}"}
                                  for i in mine]})  # fmt: skip
    other = [{"i": i, "name": blocks.display_name(lib[i]), "href": f"/blocks/new?template={i}"}
             for i in using if i not in placed]  # fmt: skip
    return {"intro": entry.get("intro") or "", "applications": rows, "other": other, "n_using": len(using)}
