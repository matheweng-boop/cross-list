"""Business opportunity: application-driven portfolio intelligence on top of the block-diagram applications.

Model (a graph, kept simple):
  application (data/blocks/templates.yaml) -> functional block (level 2: the diagram group)
    -> design-in position (level 3: a block = function id x quantity)
    -> product candidates (level 4: Skyworks / Qorvo / competitor parts that can fill the function).
Alternative parts for one position count once: coverage is counted per position, never per SKU.

Position status for a chosen company (or the combined Skyworks + Qorvo portfolio):
  supported   a part of the company exists for the function (candidate, not yet checked against the
              application's electrical requirements)
  gap         the function is in scope but no company part exists in BizDev
  competitor  only other companies have parts
  na          customer / platform part or outside the semiconductor scope (excluded)
  unknown     the function is not in the catalogue (excluded from the confirmed score, shown separately)

Commercial data (ASP per function, annual volume per application) is optional. Count-based coverage never
needs it; revenue-weighted figures use only the priced positions and always come with their completeness.
"""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import yamlio
from app.models import BusinessInput, Manufacturer, ManufacturerRole, Part, PartMapping
from app.services import blocks

COMPANIES = {
    "combined": ("Skyworks + Qorvo", frozenset({"Skyworks", "Qorvo"})),
    "skyworks": ("Skyworks", frozenset({"Skyworks"})),
    "qorvo": ("Qorvo", frozenset({"Qorvo"})),
}
IN_SCOPE = ("supported", "gap", "competitor")
CROWDING_LABEL = {"low": "Few suppliers", "medium": "Several suppliers", "high": "Crowded"}
_COMPETITION = Path(__file__).resolve().parents[2] / "data" / "business" / "competition.yaml"
STATUS_LABEL = {"supported": "Portfolio", "gap": "Gap (opportunity)", "competitor": "Competitor only",
                "na": "Not our product type", "unknown": "Unknown"}  # fmt: skip
STATUS_HELP = {
    "supported": "A Skyworks or Qorvo part exists for this function (a candidate, not yet checked against the specs).",
    "gap": "Needed here, but no company in BizDev has a part for it yet.",
    "competitor": "Only other companies have parts for it in BizDev.",
    "na": "Chips the customer picks from other kinds of suppliers: processors, MCUs, memory, sensors, antennas, "
    "connectors. Left out of coverage; the Technology fit page still counts how often they appear.",
    "unknown": "The function is not in the catalogue yet.",
}


def company(key: str) -> tuple[str, str, frozenset]:
    key = key if key in COMPANIES else "combined"
    return (key, *COMPANIES[key])


# ---- products per function -------------------------------------------------------------------------------
def makers(session: Session) -> dict[str, dict[str, int] | None]:
    """Parts per manufacturer for every function; None for customer / external functions. Competitors come from
    the BizDev families (e.g. TI and Novosense isolators)."""
    cat = blocks.catalogue()["functions"]
    fam_competitors: dict[str, Counter] = defaultdict(Counter)
    rows = session.execute(
        select(Part.family, Manufacturer.name, func.count(Part.id))
        .join(Part.manufacturer)
        .where(Manufacturer.role == ManufacturerRole.competitor)
        .group_by(Part.family, Manufacturer.name)
    ).all()
    for fam, name, n in rows:
        fam_competitors[fam][name] += n
    confirmed: dict[str, Counter] = defaultdict(Counter)  # catalogue parts a reviewer mapped to the function
    for m in session.scalars(select(PartMapping).where(PartMapping.verdict == "yes")):
        confirmed[m.fn][m.manufacturer] += 1
    out: dict[str, dict[str, int] | None] = {}
    for fn, f in cat.items():
        cands = blocks._candidates(session, fn)
        if cands is None:  # a customer part, unless a reviewer confirmed that one of our parts fills it
            out[fn] = dict(confirmed[fn]) if fn in confirmed else None
            continue
        c = Counter(x["manufacturer"] for x in cands)
        c.update(confirmed.get(fn, {}))
        src = f.get("source")
        if isinstance(src, dict) and "family" in src:
            c.update(fam_competitors.get(src["family"], {}))
        out[fn] = dict(c)
    return out


def status_of(fn: str, mk: dict, mine: frozenset) -> str:
    if fn not in mk:
        return "unknown"
    m = mk[fn]
    if m is None:
        return "na"
    if any(m.get(x) for x in mine):
        return "supported"
    if any(n for x, n in m.items() if x not in mine):
        return "competitor"
    return "gap"


# ---- applications ----------------------------------------------------------------------------------------
@dataclass
class Position:
    fn: str
    label: str
    group: str  # level 2: functional block (diagram group)
    qty: int
    status: str = "unknown"
    makers: dict = field(default_factory=dict)


@dataclass
class Application:
    i: int
    name: str
    category: str
    positions: list[Position]
    market: str = ""  # end market: Automotive when the application is a vehicle system, else its category
    background: bool = False  # diagram outside the library (used for statistics only)


_AUTO_APP = re.compile(
    r"automotive|vehicle|\bcar\b|HEV|\bEV\b|ADAS|V2X|infotainment|telematics|cockpit|radar|phone-as-a-key", re.I
)


def market_of(name: str, category: str) -> str:
    """Vehicle systems by name (parentheticals ignored: "client / IoT / automotive module" is not one; light EVs are
    e-bikes and scooters)."""
    core = re.sub(r"\([^()]*\)", "", name)
    auto = category.startswith("Automotive") or (_AUTO_APP.search(core) and "Light EV" not in core)
    return "Automotive" if auto else category


def applications() -> list[Application]:
    cat = blocks.catalogue()["functions"]
    out = []
    lib = blocks.templates()
    for i, t in enumerate([*lib, *blocks.background_templates()]):
        pos = []
        for g in t.get("groups") or []:
            for b in g.get("blocks") or []:
                if isinstance(b, dict):
                    fn, qty, label = b["fn"], int(b.get("qty") or 1), b.get("label") or ""
                else:
                    fn, *rest = str(b).split(" x")
                    qty, label = int(rest[0]) if rest else 1, ""
                fn = fn.strip()
                pos.append(Position(fn, label or (cat.get(fn) or {}).get("label", fn), g.get("label", ""), qty))
        category = t.get("category") or "Other"
        market = market_of(t.get("name", ""), category)
        out.append(Application(i, blocks.display_name(t), category, pos, market, background=i >= len(lib)))
    return out


def with_status(apps: list[Application], mk: dict, mine: frozenset) -> list[Application]:
    for a in apps:
        for p in a.positions:
            p.status = status_of(p.fn, mk, mine)
            p.makers = mk.get(p.fn) or {}
    return apps


# ---- commercial inputs -----------------------------------------------------------------------------------
def inputs(session: Session) -> tuple[dict[str, float], dict[str, float]]:
    asp, vol = {}, {}
    for r in session.scalars(select(BusinessInput)):
        (asp if r.kind == "asp" else vol)[r.key] = r.value
    return asp, vol


def set_input(session: Session, kind: str, key: str, value: float | None, note: str = "") -> None:
    row = session.scalar(select(BusinessInput).where(BusinessInput.kind == kind, BusinessInput.key == key))
    if value is None:
        if row:
            session.delete(row)
    elif row:
        row.value, row.note = value, note or row.note
    else:
        session.add(BusinessInput(kind=kind, key=key, value=value, note=note or None))


# ---- metrics ---------------------------------------------------------------------------------------------
def metrics(positions: list[Position], asp: dict[str, float]) -> dict:
    """Functional coverage (count-based) and content on the priced subset, with its completeness."""
    scope = [p for p in positions if p.status in IN_SCOPE]
    sup = [p for p in scope if p.status == "supported"]
    priced = [p for p in scope if p.fn in asp]
    total = sum(p.qty * asp[p.fn] for p in priced)
    mine = sum(p.qty * asp[p.fn] for p in priced if p.status == "supported")
    return {
        "in_scope": len(scope),
        "supported": len(sup),
        "gap": sum(p.status == "gap" for p in scope),
        "competitor": sum(p.status == "competitor" for p in scope),
        "na": sum(p.status == "na" for p in positions),
        "unknown": sum(p.status == "unknown" for p in positions),
        "coverage": len(sup) / len(scope) if scope else None,
        "priced": len(priced),
        "price_completeness": len(priced) / len(scope) if scope else None,
        "content_total": total,
        "content_mine": mine,
        "content_share": mine / total if total else None,
        "content_open": total - mine,
    }


def by_group(app: Application, asp: dict) -> list[tuple[str, dict]]:
    groups: dict[str, list] = {}
    for p in app.positions:
        groups.setdefault(p.group, []).append(p)
    return [(g, metrics(ps, asp)) for g, ps in groups.items()]


# ---- attach (anchor-based) -------------------------------------------------------------------------------
def attach(apps: list[Application], anchor: str) -> dict:
    """For applications that contain the anchor function: the other in-scope functions, how often they appear
    next to it and their status (supported = cross-sell; gap / competitor = attach opportunity for a new
    product). A modeled attach opportunity, not an observed sales attach rate."""
    with_anchor = [a for a in apps if any(p.fn == anchor for p in a.positions)]
    seen: dict[str, dict] = {}
    for a in with_anchor:
        for fn in {p.fn for p in a.positions if p.fn != anchor and p.status in IN_SCOPE}:
            p = next(x for x in a.positions if x.fn == fn)
            e = seen.setdefault(fn, {"fn": fn, "label": p.label if p.label else fn, "status": p.status, "apps": 0,
                                     "positions": 0, "names": []})  # fmt: skip
            e["apps"] += 1
            e["positions"] += sum(x.qty for x in a.positions if x.fn == fn)
            e["names"].append(a.name)
    rows = sorted(seen.values(), key=lambda e: (-e["apps"], e["label"]))
    for e in rows:
        e["share"] = e["apps"] / len(with_anchor)
    return {"apps": with_anchor, "rows": rows, "cross_sell": [e for e in rows if e["status"] == "supported"],
            "new": [e for e in rows if e["status"] != "supported"]}  # fmt: skip


def cross_sell_pairs(apps: list[Application], limit: int = 15) -> list[dict]:
    """Pairs of functions we both have parts for that appear together most often: a bundle to offer. Modeled from the
    reference architectures, not observed sales."""
    pairs: Counter = Counter()
    cat = blocks.catalogue()["functions"]
    for a in apps:
        ours = sorted({p.fn for p in a.positions if p.status == "supported"})
        for i, x in enumerate(ours):
            for y in ours[i + 1 :]:
                pairs[(x, y)] += 1
    label = lambda f: (cat.get(f) or {}).get("label", f)  # noqa: E731
    return [
        {"a": x, "b": y, "a_label": label(x), "b_label": label(y), "apps": n} for (x, y), n in pairs.most_common(limit)
    ]


def _block_fns(g: dict) -> set[str]:
    return {(b["fn"] if isinstance(b, dict) else str(b).split(" x")[0]).strip() for b in g.get("blocks") or []}


def pair_reasons(apps: list[Application], a: str, b: str, limit: int = 5) -> dict:
    """Why two functions are offered together: in which architectures they meet, whether they sit in the same block
    there, whether the diagram connects their blocks, and whether the catalogue lists them as usual companions."""
    tpls = [*blocks.templates(), *blocks.background_templates()]
    cat = blocks.catalogue()["functions"]
    rows = []
    for app in apps:
        fns = {p.fn for p in app.positions}
        if a not in fns or b not in fns:
            continue
        t = tpls[app.i]
        ga = [g for g in t.get("groups") or [] if a in _block_fns(g)]
        gb = [g for g in t.get("groups") or [] if b in _block_fns(g)]
        ids_a, ids_b = {g["id"] for g in ga}, {g["id"] for g in gb}
        same = sorted({g["label"] for g in ga if g["id"] in ids_b})
        links = [
            (x, y, str(rest[0]) if rest else "")
            for x, y, *rest in t.get("links") or []
            if (x in ids_a and y in ids_b) or (x in ids_b and y in ids_a)
        ]
        label = {g["id"]: g["label"] for g in t.get("groups") or []}
        named = [(label.get(x, x), label.get(y, y), lab) for x, y, lab in links]
        rows.append({"i": app.i, "name": app.name, "background": app.background,
                     "a_blocks": sorted({g["label"] for g in ga}), "b_blocks": sorted({g["label"] for g in gb}),
                     "same": same, "links": named})  # fmt: skip
    companion = b in ((cat.get(a) or {}).get("companions") or []) or a in ((cat.get(b) or {}).get("companions") or [])
    n_same = sum(1 for r in rows if r["same"])
    n_link = sum(1 for r in rows if r["links"] and not r["same"])
    rows.sort(key=lambda r: (not r["same"], not r["links"], r["background"], r["name"]))
    if n_same or n_link or companion:
        bits = []
        if n_same:
            blocks_named = Counter(x for r in rows for x in r["same"]).most_common(2)
            bits.append(f"same block in {n_same} of {len(rows)} ({', '.join(x for x, _ in blocks_named)})")
        if n_link:
            bits.append(f"blocks connected in {n_link}")
        if companion:
            bits.append("listed as a usual companion")
        summary = "; ".join(bits)
    else:
        summary = (
            f"in the same {len(rows)} designs but in separate blocks with no drawn connection (co-occurrence only)"
        )
    return {"rows": rows[:limit], "more": max(0, len(rows) - limit), "n": len(rows), "same": n_same, "linked": n_link,
            "companion": companion, "summary": summary,
            "notes": [(cat.get(f) or {}).get("note") for f in (a, b)]}  # fmt: skip


# ---- gaps and ranking across applications ----------------------------------------------------------------
def gaps(apps: list[Application], asp: dict, vol: dict) -> list[dict]:
    """Every function that is a gap or competitor-only somewhere, ranked. Reach = applications that need it;
    positions = design-in positions (quantity summed); adjacency = of those applications, how many already have
    a portfolio position (an anchor); TAM only where the ASP and the application volumes are known."""
    cat = blocks.catalogue()["functions"]
    out: dict[str, dict] = {}
    for a in apps:
        anchor = any(p.status == "supported" for p in a.positions)
        for fn in {p.fn for p in a.positions if p.status in ("gap", "competitor")}:
            ps = [p for p in a.positions if p.fn == fn]
            e = out.setdefault(fn, {"fn": fn, "label": (cat.get(fn) or {}).get("label", fn), "status": ps[0].status,
                                    "category": (cat.get(fn) or {}).get("category", ""), "reach": 0, "positions": 0,
                                    "adjacent": 0, "tam": 0.0, "tam_apps": 0, "apps": [], "rows": [],
                                    "competition": competition().get(fn)})  # fmt: skip
            e["reach"] += 1
            e["positions"] += sum(p.qty for p in ps)
            e["adjacent"] += 1 if anchor else 0
            e["apps"].append(a.name)
            ours = sorted({(cat.get(p.fn) or {}).get("label", p.fn) for p in a.positions if p.status == "supported"})
            qty = sum(p.qty for p in ps)
            e["rows"].append({"i": a.i, "name": a.name, "market": a.market, "qty": qty, "ours": ours})
            if fn in asp and a.name in vol:
                e["tam"] += vol[a.name] * sum(p.qty for p in ps) * asp[fn]
                e["tam_apps"] += 1
    rows = list(out.values())
    for e in rows:
        e["adjacency"] = e["adjacent"] / e["reach"] if e["reach"] else 0
    return sorted(rows, key=lambda e: (-e["reach"], -e["adjacent"], e["label"]))




def overview(apps: list[Application], asp: dict, vol: dict) -> dict:
    allpos = [p for a in apps for p in a.positions]
    m = metrics(allpos, asp)
    covs = [metrics(a.positions, asp)["coverage"] for a in apps]
    covs = [c for c in covs if c is not None]
    in_scope_fns = {p.fn for p in allpos if p.status in IN_SCOPE}
    return {
        "apps": len(apps),
        "positions": len(allpos),
        "metrics": m,
        "avg_coverage": sum(covs) / len(covs) if covs else None,
        "functions": len({p.fn for p in allpos}),
        "gap_functions": len({p.fn for p in allpos if p.status in ("gap", "competitor")}),
        "asp_known": sum(1 for f in in_scope_fns if f in asp),
        "asp_needed": len(in_scope_fns),
        "vol_known": sum(1 for a in apps if a.name in vol),
    }


# ---- competition (indicative, public catalogues) ---------------------------------------------------------
@lru_cache
def competition() -> dict[str, dict]:
    """Established suppliers per function from public catalogues: {fn: {crowding, vendors, note}}. Not market share."""
    return (yamlio.load(_COMPETITION.read_text()) if _COMPETITION.exists() else None) or {}


@lru_cache
def explanations() -> dict:
    """Terms and "About this page" texts for the Business opportunity pages (data/business/explanations.yaml)."""
    path = _COMPETITION.parent / "explanations.yaml"
    return (yamlio.load(path.read_text()) if path.exists() else None) or {"terms": {}, "pages": {}}


def sources(apps: list[Application]) -> dict:
    """Where the numbers come from, counted live: diagrams per source vendor, catalogue sizes, data files."""
    vendors: Counter = Counter()
    for t in [*blocks.templates(), *blocks.background_templates()]:
        m = re.search(r"\((?:[^()]*\b)?(TI|NXP|Qualcomm|MediaTek|Skyworks|Microchip)\b[^()]*\)\s*$", t.get("name", ""))
        vendors[m.group(1) if m else "BizDev"] += 1
    rows = blocks.catalog_rows()
    return {
        "library": sum(not a.background for a in apps),
        "background": sum(a.background for a in apps),
        "vendors": vendors.most_common(),
        "catalogue": Counter(r["manufacturer"] for r in rows),
        "functions": len(blocks.catalogue()["functions"]),
        "competition": len(competition()),
        "technology": len(technology()),
    }


# ---- markets: one function across end markets ------------------------------------------------------------
def qual_state(c: dict) -> str:
    """automotive (AEC-Q100 stated), not_automotive (industrial / commercial or "no" stated), unknown (not stated)."""
    q = (c.get("values") or {}).get("qualification")
    return (
        "automotive"
        if q == "automotive"
        else "not_automotive"
        if q in ("industrial", "commercial", "not_automotive")
        else "unknown"
    )




def markets(session: Session, apps: list[Application], mine: frozenset) -> dict:
    """Per function: the end markets (and applications) that need it, how many portfolio parts exist and their
    qualification in three states (automotive / stated not automotive / not stated).
    requalify = automotive applications need it and no part is stated automotive, but at least one is stated not
    automotive (an industrial part that could be qualified). qual_unknown = no part is stated automotive and the
    others do not state a grade: a data gap to check, not an opportunity."""
    cat = blocks.catalogue()["functions"]
    names = sorted({a.market for a in apps}, key=lambda m: (m != "Automotive", m))
    rows: dict[str, dict] = {}
    for a in apps:
        for p in a.positions:
            if p.status not in IN_SCOPE:
                continue
            label = (cat.get(p.fn) or {}).get("label", p.fn)
            e = rows.setdefault(p.fn, {"fn": p.fn, "label": label, "status": p.status, "by_market": defaultdict(list)})
            if a not in e["by_market"][a.market]:
                e["by_market"][a.market].append(a)
    for fn, e in rows.items():
        cands = [c for c in (blocks._candidates(session, fn) or []) if c["manufacturer"] in mine]
        e["parts"] = len(cands)
        qs = Counter(qual_state(c) for c in cands)
        e["auto_parts"], e["not_auto_parts"], e["unknown_parts"] = qs["automotive"], qs["not_automotive"], qs["unknown"]
        e["n_markets"] = len(e["by_market"])
        e["n_apps"] = sum(len(v) for v in e["by_market"].values())
        auto_need = bool(e["by_market"].get("Automotive"))
        e["requalify"] = auto_need and e["auto_parts"] == 0 and e["not_auto_parts"] > 0
        e["qual_unknown"] = auto_need and e["auto_parts"] == 0 and e["not_auto_parts"] == 0 and e["unknown_parts"] > 0
        e["by_market"] = dict(e["by_market"])
    paths = evidence("path")
    for e in rows.values():  # which leap: sell what we have, build on our technology, or new technology
        pa = (paths.get(e["fn"]) or {}).get("path")
        e["path"] = pa
        e["group"] = (
            "portfolio" if e["status"] == "supported"
            else "new_tech" if pa in ("new_capability", "not_pursue")
            else "gap"
        )  # fmt: skip
    out = sorted(rows.values(), key=lambda e: (-e["n_markets"], -e["n_apps"], e["label"]))
    return {"markets": names, "rows": out, "apps_per_market": Counter(a.market for a in apps)}


MARKET_GROUPS = {
    "portfolio": ("Existing portfolio", "We have parts: sell them into more markets (or qualify them for automotive)."),
    "gap": ("Portfolio gap", "No part of ours yet; it exists elsewhere in the portfolio, is a spec variant or a new "
                             "design on our technology, or the path is not assessed yet."),
    "new_tech": ("New technology", "Needs a technology we do not have: partner or acquire, or not ours to build."),
}  # fmt: skip


# ---- technology fit: frequent functions ranked by closeness to the portfolio's technology ---------------
_TECHNOLOGY = _COMPETITION.parent / "technology.yaml"
PROXIMITY_LABEL = {3: "Same technology", 2: "Adjacent", 1: "Distant", 0: "Unrelated"}
PROXIMITY_WEIGHT = {3: 1.0, 2: 0.6, 1: 0.3, 0: 0.1}
CROWDING_WEIGHT = {"low": 1.0, "medium": 0.9, "high": 0.75}
# path to product (data/business/evidence/path.yaml) replaces the technology rating where present; trend multiplies
PATH_LABEL = {"exists": "Already in portfolio (mapping missing)", "variant": "Spec variant of an existing line",
              "new_design": "New design on our technology", "new_capability": "New technology: partner / acquire",
              "not_pursue": "Not ours to build"}  # fmt: skip
PATH_SHORT = {"exists": "Exists?", "variant": "Spec variant", "new_design": "New design",
              "new_capability": "New technology", "not_pursue": "Not ours"}  # fmt: skip
PATH_WEIGHT = {"exists": 1.0, "variant": 1.0, "new_design": 0.6, "new_capability": 0.3, "not_pursue": 0.1}
TREND_WEIGHT = {"growing": 1.15, "stable": 1.0, "declining": 0.85}
EVIDENCE_TOPICS = {"path": "Path to product", "patents": "Patents", "foundry": "Foundry route",
                   "competitor_tech": "Competitor technology", "trends": "Market trend"}  # fmt: skip
FIT_ORDER = {"high": 0, "medium": 1, "low": 2}


@lru_cache
def evidence(topic: str) -> dict[str, dict]:
    """Background evidence per function (data/business/evidence/<topic>.yaml)."""
    path = _COMPETITION.parent / "evidence" / f"{topic}.yaml"
    return (yamlio.load(path.read_text()) if path.exists() else None) or {}


# system parts in the diagrams that are not semiconductor development targets
_NOT_CHIPS = {
    "external_block",
    "antenna",
    "battery_pack",
    "display",
    "hv_battery",
    "dc_link_cap",
    "motor",
    "camera_radar",
}


@lru_cache
def technology() -> dict[str, dict]:
    """Per function: proximity 0-3 to Skyworks / Qorvo technology, technologies and reasoning (public knowledge)."""
    return (yamlio.load(_TECHNOLOGY.read_text()) if _TECHNOLOGY.exists() else None) or {}


def technology_fit(apps: list[Application]) -> list[dict]:
    """Functions the portfolio does not cover (gap, competitor-only or not our product type) by how often they
    occur in all diagrams (library + background), weighted by technology proximity and competition.
    score = share of applications x proximity weight x crowding weight. Door-opener share is shown, not scored:
    this list is about frequency, not attach."""
    cat = blocks.catalogue()["functions"]
    tech, comp, n = technology(), competition(), len(apps) or 1
    rows: dict[str, dict] = {}
    for a in apps:
        anchor = any(p.status == "supported" for p in a.positions)
        for fn in {p.fn for p in a.positions if p.status in ("gap", "competitor", "na")}:
            if fn in _NOT_CHIPS:
                continue
            ps = [p for p in a.positions if p.fn == fn]
            label = (cat.get(fn) or {}).get("label", fn)
            e = rows.setdefault(fn, {"fn": fn, "label": label, "status": ps[0].status, "reach": 0, "positions": 0,
                                     "adjacent": 0, "background": 0, "apps": []})  # fmt: skip
            e["reach"] += 1
            e["positions"] += sum(p.qty for p in ps)
            e["adjacent"] += anchor
            e["background"] += a.background
            e["apps"].append(a)
    paths, trends = evidence("path"), evidence("trends")
    for fn, e in rows.items():
        t = tech.get(fn) or {}
        prox = t.get("proximity")
        c = comp.get(fn) or {}
        pa, tr = paths.get(fn) or {}, trends.get(fn) or {}
        e.update(proximity=prox, tech=t.get("tech") or [], reasoning=t.get("reasoning", ""), competition=c or None,
                 share=e["reach"] / n, adjacency=e["adjacent"] / e["reach"])  # fmt: skip
        e.update(path=pa or None, trend=tr or None)
        e["factors"] = factors = [("Applications", e["share"], f"{e['reach']} of {n} use it")]
        if pa.get("path") in PATH_WEIGHT:
            note = f"path: {PATH_LABEL[pa['path']]}"
            if prox is not None:
                note += f" (replaces technology rating {PROXIMITY_LABEL[prox]} {PROXIMITY_WEIGHT[prox]})"
            factors.append(("Path to product", PATH_WEIGHT[pa["path"]], note))
        else:
            label = PROXIMITY_LABEL.get(prox, "not rated")
            factors.append(("Technology", PROXIMITY_WEIGHT.get(prox, 0.05), f"rating: {label}"))
        crowd = c.get("crowding")
        factors.append(("Competition", CROWDING_WEIGHT.get(crowd, 0.85), CROWDING_LABEL.get(crowd, "not assessed")))
        if tr.get("outlook") in TREND_WEIGHT:
            factors.append(("Trend", TREND_WEIGHT[tr["outlook"]], f"outlook: {tr['outlook']}"))
        e["score"] = 1.0
        for _, w, _ in factors:
            e["score"] *= w
    return sorted(rows.values(), key=lambda e: (-e["score"], -e["reach"], e["label"]))


# ---- where to hunt: companies that build the applications (public, indicative) ------------------------------
@lru_cache
def customers() -> dict[str, dict]:
    """Application segments with the companies that build them: {segment: {label, match, customers, source}}."""
    path = _COMPETITION.parent / "customers.yaml"
    return ((yamlio.load(path.read_text()) if path.exists() else None) or {}).get("segments") or {}


@lru_cache(maxsize=4096)
def segments_of(name: str) -> tuple[str, ...]:
    low = name.lower()
    return tuple(k for k, s in customers().items() if any(str(m).lower() in low for m in s.get("match") or []))


def hunt_by_segment(apps: list[Application]) -> list[dict]:
    seg = {a.name: segments_of(a.name) for a in apps}  # each application matched once, not once per segment
    out = []
    for k, s in customers().items():
        matched = [a for a in apps if k in seg[a.name]]
        out.append({"id": k, "label": s.get("label", k), "apps": matched, "customers": s.get("customers") or [],
                    "source": s.get("source", ""), "check": s.get("check")})  # fmt: skip
    return sorted(out, key=lambda e: (-len(e["apps"]), e["label"]))


def hunt_for_function(apps: list[Application], fn: str) -> list[dict]:
    """Companies that build systems needing the function, ranked by how many of those applications they cover."""
    by: dict[str, dict] = {}
    for a in apps:
        if not any(p.fn == fn for p in a.positions):
            continue
        for k in segments_of(a.name):
            for c in customers()[k].get("customers") or []:
                e = by.setdefault(c["name"], {**c, "apps": [], "segments": []})
                if a.name not in e["apps"]:
                    e["apps"].append(a.name)
                label = customers()[k].get("label", k)
                if label not in e["segments"]:
                    e["segments"].append(label)
    return sorted(by.values(), key=lambda e: (-len(e["apps"]), e["name"]))


# ---- technology base: public platforms of Skyworks and Qorvo ----------------------------------------------------
@lru_cache
def capabilities() -> dict[str, dict]:
    path = _COMPETITION.parent / "capabilities.yaml"
    return ((yamlio.load(path.read_text()) if path.exists() else None) or {}).get("platforms") or {}


def platforms_for(fn: str) -> list[tuple[str, dict]]:
    return [(k, p) for k, p in capabilities().items() if fn in (p.get("functions") or [])]


# ---- opportunity explorer: one row per function, several views; formulas unchanged ---------------------------
GAP_TYPE_LABEL = {
    "candidate": "Candidate exists – requirements not validated",
    "mapping": "Probably sold already – catalogue mapping missing",
    "true_gap": "True portfolio gap",
    "competitor_only": "Competitor only",
    "unknown_evidence": "Not assessed yet – gap without evidence",
    "not_ours": "Not our product type",
}
SCOPES = {"all": "All reference architectures (library + background)", "library": "Library architectures only"}


def gap_type(status: str, path: dict | None) -> str:
    """Separates a real gap from a missing catalogue mapping and from missing evidence. A confirmed electrical
    mismatch needs application requirements per socket, which the data does not hold yet, so it is never inferred."""
    p = (path or {}).get("path")
    if status == "supported":
        return "candidate"
    if status == "na" or p == "not_pursue":
        return "not_ours"
    if p == "exists":
        return "mapping"
    if status == "competitor":
        return "competitor_only"
    return "true_gap" if p in ("variant", "new_design", "new_capability") else "unknown_evidence"


def in_scope(apps: list[Application], scope: str) -> list[Application]:
    return [a for a in apps if not a.background] if scope == "library" else apps


def explorer(apps: list[Application], asp: dict, vol: dict) -> list[dict]:
    """Union of the gap ranking (reach, door openers, sockets, TAM) and the technology-fit ranking (path / technology,
    competition, trend, score) per function, with its gap type. Both formulas are the existing ones."""
    gap = {e["fn"]: e for e in gaps(apps, asp, vol)}
    fit = {e["fn"]: e for e in technology_fit(apps)}
    paths = evidence("path")
    out = []
    for fn in {*gap, *fit}:
        g, f = gap.get(fn) or {}, fit.get(fn) or {}
        base = g or f
        reach = base["reach"]
        row = {
            "fn": fn, "label": base["label"], "status": base["status"],
            "gap_type": gap_type(base["status"], paths.get(fn)),
            "reach": reach, "positions": base["positions"], "adjacent": base.get("adjacent", 0),
            "adjacency": (base.get("adjacent", 0) / reach) if reach else 0,
            "tam": g.get("tam", 0.0), "tam_apps": g.get("tam_apps", 0),
            "competition": competition().get(fn), "path": paths.get(fn), "proximity": f.get("proximity"),
            "trend": evidence("trends").get(fn), "score": f.get("score"), "factors": f.get("factors") or [],
            "background": f.get("background", sum(a.background for a in apps if any(p.fn == fn for p in a.positions))),
        }  # fmt: skip
        out.append(row)
    return out


# end markets in sub-groups, so a market filter is a few short columns instead of one long row
MARKET_SUBGROUPS = {
    "Vehicles & motion": ["Automotive", "Motor drives"],
    "Industrial & power": ["Industrial", "Power & isolation", "Appliances & building", "Medical"],
    "Communications & computing": ["Communications equipment", "RF & connectivity", "Enterprise & data center"],
    "Consumer": ["Consumer & personal electronics"],
}


def market_subgroups(names) -> list[tuple[str, list[str]]]:
    """The given market names grouped as MARKET_SUBGROUPS (in that order); unknown names under 'Other'."""
    names = list(names)
    out = [(t, [m for m in ms if m in names]) for t, ms in MARKET_SUBGROUPS.items()]
    known = {m for ms in MARKET_SUBGROUPS.values() for m in ms}
    out.append(("Other", [m for m in names if m not in known]))
    return [(t, ms) for t, ms in out if ms]
