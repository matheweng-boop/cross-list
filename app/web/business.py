"""Business opportunity pages: overview (pipeline), applications (coverage + simulator), attach, gaps & ranking,
TAM data."""

from collections import Counter
from datetime import UTC, date, datetime

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import (
    BusinessAssumption,
    Case,
    CaseNote,
    DataReview,
    OpportunityDecision,
    PartMapping,
    PipelineDraft,
    ShortlistItem,
    TechFeedback,
)
from app.services import blocks, cases, pipeline, quality
from app.services import opportunity as op
from app.services import rf_coverage as rf
from app.web.routes import templates

router = APIRouter()
templates.env.globals["bo_status_help"] = op.STATUS_HELP
templates.env.globals["bo_help"] = op.explanations
_CROWD = {"low": 0, "medium": 1, "high": 2}


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


@router.get("/business", response_class=HTMLResponse)
def overview(request: Request, co: str = "combined", scope: str = "all", session: Session = Depends(get_session)):
    c = _ctx(session, co, scope)
    c["ov"] = op.overview(c["apps"], c["asp"], c["vol"])
    return templates.TemplateResponse(request, "business/overview.html", c)


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
    used = Counter(fn for a in c["apps"] for fn in {p.fn for p in a.positions if p.status == "supported"})
    c["anchors"] = sorted(used.items(), key=lambda kv: (-kv[1], c["fns"].get(kv[0], {}).get("label", kv[0])))
    c["fn"] = fn if fn in used else ""
    c["result"] = op.attach(c["apps"], fn) if c["fn"] else None
    c["pairs"] = op.cross_sell_pairs(c["apps"]) if not c["fn"] else []
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
    return RedirectResponse(f"/business/explorer?co={co}&view={view}", status_code=307)


@router.get("/business/markets", response_class=HTMLResponse)
def markets(request: Request, co: str = "combined", view: str = "all", m: str = "", g: str = "",
            session: Session = Depends(get_session)):  # fmt: skip
    """Functions by end market, in three groups (existing portfolio, portfolio gap, new technology); market chips
    choose which markets count."""
    c = _ctx(session, co)
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
    if c["view"] in ("requalify", "qual_unknown"):
        rows = [e for e in rows if e[c["view"]]]
    elif c["view"] == "multi":
        rows = [e for e in rows if e["n_markets"] > 1]
    rows.sort(key=lambda e: (-e["n_markets"], -e["n_apps"], e["label"]))
    c.update(
        markets=data["markets"],
        chosen=chosen,
        path_label=op.PATH_LABEL,
        shown=shown,
        per_market=data["apps_per_market"],
        groups=op.MARKET_GROUPS,
        g=g if g in op.MARKET_GROUPS else "",
        by_group={k: [e for e in rows if e["group"] == k] for k in op.MARKET_GROUPS},
        n_requalify=sum(e["requalify"] for e in data["rows"]),
        n_qual_unknown=sum(e["qual_unknown"] for e in data["rows"]),
        shortlisted={i.key for i in session.scalars(select(ShortlistItem).where(ShortlistItem.origin == "markets"))},
    )
    return templates.TemplateResponse(request, "business/markets.html", c)


@router.get("/business/technology")
def technology_moved(co: str = "combined", view: str = "all"):
    """Old Technology fit page: now the feasibility view of the explorer (its filters map onto explorer filters)."""
    f = view if view in EXPLORER_FILTERS else ""
    return RedirectResponse(f"/business/explorer?co={co}&view=feasibility" + (f"&f={f}" if f else ""), status_code=307)


# Opportunity explorer columns that sort: key -> (label, default direction, sort key). Old `view` links map onto them.
PATH_ORDER = {"exists": 0, "variant": 1, "new_design": 2, "new_capability": 3, "not_pursue": 4}
CROWD_ORDER = {"low": 0, "medium": 1, "high": 2}
EXPLORER_SORTS = {
    "label": ("Function", "asc", lambda e: e["label"].lower()),
    "path": ("Gap type · path", "asc", lambda e: (PATH_ORDER.get((e["path"] or {}).get("path"), 5), -e["reach"])),
    "reach": ("Needed in", "desc", lambda e: (e["reach"], e["adjacent"])),
    "competition": ("Competition", "asc",
                    lambda e: (CROWD_ORDER.get((e["competition"] or {}).get("crowding"), 3), -e["reach"])),
    "score": ("Fit score", "desc", lambda e: (e["score"] if e["score"] is not None else -1, e["reach"])),
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
    "chips": ("Not our product type", lambda e: e["gap_type"] == "not_ours"),
}


@router.get("/business/explorer", response_class=HTMLResponse)
def opportunity_explorer(
    request: Request,
    co: str = "combined",
    scope: str = "all",
    view: str = "",
    sort: str = "",
    dir: str = "",
    f: str = "",
    t: str = "",
    session: Session = Depends(get_session),
):
    """One table of missing functions; any column sorts. Functions set aside are listed separately below."""
    c = _ctx(session, co, scope)
    rows = op.explorer(c["apps"], c["asp"], c["vol"])
    decisions = {d.fn: d for d in session.scalars(select(OpportunityDecision))}
    for e in rows:
        d = decisions.get(e["fn"])
        e["decision"] = {"status": d.status, "note": d.note, "date": d.updated_at} if d else None
    sort = sort if sort in EXPLORER_SORTS else VIEW_TO_SORT.get(view, "reach")
    dir = dir if dir in ("asc", "desc") else EXPLORER_SORTS[sort][1]
    c["type_counts"] = Counter(e["gap_type"] for e in rows)
    if t in op.GAP_TYPE_LABEL:
        rows = [e for e in rows if e["gap_type"] == t]
    elif f != "chips":  # chips we do not make only on request
        rows = [e for e in rows if e["gap_type"] != "not_ours"]
    if f in EXPLORER_FILTERS:
        rows = [e for e in rows if EXPLORER_FILTERS[f][1](e)]
    rows.sort(key=EXPLORER_SORTS[sort][2], reverse=dir == "desc")
    shortlisted = {i.key for i in session.scalars(select(ShortlistItem).where(ShortlistItem.origin == "explorer"))}
    c.update(
        rows=[e for e in rows if (e["decision"] or {}).get("status") != "set_aside"],
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
        max_score=max((e["score"] or 0 for e in rows), default=0),
    )
    return templates.TemplateResponse(request, "business/explorer.html", c)


def _back(request: Request, form, default: str) -> str:
    """Where to return after a form post: a local path from the form, else the default."""
    back = str(form.get("back") or "")
    return back if back.startswith("/") and not back.startswith("//") else default


@router.post("/business/decision")
async def decide(request: Request, session: Session = Depends(get_session)):
    """Keep a missing function under consideration, set it aside (with a note), or clear the decision."""
    form = await request.form()
    fn, status = str(form.get("fn") or ""), str(form.get("status") or "")
    if fn not in blocks.catalogue()["functions"] or status not in ("keep", "set_aside", "clear"):
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
    return RedirectResponse(_back(request, form, "/business/explorer"), status_code=303)


SHORTLIST_ORIGINS = {"explorer": "Opportunity explorer", "crosssell": "Cross-sell", "markets": "Markets",
                     "customers": "Customers", "idea": "New ideas", "report": "Product ideas & reports"}  # fmt: skip


@router.post("/business/shortlist")
async def shortlist_add(request: Request, session: Session = Depends(get_session)):
    """Push an item into the business-case candidates (once; pushing again keeps the first)."""
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
    return RedirectResponse(_back(request, form, "/business/shortlist"), status_code=303)


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
             origins=SHORTLIST_ORIGINS, case_titles={x.id: x.title for x in session.scalars(select(Case))})  # fmt: skip
    return templates.TemplateResponse(request, "business/shortlist.html", c)


@router.get("/business/method", response_class=HTMLResponse)
def method(request: Request, co: str = "combined", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    c.update(src=op.sources(c["apps"]), help=op.explanations(), prox_label=op.PROXIMITY_LABEL,
             prox_weight=op.PROXIMITY_WEIGHT, crowd_weight=op.CROWDING_WEIGHT)  # fmt: skip
    return templates.TemplateResponse(request, "business/method.html", c)


@router.get("/business/data", response_class=HTMLResponse)
def data(request: Request, co: str = "combined", focus: str = "", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    uses = Counter(fn for a in c["apps"] for fn in {p.fn for p in a.positions if p.status in op.IN_SCOPE})
    c["asp_fns"] = sorted(uses, key=lambda f: c["fns"].get(f, {}).get("label", f))
    c["uses"] = uses
    c["meta"] = {(m.kind, m.key): m for m in session.scalars(select(BusinessAssumption))}
    c["focus"] = focus
    return templates.TemplateResponse(request, "business/data.html", c)


def _num(v: str) -> float | None:
    v = (v or "").strip().replace(",", "").replace("$", "")
    try:
        return float(v) if v else None
    except ValueError:
        return None


@router.post("/business/data")
async def save_data(request: Request, co: str = Form("combined"), session: Session = Depends(get_session)):
    form = await request.form()
    meta: dict[tuple[str, str], dict] = {}
    for k, v in form.items():
        if k.startswith("asp:"):
            op.set_input(session, "asp", k[4:], _num(str(v)))
        elif k.startswith("vol:"):
            op.set_input(session, "volume", k[4:], _num(str(v)))
        elif k.startswith("meta:"):  # meta:<asp|volume>:<field>:<key>
            _, kind, fld, key = k.split(":", 3)
            if fld in ("source", "year", "geography", "currency", "scenario", "confidence"):
                meta.setdefault((kind, key), {})[fld] = str(v).strip()
    for (kind, key), fields in meta.items():
        row = session.scalar(
            select(BusinessAssumption).where(BusinessAssumption.kind == kind, BusinessAssumption.key == key)
        )
        if not any(fields.values()) and not row:
            continue
        row = row or BusinessAssumption(kind=kind, key=key)
        year = fields.get("year", "")
        row.source, row.year = fields.get("source") or None, int(year) if year.isdigit() else None
        row.geography, row.currency = fields.get("geography") or None, fields.get("currency") or None
        row.scenario, row.confidence = fields.get("scenario") or None, fields.get("confidence") or None
        session.add(row)
    session.commit()
    return RedirectResponse(f"/business/data?co={co}&saved=1", status_code=303)


@router.post("/api/business/asp")
def save_asp(payload: dict = Body(...), session: Session = Depends(get_session)):
    """ASPs entered in the application simulator: {function id: value or null}."""
    for fn, v in (payload or {}).items():
        if fn in blocks.catalogue()["functions"]:
            op.set_input(session, "asp", fn, _num(str(v)) if v not in (None, "") else None)
    session.commit()
    return {"ok": True}


# ---- case analysis -----------------------------------------------------------------------------------------
def _case_ctx(session: Session, co: str) -> dict:
    key, label, _ = op.company(co)
    return {"co": key, "co_label": label, "companies": op.COMPANIES, "statuses": cases.STATUSES,
            "kinds": cases.NOTE_KINDS, "fields": cases.FIELDS, "fns": blocks.catalogue()["functions"],
            "fn_choices": sorted(((k, f.get("label", k)) for k, f in blocks.catalogue()["functions"].items()),
                                 key=lambda kv: kv[1].lower())}  # fmt: skip


@router.get("/business/cases", response_class=HTMLResponse)
def case_list(request: Request, co: str = "combined", session: Session = Depends(get_session)):
    c = _case_ctx(session, co)
    c["cases"] = session.scalars(select(Case).order_by(Case.updated_at.desc())).all()
    return templates.TemplateResponse(request, "business/cases.html", c)


@router.get("/business/cases/new", response_class=HTMLResponse)
def case_new(request: Request, fn: str = "", co: str = "combined", title: str = "", idea: str = "",
             shortlist: int | None = None, session: Session = Depends(get_session)):  # fmt: skip
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
    c.update(case=None, fn=fn if ctx else "", ctx=ctx, values=values, shortlist=item.id if item else None,
             title=title[:200] or (item.title if item else "") or (f"New {ctx['label']}" if ctx else ""))  # fmt: skip
    return templates.TemplateResponse(request, "business/case.html", c)


def _inputs(form) -> dict:
    return {k: str(form.get(k) or "").strip() for k, *_ in cases.FIELDS if str(form.get(k) or "").strip()}


@router.post("/business/cases")
async def case_create(request: Request, session: Session = Depends(get_session)):
    form = await request.form()
    fn = str(form.get("fn") or "") or None
    case = Case(title=str(form.get("title") or "").strip()[:200] or "Untitled case",
                fn=fn if fn in blocks.catalogue()["functions"] else None, inputs=_inputs(form))  # fmt: skip
    session.add(case)
    session.flush()
    item = (
        session.get(ShortlistItem, int(form.get("shortlist"))) if str(form.get("shortlist") or "").isdigit() else None
    )
    if item is not None:
        item.case_id = case.id
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
            ln.volume = pipeline._num(form.get(f"vol:{ln.id}"), int)
            ln.price = pipeline._num(form.get(f"price:{ln.id}"), float)
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
    c["fn_choices"] = sorted(used.items(), key=lambda kv: c["fns"].get(kv[0], {}).get("label", kv[0]).lower())
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
    return RedirectResponse("/business/capabilities#feedback", status_code=303)


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
    row = next((e for e in op.technology_fit(c["apps"]) if e["fn"] == fn), None)
    c.update(fn=fn, label=c["fns"][fn].get("label", fn), row=row, status=op.status_of(fn, c["mk"], op.company(co)[2]),
             ev={t: op.evidence(t).get(fn) for t in op.EVIDENCE_TOPICS}, topics=op.EVIDENCE_TOPICS,
             tech=op.technology().get(fn), comp=op.competition().get(fn), platforms=op.platforms_for(fn),
             hunt=op.hunt_for_function(c["apps"], fn)[:15], existing=quality.possible_existing(session, fn),
             need=next((g for g in op.gaps(c["apps"], c["asp"], c["vol"]) if g["fn"] == fn), None),
             rev=_rev(session), path_label=op.PATH_LABEL, prox_label=op.PROXIMITY_LABEL)  # fmt: skip
    c["verdicts"] = quality.VERDICTS
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
    form = await request.form()
    mpn, verdict = str(form.get("mpn") or "").strip(), str(form.get("verdict") or "")
    if fn in blocks.catalogue()["functions"] and mpn and verdict in ("yes", "no", "undo"):
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
    c.update(checks=quality.checks(c["apps"]), stats=quality.stats(session), queue=quality.queue(session, c["apps"]),
             rev=_rev(session), verdicts=quality.VERDICTS, ds_labels={k: v[0] for k, v in quality.datasets().items()},
             mappings=session.scalars(select(PartMapping).order_by(PartMapping.created_at.desc())).all())  # fmt: skip
    return templates.TemplateResponse(request, "business/quality.html", c)


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
def product_reports(request: Request, kind: str = "", tag: str = ""):
    """Pre-lim product ideas and reports: the list."""
    from app.services import reports as rp

    rows = [
        r for r in rp.reports() if (not kind or r.get("kind") == kind) and (not tag or tag in (r.get("tags") or []))
    ]
    tags = sorted({t for r in rp.reports() for t in r.get("tags") or []})
    ctx = {"rows": rows, "kinds": rp.KINDS, "statuses": rp.STATUSES, "kind": kind, "tag": tag, "tags": tags,
           "n_all": len(rp.reports())}  # fmt: skip
    return templates.TemplateResponse(request, "business/reports.html", ctx)


def _question_day(day: str) -> date | None:
    try:
        return date.fromisoformat(day) if day else None
    except ValueError:
        raise HTTPException(400, "Bad date") from None


@router.get("/business/reports/questions", response_class=HTMLResponse)
def report_questions(request: Request, day: str = "", session: Session = Depends(get_session)):
    """Questions asked on the reports, one list per day, reviewed for good questions and duplicates."""
    from app.services import reports as rp

    days = rp.question_days(session)
    d = _question_day(day) or (days[0][0] if days else datetime.now(UTC).date())
    ctx = {"days": days, "rv": rp.review(session, d), "statuses": rp.Q_STATUSES}
    return templates.TemplateResponse(request, "business/report_questions.html", ctx)


@router.get("/business/reports/questions.txt", response_class=PlainTextResponse)
def report_questions_text(day: str = "", session: Session = Depends(get_session)):
    from app.services import reports as rp

    return rp.review_text(rp.review(session, _question_day(day) or datetime.now(UTC).date()))


@router.post("/business/reports/questions/{qid:int}")
async def report_question_decide(request: Request, qid: int, session: Session = Depends(get_session)):
    from app.services import reports as rp

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


@router.get("/business/reports/{slug}", response_class=HTMLResponse)
def product_report(request: Request, slug: str, session: Session = Depends(get_session)):
    from app.services import reports as rp

    r = rp.report(slug)
    if r is None:
        raise HTTPException(404, "Report not found")
    ctx = {"r": r, "kinds": rp.KINDS, "statuses": rp.STATUSES, "body": f"business/reports/{slug}.html",
           "has_background": rp.has_background(slug), "questions": rp.questions(session, slug),
           "q_statuses": rp.Q_STATUSES}  # fmt: skip
    return templates.TemplateResponse(request, "business/report.html", ctx)


@router.get("/business/reports/{slug}/background", response_class=HTMLResponse)
def product_report_background(request: Request, slug: str):
    """The detail behind a report: the data tables and long-form notes kept out of the report itself."""
    from app.services import reports as rp

    r = rp.report(slug)
    if r is None or not rp.has_background(slug):
        raise HTTPException(404, "No background for this report")
    ctx = {"r": r, "kinds": rp.KINDS, "statuses": rp.STATUSES, "body": f"business/reports/{slug}.background.html",
           "background": True}  # fmt: skip
    return templates.TemplateResponse(request, "business/report.html", ctx)


@router.post("/business/reports/{slug}/ask")
async def product_report_ask(request: Request, slug: str, session: Session = Depends(get_session)):
    from app.services import reports as rp

    if rp.report(slug) is None:
        raise HTTPException(404, "Report not found")
    form = await request.form()
    text = str(form.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "Write a question first")
    rp.ask(session, slug, text, str(form.get("author") or ""))
    return RedirectResponse(f"/business/reports/{slug}?asked=1#questions", status_code=303)
