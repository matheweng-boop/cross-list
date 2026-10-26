"""Shareable > Create PowerPoint (owner, 26 Oct 2026: "how the PowerPoint is presented ... it would be good if the
formatting were generally cleaner"): the slides of each Shareable report, laid out for a screen in a room. Built
from the same content model as the PDF (app/services/share_doc.py), so the facts, numbers, part names, categories
and sources are the same; only the wording is shorter: one message per slide, a headline, the section's short slide
text (the owner's "slide" field, else the first sentence), and either number tiles, at most 5 bullets, three short
company columns or a table of at most 6 rows (a longer one continues on the next slide).

Each function takes (data, vals, today, ip_note): data is the report's build() and vals its shown values (the owner's
edits over the defaults); it returns slide dicts for app/services/presentation_pptx.build. The registry in
app/services/share_reports.py (REGISTRY) names the slide function of each report."""

from app.services import share_doc as sd

PREFIX = sd.PREFIX
TABLE_ROWS = 6  # rows per table slide before it continues on the next
COL_ITEMS = 8  # items per company column on one slide
BULLETS = 5  # bullets per slide
PAIRS = 3  # Skyworks + Qorvo pairs per slide
CELL_CHARS = 90  # a long table text is cut to its first sentence, at most this long


def head_of(vals: dict, fallback: str) -> str:
    return sd.head_of(vals, fallback)


def chunks(items: list, most: int) -> list[list]:
    """Split a list into even parts of at most `most` items (no slide with a lone last row)."""
    if len(items) <= most:
        return [items]
    n = -(-len(items) // most)
    per = -(-len(items) // n)
    return [items[i : i + per] for i in range(0, len(items), per)]


def table(head: str, title: str, cols: list[str], rows: list[list[str]], lead: str = "", note: str = "",
          widths: tuple[float, ...] = (), who_cols: tuple[int, ...] = ()) -> list[dict]:  # fmt: skip
    """One native table slide of at most TABLE_ROWS rows, continued on more slides when longer."""
    parts = chunks(rows, TABLE_ROWS)
    out = []
    for n, chunk in enumerate(parts):
        out.append({"kind": "table", "head": head, "title": title + (" (continued)" if n else ""),
                    "body": {"lead": lead, "cols": cols, "rows": chunk, "widths": list(widths),
                             "who_cols": list(who_cols), "note": note if n == len(parts) - 1 else ""}})  # fmt: skip
    return out


def bullets(head: str, title: str, points: list[str], lead: str = "") -> list[dict]:
    parts = chunks([p for p in points if p], BULLETS)
    return [{"kind": "bullets", "head": head, "title": title + (" (continued)" if n else ""),
             "body": {"lead": lead if not n else "", "points": c}} for n, c in enumerate(parts)]  # fmt: skip


def _short(text: str) -> str:
    return sd.first_sentence(text, CELL_CHARS)


def _cell_text(c: dict, first: bool) -> str:
    t = c["t"] if first else _short(c["t"])
    return " · ".join(x for x in (t, ", ".join(c["code"]), *(m for m, _ in c["marks"])) if x)


def _block(head: str, title: str, lead: str, b: dict) -> list[dict]:
    kind = b["kind"]
    if kind == "facts":
        return [{"kind": "glance", "head": head, "title": title,
                 "body": {"lead": lead, "facts": [{"num": f["num"], "label": f["label"], "note": f.get("note", "")}
                                                  for f in b["items"]]}}]  # fmt: skip
    if kind == "table":
        rows = [[_cell_text(c, i == 0) for i, c in enumerate(r)] for r in b["rows"]]
        who = tuple(range(1, len(b["cols"]))) if b.get("dots") else tuple(
            i for i in range(len(b["cols"])) if b["rows"] and all(not r[i]["t"] and r[i]["marks"] for r in b["rows"]))
        return table(head, title, list(b["cols"]), rows, lead, b.get("note", ""), tuple(b.get("widths") or ()), who)
    if kind == "cols":
        parts = chunks(list(range(max(len(c["items"]) for c in b["cols"]))), COL_ITEMS)
        out = []
        for n, idx in enumerate(parts):
            cols = [{"who": c["who"], "head": f"{c['head']} ({c['count']})" if c["count"] else c["head"],
                     "line": " · ".join(x for x in (c["line"], c["tag"]) if x) if not n else "",
                     "items": [" · ".join([c["items"][i]["t"], *(m for m, _ in c["items"][i]["marks"])])
                               for i in idx if i < len(c["items"])]} for c in b["cols"]]  # fmt: skip
            out.append({"kind": "cols", "head": head, "title": title + (" (continued)" if n else ""),
                        "body": {"lead": lead if not n else "", "cols": cols,
                                 "note": b.get("note", "") if n == len(parts) - 1 else ""}})  # fmt: skip
        return out
    if kind == "pairs":
        parts = chunks(b["items"], PAIRS)
        return [{"kind": "pairs", "head": head, "title": title + (" (continued)" if n else ""),
                 "body": {"lead": lead if not n else "",
                          "items": [{**p, "line": sd.first_sentence(p["line"], 130)} for p in c],
                          "note": b.get("note", "") if n == len(parts) - 1 else ""}}
                for n, c in enumerate(parts)]  # fmt: skip
    if kind == "links":
        return bullets(head, b["head"], b["items"])
    return []


def from_doc(d: dict, today=None, sub: str = "") -> list[dict]:
    """The slides of one report's content model: a cover, one slide (or more) per block, the sources."""
    h = d["head"]
    slides = [{"kind": "title", "head": h, "title": d["title"],
               "body": {"heading": d["title"], "sub": sub or d["kicker"], "date": today}}]  # fmt: skip
    for s in d["sections"]:
        title = s["heading"] or d["title"]
        for i, b in enumerate(s["blocks"]):
            slides += _block(h, title, s["slide"] if i == 0 else "", b)
    slides += bullets(h, "Sources", [*d["sources"], d["prepared"]])
    return slides


def _slides(key: str, sub: str = ""):
    def make(data: dict, vals: dict, today=None, ip_note: str = "") -> list[dict]:
        return from_doc(sd.doc(key, data, vals, today, ip_note), today, sub)

    return make


synergies = _slides("synergies", "Management brief")
automotive = _slides("automotive", "Extension of: Skyworks + Qorvo synergies")
overview = _slides("overview", "Technology overview")
