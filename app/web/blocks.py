"""Block-diagram generator pages and API."""

import json
from collections import Counter

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import AreaRequest, BlockDiagram, BlockFeedback
from app.services import blocks, prelim, refdesigns, schematic, vocab
from app.services import opportunity as op
from app.web.routes import templates

router = APIRouter()


@router.get("/blocks", response_class=HTMLResponse)
def index(request: Request, market: str = "", source: str = "", variants: bool = False, verified: str = "",
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
            and (verified not in ("yes", "no") or bool(c["verified"]) == (verified == "yes"))
        )

    cards = [(cat, [c for c in items if keep(c)]) for cat, items in groups]

    def facet(key):
        return sorted(Counter(c[key] for c in allcards).items(), key=lambda kv: (-kv[1], kv[0]))

    shown = [c for _, v in cards for c in v]
    focus = [(k, label, [c for c in shown if k in c["focus"]]) for k, label in blocks.FOCUS_AREAS.items()]
    other = [(k, [c for c in v if not c["focus"]]) for k, v in cards]
    ctx = {"designs": designs, "cards": [(k, v) for k, v in cards if v], "n_all": len(allcards),
           "focus": focus, "other": [(k, v) for k, v in other if v],
           "asked": request.query_params.get("asked") == "1",
           "n_shown": sum(len(v) for _, v in cards), "markets": facet("market"), "sources": facet("source"),
           "market": market, "source": source, "variants": variants, "verified": verified,
           "n_verified": sum(1 for c in allcards if c["verified"]),
           "n_variant": sum(1 for c in allcards if c["variant"]), "n_groups": len(blocks.variant_groups())}  # fmt: skip
    from app.services import library

    ctx["deep_dives"] = library.topics()  # owner, 23 Oct 2026: the Systems library sits with the applications
    return templates.TemplateResponse(request, "blocks/index.html", ctx)


@router.post("/blocks/area-request")
def area_request(area: str = Form(""), why: str = Form(""), author: str = Form(""),
                 session: Session = Depends(get_session)):  # fmt: skip
    """Ask for another application area in the library; reviewed in Requests & reviews and in the daily inbox."""
    area = " ".join(area.split())[:200]
    if not area:
        raise HTTPException(400, "Name the area")
    session.add(AreaRequest(area=area, why=why.strip()[:2000] or None, author=author.strip()[:100] or None))
    session.commit()
    return RedirectResponse("/blocks?asked=1#request-area", status_code=303)


AREA_STATUSES = {"new": "New", "planned": "Planned", "done": "Added", "declined": "Declined"}


@router.get("/blocks/area-requests", response_class=HTMLResponse)
def area_requests(request: Request, session: Session = Depends(get_session)):
    rows = session.scalars(select(AreaRequest).order_by(AreaRequest.created_at.desc())).all()
    ctx = {"rows": rows, "statuses": AREA_STATUSES}
    return templates.TemplateResponse(request, "blocks/area_requests.html", ctx)


@router.post("/blocks/area-requests/{req_id:int}")
def area_request_status(req_id: int, status: str = Form(...), session: Session = Depends(get_session)):
    row = session.get(AreaRequest, req_id)
    if row is None:
        raise HTTPException(404)
    if status not in AREA_STATUSES:
        raise HTTPException(400, "Unknown status")
    row.status = status
    session.commit()
    return RedirectResponse("/blocks/area-requests", status_code=303)


@router.get("/blocks/coverage", response_class=HTMLResponse)
def coverage(request: Request, session: Session = Depends(get_session)):
    cat = blocks.catalogue()
    return templates.TemplateResponse(
        request, "blocks/coverage.html", {"cat": cat, "counts": blocks.counts(session), "uses": blocks.function_uses()}
    )


def _place(data: dict | None, name: str, place: str, fn: str, design_id: int | None = None) -> dict:
    """The editor's design with a part placed in its function's block (or a new frame): the walk-through's
    "Add to an application". Nothing is saved until the person presses Save."""
    fn = fn if fn in blocks.catalogue()["functions"] else ""
    data, where = blocks.placed(data, fn or None, place[:100])
    return {"id": design_id, "name": name[:200], "data": data,
            "prefill": f"{place[:100]} placed in {where}: press Save to keep it"}  # fmt: skip


@router.get("/blocks/new", response_class=HTMLResponse)
def new(request: Request, template: int | None = None, case: str = "", library: str = "", bare: bool = False,
        place: str = "", fn: str = "", bg: int | None = None, name: str = "", diagram: str = "",
        session: Session = Depends(get_session)):  # fmt: skip
    if diagram and template is None:  # a library diagram by its name: links stay right when diagrams are added
        template = next((i for i, t in enumerate(blocks.templates()) if t.get("name") == diagram), None)
    if place.strip():  # a part to place: in a library or background diagram, or in a new diagram of its own
        from app.services import pipeline as pl

        place = place.strip()
        lib, back = blocks.templates(), blocks.background_templates()
        t = (lib[template] if template is not None and 0 <= template < len(lib)
             else back[bg] if bg is not None and 0 <= bg < len(back) else None)  # fmt: skip
        if t is not None:
            info = _place(pl.diagram_from_template(t, None, None), blocks.display_name(t), place, fn)
        else:
            known = fn in blocks.catalogue()["functions"]
            start = pl.new_diagram(fn, vocab.fn_label(fn), None) if known else {"groups": [], "links": []}
            info = _place(start, name.strip() or f"New design with {place}", place, fn)
        return _editor(request, session, None, None, None, bare, info)
    if case:  # the customer diagram of a preliminary case, opened as an unsaved design
        c = prelim.raw(case) or {}
        if not c.get("diagram"):
            raise HTTPException(404, "This case has no block diagram")
        return _editor(request, session, None, {"name": c["title"], **c["diagram"]}, None, bare)
    if library:  # a technical-library topic's block diagram, opened as an unsaved design
        from app.services import library as lib

        d = (lib.topic(library) or {}).get("block_diagram")
        if not d:
            raise HTTPException(404, "This topic has no block diagram")
        return _editor(request, session, None, d, None, bare)
    tpl = blocks.templates()[template] if template is not None and 0 <= template < len(blocks.templates()) else None
    return _editor(request, session, None, tpl, template if tpl else None, bare)


@router.post("/blocks/verify")
def verify(i: int = Form(...), on: str = Form("1"), author: str = Form(""), note: str = Form(""),
           bare: str = Form(""), session: Session = Depends(get_session)):  # fmt: skip
    """Mark a library architecture as technically verified, or back to entered."""
    if not 0 <= i < len(blocks.templates()):
        raise HTTPException(404, "Application not found")
    blocks.set_verified(session, i, on == "1", author, note)
    return RedirectResponse(f"/blocks/new?template={i}{'&bare=1' if bare else ''}#bk-verify", status_code=303)


@router.get("/blocks/{design_id:int}", response_class=HTMLResponse)
def edit(request: Request, design_id: int, bare: bool = False, place: str = "", fn: str = "",
         session: Session = Depends(get_session)):  # fmt: skip
    d = session.get(BlockDiagram, design_id)
    if d is None:
        raise HTTPException(404, "Block diagram not found")
    if place.strip():  # extend a saved diagram with a part (saved over it only when the person presses Save)
        return _editor(request, session, None, None, None, bare, _place(d.data, d.name, place.strip(), fn, d.id))
    return _editor(request, session, d, None, None, bare)


def _editor(request, session, design, tpl, tpl_i=None, bare=False, info=None):
    info = info or {"id": None, "name": blocks.display_name(tpl) if tpl else "", "data": None}
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
            "tpl_i": tpl_i,
            "verified": blocks.verifications(session).get(blocks.verify_key(tpl)) if tpl else None,
            "bare": bare,
        },
    )


@router.post("/blocks/{design_id}/delete")
def delete(design_id: int, session: Session = Depends(get_session)):
    d = session.get(BlockDiagram, design_id)
    if d is None:
        raise HTTPException(404, "Block diagram not found")
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


def _diagram(payload: dict) -> dict:
    """The diagram to store: it must have its groups list (an empty object would open as a blank, broken editor)."""
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("groups"), list):
        raise HTTPException(400, "Nothing to save: the diagram has no blocks data")
    return data


@router.post("/api/blocks/designs")
def create(payload: dict = Body(...), session: Session = Depends(get_session)):
    d = BlockDiagram(name=_name(payload), data=_diagram(payload))
    session.add(d)
    session.commit()
    return {"id": d.id, "name": d.name}


@router.put("/api/blocks/designs/{design_id}")
def update(design_id: int, payload: dict = Body(...), session: Session = Depends(get_session)):
    d = session.get(BlockDiagram, design_id)
    if d is None:
        raise HTTPException(404, "Block diagram not found")
    d.name, d.data = _name(payload), _diagram(payload)
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
    if fb is None:
        raise HTTPException(404, "Feedback not found")
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
                      iso: bool = False, docs: bool = False, page: int = 1, view: str = "", atype: str = "",
                      sub: str = "", session: Session = Depends(get_session)):  # fmt: skip
    """Manufacturers' public reference designs, searchable; each function is marked portfolio / gap for us. The
    types view groups them broadly (application type, then voltage class or frequency band); the families view lists
    each product family once, with its member parts and the designs that use them. With no search or filter the
    page opens on the types view."""
    base = refdesigns.search(q, vendor, market, fn, iso, docs)
    tree = refdesigns.type_tree(base)
    rows = [d for d in base if (not atype or d["_type"] == atype) and (not sub or d["_sub"] == sub)]
    if not view and not any((q, vendor, market, fn, iso, docs, atype, sub, page > 1)):
        view = "types"
    view = view if view in ("families", "types") else ""
    items = refdesigns.families(rows, q) if view == "families" else [] if view == "types" else rows
    per = 50
    pages = max(1, -(-len(items) // per))
    page = min(max(page, 1), pages)
    shown = items[(page - 1) * per : page * per]
    mk = op.makers(session)
    mine = op.company("combined")[2]
    fns = (
        {f for d in shown for f in d.get("functions") or []}
        if view != "families"
        else {f for x in shown for f, _ in x["functions"]}
    )
    facets = refdesigns.facets(rows)
    fns |= {f for f, _ in facets["function"]}
    ctx = {"rows": shown if not view else [], "fams": shown if view == "families" else [], "view": view,
           "n_items": len(items), "tree": tree, "atype": atype, "sub": sub,
           "family_of": refdesigns.family_of, "grouped": refdesigns.grouped_parts,
           "n": len(rows), "n_all": len(refdesigns.designs()),
           "page": page, "pages": pages, "facets": facets, "sources": refdesigns.sources(),
           "q": q, "vendor": vendor, "market": market, "fn": fn, "iso": iso, "docs": docs,
           "status": {f: op.status_of(f, mk, mine) for f in fns},
           "label": {f: vocab.fn_label(f) for f in fns}, "doc_labels": refdesigns.DOC_LABELS}  # fmt: skip
    return templates.TemplateResponse(request, "blocks/reference_designs.html", ctx)
