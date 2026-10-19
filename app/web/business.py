"""Business opportunity pages: overview (pipeline), applications (coverage + simulator), attach, gaps & ranking,
TAM data."""

from collections import Counter

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Case, CaseNote
from app.services import blocks, cases
from app.services import opportunity as op
from app.web.routes import templates

router = APIRouter()
templates.env.globals["bo_status_help"] = op.STATUS_HELP
templates.env.globals["bo_help"] = op.explanations
_CROWD = {"low": 0, "medium": 1, "high": 2}


def _ctx(session: Session, co: str) -> dict:
    key, label, mine = op.company(co)
    mk = op.makers(session)
    apps = op.with_status(op.applications(), mk, mine)
    asp, vol = op.inputs(session)
    return {"co": key, "co_label": label, "companies": op.COMPANIES, "apps": apps, "asp": asp, "vol": vol, "mk": mk,
            "status_label": op.STATUS_LABEL, "fns": blocks.catalogue()["functions"],
            "crowding_label": op.CROWDING_LABEL}  # fmt: skip


@router.get("/business", response_class=HTMLResponse)
def overview(request: Request, co: str = "combined", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    c["ov"] = op.overview(c["apps"], c["asp"], c["vol"])
    c["top_gaps"] = op.gaps(c["apps"], c["asp"], c["vol"])[:5]
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
def attach(request: Request, fn: str = "", co: str = "combined", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    used = Counter(fn for a in c["apps"] for fn in {p.fn for p in a.positions if p.status == "supported"})
    c["anchors"] = sorted(used.items(), key=lambda kv: (-kv[1], c["fns"].get(kv[0], {}).get("label", kv[0])))
    c["fn"] = fn if fn in used else ""
    c["result"] = op.attach(c["apps"], fn) if c["fn"] else None
    return templates.TemplateResponse(request, "business/attach.html", c)


@router.get("/business/gaps", response_class=HTMLResponse)
def gaps(request: Request, co: str = "combined", sort: str = "reach", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    rows = op.gaps(c["apps"], c["asp"], c["vol"])
    keys = {
        "reach": lambda e: (-e["reach"], -e["adjacent"]),
        "adjacency": lambda e: (-e["adjacency"], -e["reach"]),
        "positions": lambda e: (-e["positions"], -e["reach"]),
        "tam": lambda e: (-e["tam"], -e["reach"]),
        "crowding": lambda e: (_CROWD.get((e["competition"] or {}).get("crowding"), 3), -e["reach"]),
    }
    c["sort"] = sort if sort in keys else "reach"
    c["rows"] = sorted(rows, key=keys[c["sort"]])
    c["portfolio"] = op.reach_of_portfolio(c["apps"])[:15]
    return templates.TemplateResponse(request, "business/gaps.html", c)


@router.get("/business/markets", response_class=HTMLResponse)
def markets(request: Request, co: str = "combined", view: str = "all", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    m = op.markets(session, c["apps"], op.company(co)[2])
    c["view"] = view if view in ("all", "requalify", "multi") else "all"
    rows = m["rows"]
    if c["view"] == "requalify":
        rows = [e for e in rows if e["requalify"]]
    elif c["view"] == "multi":
        rows = [e for e in rows if e["n_markets"] > 1]
    c.update(
        markets=m["markets"],
        per_market=m["apps_per_market"],
        rows=rows,
        n_requalify=sum(e["requalify"] for e in m["rows"]),
        n_multi=sum(e["n_markets"] > 1 for e in m["rows"]),
    )
    return templates.TemplateResponse(request, "business/markets.html", c)


@router.get("/business/technology", response_class=HTMLResponse)
def technology(request: Request, co: str = "combined", view: str = "all", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    rows = op.technology_fit(c["apps"])
    views = {
        "all": lambda e: True,
        "develop": lambda e: (e["proximity"] or 0) >= 2,
        "low_attach": lambda e: e["adjacency"] < 0.5,
        "chips": lambda e: e["status"] == "na",
    }
    c["view"] = view if view in views else "all"
    c["counts"] = {k: sum(map(f, rows)) for k, f in views.items()}
    c["rows"] = [e for e in rows if views[c["view"]](e)]
    c.update(prox_label=op.PROXIMITY_LABEL, prox_weight=op.PROXIMITY_WEIGHT, crowd_weight=op.CROWDING_WEIGHT,
             n_background=sum(a.background for a in c["apps"]))  # fmt: skip
    return templates.TemplateResponse(request, "business/technology.html", c)


@router.get("/business/method", response_class=HTMLResponse)
def method(request: Request, co: str = "combined", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    c.update(src=op.sources(c["apps"]), help=op.explanations(), prox_label=op.PROXIMITY_LABEL,
             prox_weight=op.PROXIMITY_WEIGHT, crowd_weight=op.CROWDING_WEIGHT)  # fmt: skip
    return templates.TemplateResponse(request, "business/method.html", c)


@router.get("/business/data", response_class=HTMLResponse)
def data(request: Request, co: str = "combined", session: Session = Depends(get_session)):
    c = _ctx(session, co)
    in_scope = {p.fn for a in c["apps"] for p in a.positions if p.status in op.IN_SCOPE}
    c["asp_fns"] = sorted(in_scope, key=lambda f: c["fns"].get(f, {}).get("label", f))
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
    for k, v in form.items():
        if k.startswith("asp:"):
            op.set_input(session, "asp", k[4:], _num(str(v)))
        elif k.startswith("vol:"):
            op.set_input(session, "volume", k[4:], _num(str(v)))
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
def case_new(request: Request, fn: str = "", co: str = "combined", session: Session = Depends(get_session)):
    c = _case_ctx(session, co)
    ctx = cases.context(session, fn, co)
    c.update(case=None, fn=fn if ctx else "", ctx=ctx, values=cases.prefill(ctx),
             title=f"New {ctx['label']}" if ctx else "")  # fmt: skip
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
    c.update(case=case, fn=case.fn or "", ctx=ctx, values=case.inputs or {}, title=case.title,
             brief=cases.brief(case, ctx))  # fmt: skip
    return templates.TemplateResponse(request, "business/case.html", c)


@router.get("/business/cases/{case_id:int}/brief.md", response_class=PlainTextResponse)
def case_brief(case_id: int, co: str = "combined", session: Session = Depends(get_session)):
    case = _case(session, case_id)
    return PlainTextResponse(cases.brief(case, cases.context(session, case.fn, co)), media_type="text/markdown")


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
    elif act == "delete":
        session.delete(case)
        session.commit()
        return RedirectResponse("/business/cases", status_code=303)
    session.commit()
    return RedirectResponse(f"/business/cases/{case.id}#{act}", status_code=303)
