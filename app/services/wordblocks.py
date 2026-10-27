"""Block diagram from words (owner, 27 Oct 2026: "a block diagram builder that allows for word input ... I have a 48V
input and an MCU then this text should already build the first 2-3 blocks").

The "Describe your system" box in the block editor sends its text here. Rules only, on the server (no AI, nothing
sent out): voltages, function words and a few link rules from data/blocks/word_synonyms.yaml build the editor's own
diagram data (groups of blocks on a grid, links between groups: the shape blocks.js and the templates use), e.g.
"I have a 48 V input and an MCU" -> 48 V input -> input protection -> buck 48 V -> 5 V -> LDO 5 V -> 3.3 V -> MCU.

Data protection (docs/plan_data_protection.md): the typed text is never stored. For the owner only, the words it did
not understand are counted (one row per word and day, nothing else) so the daily run can add synonyms: lower case,
at most 30 characters, without long numbers, e-mail or web addresses, capitalised words inside a sentence (names)
and words of the company names in data/business. Guests' words are never counted. Counts older than 12 months go.
"""

import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from itertools import pairwise

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import UnknownWord

SYNONYMS_FILE = PROJECT_ROOT / "data" / "blocks" / "word_synonyms.yaml"
BUSINESS_DIR = PROJECT_ROOT / "data" / "business"
MAX_TEXT = 1000  # characters read from the box
MAX_WORD = 30
RETENTION_MONTHS = 12


def _load(path):
    with open(path, encoding="utf-8") as f:
        return yamlio.load(f)


# "48V", "48 V", "48-volt", "12 Vdc", "3,3 V"; "3V3" / "1V8"
_VOLT = re.compile(r"(?<![\w.,])(\d{1,4}(?:[.,]\d{1,2})?)\s*-?\s*(?:volts?|vdc|vin|v)(?![a-z0-9])", re.I)
_VOLT_INFIX = re.compile(r"(?<![\w.])(\d{1,2})v(\d)(?![\w])", re.I)
_TOKEN = re.compile(r"[A-Za-z0-9µ](?:[A-Za-z0-9µ]|[./+-](?=[A-Za-z0-9µ]))*")
_SENTENCE_END = re.compile(r"[.!?;:\n]\s*$")


def _key(word: str) -> str:
    return word.lower().replace("-", "")


@lru_cache
def rules() -> dict:
    """The vocabulary, prepared: phrases (tuples of keys) -> term index, longest first."""
    raw = _load(SYNONYMS_FILE)
    from app.services import blocks

    fns = blocks.catalogue()["functions"]
    phrases: dict[tuple[str, ...], int] = {}
    for i, t in enumerate(raw["terms"]):
        assert t["fn"] in fns, f"word_synonyms.yaml: unknown function {t['fn']}"
        for w in t["words"]:
            phrases.setdefault(tuple(_key(m.group()) for m in _TOKEN.finditer(str(w))), i)
    iso = raw["isolation"]
    return {
        "terms": raw["terms"],
        "phrases": phrases,
        "longest": max(len(p) for p in phrases),
        "iso_words": {_key(w) for w in iso["words"]},
        "iso_swap": iso.get("swap") or {},
        "caps_only": {_key(w) for w in raw.get("caps_only") or []},
        "stop": {_key(str(w)) for w in raw.get("stop_words") or []},
        "power": raw["power"],
        "input_words": {_key(w) for w in raw["power"]["input_words"]},
        "chain_labels": raw.get("chain_labels") or {},
        "fn_labels": {k: f.get("label", k) for k, f in fns.items()},
    }


def vocabulary_size() -> int:
    """How many words and phrases the box understands (function words, isolation words)."""
    r = rules()
    return len(r["phrases"]) + len(r["iso_words"])


def _v(x: float) -> str:
    return f"{x:g} V"


# ---- reading the text ------------------------------------------------------------------------------------------------
@dataclass
class Hit:
    start: int
    end: int
    kind: str  # volt | term | iso | stop | unknown
    label: str = ""
    term: int | None = None
    volts: float | None = None
    word: str = ""  # volt: the input word after it (bus, battery ...)
    caps_inside: bool = False  # unknown: capitalised and not at the start of a sentence


def read(text: str) -> list[Hit]:
    """Every word of the text with what it was understood as, in order."""
    r = rules()
    text = text[:MAX_TEXT]
    hits: list[Hit] = []
    taken: list[tuple[int, int]] = []
    for m in [*_VOLT.finditer(text), *_VOLT_INFIX.finditer(text)]:
        if any(a < m.end() and m.start() < b for a, b in taken):
            continue
        val = float(m.group(1).replace(",", ".")) + (float(m.group(2)) / 10 if m.re is _VOLT_INFIX else 0)
        end, word = m.end(), ""
        nxt = re.match(r"\s+([A-Za-z]+)", text[end:])
        if nxt and _key(nxt.group(1)) in r["input_words"]:
            end, word = end + nxt.end(), _key(nxt.group(1))
        hits.append(Hit(m.start(), end, "volt", volts=val, word=word))
        taken.append((m.start(), end))
    toks = [m for m in _TOKEN.finditer(text) if not any(a < m.end() and m.start() < b for a, b in taken)]
    i = 0
    while i < len(toks):
        found = None
        for n in range(min(r["longest"], len(toks) - i), 0, -1):
            group = toks[i : i + n]
            if any(text[a.end() : b.start()].strip(" -") for a, b in pairwise(group)):
                continue  # a phrase only over spaces or hyphens
            key = tuple(_key(t.group()) for t in group)
            if key in r["phrases"]:
                if n == 1 and key[0] in r["caps_only"] and not group[0].group().isupper():
                    continue
                found = (n, r["phrases"][key])
                break
        if found:
            n, ti = found
            t = r["terms"][ti]
            hits.append(Hit(toks[i].start(), toks[i + n - 1].end(), "term", term=ti,
                            label=t.get("chip") or t.get("label") or r["fn_labels"][t["fn"]]))  # fmt: skip
            i += n
            continue
        t = toks[i]
        k = _key(t.group())
        if k in r["iso_words"]:
            hits.append(Hit(t.start(), t.end(), "iso", label="isolated"))
        elif k in r["stop"]:
            hits.append(Hit(t.start(), t.end(), "stop"))
        else:
            at_start = i == 0 and not text[: t.start()].strip() or bool(_SENTENCE_END.search(text[: t.start()]))
            hits.append(Hit(t.start(), t.end(), "unknown", caps_inside=t.group()[0].isupper() and not at_start))
        i += 1
    hits.sort(key=lambda h: h.start)
    return hits


# ---- building the diagram --------------------------------------------------------------------------------------------
@dataclass
class _Node:
    key: str
    label: str
    blocks: list[tuple[str, str]]  # (fn, block label)


@dataclass
class _Graph:
    nodes: dict[str, _Node] = field(default_factory=dict)
    links: list[list[str]] = field(default_factory=list)
    lanes: list[list[str]] = field(default_factory=list)

    def add(self, key: str, label: str, blocks: list[tuple[str, str]], lane: list[str]) -> str:
        if key not in self.nodes:
            self.nodes[key] = _Node(key, label, blocks)
            lane.append(key)
        return key

    def link(self, a: str, b: str, label: str = "") -> None:
        if a != b and not any(x[0] == a and x[1] == b for x in self.links):
            self.links.append([a, b, label])


def _levels(volts: list[float], hub_rail: float | None) -> list[float]:
    """The voltages of the power chain, highest first: the input, every rail named, the processor's rail and the
    in-between rails the rules add (5 V before a 3.3 V LDO, 12 V after a high-voltage input)."""
    p = rules()["power"]
    top = max(volts)
    lv = sorted({v for v in [*volts, *([hub_rail] if hub_rail else [])] if v <= top}, reverse=True)
    if top > p["hv_above"] and not any(p["hv_to"] <= v < top for v in lv):
        lv = sorted({*lv, float(p["hv_to"])}, reverse=True)
    out = [lv[0]]
    for v in lv[1:]:
        src = p["ldo_from"].get(v)
        if src is not None and out[-1] - v > p["ldo_max_drop"] and out[-1] > src and src not in out:
            out.append(float(src))
        out.append(v)
    return out


def _step(a: float, b: float) -> tuple[str, str, str]:
    """(function, block label, frame label) for the converter from a to b volts."""
    p = rules()["power"]
    ldo_src = p["ldo_from"].get(b)
    if a > p["hv_above"]:
        return "isolated_dcdc", f"Isolated DC-DC {_v(a)} → {_v(b)}", f"Isolated DC-DC {_v(a)} → {_v(b)}"
    if a - b <= p["ldo_max_drop"] or (ldo_src is not None and a == ldo_src):
        return "pol_ldo", f"LDO {_v(a)} → {_v(b)}", f"LDO {_v(a)} → {_v(b)}"
    fn = "wide_vin_buck" if a > p["wide_vin_above"] else "pol_buck"
    return fn, f"Buck {_v(a)} → {_v(b)}", f"Step-down {_v(a)} → {_v(b)}"


def build(text: str) -> dict:
    """{"data": the editor's diagram, "chips": the text echoed back, "notes": what the rules added, "n": blocks}."""
    r = rules()
    hits = read(text)
    terms = r["terms"]
    g = _Graph()
    notes: list[str] = []

    # isolation: the nearest term after the word, else the nearest before it
    isolated: set[int] = set()
    for i, h in enumerate(hits):
        if h.kind == "iso":
            after = next((x for x in hits[i + 1 :] if x.kind == "term"), None)
            before = next((x for x in reversed(hits[:i]) if x.kind == "term"), None)
            target = after or before
            if target is not None:
                isolated.add(id(target))
                h.label = f"isolation for {target.label}"

    term_hits = [h for h in hits if h.kind == "term"]
    hubs = [h for h in term_hits if terms[h.term].get("role") == "hub"]
    sources = [h for h in term_hits if terms[h.term].get("role") == "source"]
    loads = [h for h in term_hits if terms[h.term].get("role") not in ("hub", "source")]
    volts = [h for h in hits if h.kind == "volt"]

    hub_fn = terms[hubs[0].term]["fn"] if hubs else None
    if hub_fn is None and loads:
        hub_fn = "mcu"
        notes.append("Added a microcontroller: the other blocks connect to it.")
    hub_term = terms[hubs[0].term] if hubs else next((t for t in terms if t["fn"] == hub_fn), {})
    hub_label = hub_term.get("label") or r["fn_labels"].get(hub_fn or "", "")
    hub_rail = float(hub_term.get("rail") or r["power"]["default_rail"]) if hub_fn else None

    power = r["power"]
    lane0: list[str] = []
    feed = None  # the node that feeds the processor, and the voltage it gives
    feed_v = None
    if volts or sources:
        top = max((h.volts for h in volts), default=None)
        top_hit = next((h for h in volts if h.volts == top), None)
        battery = bool(sources) or (top_hit is not None and top_hit.word == "battery")
        if top is not None and battery:
            fn = "hv_battery" if top > power["hv_above"] else "battery_pack"
            label = f"{_v(top)} battery"
        elif battery:
            fn, label = "battery_pack", "Battery"
        else:
            word = top_hit.word if top_hit and top_hit.word in ("bus", "supply", "rail", "line", "net") else "input"
            fn, label = "external_block", f"{_v(top)} {word}"
        for h in volts:
            h.label = label if h is top_hit else f"{_v(h.volts)} rail"
        for h in sources:
            h.label = label
        src = g.add("src", label, [(fn, label)], lane0)
        last, last_v = src, top
        if top is None or power["protect_above"] < top <= power["hv_above"]:  # TVS / reverse polarity: LV inputs
            prot = g.add("prot", "Input protection", [("tvs_esd", "TVS"), ("reverse_polarity", "Reverse polarity")],
                         lane0)  # fmt: skip
            g.link(src, prot, _v(top) if top else "")
            last = prot
        if top is None and hub_fn:
            step = g.add("step0", "Step-down", [("wide_vin_buck", "Buck (set the voltages)")], lane0)
            g.link(last, step)
            last = step
            notes.append("No voltage given: a step-down is shown; add the voltages (e.g. 12 V battery, 3.3 V) to "
                         "get the converters.")  # fmt: skip
        if top is not None:
            lv = _levels([h.volts for h in volts], hub_rail if hub_fn else None)
            for k, (a, b) in enumerate(pairwise(lv), 1):
                fn_s, blabel, flabel = _step(a, b)
                node = g.add(f"step{k}", flabel, [(fn_s, blabel)], lane0)
                g.link(last, node, "" if last == "prot" else _v(a))
                last, last_v = node, b
                if hub_rail is not None and b == hub_rail:
                    feed, feed_v = node, b
        if feed is None:
            feed, feed_v = last, last_v

    if hub_fn:
        hub = g.add("hub", hub_label, [(hub_fn, hub_label)], lane0)
        if feed:
            g.link(feed, hub, _v(feed_v) if feed_v is not None else "")

    seen: set[str] = set()
    for h in [*hubs[1:], *loads]:
        t = terms[h.term]
        fn = t["fn"]
        iso = id(h) in isolated
        swap = r["iso_swap"].get(fn) if iso else None
        main_fn = swap or fn
        if main_fn in seen:
            continue
        seen.add(main_fn)
        chain = [main_fn if c == fn else c for c in t.get("chain") or ["hub", fn]]
        if iso and swap is None:  # an isolator between the processor and the block
            k = chain.index("hub")
            chain.insert(k + 1 if k + 1 < len(chain) and chain[k + 1] == main_fn else k, "digital_isolator")
        label = (r["fn_labels"][main_fn] if swap and swap != fn else t.get("label")) or r["fn_labels"][main_fn]
        if iso and swap is not None:
            h.label = label if swap != fn else f"{label} (isolated)"
        lane: list[str] = []
        keys = []
        for c in chain:
            if c == "hub":
                keys.append("hub")
            elif c == main_fn:
                keys.append(g.add(main_fn, label, [(main_fn, label)], lane))
            else:
                lab = r["chain_labels"].get(c) or r["fn_labels"].get(c, c)
                keys.append(g.add(f"{main_fn}:{c}", lab, [(c, lab)], lane))
        for a, b in pairwise(keys):
            g.link(a, b)
        if lane:
            g.lanes.append(lane)
    g.lanes.insert(0, lane0)

    data = _layout(g)
    return {"data": data, "chips": _chips(text[:MAX_TEXT], hits), "notes": notes,
            "n": sum(len(x["blocks"]) for x in data["groups"])}  # fmt: skip


def _layout(g: _Graph) -> dict:
    """Columns by signal flow (longest path from the left, blocks that only feed another one pulled next to it),
    rows by chain: each chain takes the first row free in all its columns. The editor's own data shape."""
    keys = list(g.nodes)
    succ = {k: [b for a, b, _ in g.links if a == k] for k in keys}
    pred = {k: [a for a, b, _ in g.links if b == k] for k in keys}
    col: dict[str, int] = {}
    order: list[str] = []
    indeg = {k: len(pred[k]) for k in keys}
    ready = [k for k in keys if not indeg[k]]
    while ready:
        k = ready.pop(0)
        order.append(k)
        col[k] = max((col[p] + 1 for p in pred[k]), default=0)
        for s in succ[k]:
            indeg[s] -= 1
            if not indeg[s]:
                ready.append(s)
    for k in keys:  # never expected (the chains have no loops), but a loop must not break the page
        col.setdefault(k, 0)
    for k in reversed(order):  # a block that only feeds others sits right before the first of them
        if succ[k] and k not in g.lanes[0]:
            col[k] = max(col[k], min(col[s] for s in succ[k]) - 1)
    used: set[tuple[int, int]] = set()
    row: dict[str, int] = {}
    for lane in g.lanes:
        r = 0
        while any((col[k], r) in used for k in lane):
            r += 1
        for k in lane:  # two blocks of one chain in the same column (a rail that branches off): the next free row
            rk = r
            while (col[k], rk) in used:
                rk += 1
            row[k] = rk
            used.add((col[k], rk))
    ids = {k: f"w{i}" for i, k in enumerate(keys, 1)}
    groups, n = [], 0
    for k in keys:
        nd = g.nodes[k]
        bl = []
        for fn, label in nd.blocks:
            n += 1
            bl.append({"id": f"wb{n}", "fn": fn, "label": label, "qty": 1, "part": None})
        groups.append({"id": ids[k], "label": nd.label, "col": col[k], "row": row[k], "w": 1, "blocks": bl})
    links = [[ids[a], ids[b], lab] for a, b, lab in g.links]
    return {"groups": groups, "links": links, "req": {}, "qa": {}}


def _chips(text: str, hits: list[Hit]) -> list[dict]:
    """The text in pieces: {"text", "kind": hit | grey | plain, "label"} (plain = spaces and punctuation)."""
    out, pos = [], 0
    for h in hits:
        if h.start > pos:
            out.append({"text": text[pos : h.start], "kind": "plain", "label": ""})
        if h.kind in ("volt", "term", "iso"):
            out.append({"text": text[h.start : h.end], "kind": "hit", "label": h.label})
        elif h.kind == "stop":  # ordinary words read normally; only the words not understood are grey
            out.append({"text": text[h.start : h.end], "kind": "plain", "label": ""})
        else:
            out.append({"text": text[h.start : h.end], "kind": "grey", "label": ""})
        pos = h.end
    if pos < len(text):
        out.append({"text": text[pos:], "kind": "plain", "label": ""})
    return out


# ---- unknown words (owner only) --------------------------------------------------------------------------------------
_EMAIL = re.compile(r"\S+@\S+")
_URL = re.compile(r"(?:https?://|www\.)\S+|\S+\.(?:com|org|net|de|io|ai|co|eu|cn|jp|uk)\b\S*", re.I)


@lru_cache
def company_words() -> frozenset[str]:
    """Lower-case words of every company name in data/business (customers, competition, competitor profiles)."""
    names: list[str] = []
    cust = _load(BUSINESS_DIR / "customers.yaml") or {}
    for seg in (cust.get("segments") or {}).values():
        names += [c.get("name", "") for c in seg.get("customers") or [] if isinstance(c, dict)]
    comp = _load(BUSINESS_DIR / "competition.yaml") or {}
    for row in comp.values():
        if isinstance(row, dict):
            names += [str(v) for v in row.get("vendors") or []]
    names += [p.stem for p in (BUSINESS_DIR / "competitors").glob("*.yaml") if not p.stem.startswith("_")]
    return frozenset(_key(m.group()) for n in names for m in _TOKEN.finditer(n))


def unknown_words(text: str) -> list[str]:
    """The words worth counting: not understood, lower case, never names, e-mails, web addresses or long numbers."""
    text = text[:MAX_TEXT]
    clean = _URL.sub(" . ", _EMAIL.sub(" . ", text))  # " . " keeps the next word's sentence start
    out = []
    for h in read(clean):
        w = clean[h.start : h.end]
        if h.kind != "unknown" or h.caps_inside or len(w) > MAX_WORD:
            continue
        if sum(c.isdigit() for c in w) > 6 or "@" in w or "/" in w:
            continue
        k = w.lower()
        if _key(k) in company_words() or not re.search(r"[a-zµ]", k):
            continue  # names and bare numbers
        out.append(k)
    return out


def cutoff(today: date | None = None) -> date:
    t = today or date.today()
    try:
        return t.replace(year=t.year - 1)
    except ValueError:
        return t.replace(year=t.year - 1, day=28)


def purge(session: Session, today: date | None = None) -> int:
    old = UnknownWord.day < cutoff(today)
    n = session.scalar(select(func.count(UnknownWord.id)).where(old)) or 0
    if n:
        session.execute(delete(UnknownWord).where(old))
        session.commit()
    return n


def count_unknown(session: Session, words: list[str], today: date | None = None) -> None:
    """Add one to each word's count for the day (the words only; never the text they came from)."""
    if not words:
        return
    day = today or date.today()
    purge(session, day)
    for w in sorted(set(words)):
        row = session.scalar(select(UnknownWord).where(UnknownWord.word == w, UnknownWord.day == day))
        if row is None:
            session.add(UnknownWord(word=w, day=day, count=words.count(w)))
        else:
            row.count += words.count(w)
    session.commit()


def counts_since(session: Session, since: date) -> list[tuple[str, int]]:
    purge(session)
    rows = session.execute(select(UnknownWord.word, func.sum(UnknownWord.count)).where(UnknownWord.day >= since)
                           .group_by(UnknownWord.word)).all()  # fmt: skip
    return sorted(((w, int(n)) for w, n in rows), key=lambda x: (-x[1], x[0]))


def inbox_lines(session: Session, since: date) -> list[str]:
    rows = counts_since(session, since)
    out = [
        "\n## Block builder: unknown words\n",
        'Words the owner typed in the block editor\'s "Describe your system" box that it did not understand '
        "(counts only; the text is never stored). Add synonyms to data/blocks/word_synonyms.yaml, never names.\n",
    ]
    out += [f"- {w}: {n}" for w, n in rows[:100]] or ["None."]
    return out
