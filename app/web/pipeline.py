"""Guided path from a part (with or without a cross) to a prelim case: /pipeline/new?part=<id>&our=<id>.

The last step does not create a business case: it saves the request (the volume asked accrues per part) and sends a
prelim case to the shared review queue (POST /business/schedule), where the AI schedules a check of whether there is
a real market behind it. Adding the lines to an existing business case stays possible."""

from copy import deepcopy

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import BlockDiagram, Case, Part, PipelineDraft
from app.services import blocks, pricing
from app.services import pipeline as pl
from app.web.routes import CATEGORY_LABELS, DEFAULT_MAX_DEVIATIONS, _part_context, templates

router = APIRouter()
STEP_KEYS = [k for k, _ in pl.STEPS]


def _draft(session: Session, draft_id: int) -> PipelineDraft:
    d = session.get(PipelineDraft, draft_id)
    if d is None:
        raise HTTPException(404, "Not found")
    return d


@router.get("/pipeline/new", response_class=HTMLResponse)
def pipeline_new_confirm(request: Request, part: int, our: int | None = None, session: Session = Depends(get_session)):
    """A link (or a browser prefetching it) only shows the button; the draft is created by the POST below."""
    p = session.get(Part, part)
    if p is None:
        raise HTTPException(404, "Part not found")
    ctx = {"part": p, "our": session.get(Part, our) if our else None}
    return templates.TemplateResponse(request, "pipeline_start.html", ctx)


@router.post("/pipeline/new")
def pipeline_new(part: int = Form(...), our: int | None = Form(None), session: Session = Depends(get_session)):
    try:
        state = pl.start(session, part, our)
    except ValueError:
        raise HTTPException(404, "Part not found") from None
    d = PipelineDraft(state=state)
    session.add(d)
    session.commit()
    return RedirectResponse(f"/pipeline/{d.id}?step=part", status_code=303)


def _crosses(session: Session, part: Part) -> list[dict]:
    """The best crosses for a competitor part, ranked as on its page (best first)."""
    ctx = _part_context(session, part, False, "", "auto", "", DEFAULT_MAX_DEVIATIONS, "", False)
    rank = ctx.get("ranked") or {}
    rows = sorted(ctx["rows"], key=lambda rv: rank.get(rv[0].candidate.id, 99))
    return [{"id": r.candidate.id, "mpn": r.candidate.mpn, "category": CATEGORY_LABELS.get(v.category, v.category),
             "rank": rank.get(r.candidate.id)} for r, v in rows[:15]]  # fmt: skip


@router.get("/pipeline/{draft_id:int}", response_class=HTMLResponse)
def pipeline_page(request: Request, draft_id: int, step: str = "", session: Session = Depends(get_session)):
    d = _draft(session, draft_id)
    s = d.state
    if step == "send" and s.get("prelim"):
        return _send_page(request, session, d)
    if step not in STEP_KEYS:
        step = (
            "case"
            if s.get("lines") and any(x.get("volume") or x.get("price") for x in s["lines"])
            else (
                "numbers"
                if s.get("lines")
                else "design"
                if s.get("diagram_id")
                else "application"
                if s.get("fn")
                else "part"
            )
        )
    c = {"d": d, "s": s, "step": step, "steps": pl.STEPS, "role_label": pl.ROLE_LABEL}
    if step == "part" and s.get("competitor"):
        c["crosses"] = _crosses(session, session.get(Part, s["competitor"]["id"]))
    if step == "application":
        c["apps"] = pl.applications_for(session, s.get("fn"))
        c["found"] = pl.search_applications(session, s.get("description") or "", s.get("fn"))
    if s.get("diagram_id") and step in ("design", "numbers"):
        diagram = session.get(BlockDiagram, s["diagram_id"])
        c["rows"] = pl.design_rows(session, diagram.data if diagram else {}, s.get("fn"))
        if step == "design":
            c["suggest"] = pl.suggestions(session, c["rows"])
    if step == "numbers":
        c["revenue"] = {x["key"]: pl.revenue(x) for x in s.get("lines") or []}
        c["total"] = sum(v for v in c["revenue"].values() if v)
        c["suggest"] = _price_hint(session, s)
    if step == "case":
        c["cases"] = list(session.scalars(select(Case).where(Case.status != "merged").order_by(Case.updated_at.desc())))
        c["total"] = sum(pl.revenue(x) or 0 for x in s.get("lines") or [] if x.get("include"))
        c["volume"] = pl.request_volume(s)
        c["sent"] = request.query_params.get("sent") == "1"
    c["mpn"] = (s.get("competitor") or s.get("part") or {}).get("mpn")
    c["requested"] = pl.requested(session, c["mpn"])
    return templates.TemplateResponse(request, "pipeline.html", c)


@router.get("/pipeline/apps.json")
def pipeline_apps(q: str = "", fn: str = "", session: Session = Depends(get_session)):
    """The top 10 diagrams for an application description as it is typed (library and saved diagrams)."""
    return JSONResponse(pl.search_applications(session, q[:300], fn or None))


def _send_page(request: Request, session: Session, d: PipelineDraft):
    """The prelim case, ready for the review queue: a form to POST /business/schedule, sent by the page itself the
    first time it opens (a button otherwise)."""
    s = d.state
    p = s["prelim"]
    auto = not p.get("shown")
    if auto:
        s = deepcopy(s)
        s["prelim"]["shown"] = True
        d.state = s
        session.commit()
    ctx = {"d": d, "s": s, "p": p, "auto": auto, "next": f"/pipeline/{d.id}?step=case&sent=1"}
    return templates.TemplateResponse(request, "pipeline_send.html", ctx)


def _price_hint(session: Session, s: dict) -> str | None:
    """The competitor part's distributor price at 1,000 pieces, when DigiKey is connected (else nothing)."""
    comp = s.get("competitor")
    if not comp or not pricing.enabled():
        return None
    try:
        pq = pricing.quote_for(session, session.get(Part, comp["id"]))
        p = pricing.price_at(pq, 1000)
        session.commit()
    except pricing.DigiKeyError:
        return None
    return f"{comp['mpn']}: ${p[0]:.2f} at 1,000 pcs (DigiKey, {p[1]})" if p else None


@router.post("/pipeline/{draft_id:int}")
async def pipeline_step(request: Request, draft_id: int, session: Session = Depends(get_session)):
    d = _draft(session, draft_id)
    s = deepcopy(d.state)  # JSON columns: edit a copy, so the change is saved
    form = await request.form()
    act = str(form.get("act") or "")
    nxt = None
    if act == "ours":
        our = str(form.get("our") or "")
        p = session.get(Part, int(our)) if our.isdigit() else None
        s["ours"] = {"id": p.id, "mpn": p.mpn, "manufacturer": p.manufacturer.name} if p and p.is_reference else None
        if s.get("diagram_id"):  # keep the diagram in step: the cross block gets the new part
            diagram = session.get(BlockDiagram, s["diagram_id"])
            if diagram:
                data = deepcopy(diagram.data)
                for g in data.get("groups", []):
                    for b in g.get("blocks", []):
                        if b.get("fn") == s.get("fn"):
                            b["part"] = s["ours"]["mpn"] if s["ours"] else None
                diagram.data = data
        nxt = "application"
    elif act in ("template", "saved", "new_diagram"):
        if form.get("description") is not None:
            s["description"] = str(form.get("description") or "").strip()[:1000]
        our_mpn = (s.get("ours") or {}).get("mpn")
        name_part = our_mpn or (s.get("competitor") or {}).get("mpn", "")
        if act == "template":
            i = int(form.get("i") or -1)
            if not 0 <= i < len(blocks.templates()):
                raise HTTPException(400, "Unknown application")
            t = blocks.templates()[i]
            data, app = pl.diagram_from_template(t, s.get("fn"), our_mpn), blocks.display_name(t)
        elif act == "saved":
            src = session.get(BlockDiagram, int(form.get("id") or 0))
            if src is None:
                raise HTTPException(400, "Unknown diagram")
            data, app = deepcopy(src.data), src.name
            for g in data.get("groups", []):
                for b in g.get("blocks", []):
                    if b.get("fn") == s.get("fn") and not b.get("part"):
                        b["part"] = our_mpn
        else:
            app = (str(form.get("name") or "").strip() or s.get("description") or "")[:150] \
                or f"{s.get('fn_label')} application"
            data = pl.new_diagram(s.get("fn"), s.get("fn_label") or "Design", our_mpn)
        diagram = BlockDiagram(name=f"{app} – {name_part}"[:200], data=data)
        session.add(diagram)
        session.flush()
        s.update(diagram_id=diagram.id, application=app, lines=[])
        nxt = "design"
    elif act == "pick_all":
        diagram = session.get(BlockDiagram, s.get("diagram_id") or 0)
        if diagram:
            data = deepcopy(diagram.data)
            s["picked"] = pl.pick_all(session, data)
            diagram.data = data
        nxt = "design"
    elif act == "use":  # a suggested part of ours into one block of the design
        diagram = session.get(BlockDiagram, s.get("diagram_id") or 0)
        mpn, block = str(form.get("mpn") or "").strip()[:100], str(form.get("block") or "")
        if diagram and mpn:
            data = deepcopy(diagram.data)
            for g in data.get("groups", []):
                for b in g.get("blocks", []):
                    if b.get("id") == block and not b.get("part"):
                        b["part"] = mpn
            diagram.data = data
        nxt = "design"
    elif act == "design_done":
        diagram = session.get(BlockDiagram, s.get("diagram_id") or 0)
        rows = pl.design_rows(session, diagram.data if diagram else {}, s.get("fn"))
        s["lines"] = pl.build_lines(s, rows)
        nxt = "numbers"
    elif act == "numbers":
        if not s.get("lines"):
            s["lines"] = pl.build_lines(s, [])
        pl.apply_numbers(s, form)
        nxt = "case"
    elif act == "finish":
        if not s.get("lines"):
            s["lines"] = pl.build_lines(s, [])
        s["customers"], s["markets"] = pl.form_list(form, "customer"), pl.form_list(form, "market")
        if form.get("description") is not None:
            s["description"] = str(form.get("description") or "").strip()[:1000]
        pl.record_request(session, s, f"prelim:{d.id}")
        if str(form.get("target") or "new") == "existing":  # the lines into a business case that already exists
            case = pl.finish(session, s, form)
            d.case_id = case.id
            d.state = s
            session.commit()
            return RedirectResponse(f"/business/cases/{case.id}", status_code=303)
        mpn = (s.get("competitor") or s.get("part") or {}).get("mpn", "")
        title = str(form.get("title") or "").strip()[:200] or f"Prelim case: {mpn}"
        s["prelim"] = {"title": title, "note": pl.prelim_note(s), "part": mpn, "volume": pl.request_volume(s),
                       "source": f"prelim:{d.id}"}  # fmt: skip
        d.state = s
        session.commit()
        return RedirectResponse(f"/pipeline/{d.id}?step=send", status_code=303)
    else:
        raise HTTPException(400, "Unknown step")
    d.state = s
    session.commit()
    return RedirectResponse(f"/pipeline/{d.id}?step={nxt}", status_code=303)
