"""Priority score for Opportunities > Gaps & new technology (owner, 25 Oct 2026): one transparent number 0–100 per
gap, so RF and power work comes first and an LDO is listed but ranks low.

    Priority = 100 × (wT × T + wL × L + wD × D)

T technology relation (curated table), L likeliness (feasibility, a platform of ours, the owner's review answers) and
D diagrams (log scale), each 0–1, plus a signed patent adjustment of at most ± patents.cap points from the patent
barrier of the function's technology platform (owner, 6 Nov 2026; it replaced the depth-based bonus to L).
Weights and tables live in data/business/priority.yaml. The Opportunity score (app/services/scoring.py) is a different
measure and stays as it is.
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
# owner, 26 Oct 2026: patents are machine-checked, never reviewed by the owner: small and labelled
PATENT_LABEL = "indicative, not reviewed"


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


# ---- patent barrier (owner, 6 Nov 2026) -------------------------------------------------------------------------
# "some metric between similarity to our technology, distance to our technology, and difficulty in recreating that
# technology": a barrier 0-100 per function from its technology platform, and a signed adjustment of the priority
# (a low barrier a small bonus, a high one a penalty) that replaces the fixed depth-based patent bonus. Keyword counts
# of public US families: est, not legal advice. Weights: priority.yaml patents.
PATENT_NOTE = "est; US keyword counts, not legal advice"
GAP_STATUS = ("not held", "divested", "closing")


@lru_cache
def process_gaps() -> dict[str, str]:
    """Function -> a process it needs that we do not hold (est): listed only under a capabilities.yaml entry that is
    not held, divested or closing and served by no current platform of ours; plus priority.yaml patents.process_gaps."""
    out: dict[str, str] = {}
    for p in op.capabilities().values():
        if p.get("status") in GAP_STATUS:
            for fn in p.get("functions") or []:
                if fn not in _platforms():
                    out.setdefault(fn, p.get("name", ""))
    out.update((config().get("patents") or {}).get("process_gaps") or {})
    return out


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def distance_scale(distance) -> float:
    """How much the patent effect counts at this portfolio distance (0-4; None = not assessed): more when we are far.
    Distance is already in likeliness (feasibility), so here it only scales the patent effect (no double count)."""
    t = config()["patents"]["distance_scale"]
    return float(t.get(distance, t["none"]))


def barrier_parts(ours: int, rivals: dict[str, dict], process_gap: str = "") -> dict:
    """The parts and the barrier from counts: ours = our families in the last 5 years on the platform; rivals =
    {competitor: {last5, last3}}. similarity = ours / (ours + strongest competitor), 0.5 = parity; difficulty from the
    leader's density (log scale), crowding (competitors with crowd_ratio of the leader's count) and recency (share of
    their families first filed in the last 3 years), plus a flag for a process we do not hold."""
    cfg = config()["patents"]
    d = cfg["difficulty"]
    lead_key = max(rivals, key=lambda c: (rivals[c]["last5"], c)) if rivals else ""
    lead = rivals[lead_key]["last5"] if rivals else 0
    sim = ours / (ours + lead) if ours + lead else 0.5
    density = _clamp(math.log1p(lead) / math.log1p(float(d["density_full"])))
    near = [c for c, v in rivals.items() if lead and v["last5"] >= float(d["crowd_ratio"]) * lead]
    crowd = (len(near) - 1) / (len(rivals) - 1) if lead and len(rivals) > 1 else 0.0
    t5, t3 = sum(v["last5"] for v in rivals.values()), sum(v["last3"] for v in rivals.values())
    share3 = t3 / t5 if t5 else 0.0
    recency = _clamp(share3 / float(d["recency_full"]))
    diff = _clamp(float(d["density"]) * density + float(d["crowding"]) * crowd + float(d["recency"]) * recency
                  + (float(d["process_gap"]) if process_gap else 0.0))  # fmt: skip
    barrier = round(100 * (float(cfg["similarity_weight"]) * (1 - sim) + float(cfg["difficulty_weight"]) * diff))
    return {"ours": ours, "lead": lead_key, "lead_n": lead, "similarity": round(sim, 3), "density": round(density, 3),
            "crowded": len(near), "crowding": round(crowd, 3), "recent_share": round(share3, 3),
            "recency": round(recency, 3), "process_gap": process_gap, "difficulty": round(diff, 3),
            "barrier": int(_clamp(barrier, 0, 100))}  # fmt: skip


def barrier_points(barrier: int, distance=None) -> float:
    """The signed priority adjustment: barrier 50 -> 0, lower a bonus, higher a penalty, scaled by distance, capped."""
    cfg = config()["patents"]
    cap = float(cfg["cap"])
    pts = -(barrier - 50) / 50 * float(cfg["points"]) * distance_scale(distance)
    return round(_clamp(pts, -cap, cap), 1) + 0.0


def patent_words(p: dict, label: str, distance) -> dict:
    """The three parts in plain words: similarity, distance, difficulty."""
    cfg = config()["patents"]["words"]
    sim = p["similarity"]
    lead = patents.competitor_label(p["lead"]) if p["lead"] else "competitors"
    s = (f"similar to our {label} work" if sim >= cfg["similar_from"] else
         f"partly similar to our {label} work" if sim >= cfg["partly_from"] else
         f"little of ours in {label}")  # fmt: skip
    why = [x for x, on in (("crowded", p["crowded"] >= 2), ("recent filings", p["recent_share"] >= cfg["recent_from"]),
                           (f"needs {p['process_gap']}", p["process_gap"])) if on]  # fmt: skip
    hard = ("hard to recreate" if p["difficulty"] >= cfg["hard_from"] else
            "moderate to recreate" if p["difficulty"] >= cfg["moderate_from"] else "easy to recreate")  # fmt: skip
    return {"similarity": f"{s} (ours {p['ours']} vs {lead} {p['lead_n']})",
            "distance": cfg["distance"].get(distance, cfg["distance"]["none"]),
            "difficulty": hard + (f" ({', '.join(why)})" if why else "")}  # fmt: skip


def patent_effect(fn: str, distance=None) -> dict | None:
    """The patent barrier of a function and its priority adjustment, from the platform that covers it, or None:
    {platform, label, barrier, points, the parts, words, counts, line, date}."""
    got = patents.competition_for(fn)
    if not got:
        return None
    key, plat, comp = got
    rivals = {c: {"last5": int(v.get("last5") or 0), "last3": int(v.get("last3") or 0)}
              for c, v in (comp.get("competitors") or {}).items()}  # fmt: skip
    p = barrier_parts(int((comp.get("ours") or {}).get("last5") or 0), rivals, process_gaps().get(fn, ""))
    pts = barrier_points(p["barrier"], distance)
    label = plat.get("label", key)
    words = patent_words(p, label, distance)
    them = ", ".join(f"{patents.competitor_label(c)} {v['last5']}"
                     for c, v in sorted(rivals.items(), key=lambda kv: (-kv[1]["last5"], kv[0])))  # fmt: skip
    incl = f" ({comp['ours']['note']})" if (comp.get('ours') or {}).get('note') else ""
    counts = f"ours {p['ours']}{incl}, {them}"
    line = (f"Patents (US, 5 years): {counts} · {words['similarity']}, {words['distance']}, {words['difficulty']} → "
            f"barrier {p['barrier']}, {pts:+g}")  # fmt: skip
    return {**p, "platform": key, "label": label, "distance": distance, "scale": distance_scale(distance),
            "points": pts, "words": words, "counts": counts, "line": line, "note": PATENT_NOTE,
            "date": str(patents.competitors().get("searched", ""))}  # fmt: skip


def likeliness(e: dict) -> dict:
    """L for a row: from its feasibility group (1–3), plus a bonus for a platform of ours (capped at 1.0), or the
    owner's answer (no bonus then). Patents are no longer in L: see patent_effect (owner, 6 Nov 2026)."""
    cfg = config()["likeliness"]
    own = (cfg.get("owner") or {}).get(e["fn"])
    path = e.get("path")
    path = path.get("path") if isinstance(path, dict) else path
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
    label = next(x["label"] for x in cfg["labels"] if v >= x["from"] - 1e-9)
    return {"value": round(v, 3), "label": label, "basis": basis, "owner": bool(own)}


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
    base = 100 * (w["technology"] * t["value"] + w["likeliness"] * li["value"] + w["diagrams"] * d)
    pat = patent_effect(e["fn"], e.get("distance"))
    adj = pat["points"] if pat else 0.0
    total = _clamp(base + adj, 0.0, 100.0)
    cfg = config()
    return {
        "score": round(total, 1), "T": t["value"], "L": li["value"], "D": round(d, 3), "n": n, "n_max": n_max,
        "t_level": t["level"], "t_label": t["label"], "t_help": t["help"], "mapped": t["mapped"],
        "l_label": li["label"], "l_basis": li["basis"], "l_owner": li["owner"], "patent": pat,
        "base": round(base, 1), "adj": adj,
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
    return out + ([f"patents: barrier {p['patent']['barrier']}"] if p["patent"] else [])


def example(e: dict) -> str:
    """The sum written out, e.g. 100 × (0.45 × 1.00 + 0.30 × 0.70 + 0.25 × 0.43) = 76.7, with the patent adjustment
    when there is one: ... − 2.6 (patents) = 74.1."""
    p, w = e["priority"], e["priority"]["w"]
    pat = f" {'+' if p['adj'] >= 0 else '−'} {abs(p['adj']):g} (patents)" if p.get("patent") else ""
    return (f"100 × ({w['technology']:.2f} × {p['T']:.2f} + {w['likeliness']:.2f} × {p['L']:.2f} + "
            f"{w['diagrams']:.2f} × {p['D']:.2f}){pat} = {p['score']:.1f}")  # fmt: skip


def patent_example(rows: list[dict]) -> dict | None:
    """The highest-priority row with a patent adjustment, other than the top item, for the worked examples."""
    top = (ranked(rows) or [None])[0]
    hit = [e for e in rows if e is not top and e["priority"].get("patent") and e["priority"]["adj"]
           and "@" not in e.get("key", e["fn"])]  # fmt: skip
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


def patent_table() -> list[dict]:
    """The counts behind the patent barrier per platform, for the method page: label, functions, ours and the
    competitors (5 years), the ex-Silicon Labs column, the barrier (without a process flag) and its adjustment at
    distance 0 and 4."""
    out = []
    for key, comp in (patents.competitors().get("platforms") or {}).items():
        plat = patents.platforms().get(key) or {}
        rivals = {c: {"last5": int(v.get("last5") or 0), "last3": int(v.get("last3") or 0)}
                  for c, v in (comp.get("competitors") or {}).items()}  # fmt: skip
        p = barrier_parts(int((comp.get("ours") or {}).get("last5") or 0), rivals)
        fns = blocks.catalogue()["functions"]
        out.append({"key": key, "label": plat.get("label", key),
                    "functions": [(fns.get(f) or {}).get("label", f) for f in plat.get("functions") or []],
                    "ours_n": comp.get("ours") or {}, "rivals": patents.rivals((key, plat, comp)),
                    "ex_silabs": (plat.get("ex_silabs") or {}).get("count"),
                    "ex_silabs_counted": (plat.get("ex_silabs_counted") or {}).get("count"), **p,
                    "near": barrier_points(p["barrier"], 0), "far": barrier_points(p["barrier"], 4)})  # fmt: skip
    return out
