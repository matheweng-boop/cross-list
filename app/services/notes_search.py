"""Keyword search over Skyworks application notes and the Cross List engineering notes.

Everything runs locally: an in-memory SQLite FTS5 index built once from data/appnotes.jsonl
and the engineering-note templates. Nothing is sent to an outside service.
"""

import json
import re
import sqlite3
from dataclasses import dataclass
from functools import lru_cache
from html import escape, unescape

from app.config import PROJECT_ROOT
from app.services.engineering import NOTES, NOTES_DIR

APPNOTES_FILE = PROJECT_ROOT / "data" / "appnotes.jsonl"


@dataclass
class Hit:
    source: str  # "Skyworks app note" or "Cross List note"
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
    for key, (title, summary) in NOTES.items():
        body = (NOTES_DIR / f"{key}.html").read_text() if (NOTES_DIR / f"{key}.html").exists() else ""
        rows.append((title, f"{summary} {_strip_html(body)}", "Cross List note", key, f"/engineering/{key}", None))
    db.executemany("INSERT INTO docs VALUES (?, ?, ?, ?, ?, ?)", rows)
    return db


def count() -> tuple[int, int]:
    """(application notes, pages) in the index."""
    sql = "SELECT count(DISTINCT ref), count(*) FROM docs WHERE source = 'Skyworks app note'"
    return _index().execute(sql).fetchone()


def _query(q: str, op: str) -> str:
    words = re.findall(r"[\w.+-]+", q.lower())
    stop = {"what", "how", "the", "a", "an", "is", "are", "do", "does", "i", "for", "of", "to", "in", "and", "or",
            "with", "can", "should", "which", "why", "when", "my", "on", "be", "it", "about", "me"}  # fmt: skip
    terms = [w for w in words if w not in stop] or words
    return f" {op} ".join('"' + w.replace('"', "") + '"' + ("*" if len(w) > 3 else "") for w in terms)


def search(q: str, limit: int = 20) -> list[Hit]:
    """All words must match; when nothing does, fall back to any word (ranked by relevance)."""
    if not q.strip():
        return []
    db = _index()
    sql = ("SELECT source, ref, title, url, page, snippet(docs, 1, char(1), char(2), ' … ', 28) FROM docs "
           "WHERE docs MATCH ? ORDER BY bm25(docs, 4.0, 1.0) LIMIT ?")  # fmt: skip
    for op in ("AND", "OR"):
        expr = _query(q, op)
        if not expr:
            return []
        rows = db.execute(sql, (expr, limit)).fetchall()
        if rows:
            # PDF text is plain text: escape it, then turn the match markers into <mark>
            return [Hit(*r[:5], escape(r[5]).replace("\x01", "<mark>").replace("\x02", "</mark>")) for r in rows]
    return []
