"""Priority score for Opportunities > Gaps & new technology (owner, 25 Oct 2026): one transparent number 0–100 per
gap, so RF and power work comes first and an LDO is listed but ranks low.

    Priority = 100 × (wT × T + wL × L + wD × D)

T technology relation (curated table), L likeliness (feasibility, a platform of ours, US patent depth, the owner's
review answers) and D diagrams (log scale), each 0–1. Weights and tables live in data/business/priority.yaml. The
Opportunity score (app/services/scoring.py) is a different measure and stays as it is.
"""

import math
from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT
from app.services import blocks, patents, scoring
from app.services import opportunity as op

FILE = PROJECT_ROOT / "data" / "business" / "priority.yaml"
KEYS = ("technology", "likeliness", "diagrams")
PARAMS = {"technology": "wt", "likeliness": "wl", "diagrams": "wd"}  # URL parameters of the owner's sliders
# owner, 26 Oct 2026: patents are machine-checked, never reviewed by the owner: a small, labelled bonus, capped
PATENT_LABEL = "indicative, not reviewed"
PATENT_CAP = 0.05  # default cap on the patent bonus to L (priority.yaml patent_bonus_cap)


@lru_cache
def config() -> dict:
    return yamlio.load(FILE.read_text())


def default_weights() -> dict[str, float]:
    return _normalise(config()["weights"])


def _normalise(w: dict) -> dict[str, float]:
    total = sum(max(0.0, float(w.get(k) or 0)) for k in KEYS)
    if total <= 0:
        return default_weights()
    return {k: max(0.0, float(w.get(k) or 0)) / total for k in KEYS}


def weights(wt: str = "", wl: str = "", wd: str = "", allowed: bool = True) -> tuple[dict[str, float], bool]:
    """(weights adding up to 1, custom?) from the owner's sliders in percent; blank, bad or all-zero values and guests
    (allowed=False) get the defaults."""
    base = default_weights()
    if not allowed:
        return base, False
    got = {}
    for k, raw in zip(KEYS, (wt, wl, wd), strict=True):
        try:
            v = int(str(raw).strip())
        except ValueError:
            continue
        got[k] = min(100, max(0, v)) / 100
    if not got:
        return base, False
    w = _normalise({k: got.get(k, base[k]) for k in KEYS})
    return w, any(abs(w[k] - base[k]) > 0.004 for k in KEYS)


def percent(w: dict[str, float]) -> dict[str, int]:
    return {k: round(100 * w[k]) for k in KEYS}


# ---- the three factors ------------------------------------------------------------------------------------------
def level(fn: str) -> tuple[str | None, str]:
    """(technology level key or None when not mapped, where it comes from: 'function' or 'category')."""
    t = config()["technology"]
    if fn in (t.get("functions") or {}):
        return t["functions"][fn], "function"
    cat = (blocks.catalogue()["functions"].get(fn) or {}).get("category")
    if cat in (t.get("categories") or {}):
        return t["categories"][cat], "category"
    return None, ""


def relation(fn: str) -> dict:
    """T for a function: value, level key, label, help and whether it is mapped."""
    t = config()["technology"]
    key, src = level(fn)
    if key is None:
        return {"value": float(t["default"]), "level": None, "label": "Not mapped yet", "help": "", "mapped": False,
                "source": ""}  # fmt: skip
    lv = t["levels"][key]
    return {"value": float(lv["value"]), "level": key, "label": lv["label"], "help": lv.get("help", ""), "mapped": True,
            "source": src}  # fmt: skip


@lru_cache
def _platforms() -> dict[str, list[str]]:
    """Function -> names of current public platforms of ours (processes, filters, packaging, design IP) serving it;
    manufacturing sites are left out."""
    out: dict[str, list[str]] = {}
    for p in op.capabilities().values():
        if not p.get("owner") or p.get("kind") == "manufacturing" or p.get("status") not in (None, "current"):
            continue
        for fn in p.get("functions") or []:
            out.setdefault(fn, []).append(p.get("name", ""))
    return out


def patent_bonus(fn: str) -> dict:
    """The likeliness bonus for US patent depth (owner, 25 Oct 2026): from the function's entry in patents.yaml, else
    the platform entry of patents_platforms.yaml that covers it. {depth, bonus, source, label}; bonus 0 without data."""
    got = patents.depth(fn)
    if not got:
        return {"depth": None, "bonus": 0.0, "source": "", "label": ""}
    cfg = config()["likeliness"]
    table = cfg.get("patent_bonus") or {}
    cap = float(cfg.get("patent_bonus_cap", PATENT_CAP))
    return {**got, "bonus": min(cap, float(table.get(got["depth"]) or 0))}


def likeliness(e: dict) -> dict:
    """L for a row: from its feasibility group (1–3), plus a bonus for a platform of ours and one for US patent depth
    (capped at 1.0), or the owner's answer (no bonus then)."""
    cfg = config()["likeliness"]
    own = (cfg.get("owner") or {}).get(e["fn"])
    path = e.get("path")
    path = path.get("path") if isinstance(path, dict) else path
    pat = {"depth": None, "bonus": 0.0, "source": "", "label": ""}
    if own:
        v, basis = float(own["value"]), own["note"]
    elif path == "not_pursue":
        v, basis = float(cfg["not_pursue"]), "path to product: not ours to build"
    else:
        feas = e.get("feasibility")
        if feas is None:
            feas = scoring.feasibility(e.get("distance"))
        if feas in cfg["feasibility"]:
            f = cfg["feasibility"][feas]
            v, basis = float(f["value"]), f"feasibility {feas}: {f['help'].lower()}"
        else:
            v, basis = float(cfg["not_assessed"]), "no path to product or technology rating yet"
        plats = _platforms().get(e["fn"])
        if plats and v < 1.0:
            v = min(1.0, v + float(cfg["platform_bonus"]))
            basis += f" · + {cfg['platform_bonus']:g} for a platform of ours ({plats[0]})"
        pat = patent_bonus(e["fn"])
        if pat["bonus"]:
            where = f", {pat['label']} platform" if pat["source"] == "platform" else ""
            capped = (" (L already 1.0)" if v >= 1.0 - 1e-9 else
                      " (capped at 1.0)" if v + pat["bonus"] > 1.0 + 1e-9 else "")  # fmt: skip
            v = min(1.0, v + pat["bonus"])
            basis += f" · + {pat['bonus']:g} for US patents ({pat['depth']}{where}; {PATENT_LABEL}){capped}"
    label = next(x["label"] for x in cfg["labels"] if v >= x["from"] - 1e-9)
    return {"value": round(v, 3), "label": label, "basis": basis, "owner": bool(own), "patent": pat}


def diagrams_n(e: dict) -> float:
    bg = e.get("background") or 0
    return (e["reach"] - bg) + float(config()["diagrams"]["background_weight"]) * bg


def diagrams(n: float, n_max: float) -> float:
    """D = log(1 + n) / log(1 + n_max): 40 diagrams is not 10 × better than 4."""
    return math.log1p(n) / math.log1p(n_max) if n_max > 0 else 0.0


# ---- the score --------------------------------------------------------------------------------------------------
def score(e: dict, n_max: float, w: dict[str, float] | None = None, n: float | None = None) -> dict:
    """The priority of one row; n = the diagrams that need it (default: library + weighted background)."""
    w = w or default_weights()
    t, li = relation(e["fn"]), likeliness(e)
    n = diagrams_n(e) if n is None else n
    d = diagrams(n, n_max)
    total = 100 * (w["technology"] * t["value"] + w["likeliness"] * li["value"] + w["diagrams"] * d)
    cfg = config()
    return {
        "score": round(total, 1), "T": t["value"], "L": li["value"], "D": round(d, 3), "n": n, "n_max": n_max,
        "t_level": t["level"], "t_label": t["label"], "t_help": t["help"], "mapped": t["mapped"],
        "l_label": li["label"], "l_basis": li["basis"], "l_owner": li["owner"], "patent": li["patent"],
        "focus": t["value"] >= cfg["focus_from"] - 1e-9, "outside": t["value"] < cfg["outside_below"] - 1e-9,
        "w": w,
    }  # fmt: skip


def annotate(rows: list[dict], w: dict[str, float] | None = None, count=None) -> list[dict]:
    """Adds e["priority"] to every row: the explorer rows of Gaps & new technology and its detailed table, and the
    Markets rows. n_max is the most-needed row that is not a customer part, so the overview cards and the detailed
    table give the same number whatever is filtered. count(e) gives a page's own diagram count (Markets: the
    applications in the chosen markets); T and L never depend on the page."""
    count = count or diagrams_n
    pool = [e for e in rows if e.get("gap_type") != "not_ours"]
    n_max = max((count(e) for e in pool), default=0)
    for e in rows:
        e["priority"] = score(e, n_max, w, count(e))
    return rows


def with_feasibility(rows: list[dict], tab: dict) -> list[dict]:
    """Rows of another page (Markets) with the feasibility and distance of the Opportunity score table, so L is the
    same as on Gaps & new technology."""
    for e in rows:
        s = scoring.fields(tab["rows"].get(e["fn"]))
        e["feasibility"], e["distance"] = s["feasibility"], s["distance"]
    return rows


def sort_key(e: dict):
    p = e["priority"]
    return (-p["score"], -p["T"], -p["n"], e["label"].lower())


def ranked(rows: list[dict]) -> list[dict]:
    return sorted(rows, key=sort_key)


def sections(rows: list[dict], show: str = "focus") -> dict:
    """Highest priority first. "RF & power only": the focus rows (technology relation >= focus_from) and how many are
    hidden. "All": every row in three groups, each highest first: RF & power, then general power and adjacent
    technology, then outside our technology focus, so an LDO never sits above RF and power work (owner, 25 Oct 2026)
    and nothing disappears."""
    rows = ranked(rows)
    main = [e for e in rows if e["priority"]["focus"]]
    if show == "all":
        outside = [e for e in rows if e["priority"]["outside"]]
        middle = [e for e in rows if not e["priority"]["focus"] and not e["priority"]["outside"]]
        return {"main": main, "middle": middle, "outside": outside, "hidden": 0}
    return {"main": main, "middle": [], "outside": [], "hidden": len(rows) - len(main)}


def unmapped(rows: list[dict]) -> list[str]:
    """Functions on the page with no technology relation in the YAML (they get the default)."""
    return sorted({e["fn"] for e in rows if not relation(e["fn"])["mapped"]})


def chips(e: dict) -> list[str]:
    p = e["priority"]
    n = round(p["n"]) if abs(p["n"] - round(p["n"])) < 1e-9 else p["n"]
    out = [p["t_label"], f"{n:g} diagram{'' if n == 1 else 's'}", p["l_label"]]
    return out + ([f"patents: {p['patent']['depth']}"] if p["patent"]["bonus"] else [])


def example(e: dict) -> str:
    """The sum written out, e.g. 100 × (0.45 × 1.00 + 0.30 × 0.70 + 0.25 × 0.43) = 76.7."""
    p, w = e["priority"], e["priority"]["w"]
    return (f"100 × ({w['technology']:.2f} × {p['T']:.2f} + {w['likeliness']:.2f} × {p['L']:.2f} + "
            f"{w['diagrams']:.2f} × {p['D']:.2f}) = {p['score']:.1f}")  # fmt: skip


def patent_example(rows: list[dict]) -> dict | None:
    """The highest-priority row whose likeliness the patent bonus raised, other than the top item, for the worked
    examples."""
    top = (ranked(rows) or [None])[0]
    hit = [e for e in rows if e is not top and "for US patents" in e["priority"]["l_basis"]
           and "already 1.0" not in e["priority"]["l_basis"] and "@" not in e.get("key", e["fn"])]  # fmt: skip
    return (ranked(hit) or [None])[0]


def ldo_example(rows: list[dict]) -> dict | None:
    """An LDO row for the worked example: the PoL LDO if listed, else any LDO, else the first general-power row."""
    by = {e["fn"]: e for e in rows if "@" not in e.get("key", e["fn"])}
    if "pol_ldo" in by:
        return by["pol_ldo"]
    ldo = [e for e in rows if "ldo" in e["fn"]]
    gen = [e for e in rows if e["priority"]["t_level"] == "power_commodity"]
    return (ranked(ldo) or ranked(gen) or [None])[0]


def levels() -> list[tuple[str, dict]]:
    lv = config()["technology"]["levels"]
    return sorted(lv.items(), key=lambda kv: -kv[1]["value"])
