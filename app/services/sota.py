"""Parts & components > State of the art (owner, 8 Nov 2026): per part category and sub-type, the best value each maker
offers on each key figure, with the part that has it; and, on every cross, the competitor part and the offered part
next to our best and the best in our data ("vs best").

The key figures and which way is better are in data/business/sota.yaml. Sub-types are derived from the data
(subtype()), so like is compared with like: a USB isolator's 480 Mbps never counts as the general-purpose best.
Only real parts (the demo set only where a category has no real part) that are fit for new designs (not NRND, last
time buy or obsolete) count. The table is built once per data version (blocks._data_version) and reused by the page,
the part page and every row of Cross a list.
"""

import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.matching.engine import from_datasheet, is_estimate_source
from app.matching.rules import short_circuit_protection
from app.models import Manufacturer, ManufacturerRole, ParamValue, Part
from app.services import blocks, lifecycle, vendors

FILE = PROJECT_ROOT / "data" / "business" / "sota.yaml"
OURS = ("Skyworks", "Qorvo")  # listed first, in this order; "ours" is any maker with the reference role
SCOPE_NOTE = "Best in our data = the makers we've imported, not the whole market."
TABLE_MARK = "‡"  # a value from a product table or selection guide (or an estimate), not read in a datasheet
# the parameters the sub-types are read from
SUBTYPE_KEYS = ("channel_config", "integrated_power", "input_type", "protection", "sense_type", "output_type",
                "configuration", "function_type", "qualification")  # fmt: skip
TAGS = {"top": "our top", "better": "we have better", "leads": "market leads"}


@lru_cache
def config() -> list[dict]:
    return yamlio.load(FILE.read_text())["categories"]


def category(family: str) -> dict | None:
    return next((c for c in config() if c["family"] == family), None)


def figures(cat: dict) -> list[dict]:
    """The value figures (the automotive count left out)."""
    return [f for f in cat["figures"] if "key" in f]


# --- sub-types --------------------------------------------------------------------------------------------------------
_THROWS = re.compile(r"(?:\dX)?SP(\d+|S|D)T")


def subtype(family: str, pm: dict) -> str | None:
    """The sub-type of a part from its parameter values ({key: value}); None when the data says too little."""
    if family == "digital_isolator":
        cc = str(pm.get("channel_config") or "")
        if cc.upper().startswith("USB"):
            return "usb"
        if "bidir" in cc.lower():
            return "i2c"
        power = str(pm.get("integrated_power") or "none").lower()
        return "power" if power not in ("none", "") else "general"
    if family == "gate_driver":
        ch = str(pm.get("channel_config") or "").lower()
        if ch not in ("single", "dual"):
            return None
        base = "half_bridge" if ch == "dual" and "pwm" in str(pm.get("input_type") or "").lower() else ch
        return base + ("_desat" if short_circuit_protection(None, pm) else "")
    if family == "isolated_amplifier":
        out, sense = str(pm.get("output_type") or "").lower(), str(pm.get("sense_type") or "").lower()
        if not out or not sense:
            return None
        kind = "mod_" if out.startswith("digital") else "amp_"
        return kind + ("voltage" if sense.startswith("volt") else "current")
    if family == "rf_switch":
        cfg = str(pm.get("configuration") or "").upper().replace(" ", "")
        if not cfg:
            return None
        m = _THROWS.fullmatch(cfg)
        if not m:
            return "multi_pole"  # DPDT, 3P4T, SPDT+SPDT …
        t = {"S": 1, "D": 2}.get(m[1]) or int(m[1])
        return "spst" if t == 1 else "spdt" if t == 2 else "sp3t_4t" if t <= 4 else "sp5t_up"
    if family == "timing":
        return str(pm["function_type"]) if pm.get("function_type") else None
    return None


def subtype_label(cat: dict, key: str) -> str:
    return (cat.get("subtypes") or {}).get(key) or key.replace("_", " ").capitalize()


# --- values -----------------------------------------------------------------------------------------------------------
def value_of(fig: dict, pm: dict) -> float | None:
    """A figure's number from a part's values: the value, or the top / bottom of a [min, max] range."""
    v = pm.get(fig["key"])
    if fig.get("pick") and isinstance(v, (list, tuple)):
        nums = [x for x in v if isinstance(x, (int, float))]
        v = (max if fig["pick"] == "max" else min)(nums) if nums else None
    if isinstance(v, bool) or v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def better(fig: dict, a: float | None, b: float | None) -> bool:
    """a is strictly better than b in the figure's direction (a missing value is never better)."""
    if a is None:
        return False
    if b is None:
        return True
    if same(a, b):
        return False
    return a > b if fig["direction"] == "higher" else a < b


def same(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-12)


def fmt(v: float | None, fig: dict | None = None) -> str:
    if v is None:
        return "–"
    if fig and fig.get("decimals") is not None:
        return f"{v:.{fig['decimals']}f}"
    if v == int(v) and abs(v) < 1e7:
        return f"{int(v):,}"
    return f"{v:.3g}"


def with_unit(v: float | None, fig: dict) -> str:
    s = fmt(v, fig)
    return f"{s} {fig['unit']}" if v is not None and fig.get("unit") else s


_IN_DATASHEET = re.compile(r"\.pdf\b", re.I)
_FILE = re.compile(r"([\w.()\-]+\.pdf)\b", re.I)
_PAGE = re.compile(r"([\w.()\-]+\.pdf)\b[^;]*?\bp\.?\s?(\d+)", re.I)


def short_source(src: str | None) -> str:
    """'si861x-2x-datasheet.pdf p.10' from a long source text; 'product table' (or the text) when no page is given."""
    if not src:
        return "no source given"
    m = _PAGE.search(src)
    if m and from_datasheet(src):
        return f"{m[1]} p.{m[2]}"
    if (f := _FILE.search(src)) and not is_estimate_source(src):
        return f[1]  # a datasheet, section named but no page
    return src if len(src) <= 40 else src[:37] + "…"


@dataclass
class Cell:
    value: float
    part_id: int
    mpn: str
    maker: str
    source: str = ""
    others: int = 0  # other parts with the same value
    ours: bool = False  # Skyworks or Qorvo (a maker with the reference role)

    @property
    def table(self) -> bool:
        """Not read in a datasheet (a product table, selection guide, our estimate or no source): marked on the page."""
        return not _IN_DATASHEET.search(self.source or "") or is_estimate_source(self.source)

    @property
    def where(self) -> str:
        return short_source(self.source)


@dataclass
class MakerRow:
    name: str
    ours: bool
    n: int
    cells: dict = field(default_factory=dict)  # figure key -> Cell
    automotive: int = 0
    best: set = field(default_factory=set)  # figure keys where this maker has the best value in our data


@dataclass
class Group:
    """One sub-type of one category."""

    key: str
    label: str
    makers: list = field(default_factory=list)
    best: dict = field(default_factory=dict)  # figure key -> best value in our data
    ours: dict = field(default_factory=dict)  # figure key -> our best Cell (Skyworks + Qorvo together)
    market: dict = field(default_factory=dict)  # figure key -> best Cell in our data (any maker)
    rival: dict = field(default_factory=dict)  # figure key -> best competitor Cell
    demo: bool = False  # only demo parts of this category are loaded (a local or test database)

    @property
    def n(self) -> int:
        return sum(m.n for m in self.makers)


def _pick(fig: dict, cells: list[Cell]) -> Cell | None:
    """The best cell, with "others" counting every other part with the same value; ties: a datasheet value first,
    then our part, then the shorter part number."""
    if not cells:
        return None
    top = cells[0].value
    for c in cells[1:]:
        if better(fig, c.value, top):
            top = c.value
    tied = sorted((c for c in cells if same(c.value, top)),
                  key=lambda c: (not from_datasheet(c.source), not c.ours, len(c.mpn), c.mpn))  # fmt: skip
    first = tied[0]
    return Cell(first.value, first.part_id, first.mpn, first.maker, first.source,
                sum(c.others + 1 for c in tied) - 1, first.ours)  # fmt: skip


def build(parts: list[dict]) -> dict:
    """{family: {subtype: Group}} from parts as dicts: id, mpn, maker, ours, family, values {key: value},
    sources {key: source}, and optionally synthetic. A family with real parts uses only those; one with only demo
    parts (a local or test database) uses those and is marked demo. Pure (no database), so tests can feed it
    fixtures."""
    out: dict = {}
    for cat in config():
        fam = cat["family"]
        mine = [p for p in parts if p["family"] == fam]
        real = [p for p in mine if not p.get("synthetic")]
        demo = not real
        by_sub: dict = defaultdict(lambda: defaultdict(list))
        for p in real or mine:
            if (st := subtype(fam, p["values"])) is not None:
                by_sub[st][(p["maker"], bool(p["ours"]))].append(p)
        groups = {}
        order = list(cat.get("subtypes") or {}) + sorted(set(by_sub) - set(cat.get("subtypes") or {}))
        for st in [s for s in order if s in by_sub]:
            g = Group(st, subtype_label(cat, st), demo=demo)
            for (maker, ours), ps in by_sub[st].items():
                row = MakerRow(maker, ours, len(ps))
                row.automotive = sum(str(p["values"].get("qualification") or "").lower() == "automotive" for p in ps)
                for fig in figures(cat):
                    cells = [Cell(v, p["id"], p["mpn"], maker, p["sources"].get(fig["key"]) or "", 0, ours) for p in ps
                             if (v := value_of(fig, p["values"])) is not None]  # fmt: skip
                    if (c := _pick(fig, cells)) is not None:
                        row.cells[fig["key"]] = c
                g.makers.append(row)
            g.makers.sort(key=lambda m: (not m.ours, OURS.index(m.name) if m.name in OURS else len(OURS), -m.n, m.name))
            for fig in figures(cat):
                k = fig["key"]
                cells = [m.cells[k] for m in g.makers if k in m.cells]
                if (best := _pick(fig, cells)) is None:
                    continue
                g.best[k], g.market[k] = best.value, best
                for m in g.makers:
                    if k in m.cells and same(m.cells[k].value, best.value):
                        m.best.add(k)
                if c := _pick(fig, [c for c in cells if c.ours]):
                    g.ours[k] = c
                if c := _pick(fig, [c for c in cells if not c.ours]):
                    g.rival[k] = c
            groups[st] = g
        out[fam] = groups
    return out


def gaps(cat: dict, g: Group) -> list[dict]:
    """The figures where the best competitor beats our best (or we have no value): label, ours, theirs."""
    out = []
    for fig in figures(cat):
        k = fig["key"]
        ours, rival = g.ours.get(k), g.rival.get(k)
        if rival is not None and (ours is None or better(fig, rival.value, ours.value)):
            out.append({"fig": fig, "ours": ours, "rival": rival})
    return out


def gap_line(cat: dict, g: Group) -> str:
    """'Our gaps at a glance: data rate (150 vs 200 Mbps), …' for the page."""
    if not any(m.ours for m in g.makers):
        return f"Our gaps at a glance: we have no {_lower(g.label)} part in our data."
    gs = gaps(cat, g)
    if not gs:
        return "Our gaps at a glance: none – our best matches or beats every other maker in our data on each figure."
    bits = []
    for x in gs:
        fig, unit = x["fig"], (" " + x["fig"]["unit"]) if x["fig"].get("unit") else ""
        ours = fmt(x["ours"].value, fig) if x["ours"] else "no value"
        bits.append(f"{_lower(_lbl(fig))} ({ours} vs {fmt(x['rival'].value, fig)}{unit}, "
                    f"{x['rival'].maker})")  # fmt: skip
    return "Our gaps at a glance: " + ", ".join(bits) + "."


# --- the cached table -------------------------------------------------------------------------------------------------
_CACHE: dict = {}


def _load(session: Session) -> list[dict]:
    fams = [c["family"] for c in config()]
    keys = {f["key"] for c in config() for f in figures(c)} | set(SUBTYPE_KEYS)
    q = (
        select(Part.id, Part.mpn, Manufacturer.name, Manufacturer.role, Part.is_synthetic, Part.family,
               Part.lifecycle_status, ParamValue.key, ParamValue.value, ParamValue.source)
        .join(Manufacturer, Manufacturer.id == Part.manufacturer_id)
        .join(ParamValue, ParamValue.part_id == Part.id)
        .where(Part.family.in_(fams), ParamValue.key.in_(keys))
    )  # fmt: skip
    parts: dict[int, dict] = {}
    for pid, mpn, maker, role, synthetic, fam, status, key, value, src in session.execute(q):
        if lifecycle.is_risk(status):
            continue
        p = parts.setdefault(pid, {"id": pid, "mpn": mpn, "maker": maker, "ours": role == ManufacturerRole.reference,
                                   "synthetic": bool(synthetic), "family": fam, "values": {}, "sources": {}})
        p["values"][key], p["sources"][key] = value, src
    return list(parts.values())


def table(session: Session) -> dict:
    """{family: {subtype: Group}}, built once per data version."""
    v = blocks._data_version(session)
    if v not in _CACHE:
        _CACHE.clear()
        _CACHE[v] = build(_load(session))
    return _CACHE[v]


def group_for(session: Session, part: Part) -> tuple[dict, Group] | None:
    """(category, sub-type group) a part is compared in; None when its category has no State-of-the-art data."""
    cat = category(part.family)
    if cat is None:
        return None
    st = subtype(part.family, _values(part))
    g = table(session).get(part.family, {}).get(st) if st else None
    return (cat, g) if g is not None else None


def _values(part: Part) -> dict:
    return {pv.key: pv.value for pv in part.params}


# --- vs best on a cross -----------------------------------------------------------------------------------------------
def vs_best(session: Session, ref: Part, cand: Part) -> dict | None:
    """Their part, the offered part, our best and the best in our data, per key figure, with tags and one reading
    sentence. Only for a competitor part crossed to one of ours, in a category with State-of-the-art data; the
    sub-type is the competitor part's."""
    if ref.is_reference or not cand.is_reference:
        return None
    hit = group_for(session, ref)
    if hit is None:
        return None
    cat, g = hit
    return compare(cat, g, _values(ref), _values(cand), cand.mpn)


def compare(cat: dict, g: Group, theirs: dict, offered: dict, offered_mpn: str = "") -> dict | None:
    rows = []
    for fig in figures(cat):
        k = fig["key"]
        t, o = value_of(fig, theirs), value_of(fig, offered)
        ours, market = g.ours.get(k), g.market.get(k)
        if t is None and o is None and ours is None:
            continue
        tags = []
        if o is not None and ours is not None:
            tags.append("better" if better(fig, ours.value, o) else "top")
        if ours is not None and market is not None and not market.ours and better(fig, market.value, ours.value):
            tags.append("leads")
        rows.append({"fig": fig, "theirs": t, "offered": o, "ours": ours, "market": market, "tags": tags,
                     "vs_theirs": None if t is None or o is None else
                     ("worse" if better(fig, t, o) else "better" if better(fig, o, t) else "same")})  # fmt: skip
    if not rows:
        return None
    return {"category": cat["label"], "family": cat["family"], "subtype": g.label, "subtype_key": g.key, "rows": rows,
            "reading": reading(rows), "offered": offered_mpn}  # fmt: skip


def _lower(label: str) -> str:
    """'Data rate' -> 'data rate'; 'CMTI', 'SNR', 'IIP3' stay as they are."""
    return label[0].lower() + label[1:] if len(label) > 1 and label[1].islower() else label


def _lbl(fig: dict) -> str:
    return fig["label"].split(" (")[0]


def _names(rows: list[dict]) -> str:
    names = [_lbl(r["fig"]) for r in rows]
    names = [_lower(n) for n in names]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def reading(rows: list[dict]) -> str:
    """One plain sentence (or two) on how the offered part stands against theirs and against our and the market's
    best."""
    compared = [r for r in rows if r["vs_theirs"] is not None]
    short = [r for r in compared if r["vs_theirs"] == "worse"]
    parts = []
    if compared and not short:
        parts.append(f"The offered part matches or beats theirs on all {len(compared)} compared figures")
    elif compared:
        parts.append(f"The offered part matches or beats theirs on {len(compared) - len(short)} of {len(compared)} "
                     f"figures and falls short on {_names(short)}")  # fmt: skip
    else:
        parts.append("Their part and the offered part share no figure to compare")
    top = [r for r in rows if "top" in r["tags"]]
    if top:
        parts[-1] += f"; it is our best on {_names(top)}"
    out = parts[0] + "."
    stronger = [r for r in rows if "better" in r["tags"]]
    if stronger:
        out += " We have a stronger part on " + ", ".join(
            f"{_names([r])} ({r['ours'].mpn}, {with_unit(r['ours'].value, r['fig'])})" for r in stronger) + "."
    leads = [r for r in rows if "leads" in r["tags"]]
    if leads:
        out += " Other makers lead on " + ", ".join(
            f"{_names([r])} ({vendors.display(r['market'].maker)} {with_unit(r['market'].value, r['fig'])})"
            for r in leads) + "."  # fmt: skip
    return out


def best_cells(session: Session, part: Part) -> tuple[str, str]:
    """Two short texts for the Excel download: our best and the best in our data per key figure, for the sub-type
    of the given (competitor) part; empty when there is no State-of-the-art data for it."""
    hit = group_for(session, part)
    if hit is None or part.is_reference:
        return "", ""
    cat, g = hit
    ours = "; ".join(f"{_lbl(f)} {with_unit(c.value, f)} ({c.mpn})" for f in figures(cat)
                     if (c := g.ours.get(f["key"])) is not None)  # fmt: skip
    market = "; ".join(f"{_lbl(f)} {with_unit(c.value, f)} ({c.maker} {c.mpn})" for f in figures(cat)
                       if (c := g.market.get(f["key"])) is not None)  # fmt: skip
    return ours, market
