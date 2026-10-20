"""Opportunity score: one additive score 0–100 per function, with a confidence, for the Opportunity explorer, Technology
fit, the Automotive map (Top moves) and the preliminary cases; Cross-sell's Bundle strength uses the same 0–100 scale.
Weights and mappings live in data/business/scoring.yaml (approved 2026-10-20) and are shown on the Methodology page.

score = Σ weight × factor (each 0–100): demand, portfolio distance, architecture fit, competition, market trend.
Missing data scores the neutral 50 with low confidence. Overall confidence = the lowest of demand, distance and
competition; a reviewer's latest "wrong" on the data behind a factor lowers that factor one step.
"""

import math
from functools import lru_cache

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import DataReview
from app.services import blocks
from app.services import opportunity as op

FILE = PROJECT_ROOT / "data" / "business" / "scoring.yaml"
CONFIDENCE = ("low", "medium", "high")
REVIEWED = ("path", "technology", "competition", "trends")  # datasets behind a factor; a "wrong" lowers it
_CACHE: dict[tuple, dict] = {}


@lru_cache
def config() -> dict:
    return yamlio.load(FILE.read_text())


def weights() -> dict[str, int]:
    return config()["weights"]


def conf(c) -> str:
    """high / medium / low ("med" in the case files is medium); missing or unknown is low."""
    c = str(c or "").lower()
    c = "medium" if c == "med" else c
    return c if c in CONFIDENCE else "low"


def lower(c, steps: int = 1) -> str:
    return CONFIDENCE[max(0, CONFIDENCE.index(conf(c)) - steps)]


def band(score) -> str | None:
    return None if score is None else next(b for b, lim in config()["bands"].items() if score >= lim)


def feasibility(d) -> int | None:
    return config()["feasibility"].get(d) if d is not None else None


def distance_label(d) -> str:
    return config()["distance"]["labels"].get(d, "not assessed")


def distance(path: dict | None = None, proximity=None, status: str = "") -> tuple[int | None, str, str, str]:
    """(distance 0–4 or None, basis, confidence, dataset behind it): the path to product where assessed, else 0 for a
    function we sell, else the technology rating."""
    cfg = config()["distance"]
    p = (path or {}).get("path")
    if p in cfg["path"]:
        return cfg["path"][p], f"path: {op.PATH_LABEL[p]}", conf(path.get("confidence")), "path"
    if status == "supported":
        return 0, "we sell a candidate part", cfg["supported_confidence"], ""
    if proximity in cfg["technology"]:
        label = op.PROXIMITY_LABEL[proximity]
        return cfg["technology"][proximity], f"technology rating: {label}", cfg["technology_confidence"], "technology"
    return None, "no path or technology rating yet", "low", ""


def ladder_distance(level: str, own=None) -> int | None:
    """Automotive ladder letter -> distance; a curated row may state its own (e.g. 2 for a package from our dies)."""
    return own if isinstance(own, int) else config()["distance"]["ladder"].get(level)


def _factor(key, value, basis, c, review=None) -> dict:
    if value is None:
        value, c = config()["neutral"], "low"
    if review == "wrong":
        c, basis = lower(c), f"{basis} · disputed by a reviewer"
    return {"key": key, "label": config()["labels"][key], "value": round(value), "weight": weights()[key],
            "basis": basis, "confidence": conf(c)}  # fmt: skip


def result(factors: list[dict], d: int | None = None) -> dict:
    score = round(sum(f["value"] * f["weight"] for f in factors) / 100)
    by = {f["key"]: f for f in factors}
    overall = min((by[k]["confidence"] for k in config()["confidence"]["overall_from"]), key=CONFIDENCE.index)
    return {"score": score, "band": band(score), "confidence": overall, "factors": factors, "distance": d,
            "feasibility": feasibility(d), "demand_basis": "tam" if by["demand"]["basis"].startswith("TAM") else
            "diagrams"}  # fmt: skip


EMPTY = {"score": None, "band": None, "confidence": None, "factors": [], "distance": None, "feasibility": None,
         "demand_basis": None}  # fmt: skip


def fields(s: dict | None) -> dict:
    """The score fields a page row carries (empty for a function that is not scored)."""
    return {k: (s or EMPTY)[k] for k in EMPTY}


# ---- factor inputs from the block diagrams ---------------------------------------------------------------------
def _usage(apps: list[op.Application], asp: dict, vol: dict) -> dict[str, dict]:
    """Per function: weighted sockets, library / background diagrams, door openers (diagrams with one of our parts),
    neighbours (one of our parts in the same block or a connected one) and TAM where ASP and volume are entered."""
    tpls = [*blocks.templates(), *blocks.background_templates()]
    w = config()["demand"]
    out: dict[str, dict] = {}
    for a in apps:
        t = tpls[a.i]
        groups = {g.get("id"): op._block_fns(g) for g in t.get("groups") or []}
        links = [(x, y) for x, y, *_ in t.get("links") or []]
        ours = {p.fn for p in a.positions if p.status == "supported"}
        for fn in {p.fn for p in a.positions}:
            qty = sum(p.qty for p in a.positions if p.fn == fn)
            status = next(p.status for p in a.positions if p.fn == fn)
            u = out.setdefault(fn, {"status": status, "raw": 0.0, "lib": 0, "bg": 0, "door": 0, "near": 0,
                                    "tam": 0.0, "tam_apps": 0})  # fmt: skip
            u["raw"] += qty * (w["background"] if a.background else w["library"])
            u["bg" if a.background else "lib"] += 1
            others = ours - {fn}
            u["door"] += bool(others)
            mine = {g for g, fns in groups.items() if fn in fns}
            with_ours = {g for g, fns in groups.items() if fns & others}
            u["near"] += bool(mine & with_ours) or any(
                (x in mine and y in with_ours) or (y in mine and x in with_ours) for x, y in links
            )
            if fn in asp and a.name in vol:
                u["tam"] += vol[a.name] * qty * asp[fn]
                u["tam_apps"] += 1
    return out


def _diagram_confidence(n_library: int) -> str:
    return "high" if n_library >= config()["demand"]["confident_from"] else "medium" if n_library else "low"


def _demand(u: dict, top: float) -> tuple:
    cfg = config()["demand"]
    if u["tam_apps"] and u["tam"] > 0:
        lo, hi = math.log10(cfg["tam_low"]), math.log10(cfg["tam_high"])
        v = min(100.0, max(0.0, 100 * (math.log10(u["tam"]) - lo) / (hi - lo)))
        return v, f"TAM ${u['tam']:,.0f} per year ({u['tam_apps']} applications with a volume)", cfg["tam_confidence"]
    c = _diagram_confidence(u["lib"])
    sockets = f"{u['raw']:g} socket{'' if u['raw'] == 1 else 's'}"
    basis = f"{sockets} (weighted) in {u['lib']} library + {u['bg']} background diagrams (top function = 100)"
    return (100 * u["raw"] / top if top else None), basis, c


def _n(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def _competition(c: dict | None) -> tuple:
    cfg = config()["competition"]
    crowd = (c or {}).get("crowding")
    if crowd not in cfg["values"]:
        return None, "not assessed", "low"
    status = ((c or {}).get("check") or {}).get("status")
    basis = f"{op.CROWDING_LABEL[crowd]} ({_n(len(c.get('vendors') or []), 'supplier')})"
    return cfg["values"][crowd], basis, cfg["confidence"].get(status, cfg["vendor_count_confidence"])


def _trend(t: dict | None) -> tuple:
    vals = config()["trend"]["values"]
    t = t or {}
    if t.get("regulation"):
        return vals["growing"], f"regulation: {t['regulation']}", conf(t.get("confidence"))
    if t.get("outlook") in vals:
        return vals[t["outlook"]], f"outlook: {t['outlook']}", conf(t.get("confidence"))
    return None, "no trend data", "low"


def _score(fn: str, u: dict, top: float, verdicts: dict, dist: tuple | None = None) -> dict:
    """One function's score; dist = (distance, basis, confidence) replaces the function's own distance (a case's
    headline feature, an automotive ladder step)."""
    cfg = config()["architecture"]
    reach = u["lib"] + u["bg"]
    door, near = u["door"] / reach, u["near"] / reach
    if dist is None:
        d, basis, c, ds = distance(op.evidence("path").get(fn), (op.technology().get(fn) or {}).get("proximity"),
                                   u["status"])  # fmt: skip
        review = verdicts.get((ds, fn)) if ds else None
    else:
        (d, basis, c), review = dist, None
    v, dbasis, dc = _demand(u, top)
    arch = 100 * (cfg["door_opener"] * door + cfg["neighbour"] * near)
    abasis = f"door openers {door:.0%} · our part in the same or a connected block {near:.0%}"
    factors = [
        _factor("demand", v, dbasis, dc),
        _factor("distance", config()["distance"]["points"].get(d), f"{d} · {basis}" if d is not None else basis, c,
                review),
        _factor("architecture", arch, abasis, _diagram_confidence(u["lib"])),
        _factor("competition", *_competition(op.competition().get(fn)), verdicts.get(("competition", fn))),
        _factor("trend", *_trend(op.evidence("trends").get(fn)), verdicts.get(("trends", fn))),
    ]  # fmt: skip
    return result(factors, d)


def scorable(fn: str, u: dict) -> bool:
    """Chips we could build: in scope, not a system part, and not marked "not ours to build"."""
    return (u["status"] in ("supported", "gap", "competitor") and fn not in op._NOT_CHIPS
            and (op.evidence("path").get(fn) or {}).get("path") != "not_pursue")  # fmt: skip


def table(apps: list[op.Application], asp: dict | None = None, vol: dict | None = None,
          verdicts: dict | None = None, key: tuple | None = None) -> dict:  # fmt: skip
    """Scores of every function in the applications: {"rows": {fn: score}, "usage", "top", "verdicts"}. Demand is
    scaled to the most-needed scorable function, so a new part mapping does not rescale everyone else."""
    if key is not None and key in _CACHE:
        return _CACHE[key]
    use, verdicts = _usage(apps, asp or {}, vol or {}), verdicts or {}
    top = max((u["raw"] for fn, u in use.items() if scorable(fn, u)), default=0)
    out = {"rows": {fn: _score(fn, u, top, verdicts) for fn, u in use.items() if scorable(fn, u)},
           "usage": use, "top": top, "verdicts": verdicts}  # fmt: skip
    if key is not None:
        if len(_CACHE) > 16:
            _CACHE.clear()
        _CACHE[key] = out
    return out


def verdicts(session: Session) -> dict[tuple[str, str], str]:
    """Latest verdict per (dataset, key) for the datasets behind a factor."""
    q = select(DataReview.dataset, DataReview.key, DataReview.verdict).where(DataReview.dataset.in_(REVIEWED))
    return {(ds, k): v for ds, k, v in session.execute(q.order_by(DataReview.id))}


def review_version(session: Session) -> tuple:
    return session.execute(select(func.count(DataReview.id), func.max(DataReview.id))).one()


def for_session(session: Session, apps: list[op.Application], asp: dict | None = None,
                vol: dict | None = None) -> dict:  # fmt: skip
    """The table with reviews applied, cached per data version, reviews, statuses and commercial inputs."""
    asp, vol = asp or {}, vol or {}
    statuses = frozenset((p.fn, p.status) for a in apps for p in a.positions)
    key = (blocks._data_version(session), tuple(review_version(session)), len(apps), hash(statuses),
           hash(frozenset(asp.items())), hash(frozenset(vol.items())))  # fmt: skip
    if key in _CACHE:
        return _CACHE[key]
    return table(apps, asp, vol, verdicts(session), key)


def combined(session: Session) -> dict:
    """The table for the combined Skyworks + Qorvo portfolio over all diagrams, with the entered ASPs and volumes."""
    apps = op.with_status(op.applications(), op.makers(session), op.COMPANIES["combined"][1])
    return for_session(session, apps, *op.inputs(session))


def rescore(tab: dict, fn: str, d: int | None, basis: str, c: str) -> dict | None:
    """A function's score with the distance of a specific step (case headline, automotive ladder); None when the
    function is not in the diagrams or not ours to build."""
    u = tab["usage"].get(fn)
    if not u or not scorable(fn, u):
        return None
    return _score(fn, u, tab["top"], tab["verdicts"], (d, basis, c))


def band_row(tab: dict, row: dict) -> dict:
    """An RF band gap from RF coverage: demand from the library diagrams that need the band, distance from the coverage
    status, competition from the competitor parts in the band (else neutral); architecture is not known per band."""
    cfg, top = config()["distance"], tab["top"]
    need = row["reach"]
    dc = _diagram_confidence(need)
    w = config()["demand"]["library"]
    d = cfg["rf"].get(row.get("rf_kind"))
    crowd = (row.get("competition") or {}).get("crowding")
    comp = config()["competition"]
    rivals = _n(len((row.get("competition") or {}).get("vendors") or []), "supplier")
    factors = [
        _factor("demand", 100 * min(1.0, need * w / top) if top else None,
                f"{need} library diagrams need this band (top function = 100)", dc),
        _factor("distance", cfg["points"].get(d), f"{d} · RF coverage: {row.get('band_note', '')}",
                cfg["rf_confidence"]),
        _factor("architecture", None, "not known per band", "low"),
        _factor("competition", comp["values"].get(crowd),
                f"{op.CROWDING_LABEL[crowd]} ({rivals} with parts in the band)"
                if crowd else "no competitor part in the band", comp["vendor_count_confidence"]),
        _factor("trend", *_trend(op.evidence("trends").get(row["fn"]))),
    ]  # fmt: skip
    return result(factors, d)


def bundle(share: float, same: float, linked: float) -> int:
    """Cross-sell Bundle strength 0–100."""
    b = config()["bundle"]
    return round(100 * (share * b["together"] + same * b["same_block"] + linked * b["connected"]))
