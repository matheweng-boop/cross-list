"""Systems and sub-systems (owner, 23 and 25 Oct 2026): Automotive, Data center, Drones, Cellular, Industrial & energy,
Aerospace & defense, Consumer & wearables, Home & building and Medical, each made of
sub-systems such as "UWB in the car" or "Car radio". The Systems library shows them as headers with their
sub-systems; the Application library groups its diagrams by them; Cross-sell works on a selected system or
sub-system. The assignment lives in data/blocks/systems.yaml; diagrams it does not list sit under "Other"."""

from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT
from app.services import blocks

FILE = PROJECT_ROOT / "data" / "blocks" / "systems.yaml"
OTHER = "other"


@lru_cache
def systems() -> tuple[dict, ...]:
    """The systems in page order, each with its sub-systems; `diagrams` resolved to template indexes (`idx`)."""
    data = yamlio.load(FILE.read_text()) or {}
    index = {t.get("name"): i for i, t in enumerate(blocks.templates())}
    out = []
    for s in data.get("systems") or []:
        subs = []
        for sub in s.get("subsystems") or []:
            elements = [e if isinstance(e, str) else e.get("name", "") for e in sub.get("elements") or []]
            idx = [index[n] for n in sub.get("diagrams") or [] if n in index]
            subs.append({**sub, "elements": elements, "idx": idx, "topics": list(sub.get("topics") or []),
                         "links": [tuple(x) for x in sub.get("links") or []]})  # fmt: skip
        out.append({**s, "subsystems": subs})
    return tuple(out)


def unknown_diagrams() -> list[str]:
    """Names in systems.yaml that match no library diagram (a renamed or removed diagram)."""
    data = yamlio.load(FILE.read_text()) or {}
    names = {t.get("name") for t in blocks.templates()}
    return [n for s in data.get("systems") or [] for sub in s.get("subsystems") or []
            for n in sub.get("diagrams") or [] if n not in names]  # fmt: skip


def get(key: str) -> dict | None:
    return next((s for s in systems() if s["key"] == key), None)


def sub(system: str, key: str) -> dict | None:
    s = get(system)
    return next((x for x in s["subsystems"] if x["key"] == key), None) if s else None


def assigned() -> set[int]:
    return {i for s in systems() for x in s["subsystems"] for i in x["idx"]}


def unassigned() -> list[int]:
    """Library diagrams in no sub-system: shown under Other, by their category."""
    done = assigned()
    return [i for i in range(len(blocks.templates())) if i not in done]


def place_of(i: int) -> list[tuple[str, str]]:
    """(system, sub-system) keys a library diagram sits in; [("other", category)] when it is in none."""
    out = [(s["key"], x["key"]) for s in systems() for x in s["subsystems"] if i in x["idx"]]
    return out or [(OTHER, blocks.templates()[i].get("category") or "Other")]


def topic_place(key: str) -> tuple[str, str] | None:
    return next(((s["key"], x["key"]) for s in systems() for x in s["subsystems"] if key in x["topics"]), None)


def selection(system: str, subsystem: str = "", template: int | None = None) -> dict:
    """What a person picked in the Application library: the library diagram indexes it covers and a label."""
    lib = blocks.templates()
    if template is not None and 0 <= template < len(lib):
        return {"idx": [template], "label": blocks.display_name(lib[template]), "level": "application"}
    x = sub(system, subsystem)
    if x:
        return {"idx": list(x["idx"]), "label": f"{get(system)['title']} › {x['title']}", "level": "subsystem"}
    s = get(system)
    if s:
        idx = sorted({i for x in s["subsystems"] for i in x["idx"]})
        return {"idx": idx, "label": s["title"], "level": "system"}
    return {"idx": [], "label": "", "level": ""}


def bottom_up(session, idx: list[int], mine: frozenset, n_parts: int = 12) -> dict:
    """Cross-sell inside a selection, bottom up: the functions we have parts for in its diagrams (most used first,
    with our best parts named), the pairs of our functions that meet most often, and how many functions are still
    gaps (those are listed under Opportunities). Modeled from the reference diagrams, not from sales."""
    from app.services import opportunity as op

    keep = set(idx)
    apps = [a for a in op.with_status(op.applications(), op.makers(session), mine) if not a.background and a.i in keep]
    used: dict[str, dict] = {}
    for a in apps:
        for p in a.positions:
            if p.status not in op.IN_SCOPE:
                continue
            e = used.setdefault(p.fn, {"fn": p.fn, "label": p.label, "status": p.status, "apps": set(), "qty": 0})
            e["apps"].add(a.i)
            e["qty"] += p.qty
    rows = sorted(used.values(), key=lambda e: (-len(e["apps"]), e["label"]))
    ours = [e for e in rows if e["status"] == "supported"]
    for k, e in enumerate(ours):
        e["n_apps"] = len(e["apps"])
        e["parts"] = []
        if k < n_parts:
            for m in blocks.parts_for(session, e["fn"])["manufacturers"]:
                if m["manufacturer"] in mine:
                    e["parts"] += [{"mpn": p["mpn"], "url": p["url"], "manufacturer": m["manufacturer"]}
                                   for p in m["best"]]  # fmt: skip
            e["parts"] = e["parts"][:4]
    pairs = op.cross_sell_pairs(apps, limit=10)
    return {"apps": apps, "ours": ours, "pairs": pairs, "n_gaps": sum(e["status"] != "supported" for e in rows),
            "n_in_scope": len(rows)}  # fmt: skip


LINES = ("Skyworks", "Qorvo")


def parts_table(session, ours: list[dict], mine: frozenset, aec_only: bool = False, per_line: int = 2) -> dict:
    """The "Skyworks and Qorvo parts here" table (owner, 25 Oct 2026): one group per function of the selection we
    have parts for (most used first), a cell per line with its best parts, each marked AEC-Q or not automotive
    (autograde.is_aec). Under "Automotive-qualified only" a cell shows the line's best AEC-Q parts instead, and
    `hidden` counts the non-automotive parts that the filter takes off the table (never removed silently)."""
    from app.services import autograde

    lines = [m for m in LINES if m in mine]
    rows, hidden = [], 0
    count = {m: 0 for m in lines}
    fns = {m: 0 for m in lines}
    for e in ours:
        by = {m["manufacturer"]: m for m in blocks.parts_for(session, e["fn"], top=per_line)["manufacturers"]}
        cells = {}
        for m in lines:
            g = by.get(m)
            if not g:
                cells[m] = []
                continue
            shown, h = autograde.marked(g["best"], aec_only)
            if aec_only:  # the line's best qualified parts, one per series, not only those among the unfiltered best
                seen, shown = set(), []
                for p in g["all"]:
                    if len(shown) < per_line and blocks._series(p["mpn"]) not in seen and autograde.is_aec(p):
                        seen.add(blocks._series(p["mpn"]))
                        shown.append({**p, "aec": True})
            cells[m], hidden = shown, hidden + h
            count[m] += len(shown)
            fns[m] += bool(shown)
        rows.append({"fn": e["fn"], "label": e["label"], "n_apps": len(e["apps"]), "cells": cells,
                     "pairs": {m: [] for m in lines}})  # fmt: skip
    return {"lines": lines, "rows": rows, "count": count, "fns": fns, "hidden": hidden, "aec_only": aec_only}


def places(idx) -> list[dict]:
    """The sub-systems a set of library diagrams sits in, most diagrams first: system and sub-system keys and titles
    and how many of the diagrams are in each (for links from a pair or a function to Cross-sell › By system)."""
    keep = set(idx)
    out = [{"system": s["key"], "sub": x["key"], "title": x["title"], "system_title": s["title"],
            "n": len(keep.intersection(x["idx"]))} for s in systems() for x in s["subsystems"]]  # fmt: skip
    return sorted((p for p in out if p["n"]), key=lambda p: -p["n"])


def places_of_function(fn: str) -> list[dict]:
    """The sub-systems whose diagrams use a function (Cross-sell › By part: from a part to its systems)."""
    from app.services import opportunity as op

    return places(a.i for a in op.applications() if not a.background and any(p.fn == fn for p in a.positions))
