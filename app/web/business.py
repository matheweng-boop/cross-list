"""Business opportunity pages: overview (pipeline), applications (coverage + simulator), attach, gaps & ranking,
TAM data."""

from collections import Counter

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Case, CaseNote, DataReview, PartMapping, TechFeedback
from app.services import blocks, cases, quality
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
    for e in c["rows"]:
        e["hunt"] = op.hunt_for_function(c["apps"], e["fn"])[:8]
        e["path"] = op.evidence("path").get(e["fn"])
    c["portfolio"] = op.reach_of_portfolio(c["apps"])[:15]
    c["path_label"] = op.PATH_LABEL
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
        "short": lambda e: (e["path"] or {}).get("path") in ("exists", "variant"),
        "build": lambda e: (e["path"] or {}).get("path") == "new_design",
        "acquire": lambda e: (e["path"] or {}).get("path") == "new_capability",
    }
    c["view"] = view if view in views else "all"
    c["counts"] = {k: sum(map(f, rows)) for k, f in views.items()}
    c["rows"] = [e for e in rows if views[c["view"]](e)]
    for e in c["rows"]:
        e["hunt"] = op.hunt_for_function(c["apps"], e["fn"])[:8]
        e["platforms"] = op.platforms_for(e["fn"])
        e["ev"] = {t: op.evidence(t).get(e["fn"]) for t in ("patents", "foundry", "competitor_tech")}
    c["path_label"] = op.PATH_LABEL
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
    c.update(techs=techs, fit=fit, rev=_rev(session), plats=op.capabilities())
    return templates.TemplateResponse(request, "business/explore.html", c)
