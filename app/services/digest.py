"""Gists, abstracts and the owner's "To confirm" feed (owner, 25 Oct 2026: "boil it down to the most simple idea or
abstract, then I can decide if I want to read or ignore it, then I can confirm it. I do not want too much
pre-filtering as all of this could be relevant").

Every research item on the site gets a gist (one plain sentence, at most 25 words) and an abstract (at most three
short bullets: what it says, why it matters to us, what decision it asks for). Written gists live in the item's own
YAML entry (``gist:`` and ``abstract:``) or, for items that are HTML only, in data/business/gists.yaml. Items with no
written gist get one derived from their first sentence and are marked ``auto`` ("auto summary"); the daily run
rewrites a few of those on every run (docs/daily_update.md).

The feed lists every item not yet confirmed or ignored, newest first, with no relevance filter. Confirm / Ignore /
Undo and comments are DataReview rows (dataset "digest", key "<type>:<id>"), append-only: the latest state answer
wins, every answer stays in the history. Ignored is not deleted: the item stays on the site and only leaves the feed.
"""

import re
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import DataReview, aware

DATASET = "digest"
MAX_WORDS = 25
GISTS_FILE = PROJECT_ROOT / "data" / "business" / "gists.yaml"
_BIZ = PROJECT_ROOT / "data" / "business"

# type -> label (chip on the card); order = the order of the type chips
TYPES = {
    "report": "Research report",
    "case": "Business case",
    "background": "Background notes",
    "expansion": "Idea expansion",
    "review": "Technology review",
    "idea": "New-market idea",
    "competitor": "Competitor profile",
    "risk": "Risk",
    "tam": "TAM estimate",
    "tam-topic": "TAM topic",
    "evidence": "Evidence",
    "patent-change": "Patent change",  # only when the quarterly patent re-check found a change (owner, 26 Oct 2026)
    "note": "Engineering note",
    "family": "Datasheet family",  # crosses grouped by datasheet, offered for a batch confirm (families.py)
    "question": "Open question",
}
# the owner's state answers; "comment" rows are kept in the history and sent to the daily inbox, never a state
CONFIRMED, IGNORED, OPEN, COMMENT = "confirmed", "ignored", "open", "comment"
STATES = (CONFIRMED, IGNORED, OPEN)
_PAST = {"agree": "agreed", "disagree": "disagreed"}  # "You agreed 22 Oct" on the card
LABELS = {CONFIRMED: "confirmed", IGNORED: "ignored", OPEN: "back to the feed", COMMENT: "comment"}


# ---- gist helpers --------------------------------------------------------------------------------------------------
def words(text: str) -> int:
    return len((text or "").split())


def _plain(text) -> str:
    text = re.sub(r"<[^>]+>", " ", str(text or ""))
    return " ".join(text.split())


def first_sentence(text) -> str:
    """The first sentence of a text (HTML tags dropped), no longer than MAX_WORDS words ("…" when cut)."""
    t = _plain(text)
    m = re.search(r"(?<=[.!?])\s+(?=[A-Z0-9“\"(])", t)
    s = t[: m.start()] if m else t
    w = s.split()
    if len(w) > MAX_WORDS:
        s = " ".join(w[:MAX_WORDS]).rstrip(",;:–-") + "…"
    return s


def _abstract(*lines) -> list[str]:
    out = []
    for x in lines:
        s = first_sentence(x) if x else ""
        if s and s not in out:
            out.append(s)
    return out[:3]


# ---- loading the items ---------------------------------------------------------------------------------------------
def _sig() -> tuple:
    files = [*_BIZ.glob("*.yaml"), *(_BIZ / "evidence").glob("*.yaml"), *(_BIZ / "cases").glob("*.yaml"),
             *(_BIZ / "competitors").glob("*.yaml"), *(PROJECT_ROOT / "data" / "reviews").glob("*.yaml"),
             PROJECT_ROOT / "data" / "engineering_rf_notes.yaml",
             PROJECT_ROOT / "docs" / "open_questions.md"]  # fmt: skip
    return tuple(sorted((str(p), p.stat().st_mtime) for p in files if p.exists()))


def _load(path: Path):
    return (yamlio.load(path.read_text()) if path.exists() else None) or {}


def _date(v) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def slug(text: str, n: int = 48) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")[:n].strip("-")


def _item(typ: str, ident: str, title: str, href: str, when, own: dict | None, fallback: str, abstract: list[str],
          gists: dict, elsewhere: tuple = ()) -> dict:  # fmt: skip
    key = f"{typ}:{ident}"[:120]
    own = own or {}
    written = own.get("gist") or (gists.get(key) or {}).get("gist")
    ab = own.get("abstract") or (gists.get(key) or {}).get("abstract")
    gist = written or first_sentence(fallback) or first_sentence(title)
    return {"key": key, "type": typ, "type_label": TYPES[typ], "id": ident, "title": _plain(title), "href": href,
            "date": _date(when), "gist": _plain(gist), "abstract": [_plain(x) for x in (ab or abstract)][:3],
            "auto": not written, "elsewhere": elsewhere}  # fmt: skip


def _reports(gists: dict) -> list[dict]:
    from app.services import prelim
    from app.services import reports as rp

    out = []
    for r in rp.reports():
        slug_ = r["slug"]
        href = f"/business/reports/{slug_}"
        ans = (r.get("answer") or {}).get("text") if isinstance(r.get("answer"), dict) else r.get("answer")
        ab = _abstract(r.get("summary"), r.get("decision"), ans)
        if r.get("kind") == "idea" and (case := prelim.raw(slug_)) is not None:
            out.append(_item("case", slug_, r["title"], href, case.get("updated") or r.get("date"), case,
                             r.get("summary"), ab, gists, (prelim.dataset(slug_),)))  # fmt: skip
        else:
            out.append(_item("report", slug_, r["title"], href, r.get("date"), r, r.get("summary"), ab, gists,
                             (prelim.dataset(slug_),)))  # fmt: skip
        if rp.has_background(slug_):
            out.append(_item("background", slug_, f"Background notes: {r['title']}", f"{href}/background",
                             r.get("date"), None, f"Every figure behind “{r['title']}” with its source and confidence.",
                             ["Every figure with its source and a confidence level.",
                              "Read it only to check or challenge a number in the main text."], gists))  # fmt: skip
        if r.get("expanded"):
            out.append(_item("expansion", slug_, f"Applications in depth: {r['title']}",
                             f"{href}#applications-in-depth", r.get("expanded"), None, _expansion_text(slug_),
                             _abstract(_expansion_text(slug_)), gists))  # fmt: skip
    return out


def _expansion_text(slug_: str) -> str:
    from app.services import reports as rp

    p = rp.BODIES / f"{slug_}.html"
    html = p.read_text() if p.exists() else ""
    m = re.search(r'<section id="applications-in-depth">(.*?)</section>', html, flags=re.S)
    body = re.sub(r"<h2>.*?</h2>", " ", m.group(1), flags=re.S) if m else ""
    return _plain(body)


def _reviews(gists: dict) -> list[dict]:
    from app.services import reviews as rv

    out = []
    for path in sorted(rv.FOLDER.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        d = _load(path)
        s = d.get("slug") or path.stem
        brief = [x.get("text") if isinstance(x, dict) else x for x in d.get("in_brief") or []]
        out.append(_item("review", s, d.get("title") or s, f"/reviews/{s}", d.get("date"), d,
                         brief[0] if brief else d.get("question"),
                         _abstract(*(brief[:1] or [d.get("question")]), d.get("our_position")), gists,
                         (rv.dataset(s),)))  # fmt: skip
    return out


def _ideas(gists: dict) -> list[dict]:
    out = []
    for tech, t in _load(_BIZ / "evidence" / "new_markets.yaml").items():
        if not isinstance(t, dict):
            continue
        for i in t.get("ideas") or []:
            ident = f"{tech}/{slug(i.get('market', ''))}"
            title = f"{i.get('market')}: {t.get('technology', tech)}"
            ab = i.get("abstract")
            ab = [i.get("application") or "", *ab] if ab else _abstract(i.get("application"), i.get("why_fit"))
            own = {"gist": i.get("gist"), "abstract": ab if i.get("abstract") else None}
            out.append(_item("idea", ident, title, f"/business/explore#t-{tech}", "2026-10-19", own,
                             i.get("why_fit") or i.get("application"), ab, gists, (("new_markets", tech),)))
    return out


def _competitors(gists: dict) -> list[dict]:
    from app.services import competitors as cp

    out = []
    for path in sorted(cp.FOLDER.glob("*.yaml")):
        if path.name.startswith("_"):
            continue
        d = _load(path)
        out.append(_item("competitor", path.stem, f"Competitor profile: {d.get('name', path.stem)}",
                         f"/business/competitors/{path.stem}", d.get("updated"), d, d.get("summary"),
                         _abstract(d.get("summary"), *(d.get("for_bizdev") or [])[:1]), gists))  # fmt: skip
    return out


def _risks(gists: dict) -> list[dict]:
    d = _load(_BIZ / "risks.yaml")
    out = []
    for g in d.get("groups") or []:
        for r in g.get("risks") or []:
            out.append(_item("risk", r["id"], f"Risk ({g.get('name')}): {first_sentence(r.get('threat'))}",
                             f"/business/risks#{r['id']}", d.get("updated"), r, r.get("threat"),
                             _abstract(r.get("threat"), r.get("impact")), gists))  # fmt: skip
    return out


def _tam(gists: dict) -> list[dict]:
    from app.services import tam

    checks = tam.checks()
    out = []
    for e in _load(_BIZ / "tam.yaml").get("estimates") or []:
        when = (checks.get(e["id"]) or {}).get("date") or e.get("date") or "2026-10-22"
        title = f"TAM: {e.get('product')} – {e.get('value')} ({e.get('year')})"
        out.append(_item("tam", e["id"], title, f"/business/tam#t-{e['id']}", when, e,
                         f"{e.get('product')}: {e.get('value')} in {e.get('year')} ({e.get('scope')}).",
                         _abstract(e.get("scope"), e.get("quality")), gists, ((tam.DATASET, e["id"]),)))
    for t in _load(_BIZ / "tam_topics.yaml").get("topics") or []:
        out.append(_item("tam-topic", t["id"], f"TAM topic: {t.get('title')}", "/business/tam", t.get("combined"), t,
                         t.get("note"), _abstract(t.get("scope"), t.get("note")), gists))  # fmt: skip
    return out


# Evidence (owner, 26 Oct 2026: "I can't check patents"): ONE item per function ("evidence:<fn>") covering path to
# product, manufacturing (foundry route), competitor technology and market trend. Patents are machine-checked: they
# are shown read-only on the item and never asked of the owner; a patent item ("patent-change") appears only when the
# quarterly re-check (docs/daily_update.md) records a `changed:` block on a patents.yaml / patents_platforms.yaml entry.
EVIDENCE_ASPECTS = {"path": "path", "foundry": "manufacturing", "competitor_tech": "competitor technology",
                    "trends": "market trend"}  # fmt: skip
_OLD_EVIDENCE = re.compile(r"^evidence:(path|foundry|competitor_tech|trends)/(.+)$")  # keys before 26 Oct 2026


def _cut(text: str, n: int = MAX_WORDS) -> str:
    w = _plain(text).split()
    return " ".join(w) if len(w) <= n else " ".join(w[:n]).rstrip(",;:–-") + "…"


def patent_line(fn: str) -> dict | None:
    """The read-only patent depth of a function: {depth, date, source, label, status, changed}, or None.
    Machine-checked (owner, 26 Oct 2026), shown as "checked automatically, <date>"."""
    from app.services import patents

    own = patents.per_function().get(fn)
    if isinstance(own, dict) and own.get("depth"):
        chk = own.get("check") or {}
        return {"depth": str(own["depth"]).replace("_", " "), "date": _date(chk.get("date")), "source": "function",
                "label": "", "status": chk.get("status") or "", "changed": own.get("changed")}  # fmt: skip
    plat = patents.platform_for(fn)
    if plat and plat[1].get("depth"):
        chk = plat[1].get("check") or {}
        return {"depth": str(plat[1]["depth"]).replace("_", " "),
                "date": _date(chk.get("date") or plat[1].get("date")), "source": "platform",
                "label": plat[1].get("label", plat[0]), "status": chk.get("status") or "",
                "changed": plat[1].get("changed")}  # fmt: skip
    return None


def checked_label(d) -> str:
    """ "checked automatically, 19 Oct 2026" for a check date (or without a date)."""
    d = _date(d)
    return f"checked automatically, {d.day} {d:%b %Y}" if d else "checked automatically"


def patent_text(p: dict | None) -> str:
    if not p:
        return ""
    where = f" ({p['label']} platform)" if p["source"] == "platform" else ""
    return f"Patents{where}: {p['depth']} · {checked_label(p['date'])}; indicative, not reviewed."


def _evidence(gists: dict) -> list[dict]:
    from app.services import opportunity as op
    from app.services.vocab import fn_label

    ev = {t: op.evidence(t) for t in EVIDENCE_ASPECTS}
    fns = sorted({fn for t in ev.values() for fn, e in t.items() if isinstance(e, dict)})
    out = []
    for fn in fns:
        pa, fo, ct, tr = (ev[t].get(fn) if isinstance(ev[t].get(fn), dict) else {} for t in EVIDENCE_ASPECTS)
        label = fn_label(fn)
        path = op.PATH_LABEL.get(pa.get("path"), str(pa.get("path") or "no path yet")).lower()
        leaders = ", ".join(map(str, (ct.get("leaders") or [])[:2]))
        gist = f"{label}: {path}; market {tr.get('outlook') or 'not assessed'}"
        gist += f"; leaders {leaders}." if leaders else "."
        base = first_sentence(pa.get("base")).rstrip(".…")
        process = f" ({_plain(fo.get('typical_process'))})" if fo.get("typical_process") else ""
        bullets = [
            _cut(f"Path: {path}. Builds on {base}." if base else f"Path: {path}."),
            _cut(f"Manufacturing: foundry route {fo.get('foundry_route') or '?'}{process}; competitor technology: "
                 f"{first_sentence(ct.get('lead_tech')) or 'not researched'}"),
            _cut(f"Trend: {tr.get('outlook') or 'not assessed'}. {first_sentence(tr.get('note'))}"),
        ]  # fmt: skip
        when = max((d for d in (_date((e.get("check") or {}).get("date")) for e in (pa, fo, ct, tr)) if d),
                   default=None)  # fmt: skip
        it = _item("evidence", fn, f"Evidence: {label}", f"/business/evidence/{fn}", when, None, _cut(gist),
                   bullets, gists, tuple((t, fn) for t in EVIDENCE_ASPECTS))  # fmt: skip
        it["patents"] = patent_text(patent_line(fn))  # read-only, never to confirm
        out.append(it)
    return out


def _patent_changes(gists: dict) -> list[dict]:
    """Patent items for the owner only when the quarterly re-check found a change: an entry of patents.yaml or
    patents_platforms.yaml with a `changed:` block {date, old_depth, new_depth, check, note}. None otherwise."""
    from app.services.vocab import fn_label

    pp = _load(_BIZ / "evidence" / "patents_platforms.yaml")
    entries = [(fn, f"/business/evidence/{fn}", fn_label(fn), e)
               for fn, e in _load(_BIZ / "evidence" / "patents.yaml").items()]  # fmt: skip
    for part in ("platforms", "automotive"):
        for k, p in (pp.get(part) or {}).items():
            p = p if isinstance(p, dict) else {}
            fns = p.get("functions") or []
            href = f"/business/evidence/{fns[0]}" if fns else "/business/capabilities"
            entries.append((f"{part}/{k}", href, f"{p.get('label', k)} platform", p))
    out = []
    for ident, href, label, e in entries:
        ch = e.get("changed") if isinstance(e, dict) else None
        if not isinstance(ch, dict) or not ch.get("date"):
            continue
        old, new = ch.get("old_depth"), ch.get("new_depth")
        moved = bool(new) and old != new
        what = (f"depth {str(old).replace('_', ' ')} → {str(new).replace('_', ' ')}" if moved
                else "a check failed")  # fmt: skip
        ab = [f"Patents, {label}: {what}.", _cut(ch.get("check") or ""), _cut(ch.get("note") or "")]
        out.append(_item("patent-change", f"{ident}@{_date(ch['date'])}", f"Patent change: {label}", href,
                         ch["date"], None, _cut(f"Quarterly patent re-check, {label}: {what}."), [x for x in ab if x],
                         gists))  # fmt: skip
    return out


def _notes(gists: dict) -> list[dict]:
    d = _load(PROJECT_ROOT / "data" / "engineering_rf_notes.yaml")
    out = []
    for t in d.get("topics") or []:
        why = [w.get("text") if isinstance(w, dict) else w for w in t.get("why") or []]
        out.append(_item("note", t["id"], t.get("title") or t["id"], f"/rf-notes#{t['id']}", t.get("added"), t,
                         t.get("summary"), _abstract(t.get("summary"), *why[:1]), gists))  # fmt: skip
    return out


_QDATE = re.compile(r"\((\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{4})\)")


def _questions(gists: dict) -> list[dict]:
    from app.services import runs

    out = []
    for title, body in runs.open_question_items():
        m = _QDATE.search(title)
        when = datetime.strptime(" ".join(m.groups()), "%d %b %Y").date() if m else None
        out.append(_item("question", slug(_QDATE.sub("", title)), f"Open question: {title.rstrip('.')}",
                         "/manage/feedback#questions", when, None, body, _abstract(body), gists))  # fmt: skip
    return out


@lru_cache(maxsize=2)
def _all(sig: tuple) -> tuple[dict, ...]:
    gists = (_load(GISTS_FILE).get("gists") or {}) if GISTS_FILE.exists() else {}
    rows = [*_reports(gists), *_reviews(gists), *_ideas(gists), *_competitors(gists), *_risks(gists), *_tam(gists),
            *_evidence(gists), *_patent_changes(gists), *_notes(gists), *_questions(gists)]  # fmt: skip
    return tuple(rows)


def items() -> list[dict]:
    """Every research item with its gist and abstract (newest first; items with no date last)."""
    rows = list(_all(_sig()))
    rows.sort(key=lambda r: (r["date"] or date.min, r["type"] != "question"), reverse=True)
    return rows


@lru_cache(maxsize=2)
def _index(sig: tuple) -> dict[str, dict]:
    return {r["key"]: r for r in _all(sig)}


def by_key() -> dict[str, dict]:
    return _index(_sig())


def gist_for(typ: str, ident: str) -> dict | None:
    """The item (with gist, abstract, auto) for a page header, or None."""
    return by_key().get(f"{typ}:{ident}"[:120])


def gist_list(typ: str, fn: str) -> list[dict]:
    """The evidence item of one function (one card since 26 Oct 2026), as a list."""
    g = gist_for(typ, fn)
    return [g] if g else []


# ---- the owner's answers -------------------------------------------------------------------------------------------
def _rows(session: Session, since: datetime | None = None) -> list[DataReview]:
    q = select(DataReview).where(DataReview.dataset == DATASET)
    if since is not None:
        q = q.where(DataReview.created_at >= since)
    return list(session.scalars(q.order_by(DataReview.created_at, DataReview.id)))


def states(session: Session) -> dict[str, dict]:
    """key -> {"state", "at", "comments": [...], "history": [...]} from the digest rows (latest state answer wins)."""
    out: dict[str, dict] = {}
    for r in _rows(session):
        e = out.setdefault(r.key, {"state": OPEN, "at": None, "comments": [], "history": []})
        e["history"].insert(0, {"verdict": r.verdict, "label": LABELS.get(r.verdict, r.verdict),
                                "comment": r.comment or "", "date": r.created_at})  # fmt: skip
        if r.verdict in STATES:
            e["state"], e["at"] = r.verdict, r.created_at
        elif r.verdict == COMMENT and r.comment:
            e["comments"].insert(0, {"text": r.comment, "date": r.created_at})
    _carry_over(out)
    return out


def _ts(d) -> float:
    return aware(d).timestamp() if d else 0.0


def _carry_over(out: dict[str, dict]) -> None:
    """The owner's answers on the old per-aspect evidence keys ("evidence:path/<fn>", foundry, competitor_tech,
    trends) carry over to the one card "evidence:<fn>" (26 Oct 2026); the old rows stay as they are (append-only).
    All old aspect items confirmed -> the card counts as confirmed, unless the card has a state answer of its own; an
    ignored aspect is shown on the card; old answers and comments join the card's history."""
    from app.services import opportunity as op

    old: dict[str, dict[str, dict]] = {}
    for k, e in out.items():
        if m := _OLD_EVIDENCE.match(k):
            old.setdefault(m.group(2), {})[m.group(1)] = e
    for fn, asp in old.items():
        key = f"evidence:{fn}"[:120]
        own = any(h["verdict"] in STATES for h in (out.get(key) or {}).get("history", []))
        e = out.setdefault(key, {"state": OPEN, "at": None, "comments": [], "history": []})
        for t, a in asp.items():
            name = EVIDENCE_ASPECTS[t]
            e["history"] += [{**h, "label": f"{h['label']} (old {name} item)"} for h in a["history"]]
            e["comments"] += [{**c, "text": f"{c['text']} (on the old {name} item)"} for c in a["comments"]]
        e["history"].sort(key=lambda h: _ts(h["date"]), reverse=True)
        e["comments"].sort(key=lambda c: _ts(c["date"]), reverse=True)
        want = [t for t in EVIDENCE_ASPECTS if isinstance(op.evidence(t).get(fn), dict)]
        e["ignored_aspects"] = [EVIDENCE_ASPECTS[t] for t in want if asp.get(t, {}).get("state") == IGNORED]
        if not own and want and all(asp.get(t, {}).get("state") == CONFIRMED for t in want):
            e["state"], e["at"], e["carried"] = CONFIRMED, max((asp[t]["at"] for t in want), key=_ts), True


def _family_keys(session: Session) -> dict[str, dict]:
    from app.services import families

    return {r["key"]: r for r in families.digest_items(session)}


def act(session: Session, key: str, action: str, comment: str = "", author: str = "") -> None:
    """Confirm, ignore, undo (back to the feed) or comment on one item; appends a row, never changes one. A datasheet
    family's Confirm / Undo is also its family verdict (DataReview "crossfamily"), which sets
    Verified on its crosses."""
    fam = _family_keys(session).get(key) if key.startswith("family:") else None
    if key not in by_key() and fam is None:
        raise ValueError("unknown item")
    verdict = {"confirm": CONFIRMED, "ignore": IGNORED, "undo": OPEN, "comment": COMMENT}.get(action)
    comment = (comment or "").strip()[:2000]
    if not verdict or (verdict == COMMENT and not comment):
        raise ValueError("unknown action or empty comment")
    session.add(DataReview(dataset=DATASET, key=key[:120], verdict=verdict, comment=comment or None,
                           author=author or None))  # fmt: skip
    session.commit()
    if fam is not None and verdict in (CONFIRMED, OPEN) and (verdict == CONFIRMED) != fam["confirmed"]:
        from app.services import families

        families.confirm(session, fam["id"], families.CONFIRMED if verdict == CONFIRMED else families.OPEN,
                         author)  # fmt: skip


def _elsewhere(session: Session, rows: list[dict]) -> dict[str, dict]:
    """The owner's latest answer on the same item elsewhere on the site (agree / disagree boxes), and whether it was
    applied (then the item counts as confirmed)."""
    from app.services import review_history as rh
    from app.services import tam

    want: dict[tuple[str, str | None], list[str]] = {}
    for r in rows:
        for e in r["elsewhere"]:
            k = (e, None) if isinstance(e, str) else (e[0], e[1])
            want.setdefault(k, []).append(r["key"])
    if not want:
        return {}
    datasets = {d for d, _ in want}
    out: dict[str, dict] = {}
    q = (select(DataReview).where(DataReview.dataset.in_(datasets), DataReview.verdict.in_(("correct", "wrong")))
         .order_by(DataReview.created_at))  # fmt: skip
    for r in session.scalars(q):
        for k in (*want.get((r.dataset, r.key), ()), *want.get((r.dataset, None), ())):
            lbl = rh.label(r.dataset, r.verdict)
            out[k] = {"label": _PAST.get(lbl, lbl), "date": r.created_at, "applied": False}
    applied = tam.applied()
    for r in rows:
        if r["type"] == "tam" and r["id"] in applied:
            a = applied[r["id"]]
            out[r["key"]] = {"label": f"{a.get('verdict', 'answer')} applied", "date": _date(a.get("date")),
                             "applied": True}  # fmt: skip
    return out


def feed(session: Session, tab: str = "open", typ: str = "", q: str = "") -> dict:
    """The To confirm page: the items of one tab (open | confirmed | ignored), counts per tab and per type."""
    rows = [dict(r) for r in items()]  # the cached items stay untouched
    rows += _family_keys(session).values()  # datasheet families: from the owner's answers, not from files
    st = states(session)
    other = _elsewhere(session, rows)

    def state(r: dict) -> str:
        s = st.get(r["key"], {}).get("state", OPEN)
        if r["type"] == "family" and s != IGNORED:  # the family verdict decides (a later Wrong reopens it)
            return CONFIRMED if r["confirmed"] else OPEN
        if s == OPEN and (other.get(r["key"]) or {}).get("applied"):
            return CONFIRMED
        return s

    for r in rows:
        r["state"] = state(r)
    counts = {t: sum(r["state"] == t for r in rows) for t in STATES}
    in_tab = [r for r in rows if r["state"] == tab]
    by_type = {t: sum(r["type"] == t for r in in_tab) for t in TYPES}
    shown = [r for r in in_tab if not typ or r["type"] == typ]
    if q.strip():
        terms = q.lower().split()
        shown = [r for r in shown if all(t in f"{r['title']} {r['gist']} {' '.join(r['abstract'])}".lower()
                                         for t in terms)]  # fmt: skip
    cards = [{**r, "answer": st.get(r["key"]), "other": other.get(r["key"])} for r in shown]
    if tab != OPEN:  # most recently answered first
        cards.sort(key=lambda c: aware(c["answer"]["at"]).timestamp() if c["answer"] and c["answer"]["at"] else 0,
                   reverse=True)
    return {"cards": cards, "counts": counts, "by_type": by_type, "total": len(rows)}


def open_count(session: Session) -> int:
    """Items still in the feed (for the menu badge: one small query, no page-wide work)."""
    from app.services import tam

    st = {k: e["state"] for k, e in states(session).items()}
    applied = {f"tam:{k}" for k in tam.applied()}
    fams = [r for r in _family_keys(session).values() if not r["confirmed"]]
    return sum(st.get(r["key"], OPEN) == OPEN and r["key"] not in applied for r in _all(_sig())) + sum(
        st.get(r["key"], OPEN) != IGNORED for r in fams)


def inbox_lines(session: Session, start: datetime) -> list[str]:
    """Inbox section: the counts since the last pull and the owner's comments for the run to act on."""
    rows = _rows(session, start)
    f = feed(session)
    n = {v: len({r.key for r in rows if r.verdict == v}) for v in STATES}
    new = sum(1 for c in f["cards"] if c["date"] and c["date"] >= start.date())
    auto = sum(r["auto"] for r in items())
    out = ["\n## To confirm: comments\n",
           f"Waiting in the feed: {f['counts'][OPEN]} ({new} new since the last pull) · confirmed since then: "
           f"{n[CONFIRMED]} · ignored since then: {n[IGNORED]} · back to the feed: {n[OPEN]} · auto summaries left: "
           f"{auto}.",
           "Act on each comment (rewrite the gist, fix the item or answer in it); never confirm or ignore for the "
           "owner.\n"]  # fmt: skip
    known = by_key()
    lines = [f"- {aware(r.created_at):%Y-%m-%d %H:%M} {r.key} ({(known.get(r.key) or {}).get('title', '?')}): "
             f"{' '.join((r.comment or '').split())}" for r in rows if r.verdict == COMMENT]  # fmt: skip
    return out + (lines or ["None."])
