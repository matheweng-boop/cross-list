"""Application knowledge (owner, 28 Oct 2026): short explainers with sources (data/library/app_knowledge.yaml), shown on
the application pages and Systems library topics that name them in a `knowledge: [ids]` list."""

from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT

FILE = PROJECT_ROOT / "data" / "library" / "app_knowledge.yaml"
KINDS = {"read": "read 28 Oct 2026", "snippet": "search snippet, not read", "ours": "our data"}


@lru_cache
def items() -> tuple[dict, ...]:
    return tuple((yamlio.load(FILE.read_text()) or {}).get("items") or [])


def get(item_id: str) -> dict | None:
    return next((x for x in items() if x.get("id") == item_id), None)


def for_ids(ids) -> list[dict]:
    """The items for a `knowledge` list, in its order; unknown ids are skipped (problems() reports them)."""
    return [x for i in ids or [] if (x := get(i))]


def href(item_id: str) -> str:
    """Where an item is read in full: its first application page, else the first library topic that names it."""
    from app.services import blocks, library

    for i, t in enumerate(blocks.templates()):
        if item_id in (t.get("knowledge") or []):
            return f"/blocks/new?template={i}#k-{item_id}"
    for t in library.topics():
        if item_id in (t.get("knowledge") or []):
            return f"/library/{t['key']}#k-{item_id}"
    return ""


def problems() -> list[str]:
    """Items without title, text or sources, sources without a usable URL or kind, and unknown ids in use."""
    from app.services import blocks, library

    bad = []
    for x in items():
        xid = x.get("id", "?")
        bad += [f"{xid}: no {k}" for k in ("id", "title", "intro", "points", "sources") if not x.get(k)]
        for s in x.get("sources") or []:
            if not (s.get("url", "").startswith("https://") or s.get("url", "").startswith("/")):
                bad.append(f"{xid}: source url {s.get('title', '')[:40]}")
            if s.get("kind") not in KINDS:
                bad.append(f"{xid}: source kind {s.get('kind')}")
        t = x.get("table")
        if t and any(len(r) != len(t["head"]) for r in t.get("rows") or []):
            bad.append(f"{xid}: table row length")
    users = [
        *(t.get("knowledge") or [] for t in blocks.templates()),
        *(t.get("knowledge") or [] for t in library.topics()),
    ]
    bad += [f"unknown knowledge id {i}" for ids in users for i in ids if get(i) is None]
    return bad


def for_app(i: int) -> list[dict]:
    """The items of application i (library diagrams, then background diagrams, as indexed on the pages)."""
    from app.services import how_it_works

    apps = how_it_works._apps()
    return for_ids(apps[i].get("knowledge")) if 0 <= i < len(apps) else []
