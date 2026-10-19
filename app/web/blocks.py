"""Block-diagram generator pages and API."""

import json
from collections import Counter

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import BlockDiagram, BlockFeedback
from app.services import blocks, refdesigns, schematic
from app.services import opportunity as op
from app.web.routes import templates

router = APIRouter()


@router.get("/blocks", response_class=HTMLResponse)
def index(request: Request, market: str = "", source: str = "", variants: bool = False,
          session: Session = Depends(get_session)):  # fmt: skip
    """Application library: reference architectures with facets for end market and source; architectures that may
    describe the same application are flagged as possible variants (never merged)."""
    designs = session.scalars(select(BlockDiagram).order_by(BlockDiagram.updated_at.desc())).all()
    groups = blocks.template_cards(session)
    allcards = [c for _, items in groups for c in items]

    def keep(c):
        return (
            (not market or c["market"] == market)
            and (not source or c["source"] == source)
            and (not variants or bool(c["variant"]))
        )

    cards = [(cat, [c for c in items if keep(c)]) for cat, items in groups]

    def facet(key):
        return sorted(Counter(c[key] for c in allcards).items(), key=lambda kv: (-kv[1], kv[0]))

    ctx = {"designs": designs, "cards": [(k, v) for k, v in cards if v], "n_all": len(allcards),
           "n_shown": sum(len(v) for _, v in cards), "markets": facet("market"), "sources": facet("source"),
           "market": market, "source": source, "variants": variants,
           "n_variant": sum(1 for c in allcards if c["variant"]), "n_groups": len(blocks.variant_groups())}  # fmt: skip
    return templates.TemplateResponse(request, "blocks/index.html", ctx)


@router.get("/blocks/coverage", response_class=HTMLResponse)
def coverage(request: Request, session: Session = Depends(get_session)):
    cat = blocks.catalogue()
    return templates.TemplateResponse(
        request, "blocks/coverage.html", {"cat": cat, "counts": blocks.counts(session), "uses": blocks.function_uses()}
    )


@router.get("/blocks/new", response_class=HTMLResponse)
def new(request: Request, template: int | None = None, session: Session = Depends(get_session)):
    tpl = blocks.templates()[template] if template is not None and 0 <= template < len(blocks.templates()) else None
    return _editor(request, session, None, tpl)


@router.get("/blocks/{design_id:int}", response_class=HTMLResponse)
def edit(request: Request, design_id: int, session: Session = Depends(get_session)):
    d = session.get(BlockDiagram, design_id)
    if d is None:
        raise HTTPException(404, "Block diagram not found")
    return _editor(request, session, d, None)


def _editor(request, session, design, tpl):
    info = {"id": None, "name": blocks.display_name(tpl) if tpl else "", "data": None}
    if design:
        info = {"id": design.id, "name": design.name, "data": design.data}
    return templates.TemplateResponse(
        request,
        "blocks/editor.html",
        {
            "design": info,
            "template": tpl,
            "catalogue": blocks.catalogue(),
            "counts": blocks.counts(session),
            "requirements": blocks.requirements(session),
            "help": blocks.question_help(),
            "templates_": blocks.templates(),
        },
    )


@router.post("/blocks/{design_id}/delete")
def delete(design_id: int, session: Session = Depends(get_session)):
    d = session.get(BlockDiagram, design_id)
    if d is not None:
        session.delete(d)
        session.commit()
    return RedirectResponse("/blocks", status_code=303)


@router.get("/api/blocks/parts")
def parts(fn: str, q: str = "", req: str = "", lite: bool = False, session: Session = Depends(get_session)):
    """Parts for one function. lite=1 returns only the best picks per manufacturer (the overview list loads these
    when a block is opened); the full list comes with the clicked block."""
    try:
        answers = json.loads(req) if req else {}
    except ValueError:
        answers = {}
    out = blocks.parts_for(session, fn, q, answers)
    if lite:
        out = {**out, "manufacturers": [{**m, "all": []} for m in out["manufacturers"]]}
    return out


@router.post("/api/blocks/counts")
def counts(payload: dict = Body(default={}), session: Session = Depends(get_session)):
    return blocks.counts(session, payload.get("req") or {})


@router.post("/api/blocks/schematic")
def to_schematic(payload: dict = Body(...), session: Session = Depends(get_session)):
    """Convert to schematic: {data, scope: {kind: all|group|block, group, block}, answers, draw, title}.
    Without draw: the design-rule check and questions; with draw: also the sheets and the external parts list."""
    data, scope, answers = payload.get("data") or {}, payload.get("scope") or {}, payload.get("answers") or {}
    if payload.get("draw"):
        return schematic.draw(session, data, scope, answers, str(payload.get("title") or "")[:200])
    return schematic.check(session, data, scope, answers)


@router.post("/api/blocks/designs")
def create(payload: dict = Body(...), session: Session = Depends(get_session)):
    d = BlockDiagram(name=_name(payload), data=payload.get("data") or {})
    session.add(d)
    session.commit()
    return {"id": d.id, "name": d.name}


@router.put("/api/blocks/designs/{design_id}")
def update(design_id: int, payload: dict = Body(...), session: Session = Depends(get_session)):
    d = session.get(BlockDiagram, design_id)
    if d is None:
        raise HTTPException(404, "Block diagram not found")
    d.name, d.data = _name(payload), payload.get("data") or {}
    session.commit()
    return {"id": d.id, "name": d.name}


def _name(payload: dict) -> str:
    return (str(payload.get("name") or "").strip() or "Untitled block diagram")[:200]


# --- feedback: kept for discussion before a change is made -------------------------------------------
FEEDBACK_STATUS = {"open": "To review", "agreed": "Agreed, to do", "rejected": "Not doing", "done": "Done"}


@router.post("/api/blocks/feedback")
def add_feedback(payload: dict = Body(...), session: Session = Depends(get_session)):
    msg = str(payload.get("message") or "").strip()
    if not msg:
        raise HTTPException(400, "Empty feedback")
    fb = BlockFeedback(
        diagram_id=payload.get("diagram_id"),
        diagram_name=(str(payload.get("diagram_name") or "") or None),
        target=(str(payload.get("target") or "")[:200] or None),
        message=msg[:4000],
    )
    session.add(fb)
    session.commit()
    return {"id": fb.id}


@router.get("/api/blocks/feedback")
def list_feedback(diagram_id: int | None = None, session: Session = Depends(get_session)):
    stmt = select(BlockFeedback).order_by(BlockFeedback.created_at.desc())
    if diagram_id is not None:
        stmt = stmt.where(BlockFeedback.diagram_id == diagram_id)
    return [
        {"id": f.id, "target": f.target, "message": f.message, "status": f.status, "diagram": f.diagram_name,
         "created": f.created_at.strftime("%Y-%m-%d") if f.created_at else ""}
        for f in session.scalars(stmt)
    ]  # fmt: skip


@router.get("/blocks/feedback", response_class=HTMLResponse)
def feedback_page(request: Request, session: Session = Depends(get_session)):
    rows = session.scalars(select(BlockFeedback).order_by(BlockFeedback.created_at.desc())).all()
    order = list(FEEDBACK_STATUS)
    rows = sorted(rows, key=lambda f: order.index(f.status) if f.status in order else 9)
    return templates.TemplateResponse(request, "blocks/feedback.html", {"rows": rows, "statuses": FEEDBACK_STATUS})


@router.post("/blocks/feedback/{fb_id}")
def update_feedback(
    fb_id: int, status: str = Form(""), delete: str = Form(""), session: Session = Depends(get_session)
):
    fb = session.get(BlockFeedback, fb_id)
    if fb is not None:
        if delete:
            session.delete(fb)
        elif status in FEEDBACK_STATUS:
            fb.status = status
        session.commit()
    return RedirectResponse("/blocks/feedback", status_code=303)


@router.get("/blocks/feedback.txt", response_class=PlainTextResponse)
def feedback_text(session: Session = Depends(get_session)):
    rows = session.scalars(select(BlockFeedback).where(BlockFeedback.status.in_(["open", "agreed"]))).all()
    lines = ["Block-diagram feedback to discuss (is a change warranted?):"]
    for f in rows:
        where = " / ".join(x for x in (f.diagram_name, f.target) if x)
        lines.append(f"- [{FEEDBACK_STATUS.get(f.status, f.status)}] {where + ': ' if where else ''}{f.message}")
    return "\n".join(lines) + "\n"


@router.get("/reference-designs", response_class=HTMLResponse)
def reference_designs(request: Request, q: str = "", vendor: str = "", market: str = "", fn: str = "",
                      iso: bool = False, docs: bool = False, page: int = 1,
                      session: Session = Depends(get_session)):  # fmt: skip
    """Manufacturers' public reference designs, searchable; each function is marked portfolio / gap for us."""
    rows = refdesigns.search(q, vendor, market, fn, iso, docs)
    per = 50
    pages = max(1, -(-len(rows) // per))
    page = min(max(page, 1), pages)
    mk = op.makers(session)
    mine = op.company("combined")[2]
    fns = {f for d in rows[(page - 1) * per : page * per] for f in d.get("functions") or []}
    facets = refdesigns.facets(rows)
    fns |= {f for f, _ in facets["function"]}
    ctx = {"rows": rows[(page - 1) * per : page * per], "n": len(rows), "n_all": len(refdesigns.designs()),
           "page": page, "pages": pages, "facets": facets, "sources": refdesigns.sources(),
           "q": q, "vendor": vendor, "market": market, "fn": fn, "iso": iso, "docs": docs,
           "status": {f: op.status_of(f, mk, mine) for f in fns},
           "label": {f: refdesigns.function_label(f) for f in fns}, "doc_labels": refdesigns.DOC_LABELS}  # fmt: skip
    return templates.TemplateResponse(request, "blocks/reference_designs.html", ctx)
