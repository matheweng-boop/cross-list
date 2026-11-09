"""Questions to ask per segment (owner, 9 Nov 2026): "start including questions to customers and to the Business Unit on
all of the segments, to understand what the applications are about, and what forward-thinking topics one should ask
the customers and the developers."

Every system and sub-system of the Systems library (data/blocks/systems.yaml) has a question set in
data/business/segment_questions.yaml, in three groups: to the customer (the application), to the customer's
developers (what comes next) and to our business unit. A system's own set holds the cross-cutting questions. Where a
research report covers the segment, its questions are linked (``reports``), not repeated.

Answers use the same store, answer box, sharing switch and rules as the report questions (app/services/answers.py),
keyed by the segment: slug ``seg:<system>`` or ``seg:<system>/<sub-system>`` and the question's id.
"""

from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT

FILE = PROJECT_ROOT / "data" / "business" / "segment_questions.yaml"
PREFIX = "seg:"
GROUPS = (
    ("customer", "Customer: the application"),
    ("developers", "Developers: what comes next"),
    ("bu", "Business unit"),
)
TABS = {"customer": "Customer", "developers": "Developers", "bu": "Business unit"}
ASK = {"customer": "the customer (product, purchasing or system team)",
       "developers": "the customer's design engineers",
       "bu": "our business unit"}  # fmt: skip


@lru_cache
def _raw() -> dict:
    return (yamlio.load(FILE.read_text()) or {}) if FILE.exists() else {}


def _file() -> dict:
    return _raw().get("segments") or {}


def moved() -> dict[str, list[str]]:
    """Retired segment keys -> the segments their questions moved to (owner, 9 Nov 2026: Data center regrouped).
    Answers stay stored under the old slug; each shows on the first listed segment that has its question id."""
    return {k: list(v or []) for k, v in (_raw().get("moved") or {}).items()}


def home_of(old: str, qid: str) -> str:
    """The segment an answer stored under a retired key belongs to now ("" when its question is gone)."""
    return next((k for k in moved().get(old, []) if any(q["id"] == qid for q in questions(k))), "")


def old_keys(key: str) -> list[str]:
    """Retired segment keys whose questions moved (partly) into `key`."""
    return [old for old, new in moved().items() if key in new]


def is_segment(slug: str) -> bool:
    return (slug or "").startswith(PREFIX)


def slug_of(key: str) -> str:
    return PREFIX + key


def key_of(slug: str) -> str:
    return slug[len(PREFIX):] if is_segment(slug) else ""


@lru_cache
def segments() -> tuple[dict, ...]:
    """Every system and sub-system in Systems library order: key (system or system/sub), system, sub, title (with the
    system for a sub-system), href (its questions page)."""
    from app.services import systems as sy

    out = []
    for s in sy.systems():
        out.append({"key": s["key"], "system": s["key"], "sub": "", "title": s["title"], "short": s["title"],
                    "system_title": s["title"], "href": f"/library/questions/{s['key']}"})  # fmt: skip
        for x in s["subsystems"]:
            out.append({"key": f"{s['key']}/{x['key']}", "system": s["key"], "sub": x["key"],
                        "title": f"{s['title']} › {x['title']}", "short": x["title"], "system_title": s["title"],
                        "href": f"/library/questions/{s['key']}/{x['key']}"})  # fmt: skip
    return tuple(out)


def segment(key: str) -> dict | None:
    return next((s for s in segments() if s["key"] == key), None)


def _current(key: str) -> str:
    return key if segment(key) else next(iter(moved().get(key) or []), key)


def title(slug_or_key: str) -> str:
    s = segment(_current(key_of(slug_or_key) or slug_or_key))
    return s["title"] if s else slug_or_key


def href(slug: str) -> str:
    s = segment(_current(key_of(slug)))
    return s["href"] if s else "/library"


def questions(key: str) -> list[dict]:
    """A segment's questions in page order (customer, developers, business unit). Each: id, text, group, ask (whom to
    ask), why, opener (always False: the shape of the report questions)."""
    if segment(key) is None:
        return []
    src = _file().get(key) or {}
    out = []
    for g, _ in GROUPS:
        for q in src.get(g) or []:
            if q.get("id"):
                out.append({"id": str(q["id"]), "text": str(q.get("text") or ""), "group": g,
                            "ask": str(q.get("who") or ""), "why": str(q.get("why") or ""),
                            "opener": False})  # fmt: skip
    return out


def reports(key: str) -> list[dict]:
    """Research reports and cases that cover the segment, with their own Questions to ask (linked, not repeated)."""
    from app.services import answers
    from app.services import reports as rp

    out = []
    for slug in (_file().get(key) or {}).get("reports") or []:
        r = rp.report(slug)
        if r is not None:
            n = len(answers.questions(slug))
            out.append({"slug": slug, "title": r["title"], "n": n,
                        "href": f"/business/reports/{slug}#questions-to-ask"})  # fmt: skip
    return out


def counts() -> dict[str, int]:
    """Number of questions per segment key."""
    return {s["key"]: len(questions(s["key"])) for s in segments()}
