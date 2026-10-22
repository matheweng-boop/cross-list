"""Part walk-through: from a competitor part, the five questions in selling order, each answered from data the rest
of the site already holds.

1. Replacement: is our cross suitable (the part page's own result).
2. Sell around it: the functions in the same block diagrams (Cross-sell).
3. Best of ours around it: our parts per companion, grade and band checked as Cross-sell does.
4. Make it better, other applications: where our replacement falls short, where the function is used, competition,
   market size and trend.
5. Future: one verdict (sell what we have, improve it, new chip, partner, hold) with the path to product, the
   Opportunity score and every research item, preliminary case and business case on the function.

Data a step needs but the site does not hold is a gap: it is shown on the step and recorded once as site feedback
(kind "data"), so the next feedback review picks it up.
"""

from collections import Counter
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BlockDiagram, Case, Part, ShortlistItem, SiteFeedback
from app.services import blocks, crosssell, library, prelim, scoring, vocab
from app.services import opportunity as op
from app.services import reports as rp
from app.services.pipeline import fn_for_family, requested

STEPS = {1: "Replacement", 2: "Sell around it", 3: "Best of ours around it", 4: "Make it better, other applications",
         5: "What the future needs"}  # fmt: skip
AUTHOR = "Walk-through (automatic)"
ACCEPTABLE = ("fff",)  # only a drop-in counts as "we can cross it" (owner, 22 Oct 2026)
VERDICTS = {
    "sell": "Sell what we have",
    "improve": "Improve what we have",
    "variant": "Similar part: a variant of our line",
    "new_chip": "New design: a new chip from our technology",
    "partner": "Partner or acquire",
    "hold": "Hold: the market is declining",
    "unknown": "Not enough data to say",
}


def competitor_parts(session: Session, fn: str, limit: int = 6) -> list[Part]:
    """Competitor parts in the cross-reference database whose family maps to the function (for links back from
    the function, case and cross-sell pages to a walk-through)."""
    mine = [f for f in session.scalars(select(Part.family).distinct()) if fn_for_family(f) == fn]
    if not mine:
        return []
    q = select(Part).where(Part.family.in_(mine)).order_by(Part.mpn)
    return [p for p in session.scalars(q) if not p.is_reference][:limit]


def _step1(rows: list) -> dict:
    """The best cross of the part page and whether it is suitable as it is."""
    if not rows:
        return {"best": None, "suitable": "none", "worse": [], "minor": [], "short_everywhere": [], "acceptable": None}
    r, v = rows[0]
    worse = [d.label for d in v.worse]
    minor = [d.label for d in v.info_worse]
    suitable = "dropin" if v.category == "fff" and not worse else "deviations"
    # a drop-in means we can cross it: no new development, so no case
    acceptable = next((rr.candidate for rr, vv in rows if vv.category in ACCEPTABLE), None)
    # specs where every listed cross of ours is worse: the line as a whole falls short
    lists = [{d.label for d in vv.worse} for _, vv in rows]
    short = sorted(set.intersection(*lists)) if lists else []
    return {"best": r.candidate, "verdict": v, "suitable": suitable, "worse": worse, "minor": minor,
            "short_everywhere": short, "n": len(rows), "acceptable": acceptable}  # fmt: skip


def walk(session: Session, part: Part, rows: list, upto: int = 2, co: str = "combined") -> dict:
    """The answers of steps 1..upto and the gaps found on the way; later steps are not computed until asked for.
    `rows` = the part page's cross results (best first)."""
    gaps: list[tuple[int, str]] = []
    s1 = _step1(rows)
    fn = fn_for_family(part.family)
    anchor = crosssell.resolve_part(session, part.mpn) or (
        {"mpn": part.mpn, "manufacturer": part.manufacturer.name, "ours": part.is_reference, "fns": [fn],
         "automotive": False, "grade": None, "ranges": [], "exact": True, "others": []} if fn else None
    )  # fmt: skip
    fn = fn or (anchor["fns"][0] if anchor else None)
    label = vocab.fn_label(fn) if fn else part.family
    if s1["best"] is None:
        gaps.append((1, f"No Skyworks / Qorvo cross for {label}: the part is a portfolio gap or its specs are missing"))
    out = {"fn": fn, "label": label, "anchor": anchor, "s1": s1, "upto": upto, "gaps": gaps,
           "requested": requested(session, part.mpn)}  # fmt: skip
    if not fn:
        if upto >= 2:
            gaps.append((2, f"Family '{part.family}' is not mapped to a block-diagram function: no data for steps 2–5"))
        return out
    if upto < 2:
        return out

    # 2 and 3: cross-sell around the part
    sell = crosssell.suggest(session, anchor, "", co)
    if not sell["n"]:
        gaps.append((2, f"No block diagram contains {label}: add an application diagram that uses it"))
    ours, new = sell["ours"][:8], sell["new"][:6]
    for e in ours:
        if not e["offer"]:
            gaps.append((3, f"{e['label']}: we sell it but no part of ours is named for it (catalogue mapping)"))
        elif anchor["automotive"] and not any(o["auto"] for o in e["offer"]):
            gaps.append((3, f"{e['label']}: no automotive-grade part of ours to offer next to an automotive {label}"))
    out.update(s2=sell, ours=ours, new=new, cards=app_cards(sell, fn, part.mpn, bool(anchor and anchor["automotive"])),
               saved=saved_designs(session, fn))  # fmt: skip
    if upto < 4:
        return out

    # 4: where we fall short, where it is used, competition, market size, trend
    tab = scoring.combined(session)
    use = tab["usage"].get(fn) or {}
    apps = [a for a, _, _ in sell["apps"]]
    markets = Counter(a.market or a.category for a in apps).most_common(6)
    comp = op.competition().get(fn)
    trend = op.evidence("trends").get(fn)
    hunt = op.hunt_for_function(apps, fn)[:6] if apps else []
    tam = use.get("tam") if use.get("tam_apps") else None
    if not comp:
        gaps.append((4, f"{label}: competition not assessed (data/business/competition.yaml)"))
    if not trend:
        gaps.append((4, f"{label}: no market trend recorded (data/business/evidence/trends.yaml)"))
    # no public TAM estimate yet is expected (owner, 22 Oct 2026): shown on the step, not logged as a data error
    if apps and not hunt:
        gaps.append((4, f"{label}: no customers listed for the applications that use it (customers.yaml)"))
    lib = library.for_function(fn)
    if not lib:
        gaps.append((4, f"{label}: no technical-library topic covers it yet (design rules, research trends)"))
    s4 = {"library": lib, "short": s1["worse"], "short_everywhere": s1["short_everywhere"], "markets": markets,
          "n_apps": len(apps), "comp": comp, "trend": trend, "hunt": hunt, "tam": tam,
          "tam_apps": use.get("tam_apps", 0)}  # fmt: skip
    out["s4"] = s4
    if upto < 5:
        return out

    # 5: the verdict, the path to product, the score and everything written about the function
    score = tab["rows"].get(fn)
    path = op.evidence("path").get(fn)
    outlook = (trend or {}).get("outlook")
    if outlook == "declining" and not (trend or {}).get("regulation"):
        verdict, why = "hold", f"market trend for {label}: declining"
    elif s1["suitable"] == "dropin":
        verdict, why = "sell", f"{s1['best'].mpn} is a drop-in with no priority 1 spec worse"
    elif s1["best"] is not None:
        verdict, why = "improve", f"{s1['best'].mpn} fits but is worse on {', '.join(s1['worse'][:4]) or 'package'}"
    elif score and score.get("suggestion") in ("new_chip", "partner"):
        verdict, why = score["suggestion"], score["suggestion_help"]
    elif score and score.get("distance") is not None and score["distance"] <= 2:
        verdict, why = "variant", score["suggestion_help"] or "close to what we build"
    else:
        verdict, why = "unknown", "no cross, and no path to product or technology rating for the function"
    if not path:
        gaps.append((5, f"{label}: no path to product assessed (data/business/evidence/path.yaml)"))
    cases_on = [{"slug": r["slug"], "title": r["title"], "how": how} for r in rp.reports()
                if (how := _case_link(r["slug"], fn))]  # fmt: skip
    business = list(session.scalars(select(Case).where(Case.fn == fn).order_by(Case.updated_at.desc()).limit(5)))
    listed = session.scalar(select(ShortlistItem).where(ShortlistItem.origin == "part",
                                                        ShortlistItem.key == part.mpn))  # fmt: skip
    if not cases_on and not business:
        gaps.append((5, f"{label}: no research report, preliminary case or business case yet"))
    out["s5"] = {"verdict": verdict, "verdict_label": VERDICTS[verdict], "why": why, "score": score, "path": path,
                 "cases": cases_on, "business": business, "shortlisted": listed is not None}  # fmt: skip
    return out


BLOCK_CLASS = {"supported": "ours", "gap": "gap", "competitor": "gap"}


def app_cards(sell: dict, fn: str, mpn: str, automotive: bool = False) -> list[dict]:
    """Step 2 seen from the customer: one card per application that uses the part's function, with a small diagram
    (frames and their blocks: this part, ours, gap, customer part), our parts for the other blocks, the general
    categories it falls in (HVAC, BMS, traction inverter...) and what the search looks at."""
    lib, back = blocks.templates(), blocks.background_templates()
    offers = {e["fn"]: e["offer"] for e in sell["ours"]}
    labels = {c["key"]: c["label"] for c in blocks.categories()}
    cards = []
    for a, _, _ in sell["apps"]:
        t = lib[a.i] if a.i < len(lib) else back[a.i - len(lib)]
        groups: dict[str, list] = {}
        also, seen, gaps = [], {fn}, 0
        for p in a.positions:
            cls = "mine" if p.fn == fn else BLOCK_CLASS.get(p.status, "ext")
            groups.setdefault(p.group, []).append({"label": p.label, "cls": cls})
            gaps += cls == "gap"
            if cls == "ours" and p.fn not in seen:
                seen.add(p.fn)
                if offers.get(p.fn):
                    also.append({"label": p.label, **offers[p.fn][0]})
        index = blocks.template_index(t, a.market)
        where = f"template={a.i}" if a.i < len(lib) else f"bg={a.i - len(lib)}"
        uses = sum(p.fn == fn for p in a.positions)  # designs that use the part's function several times first
        cards.append({"i": a.i, "name": blocks.display_name(t), "market": a.market, "background": a.background,
                      "uses": uses, "grade_fit": not automotive or a.market == "Automotive",
                      "tag_keys": index["tags"],
                      "tags": [labels[k] for k in index["tags"]], "index": index,
                      "groups": [{"label": g, "blocks": bs} for g, bs in groups.items()], "also": also, "gaps": gaps,
                      "open": f"/blocks/new?{where}&place={quote(mpn)}&fn={fn}"})  # fmt: skip
    # most relevant first: library designs, the part's grade (automotive part: vehicle designs), designs that use its
    # function more often, then the most of our parts around it
    cards.sort(key=lambda c: (c["background"], not c["grade_fit"], -c["uses"], -len(c["also"]), c["name"]))
    return cards


def filter_cards(cards: list[dict], q: str) -> list[dict]:
    """The cards that match every part of the search (general categories, then words)."""
    return [c for c in cards if blocks.search_all(c["index"], q)]


def category_counts(cards: list[dict]) -> list[tuple[str, str, int]]:
    """General categories over the cards, most used first: the quick picks above the search (what to type, label,
    number of applications)."""
    labels = {c["key"]: c["label"] for c in blocks.categories()}
    n = Counter(t for c in cards for t in c["tag_keys"]).most_common(10)
    return [(k.replace("_", " "), labels[k], k_n) for k, k_n in n]


def saved_designs(session: Session, fn: str, limit: int = 30) -> list[dict]:
    """Saved block diagrams to add the part to: those that already have its function first."""
    rows = []
    for d in session.scalars(select(BlockDiagram).order_by(BlockDiagram.updated_at.desc()).limit(200)):
        has = any(b.get("fn") == fn for g in (d.data or {}).get("groups") or [] for b in g.get("blocks") or [])
        rows.append({"id": d.id, "name": d.name, "has": has})
    rows.sort(key=lambda r: not r["has"])
    return rows[:limit]


def search_phrases() -> dict:
    """The category phrases and ignored words for the page's live search (the same rules as blocks.search_all)."""
    return {"phrases": [[w, sorted(k)] for w, k in blocks.category_phrases()], "stop": sorted(blocks.STOP_WORDS)}


def _case_link(slug: str, fn: str) -> str:
    """How a preliminary case relates to the function: its main function, or a block in its customer diagram."""
    c = prelim.raw(slug)
    if not c:
        return ""
    if c.get("fn") == fn:
        return "main function"
    blocks_ = [b if isinstance(b, dict) else {"fn": b} for g in (c.get("diagram") or {}).get("groups") or []
               for b in g.get("blocks") or []]  # fmt: skip
    return "in its customer diagram" if any(vocab.canonical(b.get("fn", "")) == fn for b in blocks_) else ""


def record_gaps(session: Session, part: Part, gaps: list[tuple[int, str]]) -> int:
    """Each gap once as site feedback for the next review: not again while an item with the same text is open,
    planned, declined or a duplicate (a done item is raised again if the data is still missing)."""
    added = 0
    for step, text in gaps:
        q = select(SiteFeedback.id).where(SiteFeedback.author == AUTHOR, SiteFeedback.text.startswith(text),
                                          SiteFeedback.status != "done")  # fmt: skip
        if session.scalar(q.limit(1)) is not None:
            continue
        page = f"Products › {part.mpn} › Walk-through › Step {step}: {STEPS[step]}"
        session.add(SiteFeedback(text=f"{text} · found walking through {part.mpn}", kind="data", author=AUTHOR,
                                 path=f"/parts/{part.id}/walk#step-{step}", page=page))  # fmt: skip
        added += 1
    if added:
        session.commit()
    return added
