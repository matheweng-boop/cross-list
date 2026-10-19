"""One product index for Products > Browse: the manufacturer catalogues (public product pages) and the Cross List
families (parts with full parameters and crosses), classified by one functional taxonomy (data/taxonomy.yaml).

A part has one canonical identity (manufacturer + normalised part number). When it exists in both sources it is
shown once, with the capabilities of both. Capabilities say what Cross List can do with a record, so a catalogue-only
record is never presented as if it supported a validated comparison:
  catalogue   listed in the manufacturer's public catalogue
  detailed    full parameters in Cross List
  crosses     cross-reference supported (a matching-rules family)
  pinout      pin functions available
  source      a product page or datasheet link
Qualification has three states: automotive (stated AEC-Q100), not_automotive (stated industrial / commercial or
stated "no"), unknown (not stated).
"""

import re
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.matching.rules import load_all_rules
from app.models import Part
from app.services import blocks

TAXONOMY = Path(__file__).resolve().parents[2] / "data" / "taxonomy.yaml"
UNCLASSIFIED = ("unclassified", "unclassified")
QUAL_LABEL = {"automotive": "Automotive (AEC-Q100)", "not_automotive": "Not automotive", "unknown": "Not stated"}
CAPABILITIES = {
    "detailed": "Detailed parameters",
    "crosses": "Cross-reference supported",
    "pinout": "Pinout available",
    "catalogue": "Catalogue record",
    "source": "Source link",
}


@lru_cache
def taxonomy() -> dict:
    data = yaml.safe_load(TAXONOMY.read_text())
    cats, subs, rules, fam = {}, {}, [], {}
    for c in data["categories"]:
        cats[c["id"]] = {"label": c["label"], "subs": [s["id"] for s in c["subfamilies"]]}
        for s in c["subfamilies"]:
            subs[s["id"]] = {"label": s["label"], "category": c["id"]}
            for f in s.get("families") or []:
                fam[f] = s["id"]
            for m in s.get("catalog") or []:
                rx = re.compile(m["sub"], re.I) if m.get("sub") else None
                rules.append((m["category"], rx, c["id"], s["id"]))
    cats["unclassified"] = {"label": "Unclassified", "subs": ["unclassified"]}
    subs["unclassified"] = {"label": "Unclassified (see source category)", "category": "unclassified"}
    return {"categories": cats, "subs": subs, "rules": rules, "families": fam}


def classify(category: str, sub: str) -> tuple[str, str]:
    for cat, rx, cid, sid in taxonomy()["rules"]:
        if cat == category and (rx is None or rx.search(sub or "")):
            return cid, sid
    return UNCLASSIFIED


def _lifecycle(status: str) -> str:
    s = (status or "").lower()
    if re.search(r"obsolete|discontinu|end of life|eol", s):
        return "obsolete"
    if re.search(r"nrnd|not recommended|last time", s):
        return "nrnd"
    if "preview" in s or "sampling" in s or "pre-release" in s:
        return "preview"
    if s in ("active", "standard", "production", "released", "new"):
        return "active"
    return "unknown"


@lru_cache
def _catalogue_index() -> dict[tuple[str, str], dict]:
    out = {}
    for r in blocks.catalog_rows():
        cid, sid = classify(r["category"], r["sub"])
        auto = r.get("automotive")
        out[(r["manufacturer"], blocks._norm_mpn(r["mpn"]))] = {
            "mpn": r["mpn"],
            "manufacturer": r["manufacturer"],
            "description": r["description"],
            "package": r["package"],
            "category": cid,
            "sub": sid,
            "source_category": r["category"],
            "source_sub": r["sub"],
            "lifecycle": _lifecycle(r["status"]),
            "status_text": r["status"],
            "qualification": "automotive" if auto is True else "not_automotive" if auto is False else "unknown",
            "url": r["url"],
            "part_id": None,
            "role": "reference",
            "caps": {"catalogue", *(["source"] if r["url"] or r.get("datasheet") else [])},
        }
    return out


def index(session: Session) -> list[dict]:
    """Every product once: catalogue records, merged with Cross List parts of the same identity."""
    rows = {k: {**v, "caps": set(v["caps"])} for k, v in _catalogue_index().items()}
    rules = load_all_rules()
    fam_sub = taxonomy()["families"]
    for p in session.scalars(select(Part)).unique():
        key = (p.manufacturer.name, blocks._norm_mpn(p.mpn))
        q = next((pv.value for pv in p.params if pv.key == "qualification"), None)
        qual = (
            "automotive" if q == "automotive" else "not_automotive" if q in ("industrial", "commercial") else "unknown"
        )
        sid = fam_sub.get(p.family)
        cid = taxonomy()["subs"][sid]["category"] if sid else UNCLASSIFIED[0]
        caps = {
            "detailed",
            *(["crosses"] if p.family in rules else []),
            *(["pinout"] if p.pinout else []),
            *(["source"] if p.datasheet_url or p.product_url else []),
        }
        e = rows.get(key)
        if e:  # same part in the catalogue: one identity, Cross List detail page, catalogue metadata kept
            e.update(part_id=p.id, caps=e["caps"] | caps, role=p.manufacturer.role.value)
            # the datasheet value is per orderable part number; the catalogue's flag is often per series, so the
            # Cross List value wins whenever it is stated (e.g. SI8600AB-IS is industrial in an AEC-Q100 series)
            if qual != "unknown":
                e["catalogue_qualification"] = e["qualification"]
                e["qualification"] = qual
            if e["category"] == UNCLASSIFIED[0] and sid:
                e.update(category=cid, sub=sid)
        else:
            rows[key] = {
                "mpn": p.mpn,
                "manufacturer": p.manufacturer.name,
                "description": p.description or "",
                "package": p.package.code if p.package else "",
                "category": cid,
                "sub": sid or UNCLASSIFIED[1],
                "source_category": "Cross List family",
                "source_sub": rules[p.family].title if p.family in rules else p.family,
                "lifecycle": {"last_time_buy": "nrnd"}.get(p.lifecycle_status.value, p.lifecycle_status.value),
                "status_text": p.lifecycle_status.value,
                "qualification": qual,
                "url": p.product_url or p.datasheet_url or "",
                "part_id": p.id,
                "role": p.manufacturer.role.value,
                "caps": caps,
            }
    return list(rows.values())


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

    def ok(r, skip=""):
        if ql and not (qn and qn in re.sub(r"[^a-z0-9]", "", r["mpn"].lower()) or ql in r["description"].lower()):
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
