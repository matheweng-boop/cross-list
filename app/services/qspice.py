"""QSPICE library (owner, 27 Oct 2026: "Use the Qspice forum for design discussions and things. Also, if you can draw
useful conclusions to block diagrams." and "a full user library where I can ask questions").

Content in data/library/qspice_forum.yaml: our own summaries of design threads in the QSPICE section of the Qorvo Tech
Forum (topics), "Seen in practice" notes per block-diagram function (each backed by at least two threads), how-tos
from the section's own guide threads (help), common fixes (each from at least two threads) and which of our parts have
a public SPICE model in our data (models). No user names, handles or e-mails are stored (tests/test_qspice.py).

The Ask box is a keyword search (SQLite FTS5, like app/services/notes_search.py), not AI. A question with no good match
is kept for the owner only, screened like the block builder's unknown words (no names, e-mails, web addresses), for
12 months; the daily run researches it and adds an answer note (docs/daily_update.md). Guests' questions are never
stored.
"""

import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import QspiceQuestion

FILE = PROJECT_ROOT / "data" / "library" / "qspice_forum.yaml"
HOST = "forum.qorvo.com"
# the only links a topic may carry: the QSPICE category (id 9) and topics in it
TOPIC_URL = re.compile(r"^https://forum\.qorvo\.com/t/(?:[a-z0-9-]+/)?(\d+)$")
CATEGORY_URL = "https://forum.qorvo.com/c/qspice/9"
MAX_QUESTION = 300
GOOD = 0.5  # share of the question's words the best hit must contain to count as an answer


@lru_cache
def data() -> dict:
    return (yamlio.load(FILE.read_text()) if FILE.exists() else None) or {}


def topics(fn: str = "") -> list[dict]:
    """Kept forum topics, newest first; with ``fn`` only those tagged with that function."""
    rows = [t for t in data().get("topics") or [] if not fn or fn in (t.get("fns") or [])]
    return sorted(rows, key=lambda t: str(t.get("date") or ""), reverse=True)


def topic_by_id() -> dict[int, dict]:
    return {int(t["id"]): t for t in data().get("topics") or []}


def practice(fn: str = "") -> list[dict]:
    """ "Seen in practice (QSPICE forum)" notes, each with its threads resolved (title, url)."""
    by_id = topic_by_id()
    out = []
    for n in data().get("practice") or []:
        if fn and fn != n["fn"]:
            continue
        out.append(n | {"threads": [by_id[i] for i in n.get("topics") or [] if i in by_id]})
    return out


def practice_by_fn() -> dict[str, list[dict]]:
    """Function id -> its notes in the short form the block editor shows (text, thread count, links)."""
    out: dict[str, list[dict]] = {}
    for n in practice():
        out.setdefault(n["fn"], []).append({"text": n["text"], "n": len(n["threads"]),
                                            "links": [t["url"] for t in n["threads"]]})  # fmt: skip
    return out


def help_items() -> list[dict]:
    return list(data().get("help") or [])


def fixes() -> list[dict]:
    by_id = topic_by_id()
    return [f | {"threads": [by_id[i] for i in f.get("topics") or [] if i in by_id]} for f in data().get("fixes") or []]


def models(group: str = "") -> list[dict]:
    """Model rows of our current parts (group ""), or of former parts (group "former": UnitedSiC, now onsemi)."""
    return [m for m in data().get("models") or [] if (m.get("group") or "") == group]


def answers() -> list[dict]:
    """Answer notes the daily run added for unanswered questions."""
    return list(data().get("answers") or [])


def function_counts() -> list[tuple[str, str, int]]:
    """(function id, label, number of topics) for the filter, most topics first."""
    from app.services import vocab

    n: dict[str, int] = {}
    for t in data().get("topics") or []:
        for f in t.get("fns") or []:
            n[f] = n.get(f, 0) + 1
    return sorted(((f, vocab.fn_label(f), c) for f, c in n.items()), key=lambda x: (-x[2], x[1]))


# ---- the Ask box: keyword search, not AI -------------------------------------------------------------------------
_STOP = frozenset(
    """a an and are as at be by can could do does doing for from get got how i if in into is it its me my
not of on or should so that the their them then there these this to use using was what when where which while who why
will with would you your qspice simulate simulation simulating sim""".split()
)
_WORD = re.compile(r"[a-z0-9µ][a-z0-9µ.+-]*[a-z0-9µ]|[a-z0-9µ]")


def terms(q: str) -> list[str]:
    seen = []
    for w in _WORD.findall(q.lower()):
        if w not in _STOP and w not in seen:
            seen.append(w)
    return seen


@dataclass
class Hit:
    kind: str  # "Forum thread", "Seen in practice", "Help", "Common fix", "Model", "Answer note"
    title: str
    url: str
    text: str
    cover: float  # share of the question's words found in the item


def _rows() -> list[tuple[str, str, str, str]]:
    from app.services import vocab

    rows = []
    for t in data().get("topics") or []:
        labels = " ".join(vocab.fn_label(f) for f in t.get("fns") or [])
        body = " ".join(str(t.get(k) or "") for k in ("circuit", "problem", "fix"))
        rows.append(("Forum thread", t["title"], t["url"], f"{body} {labels} {' '.join(t.get('parts') or [])}"))
    for n in data().get("practice") or []:
        label = vocab.fn_label(n["fn"])
        rows.append(("Seen in practice", f"Seen in practice: {label}", f"/qspice?fn={n['fn']}#practice",
                     f"{n['text']} {label}"))  # fmt: skip
    for h in data().get("help") or []:
        rows.append(("Help", h["title"], f"/qspice#help-{h['id']}", f"{h['text']} {' '.join(h.get('commands') or [])}"))
    for f in data().get("fixes") or []:
        rows.append(("Common fix", f["title"], f"/qspice#fix-{f['id']}", f["text"]))
    for m in data().get("models") or []:
        text = f"{m['parts']} {m.get('vendor', '')} {m['model']}"
        rows.append(("Model", f"Model: {m['parts']}", "/qspice#models", text))
    for a in data().get("answers") or []:
        rows.append(("Answer note", a["question"], f"/qspice#answer-{a['id']}", a["text"]))
    return rows


@lru_cache
def _index() -> tuple[sqlite3.Connection, tuple]:
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.execute("CREATE VIRTUAL TABLE q USING fts5(title, text, kind UNINDEXED, url UNINDEXED, "
               "tokenize='porter unicode61')")  # fmt: skip
    rows = _rows()
    db.executemany("INSERT INTO q (kind, title, url, text) VALUES (?, ?, ?, ?)", rows)
    return db, tuple(rows)


def _expr(ws: list[str]) -> str:
    return " OR ".join('"' + w.replace('"', "") + '"' + ("*" if len(w) > 3 else "") for w in ws)


def _stem(w: str) -> str:
    return w[:5] if len(w) > 5 else w


def ask(q: str, limit: int = 12) -> list[Hit]:
    """The best-matching items for a question, ranked by how many of its words they contain, then by FTS5 bm25."""
    ws = terms(q[:MAX_QUESTION])
    if not ws:
        return []
    db, _ = _index()
    sql = "SELECT kind, title, url, text FROM q WHERE q MATCH ? ORDER BY bm25(q, 3.0, 1.0) LIMIT 60"
    hits = []
    for rank, (kind, title, url, text) in enumerate(db.execute(sql, (_expr(ws),)).fetchall()):
        low = f"{title} {text}".lower()
        cover = sum(_stem(w) in low for w in ws) / len(ws)
        hits.append((-cover, rank, Hit(kind, title, url, text, round(cover, 2))))
    hits.sort(key=lambda x: x[:2])
    return [h for *_, h in hits[:limit]]


def answered(hits: list[Hit]) -> bool:
    return bool(hits) and hits[0].cover >= GOOD


# ---- unanswered questions (owner only, screened, 12 months) ------------------------------------------------------
_HANDLE = re.compile(r"(?<![\w.])@\w+")


@lru_cache
def _known() -> frozenset[str]:
    """Lower-case words of our own library text (which holds no names): a capitalised word outside it may be a name."""
    words = set(_STOP)
    for _, title, _, text in _index()[1]:
        words |= set(_WORD.findall(f"{title} {text}".lower()))
    return frozenset(words)


def screen(text: str) -> str:
    """The question with e-mails, web addresses, @handles, company names and capitalised words we do not know (possible
    names) removed, as the block builder screens its unknown words."""
    from app.services import wordblocks

    t = wordblocks._URL.sub(" ", wordblocks._EMAIL.sub(" ", _HANDLE.sub(" ", text[:MAX_QUESTION])))
    out = []
    for w in t.split():
        core = w.strip(".,;:!?()[]\"'")
        k = core.lower()
        if not core:
            continue
        if wordblocks._key(k) in wordblocks.company_words() and (core[:1].isupper() or k not in _known()):
            continue  # a company name (a common technical word such as "crystal" stays)
        if sum(c.isdigit() for c in core) > 6 or "@" in core:
            continue
        if core[:1].isupper() and core[1:].islower() and k not in _known():
            continue  # a capitalised word we do not know: maybe a name
        out.append(w)
    return " ".join(out)[:MAX_QUESTION]


def cutoff(today: date | None = None) -> date:
    from app.services import wordblocks

    return wordblocks.cutoff(today)


def purge(session: Session, today: date | None = None) -> int:
    old = QspiceQuestion.day < cutoff(today)
    n = session.scalar(select(func.count(QspiceQuestion.id)).where(old)) or 0
    if n:
        session.execute(delete(QspiceQuestion).where(old))
        session.commit()
    return n


def store(session: Session, q: str, today: date | None = None) -> QspiceQuestion | None:
    text = screen(q)
    if not terms(text):
        return None
    day = today or date.today()
    purge(session, day)
    if session.scalar(select(QspiceQuestion).where(QspiceQuestion.text == text, QspiceQuestion.day == day)):
        return None
    row = QspiceQuestion(text=text, day=day)
    session.add(row)
    session.commit()
    return row


def unanswered(session: Session, since: date | None = None) -> list[QspiceQuestion]:
    purge(session)
    q = select(QspiceQuestion).order_by(QspiceQuestion.day.desc(), QspiceQuestion.id.desc())
    if since is not None:
        q = q.where(QspiceQuestion.day >= since)
    return list(session.scalars(q))


def inbox_lines(session: Session, since: date) -> list[str]:
    rows = unanswered(session, since)
    out = ["\n## QSPICE: unanswered questions\n",
           "Questions the owner asked in the QSPICE library's Ask box with no good match (screened text, no names). "
           "Research each in the allowed sources (docs/daily_update.md) and add an answer note to "
           "data/library/qspice_forum.yaml under answers:, citing them.\n"]  # fmt: skip
    out += [f"- {r.day:%d %b %Y}: {r.text}" for r in rows[:50]] or ["None."]
    return out
