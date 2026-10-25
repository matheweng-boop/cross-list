"""Public reference designs as one knowledge base behind the library block diagrams (owner, 25 Oct 2026).

Each library diagram (data/blocks/templates.yaml) is matched to the public reference designs of the same application
(data/reference_designs/*.yaml); from the matches, how often each function appears. Anchors: parts in the designs that
the site crosses to one of our parts (the socket where our part goes in). The matching and the crosses are computed
offline by scripts/match_refdesigns.py into data/blocks/refdesign_matches.yaml; the function and part counts are
indexed once per process from the designs themselves.
"""

import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path

from app import yamlio

FILE = Path(__file__).resolve().parents[2] / "data" / "blocks" / "refdesign_matches.yaml"
SUGGEST_SHARE = 0.30  # a function in at least this share of the matched designs is a suggestion when missing
ADD_SHARE, ADD_MIN = 0.50, 5  # ... and is added to the template when this common and in at least this many designs
MIN_DESIGNS_FOR_SUGGESTIONS = 3  # fewer matched designs give no suggestions (one design is not a pattern)
MAX_MATCHES = 150
RARE = 5.5  # a single-word application tag must be at least this rare (about 1 in 100 designs)
MIN_WEIGHT = 4.6  # word weight log((n+1)/(df+1)) + 1: about 4.6 for a word in 1 of 40 designs

# words that say nothing about the application
_STOP = frozenset(
    "a an and or the of for with to in on by from at as via per plus into vs x two one three four multi multiple "
    "system systems module modules unit units board boards design designs reference after based using use type types "
    "solution solutions application applications device devices equipment general generic other end product products "
    "high low mid medium small large new smart full single dual digital integrated standalone variant e g "
    "automotive industrial consumer car vehicle personal electronics electronic electrical infrastructure".split()
)  # fmt: skip
_UNIT = re.compile(r"[\d.]+|[\d.]*(?:k|m|g)?(?:w|v|a|hz|ghz|mhz|khz|kw|kv|ma|mw|db|dbm|s)|\d+[a-z]{0,2}")
_WORD = re.compile(r"[a-z0-9]+(?:[-/][a-z0-9]+)*")
_SYN = {"chargers": "charger", "charging": "charger", "batteries": "battery", "inverters": "inverter",
        "drives": "drive", "motors": "motor", "meters": "meter", "metering": "meter", "radios": "radio",
        "converters": "converter", "supplies": "supply", "sensors": "sensor", "sensing": "sensor",
        "robots": "robot", "robotic": "robot", "robotics": "robot", "cameras": "camera", "speakers": "speaker",
        "lights": "light", "lighting": "light", "lamps": "lamp", "displays": "display", "trackers": "tracker",
        "controllers": "controller", "control": "controller", "monitors": "monitor", "monitoring": "monitor",
        "stations": "station", "ev": "ev", "evs": "ev", "hev/ev": "ev", "hev": "ev", "obc": "on-board-charger",
        "bms": "battery-management", "pv": "solar", "photovoltaic": "solar", "e-bike": "light-ev",
        "e-bikes": "light-ev", "scooter": "light-ev", "drones": "drone", "uav": "drone", "wearables": "wearable",
        "earbud": "earbuds", "headphones": "headphone", "appliances": "appliance", "servers": "server",
        "switches": "switch", "routers": "router", "gateways": "gateway", "amplifiers": "amplifier",
        "transmitters": "transmitter", "receivers": "receiver", "tools": "tool", "pumps": "pump",
        "terminals": "terminal", "panels": "panel", "breakers": "breaker", "relays": "relay"}  # fmt: skip


def words(text: str) -> list[str]:
    out = []
    text = re.sub(r"on-?board charger", "on-board-charger", (text or "").lower())
    text = re.sub(r"(?:hybrid, )?electric vehicles?|hev/ev", "ev", text)
    for w in _WORD.findall(text):
        w = _SYN.get(w, w)
        if len(w) > 1 and w not in _STOP and not _UNIT.fullmatch(w):
            out.append(w)
    return out


def diagram_key(t: dict) -> str:
    """Stable short key of a library diagram for links (its name as a slug; indexes shift when templates change)."""
    return re.sub(r"[^a-z0-9]+", "-", str(t.get("name") or "").lower()).strip("-")[:80]


_VARIANT = re.compile(r"\.\d+$")


def design_key(d: dict) -> str:
    return f"{d.get('vendor')}:{d.get('id')}"


# ---- matching (offline, scripts/match_refdesigns.py) ------------------------------------------------------------
def _idf(designs) -> dict[str, float]:
    df: Counter = Counter()
    for d in designs:
        df.update(set(words(" ".join([d.get("title") or "", *(d.get("applications") or [])]))))
    n = len(designs) or 1
    return {w: math.log((n + 1) / (c + 1)) + 1 for w, c in df.items()}


def _cover(key: list[str], have: set[str], idf: dict[str, float]) -> float:
    """Share of the key's weight (rare words weigh more) found in ``have``; 0 when the words found are only common
    ones (together less specific than one word used by about 1 in 40 designs) or only one word of several."""
    if not key:
        return 0.0
    hit = [w for w in key if w in have]
    if len(set(hit)) < min(2, len(set(key))):
        return 0.0  # a two-word application needs both words at least ("vehicle control unit" is not "control")
    got = sum(idf.get(w, 9.0) for w in hit)
    return got / sum(idf.get(w, 9.0) for w in key) if got >= MIN_WEIGHT else 0.0


def match(templates: list[dict], designs, fns_of) -> list[list[tuple]]:
    """For each template: the matched designs as (score, design key, shared functions), best first.

    A design matches a diagram when
      - its application tags and title name the diagram's application: at least 60 % of the weight of the words of
        the diagram's short title (rare words weigh more), or one of its application tags lies wholly inside the
        diagram's name (a tag of two or more words, or one rare word), and
      - it shares functions with the diagram: at least 2, or 1 when the title words match fully.
    """
    from app.services.blocks import display_name, title_parts

    idf = _idf(designs)
    pre = []
    for d in designs:
        tags = [set(words(a)) for a in d.get("applications") or []]
        pre.append((d, tags, [set(words(d.get("title") or "")), *tags], set(d.get("functions") or [])))
    out = []
    for t in templates:
        title = words(title_parts(t)[0]) or words(display_name(t))
        name_words = set(words(display_name(t)))
        fns = set(fns_of(t))
        seen: dict[str, tuple] = {}
        for d, tags, texts, dfns in pre:
            shared = fns & dfns
            if not shared:
                continue
            cov = max(_cover(title, x, idf) for x in texts)
            tag_in = any(tg and tg <= name_words and (len(tg) >= 2 or idf.get(next(iter(tg)), 0) >= RARE)
                         for tg in tags)  # fmt: skip
            ok = (cov >= 0.6 and len(shared) >= (1 if cov >= 0.999 else 2)) or (tag_in and len(shared) >= 2)
            if ok:
                score = round(cov + (0.5 if tag_in else 0) + 0.05 * len(shared), 4)
                row = (score, design_key(d), sorted(shared))
                base = _VARIANT.sub("", row[1])  # TIDA-01606.1 and .2 are one design: counted once, best kept
                if base not in seen or (-row[0], row[1]) < (-seen[base][0], seen[base][1]):
                    seen[base] = row
        rows = sorted(seen.values(), key=lambda r: (-r[0], r[1]))
        out.append(rows[:MAX_MATCHES])
    return out


# ---- anchors: design parts we cross ------------------------------------------------------------------------------
OUR_VENDORS = frozenset({"Skyworks", "Qorvo"})
_STEM = re.compile(r"(?:[-\s].*)$")  # ordering / grade suffixes: -Q1, -SEP, " G" ...


def stem(part: str) -> str:
    """The part number as a design names it, without grade or ordering suffix (UCC21750-Q1 -> UCC21750)."""
    return _STEM.sub("", part.strip()).upper() or part.strip().upper()


def _extends(mpn: str, base: str) -> bool:
    """An orderable part number of the design's part: ISO7741DBQR extends ISO7741, ISO77410 does not."""
    return mpn.startswith(base) and (len(mpn) == len(base) or not mpn[len(base)].isdigit())


def _fn_of_family(family: str, function_type) -> str | None:
    from app.services.blocks import catalogue

    for fn, f in catalogue()["functions"].items():
        src = f.get("source")
        fits = src.get("function", function_type) == function_type if isinstance(src, dict) else False
        if fits and src.get("family") == family:
            return fn
    return None


def compute_anchors(session, designs) -> dict[str, dict]:
    """Design part (as the design names it) -> the cross the site offers for it: the competitor part number in the
    database, our crossed part, its maker, the cross type (Drop-in / Functional / Package eq.) and the function.
    Uses the same crosses as the part pages (best of the first cross type that has one, in the site's order)."""
    import bisect

    from sqlalchemy import select

    from app.matching.engine import CATEGORY_ORDER, CATEGORY_SHORT
    from app.models import Manufacturer, ManufacturerRole, Part
    from app.services import queries

    comp = session.scalars(select(Part).join(Part.manufacturer)
                           .where(Manufacturer.role == ManufacturerRole.competitor)).unique().all()  # fmt: skip
    comp = sorted(comp, key=lambda p: p.mpn.upper())
    mpns = [p.mpn.upper() for p in comp]
    names = sorted({p.strip().upper() for d in designs if d.get("vendor") not in OUR_VENDORS
                    for p in d.get("parts") or []})  # fmt: skip
    by_stem: dict[str, dict | None] = {}
    out = {}
    for name in names:
        base = stem(name)
        if base not in by_stem:
            i = bisect.bisect_left(mpns, base)
            cands = []
            while i < len(mpns) and mpns[i].startswith(base):
                if _extends(mpns[i], base):
                    cands.append(comp[i])
                i += 1
            best = None
            for p in sorted(cands, key=lambda p: ("Q1" not in p.mpn.upper(), p.mpn))[:4]:
                cr = queries.crosses_for(session, p)
                c = next((c for c in CATEGORY_ORDER if cr.get(c)), None)
                if c:
                    r = cr[c][0]
                    best = {"mpn": p.mpn, "ours": r.candidate.mpn, "maker": r.candidate.manufacturer.name,
                            "type": CATEGORY_SHORT[c],
                            "fn": _fn_of_family(p.family, p.param_map().get("function_type"))}  # fmt: skip
                    break
            by_stem[base] = best
        if by_stem[base]:
            out[name] = by_stem[base]
    return out


# ---- the knowledge-base file -------------------------------------------------------------------------------------
def build(session) -> dict:
    """Everything scripts/match_refdesigns.py writes: anchors, the anchors of each design and, per library diagram,
    its matched designs, how often each function appears in them, the suggestions and the anchors."""
    from app.services import blocks, refdesigns

    designs = refdesigns.designs()
    by = {design_key(d): d for d in designs}
    anchors = compute_anchors(session, designs)
    design_anchors = {}
    for d in designs:
        hit = sorted({p.strip().upper() for p in d.get("parts") or []} & anchors.keys())
        if hit and d.get("vendor") not in OUR_VENDORS:
            design_anchors[design_key(d)] = hit
    tpls = blocks.templates()
    diagrams = []
    for t, rows in zip(tpls, match(tpls, designs, blocks.template_functions), strict=True):
        keys = [k for _, k, _ in rows]
        n = len(keys)
        cnt = Counter(f for k in keys for f in by[k].get("functions") or [])
        have = blocks.template_functions(t)
        common = sorted(((f, c) for f, c in cnt.items() if f not in have and c / n >= SUGGEST_SHARE),
                        key=lambda fc: (-fc[1], fc[0])) if n >= MIN_DESIGNS_FOR_SUGGESTIONS else []  # fmt: skip
        anc: dict[str, dict] = {}
        for k in keys:
            for p in design_anchors.get(k, []):
                a = anchors[p]
                e = anc.setdefault(stem(p), {"part": stem(p), "fn": a["fn"], "ours": a["ours"], "maker": a["maker"],
                                             "type": a["type"], "designs": []})  # fmt: skip
                if k not in e["designs"]:
                    e["designs"].append(k)
        diagrams.append({
            "name": t.get("name"), "key": diagram_key(t), "n": n, "designs": keys,
            "functions": {f: c for f, c in sorted(cnt.items(), key=lambda fc: (-fc[1], fc[0]))},
            "confirmed": [f for f in have if cnt[f] and (cnt[f] >= 2 or cnt[f] / n >= SUGGEST_SHARE)],
            "suggested": [{"fn": f, "n": c} for f, c in common],
            "anchors": sorted(({**e, "n": len(e["designs"])} for e in anc.values()),
                              key=lambda e: (-e["n"], e["part"])),
        })  # fmt: skip
    return {"anchors": dict(sorted(anchors.items())), "design_anchors": design_anchors, "diagrams": diagrams}


# close alternatives: a diagram that has one of them does not clearly lack another (a PMIC covers the PoL bucks)
CLOSE = (
    {"pmic", "buck_boost", "wide_vin_buck", "pol_buck", "multiphase", "pre_regulator", "hv_flyback", "acdc_controller"},
    {"pol_ldo", "pmic", "ldo_tracker", "termination_ldo"},
    {"gate_driver", "three_phase_gate_driver", "half_bridge_driver", "motor_driver_brushed", "motor_controller"},
    {"mcu", "soc", "adas_processor", "motor_controller", "wifi_soc", "ble_soc", "wireless_soc", "uwb_soc", "modem"},
    {"amplifier", "isolated_amplifier", "current_sensor", "adc"},
    {"crystal_oscillator", "clock_generator", "jitter_attenuator", "clock_buffer"},
)


def to_add(entry: dict, have: list[str] | None = None) -> list[dict]:
    """Suggestions to add to the template itself: in at least 50 % and at least 5 of the matched designs, and
    clearly missing (neither the function nor a close alternative is in the diagram)."""
    n = entry.get("n") or 0
    fns = set(have or [])
    return [s for s in entry.get("suggested") or [] if n and s["n"] >= ADD_MIN and s["n"] / n >= ADD_SHARE
            and not any(s["fn"] in c and c & fns for c in CLOSE)]  # fmt: skip


# ---- runtime ---------------------------------------------------------------------------------------------------
@lru_cache
def data() -> dict:
    raw = (yamlio.load(FILE.read_text()) if FILE.exists() else None) or {}
    raw.setdefault("anchors", {})
    raw.setdefault("design_anchors", {})
    raw["by_key"] = {e["key"]: e for e in raw.get("diagrams") or []}
    return raw


def for_template(t: dict | None) -> dict | None:
    return data()["by_key"].get(diagram_key(t)) if t else None


def anchors_of_design(d: dict) -> dict[str, dict]:
    """The design's anchor parts: design part -> cross (ours, type, ...)."""
    a = data()["anchors"]
    return {p: a[p] for p in data()["design_anchors"].get(design_key(d), []) if p in a}


@lru_cache
def index() -> dict:
    """Built once per process from the designs: design by key, designs per function and per part number stem."""
    from app.services import refdesigns

    by_key: dict[str, dict] = {}
    by_fn: dict[str, list[str]] = {}
    by_stem: dict[str, list[str]] = {}
    for d in refdesigns.designs():
        k = design_key(d)
        by_key[k] = d
        for f in d.get("functions") or []:
            by_fn.setdefault(f, []).append(k)
        for p in d.get("parts") or []:
            by_stem.setdefault(stem(p), []).append(k)
    return {"by_key": by_key, "by_fn": by_fn, "by_stem": {s: list(dict.fromkeys(v)) for s, v in by_stem.items()}}


def fn_count(fn: str) -> int:
    return len(index()["by_fn"].get(fn, ()))


def part_designs(mpn: str) -> tuple[str, list[str]]:
    """The designs that use a part (an orderable number finds the designs' base number): (the part as the designs
    name it, design keys); ("", []) when none."""
    up = (mpn or "").strip().upper()
    st = index()["by_stem"]
    if stem(up) in st:
        return stem(up), st[stem(up)]
    for i in range(len(up) - 1, 2, -1):  # longest base number first
        if up[:i] in st and _extends(up, up[:i]):
            return up[:i], st[up[:i]]
    return "", []


def anchor_of_part(name: str) -> dict | None:
    """The cross for a part as the designs name it (any grade suffix)."""
    a = data()["anchors"]
    name = (name or "").upper()
    return a.get(name) or next((v for k, v in a.items() if stem(k) == stem(name)), None)


@lru_cache
def fn_counts() -> dict[str, int]:
    """Public reference designs per function (for the gap lines in the block editor)."""
    return {f: len(v) for f, v in index()["by_fn"].items()}


def around(keys: list[str], exclude=(), top: int = 6) -> list[tuple[str, int]]:
    """The other functions in the given designs, most common first (the cross-sell around an anchor)."""
    idx = index()["by_key"]
    c = Counter(f for k in keys for f in (idx.get(k) or {}).get("functions") or [] if f not in exclude)
    return sorted(c.items(), key=lambda fc: (-fc[1], fc[0]))[:top]


def kb_view(t: dict, counts: dict) -> dict | None:
    """What the library diagram's page shows from the public reference designs: how many it is based on, the anchors
    (first) with the functions around them, the blocks the designs confirm, the common functions it lacks
    (suggestions) and the blocks added from the designs. ``counts``: parts per function (None = customer part)."""
    from app.services import vocab

    e = for_template(t)
    if e is None:
        return None

    def st(fn):
        n = counts.get(fn)
        return "customer part" if n is None else "we have" if n else "no part"

    fns = e.get("functions") or {}
    anchors = [{**a, "label": vocab.fn_label(a["fn"]) if a.get("fn") else "",
                "around": [(f, c, vocab.fn_label(f), st(f)) for f, c in around(a["designs"], {a.get("fn")})]}
               for a in (e.get("anchors") or [])[:5]]  # fmt: skip
    added = [b["fn"] for g in t.get("groups") or [] for b in g.get("blocks") or []
             if isinstance(b, dict) and b.get("src") == "refdesigns"]  # fmt: skip
    return {"key": e["key"], "n": e.get("n") or 0, "anchors": anchors,
            "confirmed": [(f, fns.get(f, 0), vocab.fn_label(f)) for f in e.get("confirmed") or []],
            "suggested": [(s["fn"], s["n"], vocab.fn_label(s["fn"]), st(s["fn"])) for s in e.get("suggested") or []
                          if s["fn"] not in added],
            "added": [(f, fns.get(f, 0), vocab.fn_label(f)) for f in added],
            "anchor_fns": {a["fn"]: f"{a['n']} reference design{'s' if a['n'] != 1 else ''} use {a['part']} → "
                                    f"we cross with {a['ours']} ({a['type']})"
                           for a in reversed(e.get("anchors") or []) if a.get("fn")}}  # fmt: skip


def anchors_for(tpls: list[dict], counts: dict, top: int = 5) -> list[dict]:
    """Anchors across several library diagrams (a sub-system's cross-sell): each competitor part we cross with the
    matched designs that use it, and the functions around it in those designs (we have / no part)."""
    from app.services import vocab

    merged: dict[str, dict] = {}
    for t in tpls:
        for a in (for_template(t) or {}).get("anchors") or []:
            e = merged.setdefault(a["part"], {**a, "designs": []})
            e["designs"] += [k for k in a["designs"] if k not in e["designs"]]

    def st(fn):
        n = counts.get(fn)
        return "customer part" if n is None else "we have" if n else "no part"

    out = sorted(merged.values(), key=lambda e: (-len(e["designs"]), e["part"]))[:top]
    return [{**e, "n": len(e["designs"]), "label": vocab.fn_label(e["fn"]) if e.get("fn") else "",
             "around": [(f, c, vocab.fn_label(f), st(f)) for f, c in around(e["designs"], {e.get("fn")})]}
            for e in out]  # fmt: skip
