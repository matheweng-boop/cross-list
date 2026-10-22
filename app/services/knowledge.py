"""General knowledge by product, and the "why it matters to the customer" points on each specification guide
(owner, 22 Oct 2026). Content in data/knowledge_by_product.yaml; this module resolves its keys to titles and links."""

import re
from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT
from app.services import engineering
from app.services import library as lib

FILE = PROJECT_ROOT / "data" / "knowledge_by_product.yaml"
KINDS = {"cost": "Cost", "bom": "BOM", "robust": "Robustness", "design": "Design"}
# guides whose box also shows a related topic's points (CTI is explained inside the creepage guide)
EXTRA = {"creepage_mm": [("cti", "Material group (CTI)")]}


@lru_cache
def data() -> dict:
    return yamlio.load(FILE.read_text()) or {}


def why(key: str) -> list[dict]:
    """The customer points for one guide: its own, then those of related topics, each with its heading."""
    w = data().get("why_it_matters") or {}
    out = [{"heading": "", "points": w.get(key) or []}]
    out += [{"heading": h, "points": w.get(k) or []} for k, h in EXTRA.get(key, [])]
    return [g for g in out if g["points"]]


def _rf_titles() -> dict[str, str]:
    from app.services import rf_notes

    return {t["id"]: t["title"] for _, _, items in rf_notes.by_category() for t in items}


def _reviews_for(words: list[str]) -> list[dict]:
    from app.services import reviews

    if not words:
        return []
    pat = re.compile("|".join(re.escape(w) for w in words), re.I)
    return [{"title": r["title"], "href": f"/reviews/{r['slug']}"} for r in reviews.all_reviews()
            if pat.search(" ".join(str(r.get(k) or "") for k in ("title", "family", "app_area")))]  # fmt: skip


def by_product() -> list[dict]:
    """Each product family with its guides, visuals, RF notes, library topics and technology reviews resolved to
    links, and its top customer points (from the guides listed under `why`)."""
    rf = _rf_titles()
    topics = {t["key"]: t["title"] for t in lib.topics()}
    out = []
    for p in data().get("products") or []:
        guides = [{"title": engineering.NOTES[k][0], "summary": engineering.NOTES[k][1], "href": f"/engineering/{k}"}
                  for k in p.get("guides") or [] if k in engineering.NOTES]  # fmt: skip
        w = data().get("why_it_matters") or {}
        points = [{**pt, "guide": engineering.NOTES[k][0], "href": f"/engineering/{k}"}
                  for k in p.get("why") or [] for pt in w.get(k, [])[:1]]  # fmt: skip
        out.append({
            "key": p["key"], "title": p["title"], "line": p.get("line") or "", "pitch": p.get("pitch") or "",
            "points": points, "guides": guides,
            "visuals": [{"title": lib.VISUALS[v][0], "href": lib.VISUALS[v][1]} for v in p.get("visuals") or []
                        if v in lib.VISUALS],
            "rf_notes": [{"title": rf[n], "href": f"/rf-notes#{n}"} for n in p.get("rf_notes") or [] if n in rf],
            "topics": [{"title": topics[t], "href": f"/library/{t}"} for t in p.get("topics") or [] if t in topics],
            "reviews": _reviews_for(p.get("review_words") or []),
        })  # fmt: skip
    return out


def problems() -> list[str]:
    """Keys in the data file that point nowhere (checked by the tests)."""
    rf, topics = _rf_titles(), {t["key"] for t in lib.topics()}
    bad = [f"why_it_matters: {k}" for k in data().get("why_it_matters") or {}
           if k not in engineering.NOTES and k not in {x for v in EXTRA.values() for x, _ in v}]  # fmt: skip
    for p in data().get("products") or []:
        bad += [f"{p['key']} guide {k}" for k in [*(p.get("guides") or []), *(p.get("why") or [])]
                if k not in engineering.NOTES]  # fmt: skip
        bad += [f"{p['key']} visual {v}" for v in p.get("visuals") or [] if v not in lib.VISUALS]
        bad += [f"{p['key']} rf note {n}" for n in p.get("rf_notes") or [] if n not in rf]
        bad += [f"{p['key']} topic {t}" for t in p.get("topics") or [] if t not in topics]
        for pt in [x for k in p.get("why") or [] for x in (data().get("why_it_matters") or {}).get(k, [])]:
            if pt.get("kind") not in KINDS:
                bad.append(f"{p['key']} kind {pt.get('kind')}")
    return bad
