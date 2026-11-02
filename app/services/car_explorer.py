"""Systems & applications > Car explorer (owner, 2 Nov 2026): a see-through 3D car whose areas open the Automotive map
applications that sit there.

The areas and their applications are in data/business/car_areas.yaml. Letters and functions come live from the
Automotive map (automotive.build()), grouped as its By application view groups them (automotive.by_level(): rejected
calls hidden), over all functions. A diagram row (the seat) lists the blocks of one library diagram with the letters
the map gives them under a named application. Built once per Automotive map build.
"""

from functools import lru_cache
from urllib.parse import urlencode

from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.services import automotive as au
from app.services import blocks
from app.services import systems as sy

FILE = PROJECT_ROOT / "data" / "business" / "car_areas.yaml"
SYSTEM = "automotive"
SHOWN = 6  # functions per letter before "+N more"
_CACHE: list[tuple[dict, list[dict]]] = []  # [(the map it was built from, the areas)]


@lru_cache
def config() -> dict:
    return yamlio.load(FILE.read_text()) or {}


def diagram_index(name: str) -> int | None:
    """The library diagram whose name starts with `name`."""
    return next((i for i, t in enumerate(blocks.templates()) if (t.get("name") or "").startswith(name)), None)


def _sub(idx) -> str:
    """The automotive sub-system that holds most of these library diagrams ('' when none does)."""
    return next((p["sub"] for p in sy.places(idx) if p["system"] == SYSTEM), "")


def _links(sub: str, app_id: str, template: int | None = None) -> dict:
    """Its block diagrams, Cross-sell for it (one diagram when given) and its card on the Automotive map."""
    pick = {"system": SYSTEM, **({"sub": sub} if sub else {})}
    xs = {**pick, **({"template": template} if template is not None else {})}
    return {"blocks": f"/blocks?{urlencode(pick)}", "cross_sell": f"/blocks/cross-sell?{urlencode(xs)}",
            "map": f"/business/automotive?view=apps#app-{app_id}",
            "sub_title": (sy.sub(SYSTEM, sub) or {}).get("title", "")}  # fmt: skip


def _chip(c: dict, on_map: bool) -> dict:
    """A function as the explorer shows it; it links to its cell on the map when the map has that cell."""
    return {"label": c["label"], "fn": c["fn"], "next": (c.get("next") or {}).get("level") or "",
            "accepted": c["status"] == "accepted",
            "href": f"/business/automotive?view=apps&cell={c['key']}#detail" if on_map else ""}  # fmt: skip


def _row(rid: str, label: str, n_diagrams: int, levels: dict, links: dict, on_map) -> dict:
    """One application: its letters in ladder order, the first SHOWN functions of each and the rest behind '+N more'."""
    rows = []
    for lv in au.LEVELS:
        chips = [_chip(c, on_map(c)) for c in levels.get(lv) or []]
        if chips:
            rows.append({"level": lv, "label": au.LEVEL_LABEL[lv], "n": len(chips), "shown": chips[:SHOWN],
                         "more": chips[SHOWN:]})  # fmt: skip
    return {"id": rid, "label": label, "n_diagrams": n_diagrams, "rows": rows, "links": links}


def _app_rows(m: dict) -> dict[str, dict]:
    subs = config().get("subs") or {}
    return {a["id"]: _row(a["id"], a["label"], len(a["car"]), au.by_level(m, a["id"], m["columns"]),
                          _links(subs.get(a["id"]) or _sub(a["idx"]), a["id"]), lambda c: True)
            for a in m["apps"]}  # fmt: skip


def _diagram_rows(session: Session, m: dict) -> dict[str, dict]:
    col = {f: i for i, f in enumerate(m["columns"])}
    out = {}
    for d in config().get("diagram_rows") or []:
        i, app = diagram_index(d["diagram"]), d["letters_from"]
        if i is None:  # the diagram was renamed or removed: tests/test_car_explorer.py says so
            continue
        cells = au.cells_for(session, app, blocks.template_functions(blocks.templates()[i]))
        order = sorted(cells, key=lambda f: (col.get(f, len(col)), cells[f]["label"].lower()))
        levels = au.by_level({"cells": {(app, f): cells[f] for f in order}}, app, order)
        out[d["id"]] = _row(d["id"], d["label"], 1, levels, _links(_sub([i]), app, i),
                            lambda c: (c["app"], c["fn"]) in m["cells"])  # fmt: skip
    return out


def areas(session: Session) -> list[dict]:
    """The car's areas in button order, each with its applications (letters, functions, counts, links)."""
    m = au.build(session)
    if _CACHE and _CACHE[0][0] is m:
        return _CACHE[0][1]
    rows = {**_app_rows(m), **_diagram_rows(session, m)}
    out = []
    for z in config().get("areas") or []:
        apps = [rows[i] for i in z.get("apps") or [] if i in rows]
        counts = {lv: sum(r["n"] for a in apps for r in a["rows"] if r["level"] == lv) for lv in au.LEVELS}
        out.append({"id": z["id"], "title": z["title"], "note": " ".join(str(z.get("note") or "").split()),
                    "apps": apps, "n_diagrams": sum(a["n_diagrams"] for a in apps), "counts": counts})  # fmt: skip
    _CACHE[:] = [(m, out)]
    return out
