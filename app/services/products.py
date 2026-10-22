"""One product index for Products > Browse: the manufacturer catalogues (public product pages) and the BizDev
families (parts with full parameters and crosses), classified by one functional taxonomy (data/taxonomy.yaml).

A part has one canonical identity (manufacturer + normalised part number). When it exists in both sources it is
shown once, with the capabilities of both. Capabilities say what BizDev can do with a record, so a catalogue-only
record is never presented as if it supported a validated comparison:
  catalogue   listed in the manufacturer's public catalogue
  detailed    full parameters in BizDev
  crosses     cross-reference supported (a matching-rules family)
  pinout      pin functions available
  source      a product page or datasheet link
Qualification has three states: automotive (stated AEC-Q100), not_automotive (stated industrial / commercial or
stated "no"), unknown (not stated).
"""

import re
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.matching.rules import load_all_rules
from app.models import Part
from app.partnumbers import normalize_pn
from app.services import blocks, lifecycle, text, vocab

TAXONOMY = Path(__file__).resolve().parents[2] / "data" / "taxonomy.yaml"
UNCLASSIFIED = ("unclassified", "unclassified")
CAPABILITIES = {
    "detailed": "Detailed parameters",
    "crosses": "Cross-reference supported",
    "pinout": "Pinout available",
    "catalogue": "Catalogue record",
    "source": "Source link",
}


@lru_cache
def taxonomy() -> dict:
    data = yamlio.load(TAXONOMY.read_text())
    cats, subs, rules, fam, fns = {}, {}, [], {}, {}
    for c in data["categories"]:
        cats[c["id"]] = {"label": c["label"], "subs": [s["id"] for s in c["subfamilies"]]}
        for s in c["subfamilies"]:
            subs[s["id"]] = {"label": s["label"], "category": c["id"]}
            for f in s.get("families") or []:
                fam[f] = fns[f] = s["id"]  # a BizDev family id is also the function id of its catalogue parts
            for f in s.get("functions") or []:
                fns[f] = s["id"]
            for m in s.get("catalog") or []:
                rx = re.compile(m["sub"], re.I) if m.get("sub") else None
                rules.append((m["category"], rx, c["id"], s["id"]))
    cats["unclassified"] = {"label": "Unclassified", "subs": ["unclassified"]}
    subs["unclassified"] = {"label": "Unclassified (see source category)", "category": "unclassified"}
    return {"categories": cats, "subs": subs, "rules": rules, "families": fam, "functions": fns}


def classify(category: str, sub: str, function: str | None = None) -> tuple[str, str]:
    """The part's own function first (a catalogue may file an LNA only under "Amplifiers"), then the catalogue
    category and sub-category."""
    t = taxonomy()
    sid = t["functions"].get(vocab.canonical(function) or "")
    if sid:
        return t["subs"][sid]["category"], sid
    for cat, rx, cid, sid in t["rules"]:
        if cat == category and (rx is None or rx.search(sub or "")):
            return cid, sid
    return UNCLASSIFIED


@lru_cache
def _catalogue_index() -> dict[tuple[str, str], dict]:
    out = {}
    for r in blocks.catalog_rows():
        cid, sid = classify(r["category"], r["sub"], r.get("function"))
        auto = r.get("automotive")
        out[(r["manufacturer"], blocks._norm_mpn(r["mpn"]))] = {
            "mpn": r["mpn"],
            "manufacturer": r["manufacturer"],
            "description": text.clean_description(r["description"], r["mpn"]),
            "summary": text.short_description(
                r.get("function"),
                r["package"],
                "automotive" if auto else None,
                specs=r["key_specs"],
                description=r["description"],
            ),  # fmt: skip
            "package": r["package"],
            "category": cid,
            "sub": sid,
            "source_category": r["category"],
            "source_sub": r["sub"],
            "lifecycle": lifecycle.status_class(r["status"]),
            "status_text": r["status"],
            "qualification": "automotive" if auto is True else "not_automotive" if auto is False else "unknown",
            "url": r["url"],
            "datasheet": r.get("datasheet") or "",
            "part_id": None,
            "role": "reference",
            "caps": {"catalogue", *(["source"] if r["url"] or r.get("datasheet") else [])},
        }
    return out


def search_catalogue(q: str, exclude: set[str] | None = None, limit: int = 200) -> list[dict]:
    """Manufacturer-catalogue records (Skyworks, Qorvo) whose part number contains the query; part numbers that start
    with it first. `exclude` holds normalised part numbers already found among the parts with full data."""
    qn = normalize_pn(q)
    if len(qn) < 2:
        return []
    exclude = exclude or set()
    hits = [
        r
        for (_, k), r in _catalogue_index().items()
        if qn in normalize_pn(r["mpn"]) and normalize_pn(r["mpn"]) not in exclude
    ]
    hits.sort(key=lambda r: (not normalize_pn(r["mpn"]).startswith(qn), len(r["mpn"]), r["mpn"]))
    return hits[:limit]


_INDEX: dict = {}


def index(session: Session) -> list[dict]:
    """Every product once: catalogue records, merged with BizDev parts of the same identity. Built once per data
    version (it reads every part with its parameters); callers only read the rows."""
    v = blocks._data_version(session)
    if v not in _INDEX:
        _INDEX.clear()
        _INDEX[v] = _index_uncached(session)
    return _INDEX[v]


def _index_uncached(session: Session) -> list[dict]:
    rows = {k: {**v, "caps": set(v["caps"])} for k, v in _catalogue_index().items()}
    rules = load_all_rules()
    fam_sub = taxonomy()["families"]
    for p in session.scalars(select(Part)).unique():
        key = (p.manufacturer.name, blocks._norm_mpn(p.mpn))
        q = next((pv.value for pv in p.params if pv.key == "qualification"), None)
        qual = (
            "automotive" if q == "automotive" else "not_automotive" if q in ("industrial", "commercial") else "unknown"
        )
        params = {pv.key: pv.value for pv in p.params}
        package = p.package.code if p.package else ""
        summary = text.short_description(p.family, package, qual, params=params)
        # a family holding several functions (timing) is classified by the part's own function
        sid = fam_sub.get(p.family) or taxonomy()["functions"].get(str(params.get("function_type") or ""))
        cid = taxonomy()["subs"][sid]["category"] if sid else UNCLASSIFIED[0]
        caps = {
            "detailed",
            *(["crosses"] if p.family in rules else []),
            *(["pinout"] if p.pinout else []),
            *(["source"] if p.datasheet_url or p.product_url else []),
        }
        e = rows.get(key)
        if e:  # same part in the catalogue: one identity, BizDev detail page, catalogue metadata kept
            e.update(part_id=p.id, caps=e["caps"] | caps, role=p.manufacturer.role.value)
            # the datasheet value is per orderable part number; the catalogue's flag is often per series, so the
            # BizDev value wins whenever it is stated (e.g. SI8600AB-IS is industrial in an AEC-Q100 series)
            if qual != "unknown":
                e["catalogue_qualification"] = e["qualification"]
                e["qualification"] = qual
            # the cross lists record the lifecycle per orderable part from its data sheet or notice; the catalogue
            # page can lag (SI8420BD-IS still "Active" there), so a stated BizDev lifecycle wins too
            life = lifecycle.status_class(p.lifecycle_status.value)
            if life != "unknown":
                e.update(lifecycle=life, status_text=p.lifecycle_status.value.replace("_", " "))
            if e["category"] == UNCLASSIFIED[0] and sid:
                e.update(category=cid, sub=sid)
            e["summary"] = summary  # typed BizDev parameters say more than the catalogue's key specs
        else:
            rows[key] = {
                "mpn": p.mpn,
                "manufacturer": p.manufacturer.name,
                "description": text.clean_description(p.description, p.mpn),
                "summary": summary,
                "package": package,
                "category": cid,
                "sub": sid or UNCLASSIFIED[1],
                "source_category": "BizDev family",
                "source_sub": rules[p.family].title if p.family in rules else p.family,
                "lifecycle": lifecycle.status_class(p.lifecycle_status.value),
                "status_text": p.lifecycle_status.value,
                "qualification": qual,
                "url": p.product_url or p.datasheet_url or "",
                "part_id": p.id,
                "role": p.manufacturer.role.value,
                "caps": caps,
            }
    out = list(rows.values())
    for r in out:
        r["search"] = text.search_key(r["description"], r["summary"])
    return out


def browse(
    session: Session,
    q: str = "",
    cat: str = "",
    sub: str = "",
    company: str = "",
    qual: str = "",
    life: str = "",
    cap: str = "",
    role: str = "",
) -> dict:
    """Filter the index; facet counts are computed with every other active filter applied."""
    allrows = index(session)
    ql = q.strip().lower()
    qn = re.sub(r"[^a-z0-9]", "", ql)
    qk = text.search_key(q.strip())

    def ok(r, skip=""):
        if ql and not (qn and qn in re.sub(r"[^a-z0-9]", "", r["mpn"].lower()) or qk in r.get("search", "")):
            return False
        checks = {
            "cat": (cat, r["category"]),
            "sub": (sub, r["sub"]),
            "company": (company, r["manufacturer"]),
            "qual": (qual, r["qualification"]),
            "life": (life, r["lifecycle"]),
            "role": (role, r["role"]),
        }
        if any(want and k != skip and want != have for k, (want, have) in checks.items()):
            return False
        return not (cap and skip != "cap" and cap not in r["caps"])

    def facet(name, key):
        counts: dict[str, int] = {}
        for r in allrows:
            if ok(r, skip=name):
                v = r[key]
                for x in v if isinstance(v, set) else [v]:
                    counts[x] = counts.get(x, 0) + 1
        return counts

    hits = [r for r in allrows if ok(r)]
    hits.sort(
        key=lambda r: (
            not (ql and r["mpn"].lower().startswith(ql)),
            r["part_id"] is None,
            r["lifecycle"] != "active",
            r["mpn"],
        )
    )
    return {
        "rows": hits,
        "total": len(hits),
        "all": len(allrows),
        "facets": {
            "cat": facet("cat", "category"),
            "sub": facet("sub", "sub"),
            "company": facet("company", "manufacturer"),
            "qual": facet("qual", "qualification"),
            "life": facet("life", "lifecycle"),
            "cap": facet("cap", "caps"),
            "role": facet("role", "role"),
        },
    }
