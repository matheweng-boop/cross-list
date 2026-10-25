"""Shareable > Presentation builder (owner, 25 Oct 2026): "select different topics, for example UWB, where I can also
select the associated technical knowledge ... each a separate selected section ... 'preview' to see what the
presentation is going to show, section by section."

Topics come from the data, never a hand-made list: the Systems library deep dives (data/library/topics), the systems'
sub-systems without a deep dive (data/blocks/systems.yaml) and the technology platforms (data/business/
tech_overview.yaml). Each topic offers sections (overview, diagram, our parts, Skyworks + Qorvo together, key facts)
and its technical knowledge: the specification guides and RF notes the library, knowledge-by-product and the guides
themselves link to the topic, one section per note. A few general sections (title, agenda, at a glance, closing) are
always there.

Share-safety: library topics hold internal material (opportunities, competitors, design rules with confidence, open
questions, our estimates). Only public fields are read (summary, why it matters to the customer, architecture,
standards, our parts); every sentence and bullet goes through the Shareable word check (share_reports.synergy_problems
plus a few words of this page), anything marked est is left out, and a section whose slides still fail is not offered.
Counts are rounded (text.round_count); specifications are exact.

A section is one or more slides: when it holds more than one 16:9 slide carries at a readable size, it continues on
the next slide ("UWB signal path (2/2)"). Saved decks (owner only) are PageTextVersion rows with page "deck:<slug>",
the same storage as the report overrides.
"""

import math
import re
from datetime import date
from functools import lru_cache
from html.parser import HTMLParser

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PageTextVersion, utcnow
from app.services import blocks, engineering, knowledge, rf_bands, rf_notes, systems, vocab
from app.services import library as lib
from app.services import portfolio as pf
from app.services import share_reports as sr
from app.services import tech_overview as to
from app.services.text import round_count, short_description, whole_words

URL = "/shareable/presentation"
PAGE_PREFIX = "deck:"
GENERAL = (("title", "Title"), ("agenda", "Agenda"), ("glance", "Skyworks + Qorvo at a glance"),
           ("closing", "Closing and contact"))  # fmt: skip
KINDS = (("overview", "Overview"), ("diagram", "System / block diagram"), ("parts", "Our parts"),
         ("together", "Skyworks + Qorvo together"), ("facts", "Key facts and standards"))  # fmt: skip
TITLE_KIND = {"diagram": "system diagram", "parts": "our parts", "together": "Skyworks + Qorvo together",
              "facts": "key facts and standards"}  # fmt: skip
DEFAULT_TITLE = "Skyworks + Qorvo"
DEFAULT_CLOSING = "Thank you. For samples, data sheets and design support, contact your Skyworks sales representative."
DEFAULT_CONTACT = "skyworksinc.com · qorvo.com"
TITLE_MAX, TEXT_MAX, NAME_MAX = 90, 300, 60

# ---- share-safety ---------------------------------------------------------------------------------------------------
# On top of the Shareable reports' check: words that point at prices, internal planning or our own reading.
EXTRA = ("price", "pricing", "opportunity", "open question", "last-time-buy", "last time buy", "our reading",
         "our inference", "our estimate", "BizDev", "case", "cases", "lobbying", "threat", "attacker")  # fmt: skip


# references to our own notes and reviews ("library d12", "the owner's rule", "confirmed 23 Oct 2026")
_INTERNAL_REF = re.compile(
    r"\b(?:owner|owner's|library\s+(?:rule\s+)?d\d+|rules?\s+d\d+|d\d{1,2}\b(?=[ ,;)])|"
    r"confirmed\s+\d|repo|daily run)",
    re.I,
)


def problems(text: str) -> list[str]:
    """Why a slide text cannot be shown (empty: fine): the Shareable reports' check plus this page's words."""
    out = sr.synergy_problems(text)
    out += [f"“{w}” does not belong on a public slide." for w in whole_words(text, EXTRA, plural=True)]
    out += [f"“{m.group(0)}” refers to our own notes." for m in _INTERNAL_REF.finditer(text)]
    return out


def safe(text: str) -> bool:
    return not problems(text)


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9(“\"])")
_EST = "⁣EST⁣"


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(" ".join(str(text or "").split())) if s.strip()]


def safe_sentences(text: str, limit: int = 0) -> list[str]:
    out = [s for s in sentences(text) if _EST not in s and safe(s) and not re.search(r"\best\b", s)]
    return out[:limit] if limit else out


def clean(items) -> list[str]:
    """Bullets that pass the check, without duplicates, in order."""
    seen, out = set(), []
    for x in items:
        x = " ".join(str(x or "").split())
        if x and x not in seen and safe(x):
            seen.add(x)
            out.append(x)
    return out


# ---- spec guide bodies (Jinja/HTML) to key points -------------------------------------------------------------------
class _Points(HTMLParser):
    SKIP = {"table", "form", "fieldset", "script", "style", "svg", "figure", "details", "canvas", "select", "button"}

    def __init__(self):
        super().__init__()
        self.skip, self.cur, self.items, self.tag = 0, [], [], None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        cls = a.get("class") or ""
        if (
            self.skip
            or tag in self.SKIP
            or "viz" in cls
            or "impact" in cls
            or (tag == "p" and ("small" in cls or "muted" in cls))
        ):
            if tag not in ("br", "input", "img", "hr"):
                self.skip += 1
            return
        if tag in ("p", "li", "h2", "h3"):
            self.flush()
            self.tag = tag

    def handle_endtag(self, tag):
        if self.skip:
            if tag not in ("br", "input", "img", "hr"):
                self.skip -= 1
            return
        if tag in ("p", "li", "h2", "h3"):
            self.flush()

    def handle_data(self, data):
        if not self.skip and self.tag:
            self.cur.append(data)

    def flush(self):
        if self.tag and self.cur:
            self.items.append((self.tag, " ".join("".join(self.cur).split())))
        self.cur, self.tag = [], None


@lru_cache
def guide_points(key: str, limit: int = 8) -> tuple[str, ...]:
    """A specification guide condensed to slide-size points: the first sentence of each paragraph and list item that
    passes the check (BizDev's own reasoning, marked est, left out)."""
    path = engineering.NOTES_DIR / f"{key}.html"
    if not path.exists():
        return ()
    raw = path.read_text()
    raw = re.sub(r"\{\{\s*est\|safe\s*\}\}", _EST, raw)
    raw = re.sub(r"\{%.*?%\}|\{\{.*?\}\}|\{#.*?#\}", " ", raw, flags=re.S)
    p = _Points()
    p.feed(raw)
    p.flush()
    out = []
    for tag, text in p.items:
        if tag in ("h2", "h3"):
            continue
        first = next(iter(safe_sentences(text)), "")
        if 25 <= len(first) <= 240:
            first = first.rstrip(":")
            out.append(first if first[-1] in ".!?)" else first + ".")
    return tuple(clean(out)[:limit])


# ---- knowledge items (one selectable section each) ------------------------------------------------------------------
@lru_cache
def _rf() -> dict[str, dict]:
    return {t["id"]: t for t in rf_notes.topics()}


def _why_points(points) -> list[str]:
    return [w.get("text", "") for w in points or [] if not w.get("est")]


@lru_cache
def note(nid: str) -> dict | None:
    """A knowledge section: {id, title, lead, points}; None when the note is unknown or nothing public remains."""
    if nid in engineering.NOTES:
        title, summary = engineering.NOTES[nid]
        why = [p for g in knowledge.why(nid) for p in _why_points(g["points"])]
        lead = " ".join(safe_sentences(summary, 1))
        points = clean(why[:3] + list(guide_points(nid)))[:7]
    elif nid in _rf():
        t = _rf()[nid]
        title = t["title"]
        lead = " ".join(safe_sentences(t.get("summary", ""), 2))
        points = clean(list(t.get("key_points") or [])[:5] + _why_points(t.get("why"))[:2])[:7]
    else:
        return None
    if not safe(title) or not points:
        return None
    return {"id": nid, "title": title, "lead": lead, "points": points}


def _note_id(href: str) -> str:
    return href.split("#", 1)[1] if "#" in href else href.rstrip("/").rsplit("/", 1)[-1]


@lru_cache
def _guides_linking(key: str) -> tuple[str, ...]:
    """Specification guides whose page links to the library topic."""
    return tuple(k for k in engineering.NOTES if (p := engineering.NOTES_DIR / f"{k}.html").exists()
                 and f"/library/{key}" in p.read_text())  # fmt: skip


def knowledge_for_library(key: str) -> list[str]:
    """Note ids for a library topic: guides that link to it, then the knowledge-by-product guides and RF notes of the
    product families that list it, then the notes the topic's own text leans on (library.related)."""
    ids = list(_guides_linking(key))
    for p in knowledge.data().get("products") or []:
        if key in (p.get("topics") or []):
            ids += list(p.get("why") or []) + list(p.get("rf_notes") or [])
    ids += [_note_id(k["href"]) for k in lib.related(key)["knowledge"]]
    return _dedupe_notes(ids)


def _dedupe_notes(ids, limit: int = 10) -> list[str]:
    out = []
    for i in ids:
        if i not in out and note(i):
            out.append(i)
    return out[:limit]


# ---- slides ---------------------------------------------------------------------------------------------------------
# Slide budget at the slide's fixed type size (static/presentation.css): about 80 characters a line and 12 lines of
# body text; a section that needs more continues on the next slide. Tables and diagrams split by rows and groups.
LINE_CHARS, BODY_LINES, LEAD_LINES = 80, 12, 3
ROWS, PAIRS, GROUPS, DIAGRAM_HEIGHT = 6, 4, 8, 31.0


def _lines(text: str, chars: int = LINE_CHARS) -> float:
    return math.ceil(len(text) / chars) + 0.3


def split_bullets(lead: str, points: list[str]) -> list[dict]:
    """Bullets over as many slides as they need; the lead paragraph only on the first."""
    pages, cur, used = [], [], _lines(lead) if lead else 0
    for p in points:
        n = _lines(p, LINE_CHARS - 4)
        if cur and used + n > BODY_LINES:
            pages.append(cur)
            cur, used = [], 0
        cur.append(p)
        used += n
    pages.append(cur)
    return [{"lead": lead if i == 0 else "", "points": pg} for i, pg in enumerate(pages)]


def _chunks(items: list, n: int) -> list[list]:
    return [items[i : i + n] for i in range(0, len(items), n)] or [[]]


# ---- topics ---------------------------------------------------------------------------------------------------------
def _short(title: str) -> str:
    t = re.split(r" - |: ", title)[0]
    return t if len(t) <= 60 else t[:60].rsplit(" ", 1)[0] + "…"


def _fn_label(fn: str) -> str:
    return vocab.fn_label(re.sub(r"\s+x\d+$", "", str(fn)))


@lru_cache
def _active() -> dict[str, dict]:
    return {r["mpn"].upper(): r for r in to.active_rows()}


def _aec(row: dict) -> bool:
    return sr._qualified(row)


def _part(mpn: str) -> dict | None:
    r = _active().get(str(mpn).upper())
    if not r:
        return None
    return {"mpn": r["mpn"], "line": r["manufacturer"], "aec": _aec(r),
            "spec": short_description(r["function"], "", "automotive" if _aec(r) else None, r.get("key_specs") or {},
                                      None, r.get("description") or "")}  # fmt: skip


def _fn_counts(fn: str, automotive: bool) -> dict[str, int]:
    out = {}
    for line in pf.LINES:
        mpns = {p["mpn"].upper() for p in blocks.catalog_parts().get(vocab.canonical(fn) or fn, [])
                if p["manufacturer"] == line and not p.get("risk")}  # fmt: skip
        rows = [_active()[m] for m in mpns if m in _active()]
        out[line] = sum(1 for r in rows if _aec(r)) if automotive else len(rows)
    return out


def _parts_rows(fit: list[tuple[str, list[str]]], automotive: bool) -> list[dict]:
    """One row per function: its label, up to three named parts per line (AEC-Q marked) and the rounded number of
    active parts each line has for it."""
    rows = []
    for fn, named in fit:
        parts = [p for m in named if (p := _part(m))]
        if automotive and any(p["aec"] for p in parts):
            parts.sort(key=lambda p: not p["aec"])
        by = {line: [p for p in parts if p["line"] == line][:3] for line in pf.LINES}
        if not any(by.values()):
            continue
        counts = _fn_counts(fn, automotive)
        label = _fn_label(fn)
        if not safe(label):
            continue
        rows.append({"fn": label, "parts": by, "counts": {k: round_count(v) for k, v in counts.items() if v},
                     "aec_word": "AEC-Q" if automotive else ""})  # fmt: skip
    return rows


def _series_for(fns: list[str], automotive: bool, per_line: int = 2) -> list[tuple[str, list[str]]]:
    """Representative parts for functions of a diagram (no curated list): the first active parts per line, AEC-Q
    first in automotive."""
    out = []
    for fn in fns:
        cands = [p for p in blocks.catalog_parts().get(fn, []) if not p.get("risk") and p["mpn"].upper() in _active()]
        if automotive:
            cands.sort(key=lambda p: not _aec(_active()[p["mpn"].upper()]))
        picked = []
        for line in pf.LINES:
            picked += [p["mpn"] for p in cands if p["manufacturer"] == line][:per_line]
        if picked:
            out.append((fn, picked))
    return out


_STD = re.compile(r"\b(?:IEEE\s(?:Std\s)?\d{3,4}(?:\.\d+[a-z]*)*(?:-\d{4})?|ETSI\s(?:EN|TS)\s\d{3}\s\d{3}(?:-\d+)*|"
                  r"AEC-Q\d{3}|ISO\s\d{4,5}(?:-\d+)?|IEC\s\d{4,5}(?:-\d+)*|CISPR\s\d+|SAE\sJ\d+|3GPP\s(?:Rel(?:ease)?\.?"
                  r"\s?\d+|TS\s\d+\.\d+(?:-\d)?)|UL\s\d{4}|ASIL[- ][A-D]|DO-\d{3}[A-Z]?|RTCA\s[A-Z]+-\d+|"
                  r"Remote ID|CCC Digital Key|FiRa|802\.\d+[a-z]*(?:\.\d+[a-z]*)?)\b")  # fmt: skip


def standards_in(text: str, limit: int = 8) -> list[str]:
    out = []
    for m in _STD.finditer(text):
        s = m.group(0)
        if s.startswith("802."):
            s = "IEEE " + s
        if s not in out and safe(s):
            out.append(s)
    return out[:limit]


@lru_cache
def _band_terms() -> tuple[tuple[dict, tuple[str, ...]], ...]:
    out = []
    for b in rf_bands.data().get("bands") or []:
        name = re.sub(r"\(.*?\)", "", b["name"])
        terms = tuple(t for t in re.findall(r"\b(?:[A-Z][A-Za-z0-9+-]*[A-Z0-9+]|Wi-Fi \d|Bluetooth)\b", name)
                      if t not in ("MHz", "GHz", "ISM", "SRD", "EU", "US", "UHF", "HF", "TV", "PS", "DD", "APT", "AWS",
                                   "IMT", "PCS", "DCS", "SDL", "GSM", "TDD", "FDD", "ITS"))  # fmt: skip
        if terms:
            out.append((b, terms))
    return tuple(out)


def bands_in(text: str, min_hits: int = 2, limit: int = 6) -> list[str]:
    """Frequency bands (data/engineering_rf_bands.yaml) a text names: 'UWB channel 9 (8 GHz): 7738-8237 MHz'."""
    scored = []
    for b, terms in _band_terms():
        n = sum(len(re.findall(rf"(?<![\w-]){re.escape(t)}(?![\w-])", text)) for t in terms)
        if n >= min_hits:
            scored.append((n, b))
    scored.sort(key=lambda x: -x[0])
    out = []
    for _, b in scored[:limit]:
        rng = ", ".join(f"{_mhz(lo)}-{_mhz(hi)} MHz" for lo, hi, *_ in b["ranges"])
        line = f"{b['name']}: {rng}"
        if safe(line):
            out.append(line)
    return out


def _mhz(v: float) -> str:
    return f"{v:g}"


def _diagram_groups(groups: list[dict], ours: set[str]) -> list[dict]:
    out = []
    for g in sorted(groups or [], key=lambda g: (g.get("row", 0), g.get("col", 0))):
        label = " ".join(str(g.get("label", "")).split())
        if not safe(label):
            continue
        bl = []
        for b in g.get("blocks") or []:
            fn = b["fn"] if isinstance(b, dict) else re.sub(r"\s+x\d+$", "", str(b))
            text = (b.get("label") if isinstance(b, dict) else "") or _fn_label(fn)
            if safe(text):
                bl.append({"label": text, "ours": vocab.canonical(fn) in ours or fn in ours})
        if bl:
            out.append({"label": label, "blocks": bl, "col": g.get("col", 0), "row": g.get("row", 0)})
    return out


def _row_height(grp: list[dict], cols: int) -> float:
    """Estimated height of a diagram row in slide units (cqw): the tallest group, its blocks flowing in lines of
    about 30 characters at the diagram's type size (wider when there are fewer columns)."""
    per_line = max(30 * 4 / max(cols, 1), 24)
    tallest = max(math.ceil(len(g["label"]) / per_line) * 2.2 + math.ceil(sum(len(b["label"]) + 5 for b in
                  g["blocks"]) / per_line) * 3.0 for g in grp)  # fmt: skip
    return tallest + 3.5


def _diagram_slides(name: str, groups: list[dict]) -> list[dict]:
    """Rows of the diagram over as many slides as they need (about DIAGRAM_HEIGHT slide units each)."""
    rows = sorted({g["row"] for g in groups})
    cols = max(g["col"] for g in groups) - min(g["col"] for g in groups) + 1 if groups else 1
    pages, cur, used = [], [], 0.0
    for r in rows:
        grp = [g for g in groups if g["row"] == r]
        h = _row_height(grp, cols)
        if cur and (len(cur) + len(grp) > GROUPS or used + h > DIAGRAM_HEIGHT):
            pages.append(cur)
            cur, used = [], 0.0
        cur += grp
        used += h
    if cur:
        pages.append(cur)
    out = []
    for pg in pages:
        cols = max(g["col"] for g in pg) - min(g["col"] for g in pg) + 1
        out.append({"name": name, "groups": pg, "cols": min(max(cols, 1), 5)})
    return out


def _pairs_for(idx: list[int], automotive: bool) -> list[dict]:
    if not idx:
        return []
    lines = (sr.curated().get("synergies") or {}).get("pairs") or {}

    def pick(ps: list[dict]) -> str:
        """The example part of a line: AEC-Q qualified first in automotive."""
        ok = (p["mpn"] for p in ps if not automotive or _aec(_active().get(p["mpn"].upper(), {})))
        return next(ok, ps[0]["mpn"] if ps else "")

    out = []
    for x in pf.together_in(idx)["synergies"]:
        if x["weak"]:
            continue
        key = f"{x['skyworks']} + {x['qorvo']}"
        line = " ".join(str(x["reason"] or lines.get(key) or "").split())
        line = " ".join(safe_sentences(line, 2))
        item = {"skyworks": x["skyworks_label"], "qorvo": x["qorvo_label"], "line": line,
                "s_ex": pick(x["skyworks_parts"]), "q_ex": pick(x["qorvo_parts"]),
                "n": round_count(x["n"])}  # fmt: skip
        if safe(" ".join(str(v) for v in item.values())):
            out.append(item)
        if len(out) >= 8:
            break
    return out


def _diagram_pairs(groups: list[dict], fit: list[tuple[str, list[str]]], automotive: bool) -> list[dict]:
    """When the sub-system's library diagrams give no pair: Skyworks and Qorvo parts named for blocks of the same group
    of the topic's own diagram (the anchor, the front end), one pair per group."""
    named = {vocab.canonical(fn) or fn: [p for m in ms if (p := _part(m))] for fn, ms in fit}
    out = []
    for g in groups:
        fns = [vocab.canonical(b["fn"] if isinstance(b, dict) else str(b)) for b in g.get("blocks") or []]
        side = {}
        for line in pf.LINES:
            taken = [v[0] for v in side.values()]
            for fn in sorted(fns, key=lambda f: f in taken):
                ps = [p for p in named.get(fn, []) if p["line"] == line]
                if automotive:
                    ps.sort(key=lambda p: not p["aec"])
                if ps and line not in side:
                    side[line] = (fn, ps[0])
        if len(side) < 2 or side["Skyworks"][0] == side["Qorvo"][0]:
            continue
        (sfn, sp), (qfn, qp) = side["Skyworks"], side["Qorvo"]
        label = " ".join(re.sub(r"\(.*?\)", "", str(g.get("label", ""))).split())
        where = label[0].lower() + label[1:] if label and not label[:2].isupper() else label or "same block"
        item = {"skyworks": _fn_label(sfn), "qorvo": _fn_label(qfn), "s_ex": sp["mpn"], "q_ex": qp["mpn"], "n": "",
                "line": f"Both sit in the {where}: one design-in covers the {_fn_label(sfn)} and the "
                        f"{_fn_label(qfn)}."}  # fmt: skip
        if safe(" ".join(item.values())):
            out.append(item)
    return out


@lru_cache
def topics() -> tuple[dict, ...]:
    """Every topic, grouped: {id, group, title, sections: {kind: content}, notes: [note ids], source}."""
    out = []
    by_place: dict[tuple[str, str], list[dict]] = {}
    for t in lib.topics():
        place = systems.topic_place(t["key"])
        by_place.setdefault(place or ("other", ""), []).append(t)
    for s in systems.systems():
        auto = s["key"] == "automotive"
        for x in s["subsystems"]:
            for t in by_place.get((s["key"], x["key"]), []):
                out.append(_library_topic(t, s["title"], x, auto))
            if not by_place.get((s["key"], x["key"])):
                out.append(_subsystem_topic(s, x, auto))
    for t in by_place.get(("other", ""), []):
        out.append(_library_topic(t, "Other topics", None, False))
    for p in to.build()["platforms"]:
        out.append(_platform_topic(p))
    return tuple(out)


def _overview(title: str, lead: str, bullets: list[str]) -> list[dict] | None:
    bullets = clean(bullets)
    if not lead and not bullets:
        return None
    return split_bullets(lead, bullets)


def _library_topic(t: dict, group: str, sub: dict | None, automotive: bool) -> dict:
    key = t["key"]
    short = _short(t["title"])
    secs: dict[str, list[dict]] = {}
    summ = safe_sentences(t.get("summary", ""))
    ov = _overview(short, " ".join(summ[:2]), summ[2:5] + list(t.get("why_customer") or []))
    if ov:
        secs["overview"] = ov
    d = t.get("block_diagram") or {}
    fit = [(s["fn"], list(s.get("parts") or [])) for s in t.get("skyworks_fit") or []]
    ours = {vocab.canonical(fn) for fn, _ in fit} | {fn for fn, _ in fit}
    groups = _diagram_groups(d.get("groups") or [], ours)
    if groups:
        name = d.get("name") if safe(str(d.get("name", ""))) else "Block diagram"
        secs["diagram"] = _diagram_slides(name, groups)
    rows = _parts_rows(fit, automotive)
    if rows:
        secs["parts"] = [{"rows": c, "automotive": automotive} for c in _chunks(rows, ROWS)]
    idx = list(sub["idx"]) if sub else []
    pairs = _pairs_for(idx, automotive) or _diagram_pairs(d.get("groups") or [], fit, automotive)
    if pairs:
        secs["together"] = [{"pairs": c} for c in _chunks(pairs, PAIRS)]
    public = " ".join([t.get("title", ""), t.get("summary", ""), d.get("name", ""), d.get("note", ""),
                       " ".join(r.get("title", "") for r in t.get("references") or [] if r.get("type") == "standard"),
                       " ".join(t.get("why_customer") or [])])  # fmt: skip
    facts = _facts(public, [m for _, ms in fit for m in ms], automotive)
    if facts:
        secs["facts"] = facts
    return _topic(key, group, short, secs, knowledge_for_library(key), f"/library/{key}")


def _facts(text: str, mpns: list[str], automotive: bool, min_hits: int = 2) -> list[dict] | None:
    stds = standards_in(text)
    bands = bands_in(text, min_hits=min_hits)
    specs = []
    for m in mpns:
        p = _part(m)
        if p and p["spec"] and (not automotive or p["aec"]) and safe(p["spec"]):
            specs.append(f"{p['mpn']}: {p['spec']}")
    specs = specs[:4]
    if not (stds or bands or specs):
        return None
    pages = []
    cur = {"standards": stds, "bands": bands, "specs": specs}
    if len(stds) + len(bands) + len(specs) > 12:
        pages = [{"standards": stds, "bands": bands, "specs": []}, {"standards": [], "bands": [], "specs": specs}]
    else:
        pages = [cur]
    return pages


def _subsystem_topic(s: dict, x: dict, automotive: bool) -> dict:
    title = x["title"]
    secs: dict[str, list[dict]] = {}
    curated = ((sr.curated().get("automotive") or {}).get("subsystems") or {}).get(x["key"]) or {}
    lead = " ".join(safe_sentences(curated.get("line") or x.get("summary", ""), 2))
    ov = _overview(title, lead, [f"Built from: {', '.join(x['elements'])}."] if x["elements"] else [])
    if ov:
        secs["overview"] = ov
    tpl = [blocks.templates()[i] for i in x["idx"]]
    fns: list[str] = []
    for tp in tpl:
        for g in tp.get("groups") or []:
            for b in g.get("blocks") or []:
                fn = vocab.canonical(re.sub(r"\s+x\d+$", "", b if isinstance(b, str) else b.get("fn", "")))
                if fn and fn not in fns:
                    fns.append(fn)
    ours = {fn for fn in fns if any(not p.get("risk") for p in blocks.catalog_parts().get(fn, []))}
    if tpl:
        groups = _diagram_groups(tpl[0].get("groups") or [], ours)
        if groups:
            name = blocks.display_name(tpl[0])
            secs["diagram"] = _diagram_slides(name if safe(name) else title, groups)
    elif x["elements"]:
        secs["diagram"] = [
            {
                "name": title,
                "groups": [
                    {
                        "label": title,
                        "col": 0,
                        "row": 0,
                        "blocks": [{"label": e, "ours": False} for e in x["elements"] if safe(e)],
                    }
                ],
                "cols": 1,
            }
        ]
    series = curated.get("series") or []
    if automotive and series:
        fit = []
        for se in series:
            rows = [r for r in sr.series_rows(se) if _aec(r)]
            if rows:
                fit.append((rows[0]["function"], [r["mpn"] for r in rows[:3]]))
    else:
        fit = _series_for([fn for fn in fns if fn in ours][:10], automotive)
    rows = _parts_rows(fit, automotive)
    if rows:
        secs["parts"] = [{"rows": c, "automotive": automotive} for c in _chunks(rows, ROWS)]
    pairs = _pairs_for(list(x["idx"]), automotive)
    if pairs:
        secs["together"] = [{"pairs": c} for c in _chunks(pairs, PAIRS)]
    text = " ".join([title, x.get("summary", ""), " ".join(x["elements"]), lead] + [tp.get("name", "") for tp in tpl])
    facts = _facts(text, [m for _, ms in fit for m in ms], automotive, min_hits=1)
    if facts:
        secs["facts"] = facts
    notes = _dedupe_notes([_note_id(k["href"]) for k in lib.related_to(text, min_hits=1, limit=5)["knowledge"]], 5)
    tid = x["key"] if x["key"] not in {t["key"] for t in lib.topics()} else f"sub-{x['key']}"
    return _topic(tid, s["title"], title, secs, notes, f"/blocks?system={s['key']}&sub={x['key']}")


def _platform_topic(p: dict) -> dict:
    secs: dict[str, list[dict]] = {}
    who = {"Both": "Skyworks and Qorvo", "Skyworks": "Skyworks", "Qorvo": "Qorvo"}.get(p.get("owner", ""), "")
    lead = " ".join(safe_sentences(p.get("what", ""), 2))
    bullets = [p.get("good_for", "")] + ([f"Held by {who}."] if who else [])
    bullets += [f"Product families: {', '.join(p.get('families') or [])}."] if p.get("families") else []
    ov = _overview(p["label"], lead, bullets)
    if ov:
        secs["overview"] = ov
    text = " ".join(str(p.get(k, "")) for k in ("label", "what", "good_for"))
    facts = _facts(text, [], False, min_hits=1)
    if facts:
        secs["facts"] = facts
    notes = _dedupe_notes([_note_id(k["href"]) for k in lib.related_to(text, min_hits=1, limit=4)["knowledge"]], 4)
    return _topic(
        f"tech-{p['key']}",
        "Technology platforms",
        p["label"],
        secs,
        notes,
        URL.rsplit("/", 1)[0] + "/technology-overview",
    )


def _topic(tid: str, group: str, title: str, secs: dict, notes: list[str], source: str) -> dict:
    """Keep only sections whose every slide passes the check; the rest go to `left_out`."""
    ok, left = {}, []
    if not safe(title):
        return {"id": tid, "group": group, "title": title, "sections": {}, "notes": [], "source": source,
                "left_out": [f"{title}: the whole topic"]}  # fmt: skip
    for kind, label in KINDS:
        if kind not in secs:
            continue
        if all(safe(_slide_text(s)) for s in secs[kind]):
            ok[kind] = secs[kind]
        else:
            left.append(f"{title}: {label}")
    return {"id": tid, "group": group, "title": title, "sections": ok, "notes": notes, "source": source,
            "left_out": left}  # fmt: skip


def _slide_text(x) -> str:
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return " ".join(_slide_text(v) for k, v in x.items() if k not in ("ours", "automotive", "col", "row", "cols"))
    if isinstance(x, list | tuple):
        return " ".join(_slide_text(v) for v in x)
    return ""


@lru_cache
def topic_index() -> dict[str, dict]:
    return {t["id"]: t for t in topics() if t["sections"] or t["notes"]}


def groups() -> list[tuple[str, list[dict]]]:
    out: dict[str, list[dict]] = {}
    for t in topics():
        if not (t["sections"] or t["notes"]):
            continue
        out.setdefault(t["group"], []).append(t)
    return list(out.items())


def left_out() -> list[str]:
    return [x for t in topics() for x in t["left_out"]]


# ---- sections and the selection in the address ----------------------------------------------------------------------
def section_title(sid: str) -> str | None:
    """The default title of a section id ('auto_uwb.overview', 'note.uwb_signal_path', 'title'); None if unknown."""
    if sid in dict(GENERAL):
        return dict(GENERAL)[sid]
    head, _, kind = sid.partition(".")
    if head == "note":
        n = note(kind)
        return n["title"] if n else None
    t = topic_index().get(head)
    if not t or kind not in t["sections"]:
        return None
    return t["title"] if kind == "overview" else f"{t['title']}: {TITLE_KIND[kind]}"


def known(sid: str) -> bool:
    return section_title(sid) is not None


def parse(raw: str) -> list[str]:
    """?s=title,auto_uwb.overview,note.uwb_signal_path -> the known section ids in order, each once."""
    out = []
    for x in re.split(r"[,\s]+", raw or ""):
        x = x.strip()
        if x and x not in out and len(out) < 80 and known(x):
            out.append(x)
    return out


def query(ids: list[str]) -> str:
    return ",".join(ids)


def topic_of(sid: str) -> str:
    head = sid.partition(".")[0]
    return head if head in topic_index() else ""


def selected_topics(ids: list[str]) -> list[str]:
    """Topics open in the builder: those with a selected section, plus those a selected note belongs to."""
    return list(dict.fromkeys(h for s in ids if (h := topic_of(s))))


# ---- building the slides --------------------------------------------------------------------------------------------
def build(ids: list[str], deck: dict | None = None) -> list[dict]:
    """The slides of a selection, in order: {sid, kind, title, part: (i, n), body}."""
    deck = deck or {}
    titles = deck.get("titles") or {}
    topics_named = [topic_index()[h]["title"] for h in selected_topics(ids)]
    slides = []
    for sid in ids:
        base = (titles.get(sid) or section_title(sid) or "").strip()
        bodies = _bodies(sid, ids, deck, topics_named)
        for i, b in enumerate(bodies):
            n = len(bodies)
            title = f"{base} ({i + 1}/{n})" if n > 1 else base
            slides.append({"sid": sid, "kind": b.pop("kind"), "title": title, "part": (i + 1, n), "body": b})
    return [s for s in slides if safe(s["title"] + " " + _slide_text(s["body"]))]


def _bodies(sid: str, ids: list[str], deck: dict, topics_named: list[str]) -> list[dict]:
    if sid == "title":
        sub = deck.get("subtitle") or (" · ".join(topics_named[:4]) if topics_named else "Technology and products")
        return [{"kind": "title", "heading": deck.get("title") or DEFAULT_TITLE, "sub": sub,
                 "date": date.today()}]  # fmt: skip
    if sid == "agenda":
        names = [(deck.get("titles") or {}).get(x) or section_title(x) for x in ids
                 if x not in ("title", "agenda", "closing")]  # fmt: skip
        pages, start = [], 1
        for pg in split_bullets("", [n for n in names if n]):
            pages.append({"kind": "agenda", "start": start, **pg})
            start += len(pg["points"])
        return pages
    if sid == "glance":
        g = sr.build_synergies()
        facts = [{"num": round_count(int(f["num"].replace(",", ""))), "label": f["label"]} for f in g["facts"]
                 if f["label"]]  # fmt: skip
        pairs = [f"{p['skyworks']} + {p['qorvo']}" for p in g["pairs"][:4]]
        return [{"kind": "glance", "facts": facts, "pairs": clean(pairs),
                 "lead": " ".join(safe_sentences((g["cur"] or {}).get("lead", ""), 2))}]  # fmt: skip
    if sid == "closing":
        return [{"kind": "closing", "text": deck.get("closing") or DEFAULT_CLOSING,
                 "contact": deck.get("contact") or DEFAULT_CONTACT}]  # fmt: skip
    head, _, kind = sid.partition(".")
    if head == "note":
        n = note(kind)
        return [{"kind": "bullets", **pg} for pg in split_bullets(n["lead"], n["points"])]
    t = topic_index()[head]
    return [{"kind": kind if kind != "overview" else "bullets", **dict(pg)} for pg in t["sections"][kind]]


def all_section_ids() -> list[str]:
    ids = [k for k, _ in GENERAL]
    for t in topic_index().values():
        ids += [f"{t['id']}.{k}" for k in t["sections"]]
        ids += [f"note.{n}" for n in t["notes"] if f"note.{n}" not in ids]
    return ids


# ---- saved decks (owner only) ---------------------------------------------------------------------------------------
def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]


def check_deck(d: dict) -> dict[str, str]:
    """Errors by field: every text the owner typed passes the same check as the slides."""
    errs = {}
    texts = {"name": d.get("name", ""), "title": d.get("title", ""), "subtitle": d.get("subtitle", ""),
             "closing": d.get("closing", ""), "contact": d.get("contact", "")}  # fmt: skip
    texts |= {f"t.{k}": v for k, v in (d.get("titles") or {}).items()}
    for k, v in texts.items():
        p = problems(v) or to.share_problems(v)
        if p:
            errs[k] = p[0]
    if not slug(d.get("name", "")):
        errs["name"] = "Give the presentation a name."
    return errs


def save_deck(session: Session, d: dict, author: str) -> str:
    s = slug(d["name"])
    session.add(PageTextVersion(page=PAGE_PREFIX + s, fields=d, auto={}, note=f"Presentation saved: {d['name']}"[:500],
                                author=author[:100]))  # fmt: skip
    session.flush()
    return s


def get_deck(session: Session, s: str) -> dict | None:
    q = select(PageTextVersion).where(PageTextVersion.page == PAGE_PREFIX + s, PageTextVersion.undone_at.is_(None))
    v = session.scalars(q.order_by(PageTextVersion.id.desc()).limit(1)).first()
    return {**v.fields, "slug": s, "saved": v.created_at} if v else None


def decks(session: Session) -> list[dict]:
    q = (
        select(PageTextVersion)
        .where(PageTextVersion.page.like(PAGE_PREFIX + "%"), PageTextVersion.undone_at.is_(None))
        .order_by(PageTextVersion.id.desc())
    )
    seen, out = set(), []
    for v in session.scalars(q):
        if v.page not in seen:
            seen.add(v.page)
            out.append({**v.fields, "slug": v.page[len(PAGE_PREFIX) :], "saved": v.created_at})
    return out


def delete_deck(session: Session, s: str) -> bool:
    rows = list(
        session.scalars(
            select(PageTextVersion).where(PageTextVersion.page == PAGE_PREFIX + s, PageTextVersion.undone_at.is_(None))
        )
    )
    for v in rows:
        v.undone_at = utcnow()
    return bool(rows)
