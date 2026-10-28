"""Part knowledge › How it works (owner, 28 Oct 2026): one page per product group that explains the PART (what it does,
how it works inside, the key values, how to choose, what the application notes say) with the Skyworks and Qorvo parts
of the group from our data. Applications are only linked ("Used in"), never retold.

The content lives in data/library/how_it_works.yaml (layout at its top); this module loads it, builds the parts table
from the product index (active Skyworks / Qorvo parts only) and resolves the links."""

import re
from functools import lru_cache

from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT

FILE = PROJECT_ROOT / "data" / "library" / "how_it_works.yaml"
URL = "/reviews/how"
OURS = ("Skyworks", "Qorvo")
SECTIONS = ("what", "how", "specs", "choosing", "appnotes", "parts", "used_in", "sources")
NOT_IN_DATA = "not in our data"


@lru_cache(maxsize=2)
def _load(mtime: float) -> dict:
    return yamlio.load(FILE.read_text()) or {}


def groups() -> list[dict]:
    return list(_load(FILE.stat().st_mtime).get("groups") or [])


def knowledge_pages() -> list[dict]:
    """Engineering knowledge pages written with these groups (To confirm items)."""
    return list(_load(FILE.stat().st_mtime).get("knowledge_pages") or [])


def group(gid: str) -> dict | None:
    return next((g for g in groups() if g["id"] == gid), None)


def href(g: dict) -> str:
    return f"{URL}/{g['id']}"


def for_sub(sub: str, cat: str = "") -> list[dict]:
    """Groups to show as a card on the browse page of a subfamily (or of its category)."""
    if sub:
        return [g for g in groups() if sub in (g.get("subs") or [])]
    if cat:
        from app.services import products

        subs = set(products.taxonomy()["categories"].get(cat, {}).get("subs") or [])
        return [g for g in groups() if subs & set(g.get("subs") or [])]
    return []


def for_part(mpn: str, family: str = "") -> list[dict]:
    """Groups whose link shows on a part page: the part's family, or the part listed by name or series."""
    from app.partnumbers import normalize_pn

    n = normalize_pn(mpn)
    out = []
    for g in groups():
        named = {normalize_pn(p["mpn"]) for p in g.get("parts") or []}
        series = any(re.search(s["match"], mpn, re.I) for s in g.get("series") or [])
        if family in (g.get("families") or []) or n in named or series:
            out.append(g)
    return out


def for_review(slug: str) -> list[dict]:
    return [g for g in groups() if slug in (g.get("reviews") or [])]


def for_topic(key: str) -> list[dict]:
    return [g for g in groups() if any(u.get("topic") == key for u in g.get("used_in") or [])]


# ---- links ----------------------------------------------------------------------------------------------------------
def spec_link(note: str) -> dict | None:
    """'engineering:<key>' -> the Engineering notes page, 'rf:<id>' -> the RF fundamentals entry, '/path' -> as is."""
    if not note:
        return None
    from app.services import engineering, rf_notes

    kind, _, key = note.partition(":")
    if kind == "engineering" and key in engineering.NOTES:
        return {"href": f"/engineering/{key}", "title": engineering.NOTES[key][0]}
    if kind == "rf":
        t = next((t for t in rf_notes.topics() if t["id"] == key), None)
        return {"href": f"/rf-notes#{key}", "title": t["title"]} if t else None
    if note.startswith("/"):
        return {"href": note, "title": ""}
    return None


def _apps() -> list[dict]:
    from app.services import blocks

    return [*blocks.templates(), *blocks.background_templates()]


def used_in(g: dict) -> list[dict]:
    """The group's "Used in" links: application pages (by the start of the diagram name) and library topics."""
    from app.services import library

    apps, out = _apps(), []
    for u in g.get("used_in") or []:
        if u.get("href"):
            row = {"label": u["label"], "href": u["href"], "kind": "Research report"}
        elif u.get("topic"):
            ok = library.topic(u["topic"]) is not None
            row = {"label": u["label"], "href": f"/library/{u['topic']}" if ok else "", "kind": "Systems library"}
        else:
            i = next((i for i, t in enumerate(apps) if t["name"].startswith(u["app"])), None)
            row = {"label": u["label"], "href": f"/business/applications/{i}" if i is not None else "",
                   "kind": "Application"}  # fmt: skip
        # optional: the area the case belongs to (groups the list) and the public source that shows UWB used there
        # status "emerging" (owner, 28 Oct 2026: "Do 'emerging'"): evaluation, research or proposal stage, with a why
        out.append({**row, "area": u.get("area", ""), "src": u.get("src", ""), "src_url": u.get("src_url", ""),
                    "emerging": u.get("status") == "emerging", "why": u.get("why", "")})  # fmt: skip
    return out


def used_in_areas(g: dict) -> list[tuple[str, list[dict]]]:
    """The "Used in" links grouped by area, in the order the areas first appear (one unnamed group if none)."""
    areas: dict[str, list[dict]] = {}
    for u in used_in(g):
        areas.setdefault(u["area"], []).append(u)
    return list(areas.items())


def app_emerging(i: int) -> str:
    """The "why emerging" line of an application diagram (templates + background, as indexed on the pages), or ""."""
    apps = _apps()
    return str(apps[i].get("emerging") or "") if 0 <= i < len(apps) else ""


def seen_in(g: dict) -> dict | None:
    """How many public block diagrams / reference designs (data/reference_designs) contain the group's functions:
    {n: designs with any of them, fns: [{fn, label, n, href}]}; None when the group names no functions."""
    fns = g.get("seen_in") or []
    if not fns:
        return None
    from app.services import blocks, refmatch

    by_fn = refmatch.index()["by_fn"]
    cat = blocks.catalogue()["functions"]
    keys = {k for f in fns for k in by_fn.get(f, ())}
    rows = [{"fn": f, "label": (cat.get(f) or {}).get("label", f), "n": len(by_fn.get(f, ())),
             "href": f"/reference-designs?fn={f}"} for f in fns]  # fmt: skip
    return {"n": len(keys), "fns": rows}


def reviews_of(g: dict) -> list[dict]:
    from app.services import reviews as rv

    return [r for s in g.get("reviews") or [] if (r := rv.get(s))]


# ---- the parts table ------------------------------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _key_specs() -> dict[tuple[str, str], dict]:
    from app.partnumbers import normalize_pn
    from app.services import blocks

    return {(r["manufacturer"], normalize_pn(r["mpn"])): r.get("key_specs") or {} for r in blocks.catalog_rows()}


def _fmt(v) -> str:
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _spec(ks: dict, keys: list[str]) -> str:
    return next((_fmt(ks[k]) for k in keys if str(ks.get(k) if ks.get(k) is not None else "").strip()), "")


def _natural(v: str) -> tuple:
    m = re.match(r"[-±]?\d+(\.\d+)?", v)
    return (0, float(m.group(0).replace("±", ""))) if m else (1, v)


def _params(session: Session, ids: set[int]) -> dict[int, dict]:
    """BizDev parameters of the parts with full data, as {part id: {"param:<key>": value}}."""
    from sqlalchemy import select

    from app.models import ParamValue

    out: dict[int, dict] = {}
    for pv in session.scalars(select(ParamValue).where(ParamValue.part_id.in_(ids))):
        out.setdefault(pv.part_id, {})[f"param:{pv.key}"] = pv.value
    return out


AUTO = {"automotive": "Yes", "not_automotive": "No", "unknown": "not stated"}


def _row_link(r: dict) -> dict:
    if r.get("part_id"):
        return {"href": f"/parts/{r['part_id']}", "external": False}
    return {"href": r.get("url") or "", "external": bool(r.get("url"))}


def parts_table(session: Session, g: dict) -> dict:
    """Rows: one per active Skyworks / Qorvo part of the group's table subfamilies and listed parts, and one per
    series (many orderable variants). Every value comes from our data; a missing one says so."""
    from app.partnumbers import normalize_pn
    from app.services import products

    cols = [c["label"] for c in g.get("columns") or []]
    keys = {c["label"]: c.get("keys") or [] for c in g.get("columns") or []}
    excl = {normalize_pn(x["mpn"]) for x in g.get("exclude") or []}
    listed = {normalize_pn(p["mpn"]): p for p in g.get("parts") or []}
    index = [r for r in products.index(session) if r["manufacturer"] in OURS]
    by_pn = {}
    for r in index:
        by_pn.setdefault(normalize_pn(r["mpn"]), r)
    ks = _key_specs()
    params = _params(session, {r["part_id"] for r in index if r.get("part_id")}) if any(
        k.startswith("param:") for v in keys.values() for k in v) else {}  # fmt: skip

    def spec_of(r: dict) -> dict:
        return {**(ks.get((r["manufacturer"], normalize_pn(r["mpn"]))) or {}), **params.get(r.get("part_id"), {})}

    def values(r: dict, own: dict | None) -> dict:
        spec = spec_of(r)
        return {c: (own or {}).get("specs", {}).get(c) or _spec(spec, keys[c]) or NOT_IN_DATA for c in cols}

    rows, missing = [], []
    table_subs = set(g.get("table_subs") or [])
    series = g.get("series") or []
    in_series = [re.compile(s["match"], re.I) for s in series]
    picked = [r for r in index if r["sub"] in table_subs and r["lifecycle"] == "active"
              and normalize_pn(r["mpn"]) not in excl and not any(x.search(r["mpn"]) for x in in_series)]  # fmt: skip
    seen = {normalize_pn(r["mpn"]) for r in picked}
    for pn, p in listed.items():
        r = by_pn.get(pn)
        if r is None or r["lifecycle"] != "active":
            missing.append(p["mpn"])
        elif pn not in seen:
            picked.append(r)
            seen.add(pn)
    for r in picked:
        own = listed.get(normalize_pn(r["mpn"]))
        rows.append({"mpn": r["mpn"], "maker": r["manufacturer"], "role": (own or {}).get("role") or g.get("role", ""),
                     "values": values(r, own), "package": r.get("package") or NOT_IN_DATA,
                     "automotive": AUTO.get(r["qualification"], "not stated"), "variants": 0,
                     **_row_link(r)})  # fmt: skip
    rows.sort(key=lambda x: (x["role"], x["maker"], x["mpn"]))
    srows = []
    for s, rx in zip(series, in_series, strict=True):
        hits = [r for r in index if rx.search(r["mpn"]) and r["lifecycle"] == "active"
                and (not s.get("sub") or r["sub"] == s["sub"])]  # fmt: skip
        if not hits:
            missing.append(s["id"])
            continue
        vals = {}
        for c in cols:
            seen_v = sorted(dict.fromkeys(v for r in hits if (v := _spec(spec_of(r), keys[c]))), key=_natural)
            vals[c] = (s.get("specs") or {}).get(c) or (", ".join(seen_v[:4]) + (" …" if len(seen_v) > 4 else "")
                                                         if seen_v else NOT_IN_DATA)  # fmt: skip
        n_auto = sum(r["qualification"] == "automotive" for r in hits)
        pk = list(dict.fromkeys(r.get("package") or "" for r in hits if r.get("package")))
        example = next((r for r in hits if r.get("part_id")), hits[0])
        srows.append({"mpn": s["id"], "label": s.get("label", s["id"]), "maker": hits[0]["manufacturer"],
                      "role": s.get("role", ""), "values": vals, "note": s.get("note", ""),
                      "package": ", ".join(pk[:3]) + (" …" if len(pk) > 3 else "") if pk else NOT_IN_DATA,
                      "automotive": f"{n_auto} of {len(hits)}" if n_auto else "not stated", "variants": len(hits),
                      "browse": f"/parts?q={s.get('q', s['id'].rstrip('x'))}", "example": example["mpn"],
                      **_row_link(example)})  # fmt: skip
    return {"columns": cols, "rows": rows, "series": srows, "missing": missing}


# ---- checks (tests) -------------------------------------------------------------------------------------------------
def _function_ids() -> set[str]:
    from app.services import blocks

    return set(blocks.catalogue()["functions"])


def problems() -> list[str]:
    """Keys that point nowhere or sections that are empty."""
    from app.services import products
    from app.services import reviews as rv

    bad, subs = [], products.taxonomy()["subs"]
    for g in groups():
        gid = g.get("id", "?")
        for k in ("id", "title", "link", "gist", "what", "how", "specs", "choosing", "appnotes", "sources", "used_in"):
            if not g.get(k):
                bad.append(f"{gid}: no {k}")
        bad += [f"{gid}: unknown sub {s}" for s in [*(g.get("subs") or []), *(g.get("table_subs") or [])]
                if s not in subs]  # fmt: skip
        bad += [f"{gid}: spec link {s['note']}" for s in g.get("specs") or []
                if s.get("note") and not spec_link(s["note"])]  # fmt: skip
        bad += [f"{gid}: review {s}" for s in g.get("reviews") or [] if rv.get(s) is None]
        bad += [f"{gid}: used in {u['label']}" for u in used_in(g) if not u["href"]]
        bad += [f"{gid}: used-in source {u['label']}" for u in used_in(g)
                if u["src"] and not (u["src_url"].startswith("https://") or u["src_url"].startswith("/"))]  # fmt: skip
        bad += [f"{gid}: emerging without source or why {u['label']}" for u in used_in(g)
                if u["emerging"] and not (u["src_url"] and u["why"])]  # fmt: skip
        cat = _function_ids()
        bad += [f"{gid}: seen_in function {f}" for f in g.get("seen_in") or [] if f not in cat]
        bad += [f"{gid}: app note without ref/page/url {a.get('text', '')[:40]}" for a in g.get("appnotes") or []
                if not (a.get("ref") and a.get("page") and a.get("url"))]  # fmt: skip
        if len((g.get("gist") or "").split()) > 25:
            bad.append(f"{gid}: gist over 25 words")
    return bad
