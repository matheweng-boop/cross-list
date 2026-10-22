"""Keyword search over Skyworks application notes, TI application notes (title + summary,
data/catalog/ti_appnotes.yaml), the BizDev engineering notes and the technical library (topics, design rules, trends).

Everything runs locally: an in-memory SQLite FTS5 index built once from data/appnotes.jsonl
and the engineering-note templates. Nothing is sent to an outside service.
"""

import json
import re
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from html import escape, unescape

from app import yamlio
from app.config import PROJECT_ROOT
from app.services.engineering import NOTES, NOTES_DIR

APPNOTES_FILE = PROJECT_ROOT / "data" / "appnotes.jsonl"
TI_NOTES_FILE = PROJECT_ROOT / "data" / "catalog" / "ti_appnotes.yaml"


@dataclass
class Hit:
    source: str  # "Skyworks app note", "TI app note", "Spec guide", "RF note" or "Library topic / rule / trend"
    ref: str  # AN number or note key
    title: str
    url: str
    page: int | None
    snippet: str  # HTML, matches wrapped in <mark>


def _strip_html(html: str) -> str:
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>|\{[%{#].*?[%}#]\}", " ", html))).strip()


@lru_cache
def _index() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:", check_same_thread=False)
    db.execute("CREATE VIRTUAL TABLE docs USING fts5(title, text, source UNINDEXED, ref UNINDEXED, url UNINDEXED, "
               "page UNINDEXED, tokenize='porter unicode61')")  # fmt: skip
    rows = []
    if APPNOTES_FILE.exists():
        for line in APPNOTES_FILE.read_text().splitlines():
            n = json.loads(line)
            rows.append(
                (n["title"], n["text"], "Skyworks app note", n["id"], f"{n['url']}#page={n['page']}", n["page"])
            )
    if TI_NOTES_FILE.exists():
        for n in (yamlio.load(TI_NOTES_FILE.read_text()) or {}).get("appnotes") or []:
            text = " ".join(
                [n.get("summary") or "", n.get("type") or "", (n.get("area") or "").replace("_", " "),
                 " ".join(f.replace("_", " ") for f in n.get("skyworks_qorvo_functions") or [])]
            )  # fmt: skip
            rows.append((n["title"], text, "TI app note", n["doc"], n["url"], None))
    for key, (title, summary) in NOTES.items():
        body = (NOTES_DIR / f"{key}.html").read_text() if (NOTES_DIR / f"{key}.html").exists() else ""
        rows.append((title, f"{summary} {_strip_html(body)}", "Spec guide", key, f"/engineering/{key}", None))
    from app.services import rf_notes

    for t in rf_notes.topics():
        text = " ".join([t["summary"], *(t.get("key_points") or []), *(t.get("equations") or []),
                         *(w["text"] for w in t.get("why") or [])])  # fmt: skip
        rows.append((t["title"], text, "RF note", t["id"], f"/rf-notes#{t['id']}", None))
    from app.services import library

    for tp in library.topics():
        k = tp["key"]
        rows.append((tp["title"], tp.get("summary") or "", "Library topic", k, f"/library/{k}", None))
        for r in tp.get("design_rules") or []:
            rows.append((f"{tp['title']}: {r['area']}", f"{r['rule']} {r.get('why') or ''}", "Library rule",
                         f"{k}#{r['id']}", f"/library/{k}#{r['id']}", None))  # fmt: skip
        for r in tp.get("trends") or []:
            rows.append((f"{tp['title']}: trend", f"{r['text']} {r.get('for_us') or ''}", "Library trend",
                         f"{k}#{r['id']}", f"/library/{k}#{r['id']}", None))  # fmt: skip
    db.executemany("INSERT INTO docs VALUES (?, ?, ?, ?, ?, ?)", rows)
    return db


def count() -> tuple[int, int]:
    """(application notes, pages) in the index."""
    sql = "SELECT count(DISTINCT ref), count(*) FROM docs WHERE source = 'Skyworks app note'"
    return _index().execute(sql).fetchone()


def count_ti() -> int:
    return _index().execute("SELECT count(*) FROM docs WHERE source = 'TI app note'").fetchone()[0]


def _query(q: str, op: str) -> str:
    words = re.findall(r"[\w.+-]+", q.lower())
    stop = {"what", "how", "the", "a", "an", "is", "are", "do", "does", "i", "for", "of", "to", "in", "and", "or",
            "with", "can", "should", "which", "why", "when", "my", "on", "be", "it", "about", "me"}  # fmt: skip
    terms = [w for w in words if w not in stop] or words
    return f" {op} ".join('"' + w.replace('"', "") + '"' + ("*" if len(w) > 3 else "") for w in terms)


def search(q: str, limit: int = 20, ti_limit: int = 8) -> list[Hit]:
    """All words must match; when nothing does, fall back to any word (ranked by relevance). Skyworks and Cross
    List notes come first; up to ``ti_limit`` TI notes (competitor reference) follow."""
    if not q.strip():
        return []
    db = _index()
    sql = ("SELECT source, ref, title, url, page, snippet(docs, 1, char(1), char(2), ' … ', 28) FROM docs "
           "WHERE docs MATCH ? AND (source = 'TI app note') = ? ORDER BY bm25(docs, 4.0, 1.0) LIMIT ?")  # fmt: skip
    for op in ("AND", "OR"):
        expr = _query(q, op)
        if not expr:
            return []
        rows = db.execute(sql, (expr, 0, limit)).fetchall() + db.execute(sql, (expr, 1, ti_limit)).fetchall()
        if rows:
            # PDF text is plain text: escape it, then turn the match markers into <mark>
            return [Hit(*r[:5], escape(r[5]).replace("\x01", "<mark>").replace("\x02", "</mark>")) for r in rows]
    return []
