"""Future growth > Automotive focus (owner, 3 Nov 2026): "one page that summarizes the top five things I should pursue
if I were to try to drive automotive business today", short to long term, compressed from the site's own data.

Six goals, each built live from one rung of the Automotive map ladder (app/services/automotive.py) and the pages
around it; nothing here is typed by hand except the sentences that frame the numbers:
  1 sell_now   short  A cells: our automotive-grade parts, most car applications first; Cross-sell pairs
  2 anchors    short  competitor parts in public reference designs that we cross (refmatch.anchors_for)
  3 qualify    short  the B moves with the highest Opportunity score (AEC-Q100 of a part we sell)
  4 variant    mid    the C / D moves with a preliminary case, by score; the case's first three next steps
  5 draw       mid    B / C functions we sell in other systems (industrial, data center, cellular ...): the table
  6 gaps       long   gap cells, by Opportunity score at the technology distance (partner / licence / acquire)
Every fact carries its number (`n`) and the page it comes from (`href`), so tests can check it against its source.
Effort is the step's distance on the one scale of data/business/scoring.yaml plus a time band marked "est".
"""

from collections import Counter

from sqlalchemy.orm import Session

from app.services import automotive as au
from app.services import blocks, reports, scoring, tam, vocab
from app.services import opportunity as op
from app.services import systems as sy

HORIZON = {"short": "Short term · 0–12 months", "mid": "Mid term · 1–3 years", "long": "Long term · 3+ years"}
# distance (scoring.yaml) -> effort word and a time band; both are our estimates
EFFORT = {0: ("Low", "weeks to a few months"), 1: ("Medium", "6–12 months"), 2: ("Medium", "1–2 years"),
          3: ("High", "2–3 years"), 4: ("Very high", "3+ years, or a partner")}  # fmt: skip
MAP = "/business/automotive?view=all"
_CACHE: list = []


def _cell_href(key: str) -> str:
    return f"{MAP}&cell={key}#detail"


def _part(mpn: str) -> dict:
    return {"label": mpn, "href": f"/find?q={mpn}"}


def _fact(text: str, n, href: str, src: str, is_tam: bool = False) -> dict:
    return {"text": text, "n": n, "href": href, "src": src, "tam": is_tam}


def _effort(d: int | None) -> str:
    word, time = EFFORT.get(d if d is not None else 4)
    return f"{word} ({time}, est)"


def _apps_text(apps: list[str], k: int = 2) -> str:
    return ", ".join(apps[:k]) + (f" +{len(apps) - k} more" if len(apps) > k else "")


def _tam_fact(tams: dict, fn: str) -> dict | None:
    t = tams.get(fn)
    if not t:
        return None
    return _fact(f"Market size (TAM) for {vocab.fn_label(fn)}: {t['band']}, all markets.", t["usd"],
                 "/business/tam", "TAM estimates", is_tam=True)  # fmt: skip


def _live(m: dict) -> list[dict]:
    return [c for c in m["cells"].values() if c["status"] != "rejected"]


def _by_fn(cells: list[dict], level: str) -> list[tuple[str, list[dict]]]:
    """Functions at one letter, most car applications first."""
    out: dict[str, list[dict]] = {}
    for c in cells:
        if c["level"] == level:
            out.setdefault(c["fn"], []).append(c)
    return sorted(out.items(), key=lambda kv: (-len(kv[1]), vocab.fn_label(kv[0]).lower()))


def car_diagrams() -> list[int]:
    """The library diagrams of the Automotive system (data/blocks/systems.yaml)."""
    return sorted({i for x in (sy.get("automotive") or {}).get("subsystems") or [] for i in x["idx"]})


def _parts_of(cells: list[dict], k: int = 2) -> list[str]:
    seen: list[str] = []
    for c in cells:
        for p in c.get("parts") or []:
            if p["mpn"] not in seen:
                seen.append(p["mpn"])
    return seen[:k]


# ---- the six goals ---------------------------------------------------------------------------------------------------
def _sell_now(session: Session, m: dict, live: list[dict], idx: list[int]) -> dict:
    top = _by_fn(live, "A")[:3]
    apps = op.with_status(op.applications(), op.makers(session), op.company("combined")[2])
    keep = set(idx)
    pairs = op.cross_sell_pairs([a for a in apps if a.i in keep and not a.background], limit=1)
    n_fns = len(_by_fn(live, "A"))
    why = [_fact(f"{m['counts']['A']} Sell-now calls on the Automotive map, over {n_fns} functions.", m["counts"]["A"],
                 MAP, "Automotive map")]  # fmt: skip
    if top:
        fn, cs = top[0]
        why.append(_fact(f"{vocab.fn_label(fn)} is Sell now in {len(cs)} of {len(m['apps'])} car applications.",
                         len(cs), _cell_href(cs[0]["key"]), "Automotive map"))  # fmt: skip
    if pairs:
        p = pairs[0]
        why.append(_fact(f"{p['a_label']} and {p['b_label']} sit together in {p['apps']} of {len(idx)} car block "
                         "diagrams: one visit can sell both.", p["apps"], "/blocks/cross-sell?system=automotive",
                         "Cross-sell by system"))  # fmt: skip
    steps = [f"Offer {(_parts_of(cs, 1) or [vocab.fn_label(fn)])[0]} ({vocab.fn_label(fn)}) to Tier-1s for "
             f"{_apps_text([c['app_label'] for c in cs])}." for fn, cs in top]  # fmt: skip
    return {"id": "sell_now", "horizon": "short", "angle": "a", "title": "Place our automotive parts in car designs",
            "goal": "Put the automotive-grade parts we already sell into the car diagrams where they fit.",
            "why": why, "steps": steps,
            "parts": [_part(x) for _, cs in top for x in _parts_of(cs)],
            "links": [{"label": f"{vocab.fn_label(fn)} on the map", "href": _cell_href(cs[0]["key"])} for fn, cs in top]
            + [{"label": "Car block diagrams", "href": "/blocks?system=automotive"}],
            "effort": _effort(0), "confidence": scoring.config()["distance"]["supported_confidence"],
            "rank": [f"{vocab.fn_label(fn)}: {len(cs)} applications" for fn, cs in top]}  # fmt: skip


def _anchors(session: Session, idx: list[int]) -> dict:
    from app.services import refmatch

    lib = blocks.templates()
    an = refmatch.anchors_for([lib[i] for i in idx if 0 <= i < len(lib)], blocks.counts(session))
    goal = {"id": "anchors", "horizon": "short", "angle": "a", "title": "Win reference-design sockets with our crosses",
            "goal": "Bring our crosses, and the parts next to them, to customers who build on competitor reference "
                    "designs.",
            "effort": _effort(0), "confidence": "medium", "parts": [], "links": [], "why": [], "steps": [],
            "rank": []}  # fmt: skip
    if not an:
        goal["missing"] = "No reference-design anchor found for the car diagrams yet."
        return goal
    rd = "/reference-designs?part="
    a = an[0]
    goal["why"] = [
        _fact(f"{len(an)} competitor parts in public reference designs for car diagrams have a cross of ours "
              "(top five shown on Cross-sell).", len(an), "/blocks/cross-sell?system=automotive", "Cross-sell anchors"),
        _fact(f"{a['part']} ({a['label']}) sits in {a['n']} reference designs; our {a['ours']} is a "
              f"{a['type'].lower()} cross.", a["n"], rd + a["part"], "Reference designs"),
    ]  # fmt: skip
    near = [lb for _, _, lb, st in a.get("around") or [] if st == "we have"]
    if near:
        goal["why"].append(_fact(f"Around it in those designs we also have: {', '.join(near[:3])}.", len(near),
                                 rd + a["part"], "Reference designs"))  # fmt: skip
    goal["steps"] = [f"Pitch {x['ours']} ({x['type'].lower()}) for {x['part']} to the teams using its {x['n']} "
                     "reference designs." for x in an[:2]]  # fmt: skip
    goal["steps"].append(f"Add the neighbours we have ({', '.join(near[:3]) or 'none listed'}) to the same offer.")
    goal["parts"] = [_part(x["ours"]) for x in an[:4]]
    goal["links"] = [{"label": f"Designs with {x['part']}", "href": rd + x["part"]} for x in an[:3]]
    goal["rank"] = [f"{x['part']} → {x['ours']}: {x['n']} designs" for x in an[:3]]
    return goal


def _qualify(m: dict, live: list[dict], tams: dict) -> dict:
    moves = [x for x in m["moves"] if x["level"] == "B"][:3]
    goal = {"id": "qualify", "horizon": "short", "angle": "b", "title": "Qualify the best-scoring parts (AEC-Q100)",
            "goal": "Take the parts we sell today in non-car versions through AEC-Q100, best Opportunity score first.",
            "effort": _effort(1), "why": [], "steps": [], "parts": [], "links": [], "rank": []}  # fmt: skip
    if not moves:
        goal["missing"] = "No Qualify (B) move on the Automotive map."
        return goal
    t = moves[0]
    s = (t["opp"] or {}).get("score")
    goal["why"] = [_fact(f"{t['label']} is the top Qualify move: Opportunity score {s}, needed in {len(t['apps'])} car "
                         "applications.", s, _cell_href(t["key"]), "Automotive map, Top moves")]  # fmt: skip
    goal["why"].append(_fact(f"{m['counts']['B']} Qualify calls on the map: parts we sell, none stated automotive.",
                             m["counts"]["B"], MAP, "Automotive map"))  # fmt: skip
    tf = next((f for f in (_tam_fact(tams, x["fn"]) for x in moves) if f), None)
    if tf:
        goal["why"].append(tf)
    cells = {c["fn"]: [x for x in live if x["fn"] == c["fn"] and x["level"] == "B"] for c in moves}
    for x in moves:
        ps = _parts_of(cells[x["fn"]])
        goal["steps"].append(f"{x['label']} ({(x['opp'] or {}).get('score')}): ask the BU if {(ps or ['our part'])[0]} "
                             f"passes AEC-Q100; else plan the run and PPAP. For {_apps_text(x['apps'])}.")  # fmt: skip
        goal["parts"] += [_part(p) for p in ps]
        goal["links"].append({"label": f"{x['label']} on the map", "href": _cell_href(x["key"])})
    goal["confidence"] = (t["opp"] or {}).get("confidence") or "medium"
    goal["fns"] = [x["fn"] for x in moves]
    goal["rank"] = [f"{x['label']}: score {(x['opp'] or {}).get('score')}" for x in moves]
    return goal


def _variant(m: dict, tams: dict) -> dict:
    """C / D moves that have a preliminary case, by score; the case's own next steps."""
    moves = [x for x in m["moves"] if x["level"] in ("C", "D")]
    with_case = [x for x in moves if x["case"] and reports.report(x["case"])]
    goal = {"id": "variant", "horizon": "mid", "angle": "b", "title": "Build the best new automotive variant",
            "goal": "Turn the highest-scoring New-variant move that has a business case into a product proposal.",
            "why": [], "steps": [], "parts": [], "links": [], "rank": []}  # fmt: skip
    ideas = [r for r in reports.reports() if r.get("kind") == "idea" and r["app_type"] == "Automotive"]
    if not with_case:
        goal["missing"] = "No New-variant move with a business case yet."
        goal["effort"], goal["confidence"] = _effort(3), "low"
        return goal
    t = with_case[0]
    r = reports.report(t["case"])
    s = (t["opp"] or {}).get("score")
    goal["why"] = [_fact(f"{t['label']}: Opportunity score {s}, the top New-variant move with a case "
                         f"({len(moves)} C / D moves in all).", s, _cell_href(t["key"]), "Automotive map, Top moves"),
                   _fact(f"Its business case rates feasibility {r['feasibility']} of 3 (1 = closest to today).",
                         r["feasibility"], f"/business/reports/{r['slug']}", "Research & ideas")]  # fmt: skip
    tf = _tam_fact(tams, t["fn"])
    if tf:
        goal["why"].append(tf)
    goal["steps"] = [f"{s_['what']} ({s_['who']})." for s_ in (r.get("next_steps") or [])[:3]]
    goal["parts"] = [_part(p) for p in _parts_of([c for c in m["cells"].values() if c["fn"] == t["fn"]], 4)]
    goal["links"] = [{"label": "The business case", "href": f"/business/reports/{r['slug']}"},
                     {"label": f"{t['label'][:40]} on the map", "href": _cell_href(t["key"])}]  # fmt: skip
    near = sorted((i for i in ideas if i["feasibility"]), key=lambda i: (i["feasibility"], i["slug"]))
    goal["also"] = [{"label": i["title"].split(":")[0][:70], "href": f"/business/reports/{i['slug']}",
                     "feasibility": i["feasibility"]} for i in near if i["slug"] != r["slug"]][:4]  # fmt: skip
    goal["effort"], goal["fns"] = _effort(t["distance"]), [t["fn"]]
    goal["confidence"] = (t["opp"] or {}).get("confidence") or "low"
    goal["rank"] = [f"{x['label']}: score {(x['opp'] or {}).get('score')}" for x in with_case[:3]]
    return goal


def draw_rows(m: dict, live: list[dict], skip: set[str], k: int = 6) -> list[dict]:
    """Functions on the map's Qualify and New-variant moves (beyond `skip`) with the other systems whose diagrams
    use them: source market -> our parts -> automotive use -> what it takes."""
    out = []
    for x in m["moves"]:
        if x["level"] not in ("B", "C") or x["fn"] in skip or any(r["fn"] == x["fn"] for r in out):
            continue
        src = [s for s in sy.systems_of_function(x["fn"]) if s["key"] != "automotive"][:2]
        if not src:
            continue
        cs = [c for c in live if c["fn"] == x["fn"]]
        nxt = next((c.get("next") or c for c in cs if c["key"] == x["key"]), {})
        take = ("AEC-Q100 and PPAP of the part we sell" if x["level"] == "B"
                else (nxt.get("missing") or "A new design on the same process"))  # fmt: skip
        out.append({"fn": x["fn"], "label": x["label"], "level": x["level"],
                    "source": [{"title": s["title"], "n": s["n"], "href": f"/blocks?system={s['key']}"} for s in src],
                    "parts": [_part(p) for p in _parts_of(cs)], "apps": x["apps"], "key": x["key"],
                    "score": (x["opp"] or {}).get("score"),
                    "take": f"{take} ({EFFORT[x['distance'] or 1][1]}, est)"})  # fmt: skip
        if len(out) == k:
            break
    return out


def _draw(rows: list[dict]) -> dict:
    goal = {"id": "draw", "horizon": "mid", "angle": "c", "title": "Draw new car parts from our other markets",
            "goal": "Adapt parts we sell in industrial, data center, cellular and other systems to car functions we "
                    "lack in automotive grade.",
            "effort": _effort(1), "confidence": "medium", "why": [], "steps": [], "parts": [], "links": [],
            "rank": []}  # fmt: skip
    if not rows:
        goal["missing"] = "No Qualify or New-variant function is used outside the car in the library."
        return goal
    srcs = Counter()
    for r in rows:
        for s in r["source"][:1]:
            srcs[s["title"]] += 1
    top_src, n_top = srcs.most_common(1)[0]
    r0 = rows[0]
    goal["why"] = [_fact(f"{len(rows)} next functions on the map are used in other systems' diagrams; {n_top} of them "
                         f"come mostly from {top_src}.", len(rows), "#ae-draw", "Automotive map + Systems library"),
                   _fact(f"{r0['label']} sits in {r0['source'][0]['n']} {r0['source'][0]['title']} diagrams and is "
                         f"needed in {len(r0['apps'])} car applications.", r0["source"][0]["n"],
                         r0["source"][0]["href"], "Block diagram library")]  # fmt: skip
    goal["steps"] = [f"{r['label']}: bring {(r['parts'] or [{'label': 'our part'}])[0]['label']} from "
                     f"{r['source'][0]['title']} to {_apps_text(r['apps'], 1)} (see the table)."
                     for r in rows[:3]]  # fmt: skip
    goal["parts"] = [p for r in rows[:3] for p in r["parts"]]
    goal["links"] = [{"label": "The table below", "href": "#ae-draw"}]
    goal["rank"] = [f"{r['label']}: score {r['score']}" for r in rows[:3]]
    return goal


def _gaps(session: Session, live: list[dict], tab: dict, tams: dict) -> dict:
    tech = op.technology()
    comp = op.competition()
    scored = []
    for fn, cs in _by_fn(live, "gap"):
        d, basis, c, _ = scoring.distance(None, (tech.get(fn) or {}).get("proximity"))
        s = scoring.rescore(tab, fn, d if d is not None else 4, basis, c)
        if s:
            scored.append((s["score"], fn, cs, s, d))
    scored.sort(key=lambda t: (-t[0], -len(t[2]), t[1]))
    top = scored[:3]
    n_gap = sum(1 for c in live if c["level"] == "gap")
    goal = {"id": "gaps", "horizon": "long", "angle": "b", "title": "Close the biggest car gaps with a partner",
            "goal": "Find a partner, licence or acquisition for the best-scoring car functions neither company sells.",
            "effort": _effort(4), "why": [], "steps": [], "parts": [], "links": [], "rank": []}  # fmt: skip
    goal["why"] = [_fact(f"{n_gap} Gap calls on the Automotive map, over {len(_by_fn(live, 'gap'))} functions.", n_gap,
                         MAP, "Automotive map")]  # fmt: skip
    if not top:
        goal["missing"] = "No gap function has an Opportunity score yet."
        goal["confidence"] = "low"
        return goal
    s0, fn, cs, sc, _ = top[0]
    goal["why"].append(_fact(f"{vocab.fn_label(fn)} scores {s0} as a gap and is needed in {len(cs)} car applications.",
                             s0, "/business/opportunities", "Gaps & new technology"))  # fmt: skip
    tf = next((f for f in (_tam_fact(tams, t[1]) for t in top) if f), None)
    if tf:
        goal["why"].append(tf)
    for s, fn, cs, _, _ in top:
        v = (comp.get(fn) or {}).get("vendors") or []
        goal["steps"].append(f"{vocab.fn_label(fn)} ({s}, {len(cs)} applications): scout a partner or licence"
                             + (f"; sold by {', '.join(v[:2])}." if v else "."))  # fmt: skip
        goal["links"].append({"label": f"{vocab.fn_label(fn)} on the map", "href": _cell_href(cs[0]["key"])})
    goal["links"].append({"label": "Gaps & new technology", "href": "/business/opportunities"})
    goal["confidence"] = sc.get("confidence") or "low"
    goal["rank"] = [f"{vocab.fn_label(fn)}: score {s}" for s, fn, *_ in top]
    return goal


def build(session: Session) -> dict:
    """The goals in horizon order, the Draw-from table and the counts behind "How these were picked"."""
    m = au.build(session)
    if _CACHE and _CACHE[0][0] is m:
        return _CACHE[0][1]
    live, idx, tams, tab = _live(m), car_diagrams(), tam.by_function(session), scoring.combined(session)
    q, v = _qualify(m, live, tams), _variant(m, tams)
    rows = draw_rows(m, live, {*q.get("fns", ()), *v.get("fns", ())})  # not the functions goals 3 and 4 already name
    goals = [_sell_now(session, m, live, idx), _anchors(session, idx), q, v, _draw(rows),
             _gaps(session, live, tab, tams)]  # fmt: skip
    for i, g in enumerate(goals, 1):
        g["n"] = i
        g["horizon_label"] = HORIZON[g["horizon"]]
    out = {"goals": goals, "draw": rows, "counts": m["counts"], "n_apps": len(m["apps"]), "n_diagrams": len(idx),
           "weights": scoring.weights(), "n_moves": len(m["moves"])}  # fmt: skip
    _CACHE[:] = [(m, out)]
    return out
