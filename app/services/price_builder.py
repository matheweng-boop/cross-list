"""Solution price builder: several parts priced with the same tested model, summed per system.

Each part is priced from its own prices (DigiKey prices pasted on the page, a public list price, or the DigiKey
quote the site cached) or, without any, from a priced sibling times a parity range. What the site knows about a part
(family, package, pins, automotive grade, release date) fills in by itself and can be changed on the page. Nothing is
stored: the parts and assumptions live in the page's form only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BlockDiagram, BroadcastConfig, Part
from app.services import blocks, broadcast, pricing
from app.services import price_model as pm

MAX_ROWS = 30


@dataclass
class Row:
    mpn: str = ""
    qty: int = 1
    breaks: str = ""  # pasted DigiKey (or other) price breaks
    currency: str = "USD"
    anchor: str = ""  # priced sibling, used when the part has no prices of its own
    parity_lo: float = 0.0
    parity_hi: float = 0.0
    family: str = ""
    package: str = ""
    pins: int = 0
    automotive: str = ""  # "yes" | "no" | "" (from the site)
    released: int = 0
    pset: bool = False  # the price range sliders were moved by hand
    shown: tuple = ()  # the price range used, for the sliders
    info: dict = field(default_factory=dict)


def _num(v, cast, default):
    try:
        return cast(v)
    except (TypeError, ValueError):
        return default


def rows_from_form(form) -> list[Row]:
    """The page's rows from repeated form fields; an empty part number drops the row."""
    get = form.getlist
    mpns = get("mpn")
    out = []
    for i, mpn in enumerate(mpns[:MAX_ROWS]):

        def at(name, i=i):
            vals = get(name)
            return vals[i] if i < len(vals) else ""

        if not mpn.strip():
            continue
        out.append(Row(mpn=mpn.strip()[:60], qty=max(1, min(_num(at("qty"), int, 1), 99)),
                       breaks=at("breaks")[:4000], currency=at("cur") or "USD", anchor=at("anchor").strip()[:60],
                       parity_lo=_num(at("plo"), float, 0.0) / 100, parity_hi=_num(at("phi"), float, 0.0) / 100,
                       family=at("fam"), package=at("pkg").strip()[:30], pins=_num(at("pins"), int, 0),
                       automotive=at("auto"), released=_num(at("rel"), int, 0),
                       pset=at("pset") == "1"))  # fmt: skip
    return out


def _list_price(mpn: str) -> tuple[str, dict] | None:
    """The public list price for a part number: exact (any case), else an orderable number starting with it."""
    key = mpn.upper()
    lp = {k.upper(): (k, v) for k, v in pm.list_prices().items()}
    if key in lp:
        return lp[key]
    hits = sorted(k for k in lp if k.startswith(key))
    return lp[hits[0]] if hits else None


def _broadcast(mpn: str) -> dict | None:
    key = mpn.upper()
    cat = {d["mpn"].upper(): d for d in broadcast.catalog()}
    if key in cat:
        return cat[key]
    base = max((k for k in cat if key.startswith(k)), key=len, default=None)  # Si46922A1GE1AM -> Si46922
    return cat[base] if base else cat.get(min((k for k in cat if k.startswith(key)), default=""))


FIRST_ISSUE = re.compile(r"^(?:rev\.?\s*)?(?:\d{6}A|A|V1|1(?:\.0+)?)$", re.I)  # 206709A, Rev A, V1, 1.0


def released_year(part: Part) -> int | None:
    """The year the part came out: its release date (the first datasheet issue), else the date of its datasheet when
    that datasheet is still the first issue (Skyworks document letter A, revision A, V1 or 1.0); None when unknown."""
    if part.release_date:
        return part.release_date.year
    rev = (part.datasheet_revision or "").strip()
    if part.datasheet_date and FIRST_ISSUE.match(rev):
        return part.datasheet_date.year
    return None


PINS = re.compile(r"(\d{1,4})\s*(?:L\b|-?\s*(?:pins?|leads?|lead|ld)\b)|^[A-Za-z]+-(\d{1,4})(?!\d)", re.I)


def pins_from(code: str) -> int:
    """Pin count written in a package text: "QFN, 16L (4 x 4 mm)", "MCM, 28-pin", "QFN-56"; 0 when not written."""
    m = PINS.search(code or "")
    return int(m.group(1) or m.group(2)) if m else 0


def _db_parts(session: Session, key: str) -> list[Part]:
    """The part number in the database: exact (any case), else its orderable variants (ISO7741 -> ISO7741DWR …),
    else the variants of its base before the ordering suffix (Si8641BD-B-IS -> Si8641BD…)."""
    exact = session.scalars(select(Part).where(func.upper(Part.mpn) == key)).unique().all()
    if exact:
        return list(exact)
    for prefix in (key, key.split("-", 1)[0] if "-" in key else ""):
        if len(prefix) >= 4:
            q = select(Part).where(func.upper(Part.mpn).like(prefix.replace("%", "") + "%")).limit(60)
            hits = session.scalars(q).unique().all()
            if hits:
                return list(hits)
    return []


def site_info(session: Session, mpn: str) -> dict:
    """What the site knows about a part: model family, package, pins, automotive grade, release year, sources.
    Read from the parts database (the cross lists in data/real), the radio datasheets and the makers' catalogues. For
    a base part number with several variants, what they share (family, and package and pins when they all have the
    same), and the earliest release year among them."""
    cfg, key = pm.config(), mpn.strip().upper()
    fam_of = cfg["function_family"]
    out = {"family": "", "package": "", "pins": 0, "automotive": False, "released": None, "units": None, "found": [],
           "part": None}  # fmt: skip
    hits = _db_parts(session, key) if key else []
    exact = next((p for p in hits if p.mpn.upper() == key), None)
    if hits:
        part = exact or hits[0]

        def fam(p: Part) -> str:
            return p.family if p.family in cfg["families"] else fam_of.get(p.family, "")

        pkgs = {(p.package.code, p.package.pin_count or pins_from(p.package.code)) for p in hits if p.package}
        pkg, pins = (next(iter(pkgs)) if len(pkgs) == 1 else ("", 0)) if exact is None else (
            (part.package.code, part.package.pin_count or pins_from(part.package.code)) if part.package else ("", 0))
        years = [y for y in map(released_year, [exact] if exact is not None else hits) if y]
        families = {fam(p) for p in hits} - {""}
        out.update(part=exact, automotive=pm.is_automotive(part) if exact is not None else False,
                   family=fam(part) if exact is not None else (families.pop() if len(families) == 1 else ""),
                   package=pkg or "", pins=pins or 0, released=min(years) if years else None,
                   units=pm.units_of(part) if exact is not None else None,
                   found=["parts database" if exact is not None else f"parts database ({len(hits)} variants)"])
        if exact is not None and out["released"] is None and "-" in key:  # same datasheet as its sibling variants
            years = [y for y in map(released_year, _db_parts(session, key.split("-", 1)[0] + "-")) if y]
            out["released"] = min(years) if years else None
    bc = _broadcast(mpn)
    if bc is not None:
        pk = bc.get("package") or {}
        out["package"] = out["package"] or (f"{pk['type']}-{pk['pins']}" if pk.get("type") and pk.get("pins") else "")
        out["pins"] = out["pins"] or pk.get("pins") or 0
        out["automotive"] = out["automotive"] or bool(bc.get("aec_q100"))
        out["family"] = out["family"] or fam_of.get(bc.get("role") or "", "")
        out["units"] = out["units"] or (bc.get("channels") if bc.get("role") == "coprocessor" else bc.get("tuners"))
        rev = re.match(r"\s*(?:Rev\.?\s*)?([\w.]+),.*?\b((?:19|20)\d\d)\b", str((bc.get("source") or {}).get("revision")))
        if out["released"] is None and rev and FIRST_ISSUE.match(rev.group(1)):  # "Rev. 1.0, May 2, 2019"
            out["released"] = int(rev.group(2))
        out["found"].append(f"radio datasheet ({bc['doc']})")
    row = next((r for r in blocks.catalog_rows() if r["mpn"].upper() == key), None)
    if row is not None:
        out["family"] = out["family"] or fam_of.get(row["function"] or "", "")
        out["package"] = out["package"] or row["package"] or ""
        out["pins"] = out["pins"] or pins_from(out["package"])
        out["automotive"] = out["automotive"] or bool(row.get("automotive"))
        specs = row.get("key_specs") or {}
        ch = [int(v) for k, v in specs.items() if k in ("Forward Channels", "Reverse Channels") and str(v).isdigit()]
        out["units"] = out["units"] or (sum(ch) or None)
        out["found"].append(f"{row['manufacturer']} catalogue")
    return out


def variants(session: Session, mpn: str, limit: int = 30) -> list[dict]:
    """Orderable variants of what was typed (owner, 22 Oct 2026: "if there are multiple variants of the same part, list
    all options"): part numbers that start with it, or, for a full part number, with its base before the ordering
    suffix (NSI8241C0-DSWR -> NSI8241C0...). Each {mpn, package, pins}; empty when there is only one."""
    key = mpn.strip().upper()
    if len(key) < 3:
        return []

    def find(prefix: str) -> dict[str, dict]:
        out: dict[str, dict] = {}
        q = select(Part).where(func.upper(Part.mpn).like(prefix.replace("%", "") + "%")).limit(limit)
        for p in session.scalars(q).unique():
            out[p.mpn.upper()] = {"mpn": p.mpn, "package": p.package.code if p.package else "",
                                  "pins": (p.package.pin_count if p.package else 0) or 0}  # fmt: skip
        for r in blocks.catalog_rows():
            if len(out) >= limit:
                break
            if r["mpn"].upper().startswith(prefix) and r["mpn"].upper() not in out:
                out[r["mpn"].upper()] = {"mpn": r["mpn"], "package": r.get("package") or "", "pins": 0}
        return out

    found = find(key)
    if len(found) <= 1 and "-" in key:
        found = find(key.split("-", 1)[0])
    rows = sorted(found.values(), key=lambda v: v["mpn"].upper())
    return rows if len(rows) > 1 else []


def sibling(mpn: str) -> str | None:
    """A part with prices from the same datasheet family (e.g. Si47962 for Si47961), to price from by default."""
    me = _broadcast(mpn)
    if me is None:
        return None
    for key in sorted(pm.list_prices()):
        other = _broadcast(key)
        if other is not None and other["family"] == me["family"] and other["mpn"].upper() != me["mpn"].upper():
            return other["mpn"]
    return None


def own_prices(session: Session, row: Row, info: dict) -> tuple[list[tuple[int, float]], str, str] | None:
    """(breaks, currency, source) from the part's own prices: pasted, public list price, or cached DigiKey quote."""
    pasted = pm.parse_breaks(row.breaks)
    if pasted:
        return pasted, row.currency, "pasted"
    lp = _list_price(row.mpn)
    if lp is not None:
        name, v = lp
        return [(int(q), float(p)) for q, p in v["breaks"]], (v.get("currency") or "USD").upper(), \
            f"{v.get('source') or v['maker'] + ' list price'}, {name} ({v['retrieved']})"  # fmt: skip
    if info.get("part") is not None:
        pq = pricing.quote_for(session, info["part"], fetch=False)
        pts = pm.breaks(pq)  # already in USD
        if pts:
            return pts, "USD", "DigiKey (cached on this site)"
    return None


def spec(row: Row, info: dict) -> dict:
    """What the cost model reads for a row. The part number decides package and pins when the site knows them (only
    otherwise are the row's own entries used); channels, I/Q channels or tuners come from the site data only."""
    return {"family": row.family or info["family"], "package": info["package"] or row.package,
            "pins": info["pins"] or row.pins, "units": info["units"],
            "automotive": row.automotive == "yes" if row.automotive else info["automotive"]}  # fmt: skip


def _priced(session: Session, row: Row, info: dict, gm: float, fab: str) -> tuple[dict | None, str]:
    """The model for a part with prices of its own, and where they came from; (None, "") without any."""
    got = own_prices(session, row, info)
    if got is None:
        return None, ""
    pts, cur, source = got
    sp = spec(row, info)
    m = pm.estimate(session, sp["family"], pts, sp["package"], sp["pins"], sp["automotive"], row.mpn, cur, gm, fab,
                    sp["units"])  # fmt: skip
    return m, source


def cost_ratio(row: Row, info: dict, anchor_cost: dict | None, gm: float, fab: str) -> float | None:
    """The part's unit cost over its sibling's (channels, tuners, package and family all count); None if unknown."""
    sp = spec(row, info)
    mine = pm.cost(pm.part_ns(sp["family"], sp["package"], sp["pins"], sp["automotive"], row.mpn, sp["units"]), gm, fab)
    if not mine or not anchor_cost:
        return None
    return mine["levels"]["mid"]["total"] / anchor_cost["levels"]["mid"]["total"]


def price_row(session: Session, row: Row, vol: int, gm: float, adj: float, sop: int) -> dict:
    """One part: per wafer-source scenario the band at `vol` (times the market adjustment) and its OEM path."""
    cfg = pm.config()
    info = site_info(session, row.mpn)
    row.info = info
    fam = row.family or info["family"]
    out = {"row": row, "info": info, "family": fam, "scenarios": [], "basis": "", "source": "", "error": "",
           "anchor": None}  # fmt: skip
    if fam not in cfg["families"]:
        out["error"] = "pick a family (the site does not know which model fits this part)"
        return out
    released = row.released or info["released"]
    for fab in pm.fab_scenarios():
        m, source = _priced(session, row, info, gm, fab)
        if m is not None and m["rows"]:
            out["basis"] = "own prices" + (" (pasted)" if source == "pasted" else "")
            out["source"] = source
            rows = m["rows"]
        else:
            anchor = row.anchor or sibling(row.mpn)
            if not anchor:
                out["error"] = "no prices: paste DigiKey prices, or price it from a sibling part"
                return out
            a_row = Row(mpn=anchor, family="", package="", pins=0)
            a_info = site_info(session, anchor)
            if not (a_info["family"] or fam):
                out["error"] = f"no family known for {anchor}"
                return out
            a_row.family = a_info["family"] or fam
            am, source = _priced(session, a_row, a_info, gm, fab)
            if am is None or not am["rows"]:
                out["error"] = f"{anchor} has no prices on the site either: paste DigiKey prices for one of them"
                return out
            ratio = cost_ratio(row, info, am["cost"], gm, fab)
            follow = (ratio or 1.0) ** cfg["price_follows_cost"]
            if row.pset and row.parity_lo and row.parity_hi:
                lo, hi = sorted((row.parity_lo, row.parity_hi))
            else:
                lo, hi = cfg["parity"][0] * follow, cfg["parity"][1] * follow
            rows = pm.scaled(am, lo, hi)
            row.shown = row.shown or (lo, hi)
            out["anchor"] = {"mpn": anchor, "lo": lo, "hi": hi, "source": source, "auto": not row.anchor,
                             "ratio": ratio, "follow": follow, "by_hand": row.pset}  # fmt: skip
            picked = "" if row.anchor else " (same family, picked by the site)"
            why = "" if row.pset or ratio is None or abs(follow - 1) < 0.005 else f"; unit cost ×{ratio:.2f}"
            out["basis"] = f"{lo:.0%}–{hi:.0%} of {anchor}{picked}{why}"
            out["source"] = f"{anchor}: {source}"
            m = am
        rows = [{**r, "low": r["low"] * adj, "target": r["target"] * adj, "high": r["high"] * adj} for r in rows]
        at = next((r for r in rows if r["volume"] == vol), rows[-1])
        oem = pm.oem_path({"rows": rows}, sop, volume=at["volume"], released=released)
        out["scenarios"].append((fab, {"at": at, "rows": rows, "oem": oem, "m": m}))
    return out


def solution(session: Session, rows: list[Row], vol: int, gm: float, adj: float, sop: int) -> dict:
    """Every part priced, and the system total (quantity times price) per wafer-source scenario and per OEM year."""
    parts = [price_row(session, r, vol, gm, adj, sop) for r in rows]
    totals = []
    for i, fab in enumerate(pm.fab_scenarios()):
        ok = [(p["row"].qty, p["scenarios"][i][1]) for p in parts if p["scenarios"]]
        tot = {k: sum(q * s["at"][k] for q, s in ok) for k in ("low", "target", "high")}
        years: dict[int, dict] = {}
        for q, s in ok:
            for r in (s["oem"] or {}).get("rows") or []:
                y = years.setdefault(r["year"], {"year": r["year"], "phase": r["phase"], "low": 0.0, "high": 0.0})
                y["low"] += q * r["low"]
                y["high"] += q * r["high"]
        totals.append((fab, {**tot, "oem": sorted(years.values(), key=lambda y: y["year"]), "n": len(ok)}))
    return {"parts": parts, "totals": totals, "missing": [p for p in parts if not p["scenarios"]]}


def presets(session: Session) -> list[tuple[str, str]]:
    """What can be loaded: the radio configurator's hardware presets and saved radio and block diagrams."""
    hardware = broadcast.configurations().get("hardware") or []
    out = [(f"radio:{h['name']}", f"Radio preset: {h['name']}") for h in hardware]
    out += [(f"bc:{c.id}", f"Saved radio diagram: {c.name}") for c in session.scalars(select(BroadcastConfig))]
    out += [(f"bd:{d.id}", f"Saved block diagram: {d.name}") for d in session.scalars(select(BlockDiagram))]
    return out


def load(session: Session, key: str) -> list[Row]:
    """The parts of a preset or saved diagram, one row per part number with its count."""
    mpns: list[str] = []
    kind, _, ident = key.partition(":")
    if kind == "radio":
        h = next((h for h in broadcast.configurations().get("hardware") or [] if h["name"] == ident), None)
        mpns = [m for m in ((h or {}).get("ics") or {}).values() if m]
    elif kind == "bc" and ident.isdigit():
        c = session.get(BroadcastConfig, int(ident))
        mpns = [d.get("mpn") for d in ((c.data if c else {}) or {}).get("devices") or [] if d.get("mpn")]
    elif kind == "bd" and ident.isdigit():
        d = session.get(BlockDiagram, int(ident))
        groups = ((d.data if d else {}) or {}).get("groups") or []
        mpns = [b.get("part") for g in groups for b in g.get("blocks") or [] if b.get("part")]
    counts: dict[str, int] = {}
    for m in mpns:
        counts[m] = counts.get(m, 0) + 1
    return [Row(mpn=m, qty=n) for m, n in counts.items()][:MAX_ROWS]


def suggestions() -> list[str]:
    """Part numbers to suggest while typing: those with prices, and the radio parts."""
    return sorted({*pm.list_prices(), *(d["mpn"] for d in broadcast.catalog())})
