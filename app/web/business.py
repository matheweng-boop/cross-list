"""Business opportunity pages: overview (pipeline), applications (coverage + simulator), attach, gaps & ranking,
TAM estimates."""

from collections import Counter
from datetime import UTC, date, datetime

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.session import signed_in_owner
from app.config import get_settings
from app.db import count, get_session
from app.matching import engine
from app.models import (
    Case,
    CaseNote,
    DataReview,
    OpportunityDecision,
    Part,
    PartMapping,
    PipelineDraft,
    ScheduledReview,
    ShortlistItem,
    TamEstimate,
    TechFeedback,
)
from app.services import blocks, cases, library, patents, pipeline, prelim, quality, schedule, scoring, tam, vocab, walk
from app.services import idea_requests as ir
from app.services import opportunity as op
from app.services import portfolio as pf
from app.services import priority as priority
from app.services import reports as rp
from app.services import rf_coverage as rf
from app.services.seed import unofficial_counts
from app.web.routes import templates
from app.web.urls import local_path

router = APIRouter()
templates.env.globals["bo_status_help"] = op.STATUS_HELP
templates.env.globals["bo_help"] = op.explanations


def _ctx(session: Session, co: str, scope: str = "all") -> dict:
    key, label, mine = op.company(co)
    mk = op.makers(session)
    scope = scope if scope in op.SCOPES else "all"
    apps = op.in_scope(op.with_status(op.applications(), mk, mine), scope)
    asp, vol = op.inputs(session)
    return {
        "co": key,
        "co_label": label,
        "companies": op.COMPANIES,
        "apps": apps,
        "asp": asp,
        "vol": vol,
        "mk": mk,
        "status_label": op.STATUS_LABEL,
        "fns": blocks.catalogue()["functions"],
        "crowding_label": op.CROWDING_LABEL,
        "scope": scope,
        "scopes": op.SCOPES,
        "n_library": sum(not a.background for a in apps),
        "n_background": sum(a.background for a in apps),
    }


@router.get("/business")
def overview(request: Request, co: str = "combined"):
    """The Opportunities section opens on the explorer (the overview page was retired, feedback 2026-10-20): one
    redirect straight to where /business/explorer leads."""
    return explorer_moved(request, co)


@router.get("/business/applications", response_class=HTMLResponse)
def applications(request: Request, co: str = "combined", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    c["rows"] = sorted(((a, op.metrics(a.positions, c["asp"])) for a in c["apps"]),
                       key=lambda r: (r[0].category, -(r[1]["coverage"] or 0)))  # fmt: skip
    return templates.TemplateResponse(request, "business/applications.html", c)


@router.get("/business/applications/{i:int}", response_class=HTMLResponse)
def application(request: Request, i: int, co: str = "combined", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    app = next((a for a in c["apps"] if a.i == i), None)
    if app is None:
        raise HTTPException(404, "Application not found")
    c.update(app=app, m=op.metrics(app.positions, c["asp"]), groups=op.by_group(app, c["asp"]))
    return templates.TemplateResponse(request, "business/application.html", c)


@router.get("/business/attach", response_class=HTMLResponse)
def attach(request: Request, fn: str = "", co: str = "combined", part: str = "", app: str = "",
           session: Session = Depends(get_session)):  # fmt: skip
    """Cross-sell: from a part number (optionally narrowed by a loosely described application), or from a function."""
    from app.services import crosssell

    c = _ctx(session, co)
    c["q_part"], c["q_app"] = part.strip()[:60], app.strip()[:120]
    c["anchor"] = crosssell.resolve_part(session, c["q_part"]) if c["q_part"] else None
    c["sell"] = crosssell.suggest(session, c["anchor"], c["q_app"], co) if c["anchor"] else None
    c["walk_part"] = (session.scalar(select(Part).where(Part.mpn == c["anchor"]["mpn"]).limit(1))
                      if c["anchor"] and not c["anchor"]["ours"] else None)  # fmt: skip
    c["bundle_cfg"] = scoring.config()["bundle"]
    used = Counter(fn for a in c["apps"] for fn in {p.fn for p in a.positions if p.status == "supported"})
    c["anchors"] = sorted(used.items(), key=lambda kv: (-kv[1], vocab.fn_label(kv[0])))
    c["fn"] = fn if fn in used else ""
    c["result"] = op.attach(c["apps"], fn) if c["fn"] else None
    c["pairs"] = op.cross_sell_pairs(c["apps"]) if not c["fn"] else []
    # from a part (or function) to the systems that use it (owner, 25 Oct 2026: the Cross-sell tabs work together)
    from app.services import systems as sy

    focus = c["fn"] or (c["anchor"]["fns"][0] if c["anchor"] and c["anchor"]["fns"] else "")
    c["fn_places"] = sy.places_of_function(focus) if focus else []
    mfrs = op.company(co)[2]

    def offer(f: str) -> list[dict]:
        """Our best parts for a function (two per manufacturer), named, so a cross-sell has something to offer."""
        out = []
        for m in blocks.parts_for(session, f)["manufacturers"]:
            if m["manufacturer"] in mfrs:
                out += [{"mpn": p["mpn"], "url": p["url"], "manufacturer": m["manufacturer"]} for p in m["best"]]
        return out[:4]

    if c["result"]:
        c["anchor_parts"] = offer(c["fn"])
        for e in c["result"]["rows"]:
            e["offer"] = offer(e["fn"]) if e["status"] == "supported" else []
            e["why"] = op.pair_reasons(c["result"]["apps"], c["fn"], e["fn"])
    for pr in c["pairs"]:
        pr["why"] = op.pair_reasons(c["apps"], pr["a"], pr["b"])
    c["shortlisted"] = {
        i.key for i in session.scalars(select(ShortlistItem).where(ShortlistItem.origin == "crosssell"))
    }
    return templates.TemplateResponse(request, "business/attach.html", c)


@router.get("/business/gaps")
def gaps_moved(co: str = "combined", sort: str = "reach"):
    """Old Gaps & ranking page: now the reach / cross-sell / competition / commercial views of the explorer."""
    view = {"adjacency": "crosssell", "positions": "reach", "tam": "commercial", "crowding": "competition"}.get(
        sort, "reach"
    )
    return RedirectResponse(f"/business/explorer/table?co={co}&view={view}", status_code=307)


@router.get("/business/markets", response_class=HTMLResponse)
def markets(request: Request, co: str = "combined", view: str = "all", m: str = "", g: str = "", show: str = "",
            wt: str = "", wl: str = "", wd: str = "", session: Session = Depends(get_session)):  # fmt: skip
    """Functions by end market, in three groups (existing portfolio, portfolio gap, new technology); market chips
    choose which markets count. Each group is in priority order, "RF & power only" by default, with the same score as
    Gaps & new technology (owner, 25 Oct 2026); its diagram count is the applications in the chosen markets."""
    c = _ctx(session, co)
    w, custom = _priority_weights(request, wt, wl, wd)
    data = op.markets(session, c["apps"], op.company(co)[2])
    chosen = [x for x in m.split(",") if x in data["markets"]] if m else []
    shown = chosen or data["markets"]
    c["view"] = view if view in ("all", "requalify", "qual_unknown", "multi") else "all"
    rows = []
    for e in data["rows"]:
        by = {k: v for k, v in e["by_market"].items() if k in shown}
        if not by:
            continue
        rows.append({**e, "by_market": by, "n_markets": len(by), "n_apps": sum(len(v) for v in by.values())})
    tab = scoring.for_session(session, c["apps"], c["asp"], c["vol"])
    priority.annotate(priority.with_feasibility(rows, tab), w, count=lambda e: e["n_apps"])
    if c["view"] in ("requalify", "qual_unknown"):
        rows = [e for e in rows if e[c["view"]]]
    elif c["view"] == "multi":
        rows = [e for e in rows if e["n_markets"] > 1]
    rows = priority.ranked(rows)
    show = "all" if show == "all" else "focus"
    by_group = {k: [e for e in rows if e["group"] == k] for k in op.MARKET_GROUPS}
    c.update(
        show=show,
        sec={k: priority.sections(v, show) for k, v in by_group.items()},
        wts={priority.PARAMS[k]: v for k, v in priority.percent(w).items()} if custom else {},
        prio=priority.config(),
        prio_w=priority.percent(w),
        prio_default=priority.percent(priority.default_weights()),
        prio_custom=custom,
        prio_sliders=not _is_guest(request),
    )
    c.update(
        markets=data["markets"],
        chosen=chosen,
        path_label=op.PATH_LABEL,
        shown=shown,
        per_market=data["apps_per_market"],
        groups=op.MARKET_GROUPS,
        g=g if g in op.MARKET_GROUPS else "",
        by_group=by_group,
        n_requalify=sum(e["requalify"] for e in data["rows"]),
        n_qual_unknown=sum(e["qual_unknown"] for e in data["rows"]),
        shortlisted={i.key for i in session.scalars(select(ShortlistItem).where(ShortlistItem.origin == "markets"))},
    )
    return templates.TemplateResponse(request, "business/markets.html", c)


@router.get("/business/technology")
def technology_moved(co: str = "combined", view: str = "all"):
    """Old Technology fit page: now the feasibility view of the explorer (its filters map onto explorer filters)."""
    f = view if view in EXPLORER_FILTERS else ""
    url = f"/business/explorer/table?co={co}&view=feasibility" + (f"&f={f}" if f else "")
    return RedirectResponse(url, status_code=307)


# Opportunity explorer columns that sort: key -> (label, default direction, sort key). Old `view` links map onto them.
PATH_ORDER = {"exists": 0, "variant": 1, "new_design": 2, "new_capability": 3, "not_pursue": 4}
CROWD_ORDER = {"low": 0, "medium": 1, "high": 2}
SUGGESTION_ORDER = {"quick_win": 0, "new_chip": 1, "niche": 2, "partner": 3, "unknown": 4}
EXPLORER_SORTS = {
    "priority": ("Priority", "desc", lambda e: (e["priority"]["score"], e["priority"]["T"], e["reach"])),
    "label": ("Function", "asc", lambda e: e["label"].lower()),
    "path": ("Gap type · path", "asc", lambda e: (PATH_ORDER.get((e["path"] or {}).get("path"), 5), -e["reach"])),
    "reach": ("Needed in", "desc", lambda e: (e["reach"], e["adjacent"])),
    "competition": ("Competition", "asc",
                    lambda e: (CROWD_ORDER.get((e["competition"] or {}).get("crowding"), 3), -e["reach"])),
    "score": ("Type · score", "desc",
              lambda e: (-SUGGESTION_ORDER.get(e["suggestion"], 9), e["score"] if e["score"] is not None else -1)),
    "tam": ("TAM / year", "desc", lambda e: (e["tam"], e["reach"])),
}  # fmt: skip
VIEW_TO_SORT = {"reach": "reach", "crosssell": "reach", "feasibility": "score", "competition": "competition",
                "commercial": "tam", "evidence": "reach"}  # fmt: skip
EXPLORER_FILTERS = {
    "develop": ("Same or adjacent technology", lambda e: (e["proximity"] or 0) >= 2),
    "short": ("Exists or spec variant", lambda e: (e["path"] or {}).get("path") in ("exists", "variant")),
    "build": ("New design", lambda e: (e["path"] or {}).get("path") == "new_design"),
    "acquire": ("New technology: partner / acquire", lambda e: (e["path"] or {}).get("path") == "new_capability"),
    "kept": ("Kept for consideration", lambda e: (e["decision"] or {}).get("status") == "keep"),
    "chips": ("Customer parts (chips we do not make)", lambda e: e["gap_type"] == "not_ours"),
}


EXPLORER_PARAMS = ("scope", "view", "sort", "dir", "f", "t", "g", "s")


@router.get("/business/explorer")
def explorer_moved(request: Request, co: str = "combined"):
    """The explorer now opens as Opportunities > Gaps & new technology (owner, 23 Oct 2026); links that sort or
    filter keep landing on the detailed table."""
    if any(k in request.query_params for k in EXPLORER_PARAMS):
        return RedirectResponse(f"/business/explorer/table?{request.url.query}", status_code=307)
    return RedirectResponse(f"/business/opportunities?co={op.company(co)[0]}", status_code=307)


def _by_score(e: dict):
    return (e["score"] is None, -(e["score"] or 0), -e["reach"], e["label"])


@router.get("/blocks/cross-sell", response_class=HTMLResponse)
def cross_sell(request: Request, co: str = "combined", system: str = "", sub: str = "", sel: str = "",
               template: str = "", aec: str = "", session: Session = Depends(get_session)):  # fmt: skip
    """Cross-sell, bottom up (owner, 23 Oct 2026): pick a system, a sub-system or one diagram of the Application
    library and see which of our parts go together in it. Gaps and new technology are under Opportunities.
    ?aec=1 / 0: "Automotive-qualified only" (owner, 24 Oct 2026), on by default for the Automotive system."""
    from app.services import systems as sy

    if sel:  # the picker sends "system" or "system:sub"
        system, _, sub = sel.partition(":")
    aec_on = aec == "1" if aec in ("0", "1") else system == "automotive"
    template = int(template) if template.isdigit() else None
    if template is not None and sy.get(system) and template not in sy.selection(system, sub)["idx"]:
        template = None  # a diagram left over from the previous pick
    c = _ctx(session, co)
    mine = op.company(co)[2]
    picked = sy.selection(system, sub, template)
    c.update(tree=sy.systems(), system=system if sy.get(system) else "", sub=sub if sy.sub(system, sub) else "",
             template=template if picked["level"] == "application" else None, picked=picked,
             names={i: blocks.display_name(t) for i, t in enumerate(blocks.templates())})  # fmt: skip
    if picked["idx"]:
        c["xs"] = sy.bottom_up(session, picked["idx"], mine)
        # Skyworks + Qorvo together here (owner, 25 Oct 2026): each pair is shown once. A synergy pair leaves the
        # Bundles table and is shown in the block below with everything (count, reason, diagrams, parts, design mark)
        # (both lines only when the page shows the combined company)
        both = op.company(co)[0] == "combined"
        tog = pf.together_in([a.i for a in c["xs"]["apps"]]) if both else {"synergies": [], "bundles": []}
        syn = {frozenset((x["skyworks"], x["qorvo"])) for x in tog["synergies"]}
        c["xs"]["n_moved"] = sum(frozenset((pr["a"], pr["b"])) in syn for pr in c["xs"]["pairs"])
        c["xs"]["pairs"] = [pr for pr in c["xs"]["pairs"] if frozenset((pr["a"], pr["b"])) not in syn]
        for pr in c["xs"]["pairs"]:
            pr["why"] = op.pair_reasons(c["xs"]["apps"], pr["a"], pr["b"])
        c["tog"] = tog if tog["synergies"] or tog["bundles"] else None
        c["in_sel"] = sy.selection(system, sub)["idx"] if picked["level"] == "application" else picked["idx"]
        # Skyworks and Qorvo parts here (owner, 25 Oct 2026): the parts by function at the top; a function in a
        # synergy pair links to its card in the block below (the table lists the parts, the block explains the pairs)
        c["table"] = sy.parts_table(session, c["xs"]["ours"], mine, aec_on)
        rows = {r["fn"]: r for r in c["table"]["rows"]}
        for j, x in enumerate(tog["synergies"], 1):
            for fn, line, other in ((x["skyworks"], "Skyworks", x["qorvo_label"]),
                                    (x["qorvo"], "Qorvo", x["skyworks_label"])):  # fmt: skip
                if fn in rows and line in rows[fn]["pairs"]:
                    rows[fn]["pairs"][line].append({"j": j, "other": other})
    else:  # nothing picked yet: what we can sell across the whole library, as before
        sell = []
        for e in op.markets(session, c["apps"], mine)["rows"]:
            if e["group"] == "portfolio":
                by = e["by_market"]
                sell.append({"fn": e["fn"], "label": e["label"], "n_apps": sum(len(v) for v in by.values()),
                             "markets": sorted(by, key=lambda m: (-len(by[m]), m)),
                             "requalify": e["requalify"]})  # fmt: skip
        c["sell"] = sorted(sell, key=lambda e: (-e["n_apps"], e["label"]))
    c["aec"], c["aec_param"] = aec_on, aec if aec in ("0", "1") else ""
    c["aec_base"] = (f"/blocks/cross-sell?co={op.company(co)[0]}" + (f"&system={system}" if sy.get(system) else "")
                     + (f"&sub={sub}" if sy.sub(system, sub) else "")
                     + (f"&template={template}" if c["template"] is not None else ""))  # fmt: skip
    return templates.TemplateResponse(request, "business/cross_sell.html", c)


def _is_guest(request: Request) -> bool:
    from app.auth.session import principal

    me = principal(request)
    return bool(me and me.is_guest)


def _priority_weights(request: Request, wt: str, wl: str, wd: str) -> tuple[dict, bool]:
    """The priority weights: the owner's sliders from the URL, the defaults for guests (owner, 25 Oct 2026)."""
    return priority.weights(wt, wl, wd, allowed=not _is_guest(request))


@router.get("/business/opportunities", response_class=HTMLResponse)
def gaps_new_tech(request: Request, co: str = "combined", show: str = "", wt: str = "", wl: str = "", wd: str = "",
                  session: Session = Depends(get_session)):  # fmt: skip
    """Opportunities > Gaps & new technology (owner, 23 Oct 2026, moved out of Cross-sell & gaps): functions with no
    part of ours yet that our technology could cover, and those that need new technology; highest priority first
    (owner, 25 Oct 2026: technology relation, likeliness and diagrams), "RF & power only" by default."""
    c = _ctx(session, co)
    w, custom = _priority_weights(request, wt, wl, wd)
    rows = op.explorer(c["apps"], c["asp"], c["vol"], scoring.for_session(session, c["apps"], c["asp"], c["vol"]))
    priority.annotate(rows, w)
    decisions = {d.fn: d.status for d in session.scalars(select(OpportunityDecision))}
    rows = [{**e, "decision": decisions.get(e["key"])} for e in rows]
    open_rows = [e for e in rows if e["gap_type"] != "not_ours" and e["decision"] != "set_aside"]
    new = priority.ranked([e for e in open_rows if (e["path"] or {}).get("path") == "new_capability"])
    gaps = priority.ranked([e for e in open_rows if e not in new])
    show = "all" if show == "all" else "focus"
    shortlisted = {i.key for i in session.scalars(select(ShortlistItem).where(ShortlistItem.origin == "explorer"))}
    pc = priority.config()
    wq = "".join(f"&{priority.PARAMS[k]}={v}" for k, v in priority.percent(w).items()) if custom else ""
    c.update(gaps=gaps, new=new, show=show, shortlisted=shortlisted, path_label=op.PATH_LABEL, wq=wq,
             sec={"gaps": priority.sections(gaps, show), "new": priority.sections(new, show)},
             prio=pc, prio_w=priority.percent(w), prio_default=priority.percent(priority.default_weights()),
             prio_custom=custom, prio_levels=priority.levels(), prio_example=priority.example,
             prio_top=priority.ranked(open_rows)[0] if open_rows else None, prio_ldo=priority.ldo_example(open_rows),
             prio_patent=priority.patent_example(open_rows),
             prio_unmapped=priority.unmapped(open_rows), prio_sliders=not _is_guest(request),
             prio_owner=[(vocab.fn_label(fn), o) for fn, o in (pc["likeliness"].get("owner") or {}).items()],
             n_not_ours=sum(e["gap_type"] == "not_ours" for e in rows),
             n_aside=sum(e["decision"] == "set_aside" for e in rows))  # fmt: skip
    return templates.TemplateResponse(request, "business/gaps_new.html", c)


@router.get("/business/explorer/table", response_class=HTMLResponse)
def opportunity_explorer(
    request: Request,
    co: str = "combined",
    scope: str = "all",
    view: str = "",
    sort: str = "",
    dir: str = "",
    f: str = "",
    t: str = "",
    g: str = "",
    s: str = "",
    wt: str = "",
    wl: str = "",
    wd: str = "",
    session: Session = Depends(get_session),
):
    """Missing functions and RF band gaps, grouped by big category; any column sorts, the priority by default (owner,
    25 Oct 2026). Rows set aside are listed separately below."""
    c = _ctx(session, co, scope)
    w, custom = _priority_weights(request, wt, wl, wd)
    rows = op.explorer(c["apps"], c["asp"], c["vol"], scoring.for_session(session, c["apps"], c["asp"], c["vol"]))
    priority.annotate(rows, w)
    decisions = {d.fn: d for d in session.scalars(select(OpportunityDecision))}
    for e in rows:
        d = decisions.get(e["key"])
        e["decision"] = {"status": d.status, "note": d.note, "date": d.updated_at} if d else None
    sort = sort if sort in EXPLORER_SORTS else VIEW_TO_SORT.get(view, "priority")
    dir = dir if dir in ("asc", "desc") else EXPLORER_SORTS[sort][1]
    c["type_counts"] = Counter(e["gap_type"] for e in rows)
    if t in op.GAP_TYPE_LABEL:
        rows = [e for e in rows if e["gap_type"] == t]
    elif f != "chips":  # chips we do not make only on request
        rows = [e for e in rows if e["gap_type"] != "not_ours"]
    if f in EXPLORER_FILTERS:
        rows = [e for e in rows if EXPLORER_FILTERS[f][1](e)]
    c["sugg_counts"] = Counter(e["suggestion"] for e in rows if (e["decision"] or {}).get("status") != "set_aside")
    s = s if s in SUGGESTION_ORDER else ""
    if s:
        rows = [e for e in rows if e["suggestion"] == s]
    c["group_counts"] = Counter(e["group"] for e in rows if (e["decision"] or {}).get("status") != "set_aside")
    g = g if g in c["group_counts"] else ""
    if g:
        rows = [e for e in rows if e["group"] == g]
    rows.sort(key=EXPLORER_SORTS[sort][2], reverse=dir == "desc")
    shortlisted = {i.key for i in session.scalars(select(ShortlistItem).where(ShortlistItem.origin == "explorer"))}
    shown = [e for e in rows if (e["decision"] or {}).get("status") != "set_aside"]
    # columns with one value in every row are said once above the table instead (the sorted column always stays)
    crowds = {(e["competition"] or {}).get("crowding") for e in shown}
    c["same"] = {"gap": len({e["gap_type"] for e in shown}) == 1,
                 "crowd": len(crowds) == 1 and len(shown) > 1 and sort != "competition",
                 "tam": not any(e["tam_apps"] for e in shown) and sort != "tam"}  # fmt: skip
    order = [*op.GROUPS, "Other"]
    c.update(
        rows=shown,
        groups=[(n, [e for e in shown if e["group"] == n]) for n in order if any(e["group"] == n for e in shown)],
        g=g,
        s=s,
        aside=[e for e in rows if (e["decision"] or {}).get("status") == "set_aside"],
        sort=sort,
        dir=dir,
        sorts=EXPLORER_SORTS,
        f=f,
        filters=EXPLORER_FILTERS,
        t=t,
        shortlisted=shortlisted,
        gap_labels=op.GAP_TYPE_LABEL,
        path_label=op.PATH_LABEL,
        prox_label=op.PROXIMITY_LABEL,
        scoring=scoring.config(),
        wts={priority.PARAMS[k]: v for k, v in priority.percent(w).items()} if custom else {},
    )
    return templates.TemplateResponse(request, "business/explorer.html", c)


def _back(request: Request, form, default: str) -> str:
    """Where to return after a form post: a local path from the form, else the default."""
    return local_path(form.get("back"), default)


@router.post("/business/decision")
async def decide(request: Request, session: Session = Depends(get_session)):
    """Keep a missing function under consideration, set it aside (with a note), or clear the decision."""
    form = await request.form()
    fn, status = str(form.get("fn") or ""), str(form.get("status") or "")
    known = fn in blocks.catalogue()["functions"] or any(r["key"] == fn for r in op.rf_band_rows())
    if not known or status not in ("keep", "set_aside", "clear"):
        raise HTTPException(400, "Unknown function or decision")
    d = session.scalar(select(OpportunityDecision).where(OpportunityDecision.fn == fn))
    if status == "clear":
        if d is not None:
            session.delete(d)
    else:
        if d is None:
            d = OpportunityDecision(fn=fn, status=status)
            session.add(d)
        d.status = status
        d.note = str(form.get("note") or "").strip()[:500] or d.note
    session.commit()
    return RedirectResponse(_back(request, form, "/business/explorer/table"), status_code=303)


SHORTLIST_ORIGINS = {"explorer": "Gaps & new technology", "crosssell": "Cross-sell", "markets": "Markets",
                     "customers": "Customers", "idea": "New ideas", "report": "Research & ideas",
                     "part": "Part walk-through"}  # fmt: skip


@router.post("/business/shortlist")
async def shortlist_add(request: Request, session: Session = Depends(get_session)):
    """Put an item on the shortlist for a business case (once; pushing again keeps the first)."""
    form = await request.form()
    origin, key = str(form.get("origin") or ""), str(form.get("key") or "").strip()[:200]
    if origin not in SHORTLIST_ORIGINS or not key:
        raise HTTPException(400, "Unknown origin or empty item")
    if session.scalar(select(ShortlistItem).where(ShortlistItem.origin == origin, ShortlistItem.key == key)) is None:
        fn = str(form.get("fn") or "")
        session.add(ShortlistItem(origin=origin, key=key, title=str(form.get("title") or key).strip()[:200],
                                  detail=str(form.get("detail") or "").strip()[:2000] or None,
                                  fn=fn if fn in blocks.catalogue()["functions"] else None))  # fmt: skip
        session.commit()
    if request.headers.get("accept", "").startswith("application/json"):  # the button's script: stay on the page
        return {"count": _shortlist_count(session)}
    return RedirectResponse(_back(request, form, "/business/shortlist"), status_code=303)


def _shortlist_count(session: Session) -> int:
    return count(session, ShortlistItem)


@router.get("/api/shortlist/count")
def shortlist_count(session: Session = Depends(get_session)):
    return {"count": _shortlist_count(session)}


@router.post("/business/shortlist/{item_id:int}")
async def shortlist_update(request: Request, item_id: int, session: Session = Depends(get_session)):
    form = await request.form()
    item = session.get(ShortlistItem, item_id)
    if item is None:
        raise HTTPException(404, "Item not found")
    if form.get("remove"):
        session.delete(item)
    else:
        item.note = str(form.get("note") or "").strip()[:2000] or None
    session.commit()
    return RedirectResponse("/business/shortlist", status_code=303)


@router.get("/business/shortlist", response_class=HTMLResponse)
def shortlist(request: Request, co: str = "combined", session: Session = Depends(get_session)):
    """Business-case candidates, from the portfolio pages and from new ideas; each can start a business case."""
    c = _case_ctx(session, co)
    items = list(session.scalars(select(ShortlistItem).order_by(ShortlistItem.created_at.desc())))
    c.update(portfolio=[i for i in items if i.origin != "idea"], ideas=[i for i in items if i.origin == "idea"],
             origins=SHORTLIST_ORIGINS, case_titles={x.id: x.title for x in session.scalars(select(Case))},
             scheduled=schedule.items(session), on_schedule=schedule.by_source(session, "shortlist"))  # fmt: skip
    return templates.TemplateResponse(request, "business/shortlist.html", c)


@router.get("/business/method", response_class=HTMLResponse)
def method(request: Request, co: str = "combined", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    c.update(src=op.sources(c["apps"]), help=op.explanations(), prox_label=op.PROXIMITY_LABEL,
             path_label=op.PATH_LABEL, cfg=scoring.config(), tam_n=tam.counts(session)["n"],
             cross={"categories": list(engine.CATEGORY_LABELS.values()), "max_dev": engine.DEFAULT_MAX_DEVIATIONS,
                    "weights": engine.PRIORITY_WEIGHT, "unknown": engine.UNKNOWN_SEVERITY})  # fmt: skip
    return templates.TemplateResponse(request, "business/method.html", c)


@router.get("/business/data")
def data_moved():
    """Commercial inputs (ASPs and volumes) were replaced by TAM estimates per product or technology."""
    return RedirectResponse("/business/tam", status_code=307)


@router.post("/business/data")
def data_moved_post():
    return RedirectResponse("/business/tam", status_code=303)


@router.get("/business/tam", response_class=HTMLResponse)
def tam_page(request: Request, saved: str = "", error: str = "", session: Session = Depends(get_session)):
    """TAM estimates: market size per product or technology, each with its source and the owner's review."""
    rows = tam.estimates(session)
    fns = blocks.catalogue()["functions"]
    tam_ctx = tam_page_extra(session, rows)
    rows = [e for e in rows if e["key"] not in tam_ctx["combined_keys"]]  # members show inside their combined topic
    ctx = {**tam_ctx, "rows": rows, "counts": tam.counts(session), "hint": tam.check_hint, "saved": saved,
           "error": error, "fns": fns, "fn_choices": sorted(((k, f.get("label", k)) for k, f in fns.items()),
                                            key=lambda kv: kv[1].lower())}  # fmt: skip
    return templates.TemplateResponse(request, "business/tam.html", ctx)


def tam_page_extra(session: Session, rows: list[dict]) -> dict:
    """The biweekly check summary, flags and combined topics for the TAM estimates page."""
    from app.services import tam_links

    combined = [t for t in tam.topics(session, rows) if t["is_combined"]]
    pages: dict[str, list[dict]] = {}
    for lk in tam_links.links():
        for ref in [lk.get("topic"), *(lk.get("keys") or [])]:
            if ref and not any(p["slug"] == lk["slug"] for p in pages.get(ref, [])):
                pages.setdefault(ref, []).append({"slug": lk["slug"], "label": lk["slug"]})
    for a in tam_links.applied():  # the applied-answers lock (data/business/tam_applied.yaml), when it exists
        for where in [a.get("applied_in")] if isinstance(a.get("applied_in"), str) else a.get("applied_in") or []:
            pages.setdefault(str(a.get("key")), []).append({"slug": None, "label": str(where)})
    return {"check": tam.check_summary(), "flags": [e for e in rows if e["flag"]], "topics": combined,
            "combined_keys": {e["key"] for t in combined for e in t["members"]}, "history": tam.history(session),
            "applied_in": pages, "check_labels": tam.CHECK_LABELS, "money": tam.money}  # fmt: skip


@router.post("/business/tam")
async def tam_add(request: Request, session: Session = Depends(get_session)):
    form = {k: str(v).strip() for k, v in (await request.form()).items()}
    product, value = form.get("product", "")[:200], form.get("value", "")[:100]
    if not product or not value:
        return RedirectResponse("/business/tam?error=Give+the+product+and+the+market+size#add", status_code=303)
    url = form.get("source_url", "")[:500]
    year = form.get("year", "")
    session.add(TamEstimate(
        product=product, value=value, usd=tam.parse_usd(value), year=int(year) if year.isdigit() else None,
        fn=form.get("fn") if form.get("fn") in blocks.catalogue()["functions"] else None,
        region=form.get("region", "")[:100] or None, scope=form.get("scope", "")[:500] or None,
        source_title=form.get("source_title", "")[:300] or None,
        source_publisher=form.get("source_publisher", "")[:200] or None,
        source_url=url if url.startswith(("http://", "https://")) else None,
        source_date=form.get("source_date", "")[:40] or None, quality=form.get("quality", "")[:2000] or None,
        author=form.get("author", "")[:100] or None,
    ))  # fmt: skip
    session.commit()
    return RedirectResponse("/business/tam?saved=1", status_code=303)


APPLIED_MSG = ("This estimate's answer is already worked into a report, so it takes no new answer. It reopens when "
               "the next check changes or removes the figure.")


@router.post("/business/tam/review")
def tam_review(key: str = Form(...), answer: str = Form(...), comment: str = Form(""), author: str = Form(""),
               back: str = Form(""), session: Session = Depends(get_session)):  # fmt: skip
    """Agree / disagree with an estimate (Yes / No in the Data quality questions), with an optional comment."""
    verdict = {"agree": "correct", "yes": "correct", "disagree": "wrong", "no": "wrong"}.get(answer)
    if verdict is None or not tam.known_key(session, key):
        raise HTTPException(400, "Unknown estimate or answer")
    if key in tam.applied():
        raise HTTPException(409, APPLIED_MSG)
    session.add(DataReview(dataset=tam.DATASET, key=key[:120], verdict=verdict, comment=comment.strip()[:2000] or None,
                           author=author.strip()[:100] or None))  # fmt: skip
    session.commit()
    return RedirectResponse(local_path(back) if back else f"/business/tam#t-{key}", status_code=303)


# ---- case analysis -----------------------------------------------------------------------------------------
def _case_ctx(session: Session, co: str) -> dict:
    key, label, _ = op.company(co)
    return {"co": key, "co_label": label, "companies": op.COMPANIES, "statuses": cases.STATUSES,
            "kinds": cases.NOTE_KINDS, "fields": cases.FIELDS, "fns": blocks.catalogue()["functions"],
            "sched_statuses": schedule.STATUSES, "sched_label": schedule.source_label,
            "sched_link": schedule.source_link,
            "fn_choices": sorted(((k, f.get("label", k)) for k, f in blocks.catalogue()["functions"].items()),
                                 key=lambda kv: kv[1].lower())}  # fmt: skip


@router.get("/business/cases", response_class=HTMLResponse)
def case_list(request: Request, co: str = "combined", session: Session = Depends(get_session)):
    c = _case_ctx(session, co)
    c["cases"] = session.scalars(select(Case).order_by(Case.updated_at.desc())).all()
    c["scheduled"] = schedule.items(session)
    return templates.TemplateResponse(request, "business/cases.html", c)


@router.post("/business/schedule")
async def schedule_add(request: Request, session: Session = Depends(get_session)):
    """Schedule a topic for a business case review (shared contract, see app/services/schedule.py): title
    (required), source, note, part, volume; adds or updates the entry, then back to `next` (a local path) or the
    list."""
    form = await request.form()
    try:
        item = schedule.schedule(session, str(form.get("title") or ""), str(form.get("source") or ""),
                                 str(form.get("note") or ""), str(form.get("part") or ""),
                                 str(form.get("volume") or ""))  # fmt: skip
    except ValueError:
        raise HTTPException(400, "Give the topic a title") from None
    if request.headers.get("accept", "").startswith("application/json"):
        return {"id": item.id, "status": item.status}
    return RedirectResponse(local_path(form.get("next"), "/business/cases#scheduled"), status_code=303)


@router.post("/business/schedule/{item_id:int}")
async def schedule_update(request: Request, item_id: int, session: Session = Depends(get_session)):
    """Change one scheduled topic: its note, mark it reviewed, put it back, or remove it."""
    form = await request.form()
    item = session.get(ScheduledReview, item_id)
    if item is None:
        raise HTTPException(404, "Scheduled topic not found")
    act = str(form.get("act") or "note")
    if act == "remove":
        session.delete(item)
    elif act == "done":
        item.status = "done"
    elif act == "reopen":
        item.status = "started" if item.case_id else "scheduled"
    else:
        item.note = str(form.get("note") or "").strip()[:4000] or None
    session.commit()
    return RedirectResponse(local_path(form.get("next"), "/business/cases#scheduled"), status_code=303)


@router.get("/business/cases/new", response_class=HTMLResponse)
def case_new(request: Request, fn: str = "", co: str = "combined", title: str = "", idea: str = "",
             shortlist: int | None = None, schedule_id: int | None = Query(None, alias="schedule"),
             session: Session = Depends(get_session)):  # fmt: skip
    """New case, optionally from a function (Opportunity explorer) or an idea (Ideas page): nothing is saved until
    the user creates it."""
    c = _case_ctx(session, co)
    ctx = cases.context(session, fn, co)
    values = cases.prefill(ctx)
    if idea:
        values["notes"] = (f"Started from the idea: {idea}\n" + values.get("notes", "")).strip()
    item = session.get(ShortlistItem, shortlist) if shortlist else None
    if item is not None:  # started from a business-case candidate
        start = f"From {SHORTLIST_ORIGINS[item.origin]}: {item.detail or item.title}\n"
        note = f"Note: {item.note}\n" if item.note else ""
        values["notes"] = (start + note + values.get("notes", "")).strip()
    sched = session.get(ScheduledReview, schedule_id) if schedule_id else None
    if sched is not None:  # started from the scheduled reviews (the usual way)
        start = f"Scheduled from {schedule.source_label(sched.source)}: {sched.title}\n"
        note = f"Note: {sched.note}\n" if sched.note else ""
        values["notes"] = (start + note + values.get("notes", "")).strip()
        if sched.volume and not values.get("volume"):
            values["volume"] = sched.volume
    c.update(case=None, fn=fn if ctx else "", ctx=ctx, values=values, shortlist=item.id if item else None,
             schedule=sched.id if sched else None,
             title=title[:200] or (sched.title if sched else "") or (item.title if item else "")
             or (f"New {ctx['label']}" if ctx else ""))  # fmt: skip
    c["suggest"] = cases.suggestions(session, None, ctx, [], sched, c["title"])
    return templates.TemplateResponse(request, "business/case.html", c)


def _inputs(form) -> dict:
    return {k: str(form.get(k) or "").strip() for k, *_ in cases.FIELDS if str(form.get(k) or "").strip()}


@router.post("/business/cases")
async def case_create(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    fn = str(form.get("fn") or "") or None
    if not str(form.get("title") or "").strip() and not fn and not _inputs(form):
        raise HTTPException(400, "Give the case a title, a function or at least one input")
    case = Case(title=str(form.get("title") or "").strip()[:200] or "Untitled case",
                fn=fn if fn in blocks.catalogue()["functions"] else None, inputs=_inputs(form))  # fmt: skip
    session.add(case)
    session.flush()
    item = (
        session.get(ShortlistItem, int(form.get("shortlist"))) if str(form.get("shortlist") or "").isdigit() else None
    )
    if item is not None:
        item.case_id = case.id
    if str(form.get("schedule") or "").isdigit():
        schedule.link_case(session, int(str(form.get("schedule"))), case)
    session.commit()
    return RedirectResponse(f"/business/cases/{case.id}", status_code=303)


def _case(session: Session, case_id: int) -> Case:
    case = session.get(Case, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    return case


@router.get("/business/cases/{case_id:int}", response_class=HTMLResponse)
def case_detail(request: Request, case_id: int, co: str = "combined", session: Session = Depends(get_session)):
    c = _case_ctx(session, co)
    case = _case(session, case_id)
    ctx = cases.context(session, case.fn, co)
    lines = pipeline.lines_of(session, case.id)
    merged = (case.inputs or {}).get("merged_into")
    others = [x for x in session.scalars(select(Case).order_by(Case.title)) if x.id != case.id and x.status != "merged"]
    c.update(case=case, fn=case.fn or "", ctx=ctx, values=case.inputs or {}, title=case.title,
             brief=cases.brief(case, ctx, lines), lines=lines, totals=pipeline.totals(lines),
             role_label=pipeline.ROLE_LABEL, others=others,
             merged_into=session.get(Case, int(merged)) if str(merged or "").isdigit() else None)  # fmt: skip
    sched = session.scalar(select(ScheduledReview).where(ScheduledReview.case_id == case.id))
    c["suggest"] = cases.suggestions(session, case, ctx, lines, sched)
    return templates.TemplateResponse(request, "business/case.html", c)


@router.get("/business/cases/{case_id:int}/brief.md", response_class=PlainTextResponse)
def case_brief(case_id: int, co: str = "combined", session: Session = Depends(get_session)):
    case = _case(session, case_id)
    lines = pipeline.lines_of(session, case.id)
    return PlainTextResponse(cases.brief(case, cases.context(session, case.fn, co), lines), media_type="text/markdown")


@router.post("/business/cases/{case_id:int}")
async def case_update(case_id: int, request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    case = _case(session, case_id)
    act = form.get("act")
    if act == "inputs":
        case.title = str(form.get("title") or case.title).strip()[:200]
        fn = str(form.get("fn") or "")
        case.fn = fn if fn in blocks.catalogue()["functions"] else None
        case.inputs = _inputs(form)
    elif act == "analysis":
        case.analysis = str(form.get("analysis") or "")
        if case.analysis.strip() and case.status in ("collecting", "analysing"):
            case.status = "discussing"
    elif act == "status" and form.get("status") in cases.STATUSES:
        case.status = str(form.get("status"))
    elif act == "note" and str(form.get("text") or "").strip():
        kind = str(form.get("kind") or "comment")
        case.notes.append(CaseNote(kind=kind if kind in cases.NOTE_KINDS else "comment",
                                   author=str(form.get("author") or "").strip()[:100] or None,
                                   text=str(form.get("text")).strip()))  # fmt: skip
    elif act == "delnote":
        case.notes = [n for n in case.notes if str(n.id) != str(form.get("note"))]
    elif act == "lines":  # volumes and target prices of the part lines; a ticked line is removed
        for ln in pipeline.lines_of(session, case.id):
            if form.get(f"del:{ln.id}"):
                session.delete(ln)
                continue
            ln.volume = pipeline.form_number(form.get(f"vol:{ln.id}"), int)
            ln.price = pipeline.form_number(form.get(f"price:{ln.id}"), float)
    elif act == "merge":
        target = session.get(Case, int(form.get("target") or 0)) if str(form.get("target") or "").isdigit() else None
        if target is None or target.id == case.id:
            raise HTTPException(400, "Choose another business case to merge into")
        pipeline.merge(session, case, target)
        session.commit()
        return RedirectResponse(f"/business/cases/{target.id}#lines", status_code=303)
    elif act == "delete":
        for ln in pipeline.lines_of(session, case.id):
            session.delete(ln)
        for it in session.scalars(select(ShortlistItem).where(ShortlistItem.case_id == case.id)):
            it.case_id = None
        for dr in session.scalars(select(PipelineDraft).where(PipelineDraft.case_id == case.id)):
            dr.case_id = None
        schedule.unlink_case(session, case.id)
        session.delete(case)
        session.commit()
        return RedirectResponse("/business/cases", status_code=303)
    session.commit()
    return RedirectResponse(f"/business/cases/{case.id}#{act}", status_code=303)


# ---- where to hunt / technology base ------------------------------------------------------------------------
@router.get("/business/customers", response_class=HTMLResponse)
def hunt(request: Request, fn: str = "", co: str = "combined", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    c["segments"] = op.hunt_by_segment(c["apps"])
    used = Counter(f for a in c["apps"] for f in {p.fn for p in a.positions if p.status in op.IN_SCOPE})
    c["fn_choices"] = sorted(used.items(), key=lambda kv: vocab.fn_label(kv[0]).lower())
    c["fn"] = fn if fn in used else ""
    c["by_fn"] = op.hunt_for_function(c["apps"], fn) if c["fn"] else None
    c["unmatched"] = [a for a in c["apps"] if not a.background and not op.segments_of(a.name)]
    c["shortlisted"] = {
        i.key for i in session.scalars(select(ShortlistItem).where(ShortlistItem.origin == "customers"))
    }
    return templates.TemplateResponse(request, "business/customers.html", c)


@router.get("/business/capabilities", response_class=HTMLResponse)
def capabilities(request: Request, co: str = "combined", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    plats = op.capabilities()
    kinds: dict[str, list] = {}
    for k, p in plats.items():
        kinds.setdefault(p.get("kind") or "other", []).append((k, p))
    c.update(kinds=kinds, tech=op.technology(), prox_label=op.PROXIMITY_LABEL,
             feedback=session.scalars(select(TechFeedback).order_by(TechFeedback.created_at.desc())).all(),
             topics=sorted(plats.items(), key=lambda kv: kv[1].get("name", kv[0])))  # fmt: skip
    return templates.TemplateResponse(request, "business/capabilities.html", c)


@router.post("/business/capabilities/feedback")
async def tech_feedback(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    if form.get("act") == "status":
        fb = session.get(TechFeedback, int(form.get("id") or 0))
        if fb and form.get("status") in ("open", "done", "rejected"):
            fb.status = str(form.get("status"))
    elif str(form.get("text") or "").strip():
        kind = str(form.get("kind") or "idea")
        topic = str(form.get("topic") or "").strip()[:120] or None
        author = str(form.get("author") or "").strip()[:100] or None
        kind = kind if kind in ("missing", "correction", "idea") else "idea"
        session.add(TechFeedback(topic=topic, kind=kind, text=str(form.get("text")).strip(), author=author))
    session.commit()
    return RedirectResponse("/business/capabilities", status_code=303)


@router.get("/business/capabilities/feedback.txt", response_class=PlainTextResponse)
def tech_feedback_txt(session: Session = Depends(get_session)):
    rows = session.scalars(select(TechFeedback).where(TechFeedback.status == "open")).all()
    return "\n".join(
        f"- [{r.kind}] {r.topic or '-'}: {r.text} ({r.author or 'anonymous'}, {r.created_at:%Y-%m-%d})" for r in rows
    )


# ---- evidence (the bigger picture per function), reviews, part mappings, data quality ------------------------
def _rev(session: Session) -> dict[str, dict]:
    return {f"{d}|{k}": {**s, "state": quality.state(s)} for (d, k), s in quality.summary(session).items()}


@router.get("/business/evidence/{fn}", response_class=HTMLResponse)
def evidence(request: Request, fn: str, co: str = "combined", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    if fn not in c["fns"]:
        raise HTTPException(404, "Function not found")
    tab = scoring.for_session(session, c["apps"], c["asp"], c["vol"])
    row = next((e for e in op.technology_fit(c["apps"], tab) if e["fn"] == fn), None)
    c.update(fn=fn, label=vocab.fn_label(fn), row=row, status=op.status_of(fn, c["mk"], op.company(co)[2]),
             ev={t: op.evidence(t).get(fn) for t in op.EVIDENCE_TOPICS}, topics=op.EVIDENCE_TOPICS,
             tech=op.technology().get(fn), comp=op.competition().get(fn), platforms=op.platforms_for(fn),
             hunt=op.hunt_for_function(c["apps"], fn)[:15], existing=quality.possible_existing(session, fn),
             need=next((g for g in op.gaps(c["apps"], c["asp"], c["vol"], tam.by_function(session))
                        if g["fn"] == fn), None),  # fmt: skip
             rev=_rev(session), path_label=op.PATH_LABEL, prox_label=op.PROXIMITY_LABEL)  # fmt: skip
    c["verdicts"] = quality.VERDICTS
    c["pat_platform"], c["pat_bonus"] = patents.platform_for(fn), priority.patent_bonus(fn)
    c["walk_parts"] = walk.competitor_parts(session, fn)
    c["library"] = library.for_function(fn)
    from app.services import key_apps  # key applications (owner, 24 Oct 2026)

    c["key_apps"] = key_apps.for_function(fn)
    return templates.TemplateResponse(request, "business/evidence.html", c)


@router.post("/api/business/review")
def review(payload: dict = Body(...), session: Session = Depends(get_session)):
    ds, key, verdict = (
        str(payload.get("dataset") or ""),
        str(payload.get("key") or ""),
        str(payload.get("verdict") or ""),
    )
    if ds not in quality.datasets() or verdict not in quality.VERDICTS or not key:
        raise HTTPException(400, "Unknown dataset, key or verdict")
    comment = str(payload.get("comment") or "").strip() or None
    author = str(payload.get("author") or "").strip()[:100] or None
    session.add(DataReview(dataset=ds, key=key[:120], verdict=verdict, comment=comment, author=author))
    session.commit()
    s = quality.summary(session).get((ds, key))
    return {"ok": True, **{k: s[k] for k in ("correct", "wrong", "unsure")}, "state": quality.state(s)}


@router.post("/business/evidence/{fn}/mapping")
async def mapping(fn: str, request: Request, session: Session = Depends(get_session)):
    if fn not in blocks.catalogue()["functions"]:
        raise HTTPException(404, "Unknown function")
    form = await request.form()
    mpn, verdict = str(form.get("mpn") or "").strip(), str(form.get("verdict") or "")
    if mpn and verdict in ("yes", "no", "undo"):
        row = session.scalar(select(PartMapping).where(PartMapping.fn == fn, PartMapping.mpn == mpn))
        if verdict == "undo":
            if row:
                session.delete(row)
        elif row:
            row.verdict = verdict
        else:
            mfr, author = str(form.get("manufacturer") or "")[:40], str(form.get("author") or "").strip()[:100] or None
            session.add(PartMapping(fn=fn, mpn=mpn, manufacturer=mfr, verdict=verdict, author=author))
        session.commit()
    return RedirectResponse(f"/business/evidence/{fn}#existing", status_code=303)


@router.get("/business/quality", response_class=HTMLResponse)
def data_quality(request: Request, co: str = "combined", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    c.update(unofficial=unofficial_counts(session), unofficial_on=get_settings().use_unofficial_data)
    tab = scoring.for_session(session, c["apps"], c["asp"], c["vol"])
    c.update(checks=quality.checks(c["apps"]), questions=quality.questions(session, c["apps"], tab),
             research=quality.research(c["apps"], tab),
             rev=_rev(session), verdicts=quality.VERDICTS, ds_labels={k: v[0] for k, v in quality.datasets().items()},
             mappings=session.scalars(select(PartMapping).order_by(PartMapping.created_at.desc())).all())  # fmt: skip
    return templates.TemplateResponse(request, "business/quality.html", c)


@router.post("/business/quality/answer")
def quality_answer(dataset: str = Form(...), key: str = Form(...), answer: str = Form(...), comment: str = Form(""),
                   author: str = Form(""), session: Session = Depends(get_session)):  # fmt: skip
    """Yes / No to one review question, with an optional comment: stored as a review of the item."""
    verdict = {"yes": "correct", "no": "wrong"}.get(answer)
    known = tam.known_key(session, key) if dataset == tam.DATASET else key in (quality.datasets().get(dataset) or
                                                                                ("", {}))[1]  # fmt: skip
    if verdict is None or not known:
        raise HTTPException(400, "Unknown question or answer")
    if dataset == tam.DATASET and key in tam.applied():
        raise HTTPException(409, APPLIED_MSG)
    session.add(DataReview(dataset=dataset, key=key[:120], verdict=verdict, comment=comment.strip()[:2000] or None,
                           author=author.strip()[:100] or None))  # fmt: skip
    session.commit()
    return RedirectResponse("/business/quality?answered=1#questions", status_code=303)


@router.get("/business/quality/todo.txt", response_class=PlainTextResponse)
def quality_todo(session: Session = Depends(get_session)):
    return quality.todo(session)


@router.get("/business/explore", response_class=HTMLResponse)
def explore(request: Request, fit: str = "", co: str = "combined", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    techs = []
    for k, t in op.evidence("new_markets").items():
        ideas = sorted(
            t.get("ideas") or [],
            key=lambda i: (op.FIT_ORDER.get(i.get("fit"), 3), op.FIT_ORDER.get(i.get("confidence"), 3)),
        )
        if fit in op.FIT_ORDER:
            ideas = [i for i in ideas if i.get("fit") == fit]
        if ideas:
            techs.append((k, t, ideas))
    techs.sort(key=lambda x: min(op.FIT_ORDER.get(i.get("fit"), 3) for i in x[2]))
    shortlisted = {i.key for i in session.scalars(select(ShortlistItem).where(ShortlistItem.origin == "idea"))}
    c.update(techs=techs, fit=fit, rev=_rev(session), plats=op.capabilities(), shortlisted=shortlisted)
    return templates.TemplateResponse(request, "business/explore.html", c)


@router.get("/manage/reviews", response_class=HTMLResponse)
def reviews_queue(request: Request, type: str = "", status: str = "", session: Session = Depends(get_session)):
    from app.services import maintenance

    rows = maintenance.items(session)
    counts = Counter(i["type"] for i in rows)
    if type in maintenance.ISSUE_TYPES:
        rows = [i for i in rows if i["type"] == type]
    else:
        type = ""
    done = {"done", "confirmed", "rejected", "cannot", "agreed"}
    if status == "open":
        rows = [i for i in rows if i["status"] not in done]
    elif status == "done":
        rows = [i for i in rows if i["status"] in done]
    ctx = {"rows": rows, "counts": counts, "types": maintenance.ISSUE_TYPES, "type": type, "status": status}
    return templates.TemplateResponse(request, "manage/reviews.html", ctx)


@router.get("/business/validation", response_class=HTMLResponse)
def human_validation(request: Request, prio: str = "", session: Session = Depends(get_session)):
    from app.services import validation

    ctx = {"scan": validation.scan(session), "prio": prio if prio in validation.PRIORITY else ""}
    return templates.TemplateResponse(request, "business/validation.html", ctx)


@router.get("/business/rf-coverage", response_class=HTMLResponse)
def rf_coverage_page(request: Request, fn: str = "", band: str = "", power: str = ""):
    """RF functions by frequency band and output power: where our parts are, and where applications need one."""
    rs = rf.rows()
    need, apps, unknown, n_rf = rf.demand()
    ctx = {"rows": rs, "gaps": rf.gaps(rs), "cfg": rf.config(), "apps": apps, "unknown": unknown, "n_rf": n_rf,
           "n_parts": len(rf.parts()), "no_freq": sum(1 for p in rf.parts() if not p["bands"]),
           "fn": fn, "band": band, "power": power,
           "slot": rf.slot_parts(fn, band, power or None) if fn and band else None,
           "why": rf.basis(fn, band) if fn and band else [], "n_stated": len(rf.block_bands()),
           "rivals": rf.slot_parts(fn, band, power or None, competitors=True) if fn and band else [],
           "n_comp": len(rf.competitor_parts()),
           "comp_makers": sorted({p["manufacturer"] for p in rf.competitor_parts()})}  # fmt: skip
    return templates.TemplateResponse(request, "business/rf_coverage.html", ctx)


@router.get("/business/reports", response_class=HTMLResponse)
def product_reports(request: Request, kind: str = "", tag: str = "", session: Session = Depends(get_session)):
    """Research & ideas: product ideas and reports, the list."""
    rows = [
        r for r in rp.reports() if (not kind or r.get("kind") == kind) and (not tag or tag in (r.get("tags") or []))
    ]
    tags = sorted({t for r in rp.reports() for t in r.get("tags") or []})
    ctx = {"rows": rows, "kinds": rp.KINDS, "statuses": rp.STATUSES, "kind": kind, "tag": tag, "tags": tags,
           "n_all": len(rp.reports()), "scheduled": schedule.by_source(session, "research")}  # fmt: skip
    ctx |= {"expansions": ir.by_slug(session), "owner": signed_in_owner(request) is not None}
    return templates.TemplateResponse(request, "business/reports.html", ctx)


def _question_day(day: str) -> date | None:
    try:
        return date.fromisoformat(day) if day else None
    except ValueError:
        raise HTTPException(400, "Bad date") from None


@router.get("/business/reports/questions", response_class=HTMLResponse)
def report_questions(request: Request, day: str = "", session: Session = Depends(get_session)):
    """Questions asked on the reports, one list per day, reviewed for good questions and duplicates."""
    days = rp.question_days(session)
    d = _question_day(day) or (days[0][0] if days else datetime.now(UTC).date())
    ctx = {"days": days, "rv": rp.review(session, d), "statuses": rp.Q_STATUSES}
    return templates.TemplateResponse(request, "business/report_questions.html", ctx)


@router.get("/business/reports/questions.txt", response_class=PlainTextResponse)
def report_questions_text(day: str = "", session: Session = Depends(get_session)):
    return rp.review_text(rp.review(session, _question_day(day) or datetime.now(UTC).date()))


@router.post("/business/reports/questions/{qid:int}")
async def report_question_decide(request: Request, qid: int, session: Session = Depends(get_session)):
    form = await request.form()
    dup = str(form.get("duplicate_of") or "").lstrip("#").strip()
    try:
        rp.decide(session, qid, str(form.get("status") or ""), str(form.get("answer") or ""),
                  int(dup) if dup.isdigit() else None)  # fmt: skip
    except ValueError:
        raise HTTPException(400, "Unknown status") from None
    except KeyError:
        raise HTTPException(404, "Question not found") from None
    day = str(form.get("day") or "")
    return RedirectResponse(f"/business/reports/questions?day={day}#q{qid}", status_code=303)


@router.get("/business/reports/method", response_class=HTMLResponse)
def case_method(request: Request):
    """How a preliminary case is built: what we learnt, and the template every case follows."""
    return templates.TemplateResponse(request, "business/case_method.html", {"distance": prelim.DISTANCE})


@router.get("/business/reports/{slug}", response_class=HTMLResponse)
def product_report(request: Request, slug: str, session: Session = Depends(get_session)):
    r = rp.report(slug)
    if r is None:
        raise HTTPException(404, "Report not found")
    ctx = {"r": r, "kinds": rp.KINDS, "statuses": rp.STATUSES, "body": f"business/reports/{slug}.html",
           "has_background": rp.has_background(slug), "questions": rp.questions(session, slug),
           "q_statuses": rp.Q_STATUSES, "case": prelim.case(session, slug), "distance": prelim.DISTANCE,
           "verdict_label": prelim.VERDICT_LABEL, "question_groups": prelim.QUESTION_GROUPS,
           "benefit_kinds": prelim.BENEFIT_KINDS, "label": vocab.fn_label, "report_of": rp.report}  # fmt: skip
    fn = (ctx["case"] or {}).get("fn")
    ctx["walk_parts"] = walk.competitor_parts(session, fn, 4) if fn else []
    ctx["library"] = library.items((ctx["case"] or {}).get("library") or [])
    ctx["scheduled"] = schedule.by_source(session, "research").get(slug)
    ctx["learn"] = rp.learn(r)
    ctx["opener"] = (ctx["case"] or {}).get("opener") or prelim.opener(session, slug)
    ctx["tam_notes"] = tam_notes(request, session, slug)
    ctx |= {"expansion": ir.get(session, slug), "owner": signed_in_owner(request) is not None}
    return templates.TemplateResponse(request, "business/report.html", ctx)


def tam_notes(request: Request, session: Session, slug: str) -> dict:
    """Owner view only: is each market figure quoted on this page still in line with the TAM? Guests see nothing."""
    from app.auth.session import principal
    from app.services import tam_links

    who = principal(request)
    return {} if who is not None and who.is_guest else tam_links.for_slug(session, slug)


@router.post("/business/reports/{slug}/react")
async def case_react(request: Request, slug: str, session: Session = Depends(get_session)):
    form = await request.form()
    key = str(form.get("key") or "")
    try:
        prelim.react(session, slug, key, str(form.get("verdict") or ""), str(form.get("comment") or ""),
                     str(form.get("author") or ""))  # fmt: skip
    except ValueError:
        raise HTTPException(400, "Unknown item or verdict") from None
    return RedirectResponse(f"/business/reports/{slug}#i-{key}", status_code=303)


@router.get("/business/reports/{slug}/background", response_class=HTMLResponse)
def product_report_background(request: Request, slug: str, session: Session = Depends(get_session)):
    """The detail behind a report: the data tables and long-form notes kept out of the report itself."""
    r = rp.report(slug)
    if r is None or not rp.has_background(slug):
        raise HTTPException(404, "No background for this report")
    ctx = {"r": r, "kinds": rp.KINDS, "statuses": rp.STATUSES, "body": f"business/reports/{slug}.background.html",
           "background": True, "tam_notes": tam_notes(request, session, slug)}  # fmt: skip
    return templates.TemplateResponse(request, "business/report.html", ctx)


@router.post("/business/reports/{slug}/ask")
async def product_report_ask(request: Request, slug: str, session: Session = Depends(get_session)):
    if rp.report(slug) is None:
        raise HTTPException(404, "Report not found")
    form = await request.form()
    text = str(form.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Write a question first")
    rp.ask(session, slug, text, str(form.get("author") or ""))
    return RedirectResponse(f"/business/reports/{slug}?asked=1#questions", status_code=303)
