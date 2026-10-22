"""Technology reviews of existing parts (Systems & applications > Technology reviews): one structured file per review,
data/reviews/<slug>.yaml (layout in data/reviews/_format.yaml; files starting with "_" are not reviews).

A review explains a part for business development: the datasheet, the problem the part solves, the concept behind it
and the datasheet features that matter in its applications. Reviewers agree or disagree with each item (DataReview
rows, dataset "review:<slug>", key "<section>.<index>", latest verdict counts; a disagreed item's confidence drops one
step). Anyone can request a review of a part (TechReviewRequest rows); the daily update run writes the requested
reviews in the same format.
"""

import re
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import DataReview, Part, TechReviewRequest
from app.partnumbers import normalize_pn
from app.services import blocks

FOLDER = PROJECT_ROOT / "data" / "reviews"
CONF = ("high", "med", "low")
STATUSES = {"draft": "Draft", "reviewed": "Reviewed"}
REQUEST_STATUSES = {"new": "New", "in_progress": "In progress", "done": "Done", "dropped": "Dropped"}
LEARN_AGES = {5: "What it is", 10: "Why it matters", 15: "How it works", 20: "What the datasheet tells you",
              25: "Who else does it, and where we stand"}  # fmt: skip
VERDICTS = {"agree": "correct", "disagree": "wrong", "reset": "unsure"}
VERDICT_LABEL = {"correct": "agreed", "wrong": "disputed"}
# sections whose items can be reviewed, in page order: (key, where the list is in the file)
SECTIONS = (
    ("in_brief", ("in_brief",)),
    ("problem", ("problem", "points")),
    ("concept", ("concept", "blocks")),
    ("datasheet", ("datasheet",)),
    ("key_features", ("key_features",)),
    ("applications", ("applications",)),
    ("competitors", ("competitors",)),
    ("our_position", ("our_position",)),
    ("open_questions", ("open_questions",)),
)
_SLUG = re.compile(r"^[a-z0-9-]+$")
MAX_SLUG = 40 - len("review:")  # DataReview.dataset is 40 characters


class ReviewError(ValueError):
    """A review file that does not follow the format; the message names the file and every problem."""


def dataset(slug: str) -> str:
    return f"review:{slug}"


def _get(d: dict, path: tuple[str, ...]):
    for k in path:
        d = d.get(k) if isinstance(d, dict) else None
    return d


def _srcs(value) -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    return [s.strip() for s in str(value or "").split(",") if s.strip()]


def _walk_src(node, out: list[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "src":
                out += _srcs(v)
            elif k != "sources":
                _walk_src(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_src(v, out)


def _walk_conf(node, out: list[str]) -> None:
    if isinstance(node, dict):
        if "conf" in node:
            out.append(str(node["conf"]))
        for v in node.values():
            _walk_conf(v, out)
    elif isinstance(node, list):
        for v in node:
            _walk_conf(v, out)


def diagram_index() -> dict[str, tuple[str, int]]:
    """Diagram name -> ("library" | "background", index in its list)."""
    out = {str(t.get("name")): ("background", i) for i, t in enumerate(blocks.background_templates())}
    out.update({str(t.get("name")): ("library", i) for i, t in enumerate(blocks.templates())})
    return out


def validate(data, slug: str) -> tuple[dict, list[str]]:
    """The review with defaults filled in, and warnings (unknown diagrams, which are left out). Raises ReviewError with
    every problem found when a required field is missing or wrong."""
    errs: list[str] = []
    if not isinstance(data, dict):
        raise ReviewError(f"{slug}: the file is not a mapping of fields")
    if not _SLUG.match(slug) or len(slug) > MAX_SLUG:
        errs.append(f"file name must be lower-case letters, digits and dashes, at most {MAX_SLUG} characters")
    if str(data.get("slug") or "") != slug:
        errs.append(f"slug must equal the file name ({slug!r}), found {data.get('slug')!r}")
    for k in ("title", "maker"):
        if not str(data.get(k) or "").strip():
            errs.append(f"{k} is missing")
    fam = data.get("family")
    if fam not in blocks.catalogue()["functions"]:
        errs.append(f"family {fam!r} is not a function id in data/blocks/functions.yaml")
    parts = data.get("parts")
    if not isinstance(parts, list) or not parts or not all(str(p).strip() for p in parts):
        errs.append("parts must be a list of part numbers")
    if str(data.get("status") or "draft") not in STATUSES:
        errs.append(f"status must be one of {', '.join(STATUSES)}")
    brief = data.get("in_brief")
    if not isinstance(brief, list) or not brief or not all(isinstance(b, dict) and b.get("text") for b in brief):
        errs.append("in_brief must be a list of {text, conf, src} items")
    problem = data.get("problem")
    if not isinstance(problem, dict) or not problem.get("summary"):
        errs.append("problem needs a summary")
    concept = data.get("concept")
    if not isinstance(concept, dict) or not concept.get("summary"):
        errs.append("concept needs a summary")
    elif not isinstance(concept.get("blocks") or [], list) or not all(
        isinstance(b, dict) and b.get("name") for b in concept.get("blocks") or []
    ):
        errs.append("concept.blocks must be a list of {name, what, why} items")
    feats = data.get("key_features")
    if not isinstance(feats, list) or not feats:
        errs.append("key_features must be a non-empty list")
    else:
        for i, f in enumerate(feats):
            missing = [k for k in ("feature", "value", "meaning", "why_it_matters") if not (f or {}).get(k)]
            if missing:
                errs.append(f"key_features[{i}] misses {', '.join(missing)}")
    for name in ("datasheet", "applications", "competitors", "open_questions", "learn_links"):
        if not isinstance(data.get(name) or [], list):
            errs.append(f"{name} must be a list")
    sources = data.get("sources")
    ids: list[str] = []
    if not isinstance(sources, list) or not sources:
        errs.append("sources must be a non-empty list")
    else:
        for i, s in enumerate(sources):
            if not isinstance(s, dict) or not str(s.get("id") or "").strip():
                errs.append(f"sources[{i}] has no id")
            else:
                ids.append(str(s["id"]))
        dup = sorted({x for x in ids if ids.count(x) > 1})
        if dup:
            errs.append(f"source ids used twice: {', '.join(dup)}")
    used: list[str] = []
    _walk_src({k: v for k, v in data.items() if k != "sources"}, used)
    unknown = sorted(set(used) - set(ids))
    if unknown:
        errs.append(f"src not in sources: {', '.join(unknown)}")
    confs: list[str] = []
    _walk_conf(data, confs)
    bad = sorted(set(confs) - set(CONF))
    if bad:
        errs.append(f"conf must be high, med or low, found {', '.join(bad)}")
    learn = data.get("learn") or {}
    if not isinstance(learn, dict) or any(not str(k).isdigit() for k in learn):
        errs.append('learn must map ages ("5" … "25") to a paragraph')
    if errs:
        raise ReviewError(f"{slug}: " + "; ".join(errs))

    warnings: list[str] = []
    where = diagram_index()
    apps = []
    for i, a in enumerate(data.get("applications") or []):
        name = str((a or {}).get("diagram") or "")
        if name not in where:
            warnings.append(f"{slug}: applications[{i}] diagram {name!r} is not in the block-diagram library; left out")
            continue
        kind, idx = where[name]
        apps.append({**a, "kind": kind, "index": idx, "name": blocks.display_name(
            (blocks.templates() if kind == "library" else blocks.background_templates())[idx])})  # fmt: skip
    r = {**data, "status": str(data.get("status") or "draft"), "date": str(data.get("date") or ""),
         "parts": [str(p).strip() for p in parts], "applications": apps,
         "app_area": str(data.get("app_area") or "Other"),
         "datasheet": data.get("datasheet") or [], "competitors": data.get("competitors") or [],
         "open_questions": data.get("open_questions") or [], "learn_links": data.get("learn_links") or []}  # fmt: skip
    return r, warnings


def _files(folder: Path) -> tuple[tuple[str, float], ...]:
    return tuple(sorted((str(p), p.stat().st_mtime) for p in folder.glob("*.yaml") if not p.name.startswith("_")))


@lru_cache(maxsize=4)
def _load(sig: tuple[tuple[str, float], ...]) -> tuple[dict[str, dict], list[str], list[str]]:
    out, errors, warnings = {}, [], []
    for path, _ in sig:
        p = Path(path)
        try:
            r, w = validate(yamlio.load(p.read_text()) or {}, p.stem)
        except ReviewError as e:
            errors.append(str(e))
            continue
        except Exception as e:  # unreadable YAML: reported like a broken file, the site keeps working
            errors.append(f"{p.stem}: cannot read the file ({e})")
            continue
        out[r["slug"]] = r
        warnings += w
    return out, errors, warnings


def load_dir(folder: Path) -> tuple[dict[str, dict], list[str], list[str]]:
    """(reviews by slug, errors of files left out, warnings) for every review file in a folder."""
    return _load(_files(folder))


def all_reviews() -> list[dict]:
    """Every valid review, grouped order: application area, then title."""
    return sorted(load_dir(FOLDER)[0].values(), key=lambda r: (r["app_area"], r["title"]))


def problems() -> tuple[list[str], list[str]]:
    _, errors, warnings = load_dir(FOLDER)
    return errors, warnings


def get(slug: str) -> dict | None:
    return load_dir(FOLDER)[0].get(slug)


def for_part(mpn: str) -> list[dict]:
    """Reviews that cover a part number (the orderable number, or the number without its package suffix)."""
    n = normalize_pn(mpn or "")
    if not n:
        return []
    return [r for r in all_reviews() if any(_same_part(n, normalize_pn(p)) for p in r["parts"])]


def _same_part(a: str, b: str) -> bool:
    return a == b or (len(b) >= 5 and a.startswith(b)) or (len(a) >= 5 and b.startswith(a))


def for_function(fn: str | None) -> list[dict]:
    return [r for r in all_reviews() if fn and r.get("family") == fn]


def for_application(i: int) -> list[dict]:
    """Reviews placed in an application (combined numbering of /business/applications: library, then background)."""
    n_lib = len(blocks.templates())
    out = []
    for r in all_reviews():
        if any((a["index"] if a["kind"] == "library" else n_lib + a["index"]) == i for a in r["applications"]):
            out.append(r)
    return out


def search(rows: list[dict], q: str) -> list[dict]:
    """Reviews whose part numbers contain the query, or that contain every word of it."""
    q = (q or "").strip()
    if not q:
        return rows
    qn = normalize_pn(q)
    words = [w for w in re.split(r"\W+", q.lower()) if w]
    out = []
    for r in rows:
        if len(qn) >= 2 and any(qn in normalize_pn(p) for p in r["parts"]):
            out.append(r)
            continue
        text = " ".join(str(r.get(k) or "") for k in ("title", "maker", "app_area", "question", "family")).lower()
        text += " " + " ".join(str(b.get("text") or "") for b in r.get("in_brief") or []).lower()
        if words and all(w in text for w in words):
            out.append(r)
    return out


# ---- feedback per item ---------------------------------------------------------------------------------------------
def items(r: dict) -> list[tuple[str, int, object]]:
    """(section, index, item) for every reviewable item."""
    out = []
    for sec, path in SECTIONS:
        v = _get(r, path)
        if sec == "our_position":
            v = [v] if v else []
        for i, x in enumerate(v or []):
            out.append((sec, i, x))
    return out


def item_keys(r: dict) -> set[str]:
    return {f"{s}.{i}" for s, i, _ in items(r)}


def feedback(session: Session, slug: str) -> dict[str, dict]:
    """Per item key: the latest verdict and every comment, oldest first."""
    out: dict[str, dict] = {}
    q = select(DataReview).where(DataReview.dataset == dataset(slug)).order_by(DataReview.id)
    for d in session.scalars(q):
        f = out.setdefault(d.key, {"verdict": None, "comments": []})
        f["verdict"] = None if d.verdict == "unsure" else d.verdict
        if d.comment:
            f["comments"].append({"text": d.comment, "author": d.author, "date": d.created_at})
    return out


def _lower(conf: str) -> str:
    return {"high": "med", "med": "low"}.get(conf, "low")


def with_feedback(session: Session, r: dict) -> dict:
    """The review with each item as {key, item, text, conf, conf_was, fb}: a disputed item's confidence drops one
    step. Strings (open questions, our position) become {text}."""
    fb = feedback(session, r["slug"])
    out: dict[str, list[dict]] = {}
    for sec, i, x in items(r):
        key = f"{sec}.{i}"
        d = dict(x) if isinstance(x, dict) else {"text": str(x)}
        f = fb.get(key, {})
        if d.get("conf") and f.get("verdict") == "wrong":
            d["conf_was"], d["conf"] = d["conf"], _lower(str(d["conf"]))
        out.setdefault(sec, []).append({**d, "key": key, "fb": f})
    n = sum(1 for f in fb.values() if f["verdict"] or f["comments"])
    learn = sorted(((int(k), v) for k, v in (r.get("learn") or {}).items()), key=lambda kv: kv[0])
    levels = [{"age": a, "title": LEARN_AGES.get(a, ""), "text": t} for a, t in learn]
    return {**r, "rows": out, "n_feedback": n, "levels": levels,
            "src": {str(s["id"]): s for s in r.get("sources") or []}}  # fmt: skip


def react(session: Session, slug: str, key: str, verdict: str, comment: str = "", author: str = "") -> None:
    r = get(slug)
    if r is None or key not in item_keys(r) or verdict not in VERDICTS:
        raise ValueError("unknown review, item or verdict")
    session.add(DataReview(dataset=dataset(slug), key=key[:120], verdict=VERDICTS[verdict],
                           comment=comment.strip()[:2000] or None, author=author.strip()[:100] or None))  # fmt: skip
    session.commit()


def live_parts(session: Session, r: dict) -> list[dict]:
    """The review's parts that are in the parts database, with their crosses from the site's matching rules."""
    from app.services.queries import crosses_for

    out = []
    for mpn in r["parts"]:
        part = session.scalars(select(Part).where(Part.mpn == mpn)).unique().first()
        if part is None:
            out.append({"mpn": mpn, "part": None, "crosses": []})
            continue
        found = crosses_for(session, part, scope="all") if part.family else {}
        crosses = [(cat, c.candidate) for cat, rows in found.items() for c in rows][:12]
        out.append({"mpn": mpn, "part": part, "crosses": crosses})
    return out


# ---- requests ------------------------------------------------------------------------------------------------------
def request_review(session: Session, mpn: str, question: str, application: str = "") -> TechReviewRequest:
    mpn = " ".join((mpn or "").split())[:100]
    question = (question or "").strip()[:2000]
    if not mpn:
        raise ValueError("Enter a part number")
    if not question:
        raise ValueError("Write what you want to understand")
    row = TechReviewRequest(mpn=mpn, question=question, application=(application or "").strip()[:200] or None)
    session.add(row)
    session.commit()
    return row


def effective(row: TechReviewRequest) -> dict:
    """A request with the review that answers it: its own link, else a review that covers the part (shown as done)."""
    linked = get(row.review_slug) if row.review_slug else None
    found = linked or next(iter(for_part(row.mpn)), None)
    status = row.status
    if found and status in ("new", "in_progress"):
        status = "done"
    return {"row": row, "review": found, "status": status, "label": REQUEST_STATUSES.get(status, status)}


def requests(session: Session, open_only: bool = False) -> list[dict]:
    rows = session.scalars(select(TechReviewRequest).order_by(TechReviewRequest.created_at.desc(),
                                                              TechReviewRequest.id.desc())).all()  # fmt: skip
    out = [effective(r) for r in rows]
    return [e for e in out if e["status"] in ("new", "in_progress")] if open_only else out


def set_request(session: Session, rid: int, status: str, review_slug: str = "") -> TechReviewRequest:
    row = session.get(TechReviewRequest, rid)
    if row is None:
        raise KeyError(rid)
    if status not in REQUEST_STATUSES or (review_slug and get(review_slug) is None):
        raise ValueError("unknown status or review")
    row.status = status
    row.review_slug = review_slug or row.review_slug
    session.commit()
    return row
