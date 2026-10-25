"""Reference designs collected from manufacturers' public sites (data/reference_designs/*.yaml, see its README)."""

import hashlib
import json
import re
import threading
from collections import Counter
from datetime import date
from functools import lru_cache
from pathlib import Path

from app import yamlio

DIR = Path(__file__).resolve().parents[2] / "data" / "reference_designs"
DOC_LABELS = {
    "design_guide": "Design guide",
    "schematic": "Schematic",
    "bom": "BOM",
    "layout": "Layout",
    "block_diagram": "Block diagram",
}


_LOCK = threading.Lock()


def _parse() -> tuple[tuple[Path, dict], ...]:
    paths = sorted(DIR.glob("*.yaml"))
    return tuple((path, yamlio.load(path.read_text()) or {}) for path in paths)


def _cache_file() -> Path:
    """A JSON copy of the indexed designs, named by a hash of the design files and of this module (the type rules):
    loading it takes a fraction of parsing and classifying 4,000+ designs."""
    from app.config import get_settings

    h = hashlib.sha256(Path(__file__).read_bytes())
    for p in sorted(DIR.glob("*.yaml")):
        h.update(p.name.encode() + p.read_bytes())
    return get_settings().data_dir / "cache" / f"refdesigns-{h.hexdigest()[:16]}.json"


@lru_cache
def _load() -> dict:
    """Designs (with their search text, type and sub-class) and sources, once per process; from the JSON cache when
    the files are unchanged. The lock keeps the start-up warm-up and a first visitor from doing it twice."""
    with _LOCK:
        cache = _cache_file()
        try:
            data = json.loads(cache.read_text())
            for s in data["sources"]:
                if isinstance(s.get("collected"), str):
                    s["collected"] = date.fromisoformat(s["collected"])
            return {"designs": tuple(data["designs"]), "sources": tuple(data["sources"])}
        except (OSError, ValueError, KeyError):
            pass
        files = _parse()
        out = []
        for _path, data in files:
            for d in data.get("designs") or []:
                if d.get("id") and d.get("url"):
                    d["_text"] = " ".join(
                        str(x)
                        for x in [d["id"], d.get("title"), d.get("summary"), *(d.get("parts") or []),
                                  *(d.get("applications") or [])]
                        if x
                    ).lower()  # fmt: skip
                    d["_type"] = app_type(d)
                    d["_sub"] = sub_class(d, d["_type"])
                    out.append(d)
        srcs = tuple({**(data.get("source") or {}), "file": path.name, "n": len(data.get("designs") or [])}
                     for path, data in files)  # fmt: skip
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_suffix(".tmp")
            tmp.write_text(json.dumps({"designs": out, "sources": srcs}, default=str))
            tmp.replace(cache)
        except OSError:
            pass
        return {"designs": tuple(out), "sources": srcs}


def sources() -> tuple[dict, ...]:
    """The `source` block of every design file (vendor, pages, collected, method)."""
    return _load()["sources"]


def designs() -> tuple[dict, ...]:
    return _load()["designs"]


# Broad application types: a design takes the type most of its application tags (and its title) point to.
TYPES = (  # (type, pattern), in tie-break order
    ("Power conversion & energy", r"power suppl|power deliver|power distribution|power conver|charg|battery|solar|"
     r"energy|grid|\bups\b|dc/dc|dc-dc|ac/dc|ac-dc|pfc|circuit breaker|electrical panel|rectifier|hybrid, electric|"
     r"buck|boost|converter|adapter|flyback|inverter|power module|gate driv|mosfet|igbt"),
    ("Motor drives & motion", r"motor|drive|servo|stepper|robot|actuat|hvac|pump|fan\b|compressor|traction|e-bike"),
    ("RF & communications", r"wireless|\brf\b|radio|antenna|\bbts\b|\brru\b|\bran\b|backhaul|microwave|satellite|"
     r"\b5g\b|wi-?fi|bluetooth|networking|telecom|communications equipment|mmimo|transceiver"),
    ("Sensing & measurement", r"sensor|sensing|test|measurement|oscillo|instrument|imaging|radar|lidar|meter|monitor|"
     r"analy|camera|detector|digitizer|vital signs|ultrasound"),
    ("Control, computing & data", r"\bplc\b|\bdcs\b|processor|gateway|zone control|data center|server|computing|"
     r"controller|fpga|automation|storage"),
    ("Displays, audio & HMI", r"infotainment|display|audio|cockpit|cluster|home theater|entertainment|"
     r"personal electronics|wearable|\btv\b|touch|human machine"),
    ("Lighting & body", r"lighting|\bled\b|body electronics|door|seat|mirror|wiper|interior"),
    ("Appliances & tools", r"appliance|kitchen|oven|coffee|cleaning|garden|power tool|induction cook|induction heat|"
     r"pet care|washer|refrigerat"),
    ("Medical & healthcare", r"medical|healthcare|surgical|patient|telehealth|vital signs|ultrasound|infusion"),
)
OTHER_TYPE = "Other"
_TYPE_RE = tuple((t, re.compile(p, re.I)) for t, p in TYPES)
_VOLT = re.compile(r"(\d+(?:\.\d+)?)\s*(kV|V)(?:AC|DC|ac|dc)?\b")
_FREQ = re.compile(r"(\d+(?:\.\d+)?)\s*(GHz|MHz)\b", re.I)
VOLT_CLASSES = ("Up to 60 V", "60–600 V", "Above 600 V", "Voltage not stated")
BAND_CLASSES = ("Below 1 GHz", "1–6 GHz", "Above 6 GHz", "Wired / baseband", "Frequency not stated")
# Fallbacks from the application tags when the title and summary name no voltage or frequency (typical class of the
# application, e.g. a grid or traction design is above 600 V, a cellular radio unit is 1–6 GHz).
_VOLT_TAGS = ((VOLT_CLASSES[2], re.compile(r"grid|solar|ev charging|traction|hev/ev|hybrid, electric|energy storage|"
                                           r"high.voltage|on-?board charger|wind|medium voltage|propulsion", re.I)),
              (VOLT_CLASSES[1], re.compile(r"ac/dc|ac-dc|mains|appliance|circuit breaker|electrical panel|hvac|pfc|"
                                           r"server|ac drive|induction|adapter|lighting", re.I)),
              (VOLT_CLASSES[0], re.compile(r"usb|battery.powered|portable|wearable|personal electronics|48 ?v|12 ?v|"
                                           r"body electronics|infotainment|cluster|poe|power over ethernet|sensor",
                                           re.I)))  # fmt: skip
_BAND_TAGS = ((BAND_CLASSES[2], re.compile(r"microwave|backhaul|satellite|radar|mmwave|e-band|ka-band", re.I)),
              (BAND_CLASSES[1], re.compile(r"\bbts\b|\brru\b|cloud ran|mmimo|\baas\b|wireless infrastructure|"
                                           r"small cell|wi-?fi|bluetooth|5g|lte", re.I)),
              (BAND_CLASSES[3], re.compile(r"wired|broadband fixed|switches|baseband|cable|ethernet|optical", re.I)),
              (BAND_CLASSES[0], re.compile(r"sub-?ghz|lora|\bism\b|smart meter|rfid|\bnfc\b", re.I)))  # fmt: skip


def _from_tags(d: dict, table) -> str | None:
    tags = " | ".join([*(d.get("applications") or []), d.get("title") or ""])
    return next((c for c, rx in table if rx.search(tags)), None)


@lru_cache(maxsize=8192)
def _type_hits(tag: str) -> tuple[bool, ...]:
    """Which type patterns a tag matches (the same few hundred application tags repeat across thousands of designs)."""
    return tuple(bool(rx.search(tag)) for _, rx in _TYPE_RE)


def app_type(d: dict) -> str:
    hits = [_type_hits(x) for x in [*(d.get("applications") or []), d.get("title") or ""]]
    score = [(sum(h[i] for h in hits), -i, t) for i, (t, _) in enumerate(_TYPE_RE)]
    best = max(score)
    return best[2] if best[0] else OTHER_TYPE


def sub_class(d: dict, atype: str) -> str:
    """Within a type: frequency band for RF designs, voltage class (highest voltage named) for the others."""
    text = f"{d.get('title') or ''} {d.get('summary') or ''}"
    if atype == "RF & communications":
        f = [float(v) * (1000 if u.lower() == "ghz" else 1) for v, u in _FREQ.findall(text)]
        if not f:
            return _from_tags(d, _BAND_TAGS) or BAND_CLASSES[4]
        top = max(f)
        return BAND_CLASSES[0] if top < 1000 else BAND_CLASSES[1] if top <= 6000 else BAND_CLASSES[2]
    v = [float(x) * (1000 if u == "kV" else 1) for x, u in _VOLT.findall(text)]
    if not v:
        return _from_tags(d, _VOLT_TAGS) or VOLT_CLASSES[3]
    top = max(v)
    return VOLT_CLASSES[0] if top <= 60 else VOLT_CLASSES[1] if top <= 600 else VOLT_CLASSES[2]


def search(q: str = "", vendor: str = "", market: str = "", fn: str = "", isolation: bool = False,
           docs: bool = False, atype: str = "", sub: str = "", pool=None) -> list[dict]:  # fmt: skip
    words = q.lower().split()
    return [
        d
        for d in (designs() if pool is None else pool)
        if all(w in d["_text"] for w in words)
        and (not vendor or d.get("vendor") == vendor)
        and (not market or market in (d.get("markets") or []))
        and (not fn or fn in (d.get("functions") or []))
        and (not isolation or d.get("isolation"))
        and (not docs or d.get("documents"))
        and (not atype or d["_type"] == atype)
        and (not sub or d["_sub"] == sub)
    ]


def type_tree(rows: list[dict]) -> list[dict]:
    """Types with their sub-classes and counts, in the fixed order (empty ones left out)."""
    order = [t for t, _ in TYPES] + [OTHER_TYPE]
    subs_order = {c: i for i, c in enumerate(VOLT_CLASSES + BAND_CLASSES)}
    tree: dict[str, Counter] = {}
    for d in rows:
        tree.setdefault(d["_type"], Counter())[d["_sub"]] += 1
    return [{"type": t, "n": sum(tree[t].values()), "subs": sorted(tree[t].items(), key=lambda kv: subs_order[kv[0]])}
            for t in order if t in tree]  # fmt: skip


def facets(rows: list[dict]) -> dict[str, list[tuple[str, int]]]:
    def count(key):
        c = Counter(v for d in rows for v in (d.get(key) or []))
        return sorted(c.items(), key=lambda kv: (-kv[1], kv[0]))

    return {
        "vendor": sorted(Counter(d.get("vendor") for d in rows).items(), key=lambda kv: -kv[1]),
        "market": count("markets"),
        "function": count("functions"),
    }


_SUFFIX = re.compile(r"(?:[-\s].*)$")  # ordering / grade suffixes: -Q1, -1, " G", -2C, -M ...
_RUN = re.compile(r"\d{4,}")


def family_of(mpn: str) -> str:
    """Product family of a part number: the last two digits of its first 4+ digit series become "xx" and a suffix of
    two or more letters right after it is kept (1EDI3025AS and 1EDI3035AS -> 1EDI30xxAS; UCC21540 -> UCC215xx).
    A part number without such a series is its own family: nothing is merged by guesswork."""
    stem = _SUFFIX.sub("", mpn.strip()).upper() or mpn.strip().upper()
    m = _RUN.search(stem)
    if not m:
        return stem
    letters = re.match(r"[A-Z]*", stem[m.end() :]).group(0)
    # TI's 4-digit LM numbers are a running catalogue (LM5113 driver, LM5180 flyback): only the last digit varies
    keep = 1 if stem[: m.start()] == "LM" and len(m.group(0)) == 4 else 2
    return stem[: m.end() - keep] + "x" * keep + (letters if len(letters) >= 2 else "")


def families(rows: list[dict], q: str = "") -> list[dict]:
    """Families of the parts used in the given designs, most used first: members (with the number of designs each
    is in) and the designs. ``q`` keeps families whose name or member matches, when it names a part."""
    fam: dict[tuple[str, str], dict] = {}
    for d in rows:
        for p in d.get("parts") or []:
            key = (d["vendor"], family_of(p))
            f = fam.setdefault(key, {"family": key[1], "vendor": key[0], "members": Counter(), "designs": {}})
            f["members"][p] += 1
            f["designs"][d["id"]] = d
    out = list(fam.values())
    words = q.upper().split()
    if words:
        hit = [f for f in out if all(any(w in s for s in [f["family"], *f["members"]]) for w in words)]
        out = hit or out
    for f in out:
        f["designs"] = sorted(f["designs"].values(), key=lambda d: d.get("title") or "")
        f["markets"] = Counter(m for d in f["designs"] for m in d.get("markets") or []).most_common(3)
        f["functions"] = Counter(x for d in f["designs"] for x in d.get("functions") or []).most_common(4)
    return sorted(out, key=lambda f: (-len(f["designs"]), f["family"]))


def grouped_parts(parts: list[str]) -> list[tuple[str, list[str]]]:
    """A design's parts grouped by family, in first-seen order."""
    out: dict[str, list[str]] = {}
    for p in parts:
        out.setdefault(family_of(p), []).append(p)
    return list(out.items())


@lru_cache(maxsize=512)
def view(q: str = "", vendor: str = "", market: str = "", fn: str = "", iso: bool = False, docs: bool = False,
         atype: str = "", sub: str = "", diagram: str = "", part: str = "", anchor: str = "", fb: tuple = ()) -> dict:
    """One list of the Reference designs page, computed once per set of filters (the designs never change while the
    site runs): the precise list a link asks for (?diagram=, &anchor=, ?part=, ?fn=) with its heading, then the search
    and filters on it; the type tree and the facets of the result."""
    from app.services import blocks, refmatch, vocab

    pool, heading = None, ""
    if diagram:
        e = refmatch.entry(diagram) or {}  # without the designs the owner marked "Doesn't fit" (fb: their token)
        keys = e.get("designs") or []
        if anchor:
            hit = {k for a in e.get("anchors") or [] if anchor in (a.get("fn"), a.get("part")) for k in a["designs"]}
            keys = [k for k in keys if k in hit]
        idx = refmatch.index()["by_key"]
        pool = [idx[k] for k in keys if k in idx]
        name = blocks.display_name(e) if e else diagram
        heading = f"Reference designs used for the block diagram {name}"
        if anchor:
            known = anchor in blocks.catalogue()["functions"]
            heading += f", with an anchor for {vocab.fn_label(anchor) if known else anchor}"
        if fn:
            heading += f", where {vocab.fn_label(fn)} appears"
    elif part:
        name, keys = refmatch.part_designs(part)
        idx = refmatch.index()["by_key"]
        pool = [idx[k] for k in keys]
        heading = f"Reference designs that use {name or part.upper()}"
    elif fn:
        heading = f"Reference designs where {vocab.fn_label(fn)} appears"
    base = search(q, vendor, market, fn, iso, docs, pool=pool)
    rows = tuple(d for d in base if (not atype or d["_type"] == atype) and (not sub or d["_sub"] == sub))
    return {"base": tuple(base), "tree": type_tree(base), "rows": rows, "facets": facets(list(rows)),
            "heading": heading}
