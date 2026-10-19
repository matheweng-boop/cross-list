"""Business opportunity: application-driven portfolio intelligence on top of the block-diagram applications.

Model (a graph, kept simple):
  application (data/blocks/templates.yaml) -> functional block (level 2: the diagram group)
    -> design-in position (level 3: a block = function id x quantity)
    -> product candidates (level 4: Skyworks / Qorvo / competitor parts that can fill the function).
Alternative parts for one position count once: coverage is counted per position, never per SKU.

Position status for a chosen company (or the combined Skyworks + Qorvo portfolio):
  supported   a part of the company exists for the function (candidate, not yet checked against the
              application's electrical requirements)
  gap         the function is in scope but no company part exists in Cross List
  competitor  only other companies have parts
  na          customer / platform part or outside the semiconductor scope (excluded)
  unknown     the function is not in the catalogue (excluded from the confirmed score, shown separately)

Commercial data (ASP per function, annual volume per application) is optional. Count-based coverage never
needs it; revenue-weighted figures use only the priced positions and always come with their completeness.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import BusinessInput, Manufacturer, ManufacturerRole, Part
from app.services import blocks

COMPANIES = {
    "combined": ("Skyworks + Qorvo", frozenset({"Skyworks", "Qorvo"})),
    "skyworks": ("Skyworks", frozenset({"Skyworks"})),
    "qorvo": ("Qorvo", frozenset({"Qorvo"})),
}
IN_SCOPE = ("supported", "gap", "competitor")
STATUS_LABEL = {"supported": "Portfolio", "gap": "Gap (opportunity)", "competitor": "Competitor only",
                "na": "Outside scope", "unknown": "Unknown"}  # fmt: skip


def company(key: str) -> tuple[str, str, frozenset]:
    key = key if key in COMPANIES else "combined"
    return (key, *COMPANIES[key])


# ---- products per function -------------------------------------------------------------------------------
def makers(session: Session) -> dict[str, dict[str, int] | None]:
    """Parts per manufacturer for every function; None for customer / external functions. Competitors come from
    the Cross List families (e.g. TI and Novosense isolators)."""
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
    out: dict[str, dict[str, int] | None] = {}
    for fn, f in cat.items():
        cands = blocks._candidates(session, fn)
        if cands is None:
            out[fn] = None
            continue
        c = Counter(x["manufacturer"] for x in cands)
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


def applications() -> list[Application]:
    cat = blocks.catalogue()["functions"]
    out = []
    for i, t in enumerate(blocks.templates()):
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
        out.append(Application(i, blocks.display_name(t), t.get("category") or "Other", pos))
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
    return {"apps": with_anchor, "cross_sell": [e for e in rows if e["status"] == "supported"],
            "new": [e for e in rows if e["status"] != "supported"]}  # fmt: skip


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
                                    "adjacent": 0, "tam": 0.0, "tam_apps": 0, "apps": []})  # fmt: skip
            e["reach"] += 1
            e["positions"] += sum(p.qty for p in ps)
            e["adjacent"] += 1 if anchor else 0
            e["apps"].append(a.name)
            if fn in asp and a.name in vol:
                e["tam"] += vol[a.name] * sum(p.qty for p in ps) * asp[fn]
                e["tam_apps"] += 1
    rows = list(out.values())
    for e in rows:
        e["adjacency"] = e["adjacent"] / e["reach"] if e["reach"] else 0
    return sorted(rows, key=lambda e: (-e["reach"], -e["adjacent"], e["label"]))


def reach_of_portfolio(apps: list[Application]) -> list[dict]:
    """Functions the portfolio already supports, by how many applications need them (where to push existing
    products: application engineering / marketing rather than a new product)."""
    cat = blocks.catalogue()["functions"]
    c: dict[str, dict] = {}
    for a in apps:
        for fn in {p.fn for p in a.positions if p.status == "supported"}:
            e = c.setdefault(fn, {"fn": fn, "label": (cat.get(fn) or {}).get("label", fn), "reach": 0, "positions": 0})
            e["reach"] += 1
            e["positions"] += sum(p.qty for p in a.positions if p.fn == fn)
    return sorted(c.values(), key=lambda e: (-e["reach"], e["label"]))


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
