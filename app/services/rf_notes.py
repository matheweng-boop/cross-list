"""RF fundamentals: engineering notes written from public Mini-Circuits and RF Essentials material, plus the physics
behind our product families (category physics; data/engineering_rf_notes.yaml explains the sources)."""

from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT

FILE = PROJECT_ROOT / "data" / "engineering_rf_notes.yaml"
CATEGORIES = {"physics": "Physics behind our products", "rf_specs": "RF specifications", "components": "Components",
              "architecture": "Architectures", "technology": "Technology"}  # fmt: skip


@lru_cache
def topics() -> tuple[dict, ...]:
    return tuple((yamlio.load(FILE.read_text()) or {}).get("topics") or []) if FILE.exists() else ()


def by_category() -> list[tuple[str, str, list[dict]]]:
    return [(k, label, sorted((t for t in topics() if t["category"] == k), key=lambda t: t["title"].lower()))
            for k, label in CATEGORIES.items()]  # fmt: skip


def _families() -> dict[str, str]:
    from app.services import knowledge

    return {p["key"]: p["title"] for p in knowledge.data().get("products") or []}


def links(t: dict) -> dict[str, list[dict]]:
    """A physics topic's links into the site: product families, catalogue searches, guides, notes and visuals."""
    from app.services import engineering
    from app.services import library as lib

    titles, fams = {x["id"]: x["title"] for x in topics()}, _families()
    return {
        "Product families": [{"title": fams[k], "href": f"/knowledge#p-{k}"} for k in t.get("families") or []
                             if k in fams],
        "Our parts": [{"title": p["label"], "href": f"/find?q={p['q']}"} for p in t.get("parts") or []],
        "Spec guides": [{"title": engineering.NOTES[g][0], "href": f"/engineering/{g}"} for g in t.get("guides") or []
                        if g in engineering.NOTES],
        "Interactive visuals": [{"title": lib.VISUALS[v][0], "href": lib.VISUALS[v][1]} for v in t.get("visuals") or []
                                if v in lib.VISUALS],
        "Related notes": [{"title": titles[n], "href": f"/rf-notes#{n}"} for n in t.get("notes") or [] if n in titles],
    }  # fmt: skip


def problems() -> list[str]:
    """Physics topics that miss a field or whose families, guides, notes, visuals or links point nowhere."""
    from app.services import engineering, knowledge
    from app.services import library as lib

    ids, fams = {t["id"] for t in topics()}, _families()
    bad = []
    for t in topics():
        if t["category"] != "physics":
            continue
        i = t["id"]
        bad += [f"{i}: no {f}" for f in ("summary", "equations", "why", "families", "sources", "try") if not t.get(f)]
        bad += [f"{i}: family {k}" for k in t.get("families") or [] if k not in fams]
        bad += [f"{i}: guide {g}" for g in t.get("guides") or [] if g not in engineering.NOTES]
        bad += [f"{i}: note {n}" for n in t.get("notes") or [] if n not in ids]
        bad += [f"{i}: visual {v}" for v in t.get("visuals") or [] if v not in lib.VISUALS]
        bad += [f"{i}: why kind {w.get('kind')}" for w in t.get("why") or [] if w.get("kind") not in knowledge.KINDS]
        bad += [f"{i}: link {s.get('url')}" for s in [*(t.get("sources") or []), *(t.get("try") or [])]
                if not str(s.get("url", "")).startswith(("http://", "https://")) or not s.get("title")]  # fmt: skip
    return bad
