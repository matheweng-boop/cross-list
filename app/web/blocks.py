"""Block-diagram generator pages and API."""

import json
from collections import Counter

from fastapi import APIRouter, Body, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.session import signed_in_owner
from app.db import get_session
from app.models import AreaRequest, BlockDiagram, BlockFeedback
from app.services import blocks, prelim, refdesigns, refmatch, schematic, vocab
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

    shown = {c["i"]: c for _, v in cards for c in v}
    from app.services import library
    from app.services import systems as sy

    topics = {t["key"]: t for t in library.topics()}
    system = request.query_params.get("system", "")
    subsystem = request.query_params.get("sub", "")
    system = system if sy.get(system) or system == sy.OTHER else ""
    subsystem = subsystem if system and sy.sub(system, subsystem) else ""
    tree = [{**s, "subs": [{**x, "cards": [shown[i] for i in x["idx"] if i in shown],
                            "deep": [topics[k] for k in x["topics"] if k in topics]} for x in s["subsystems"]]}
            for s in sy.systems()]  # fmt: skip
    for s in tree:
        s["n"] = len({c["i"] for x in s["subs"] for c in x["cards"]})
    done = sy.assigned()
    other = [(k, [c for c in v if c["i"] not in done]) for k, v in cards]
    filtered = bool(market or source or variants or verified in ("yes", "no"))
    subs = [x for s in sy.systems() for x in s["subsystems"]]
    dg = {"subs": len(subs), "with": sum(1 for x in subs if x["idx"]), "other": len(sy.unassigned())}
    ctx = {"designs": designs, "cards": [(k, v) for k, v in cards if v], "n_all": len(allcards),
           "tree": tree, "dg": dg, "other": [(k, v) for k, v in other if v], "system": system, "sub": subsystem,
           "expanded": bool(system) or filtered, "filtered": filtered,
           "asked": request.query_params.get("asked") == "1",
           "n_shown": sum(len(v) for _, v in cards), "markets": facet("market"), "sources": facet("source"),
           "market": market, "source": source, "variants": variants, "verified": verified,
           "n_verified": sum(1 for c in allcards if c["verified"]),
           "n_variant": sum(1 for c in allcards if c["variant"]), "n_groups": len(blocks.variant_groups())}  # fmt: skip
    if subsystem:  # owner, 23 Oct 2026: once a sub-system is picked, its cross-sell sits right below it
        from app.services import opportunity as op

        ctx["xsell"] = sy.bottom_up(session, sy.sub(system, subsystem)["idx"], op.company("combined")[2], n_parts=6)
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


@router.get("/blocks/area-requests")
def area_requests():
    """The old Area requests page: now the Requests tab under Site data, filtered to area requests."""
    return RedirectResponse("/manage/requests?kind=area", status_code=307)


@router.post("/blocks/area-requests/{req_id:int}")
def area_request_status(req_id: int, status: str = Form(...), session: Session = Depends(get_session)):
    row = session.get(AreaRequest, req_id)
    if row is None:
        raise HTTPException(404)
    if status not in AREA_STATUSES:
        raise HTTPException(400, "Unknown status")
    row.status = status
    session.commit()
    return RedirectResponse("/manage/requests?kind=area", status_code=303)


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


@router.get("/blocks/words")
def words_page():
    """A reload of the built page (the text is not kept): back to a new diagram."""
    return RedirectResponse("/blocks/new#bk-words", status_code=303)


@router.post("/blocks/words", response_class=HTMLResponse)
def from_words(request: Request, text: str = Form(""), bare: str = Form(""), session: Session = Depends(get_session)):
    """"Describe your system": the text read by rules (app/services/wordblocks.py) into a new, unsaved diagram. The text
    is never stored; for the owner only, the words not understood are counted (guests: nothing)."""
    from app.services import wordblocks

    text = text[: wordblocks.MAX_TEXT]
    built = wordblocks.build(text)
    if signed_in_owner(request) is not None:
        wordblocks.count_unknown(session, wordblocks.unknown_words(text))
    n = built["n"]
    info = {"id": None, "name": "From your description", "data": built["data"],
            "prefill": f"{n} block{'' if n == 1 else 's'} built from your description: press Save to keep them"
            if n else "Nothing recognised yet: try words like 48 V input, MCU, CAN"}  # fmt: skip
    return _editor(request, session, None, None, None, bare == "1", info,
                   words={"text": text, "chips": built["chips"], "notes": built["notes"], "n": n})  # fmt: skip


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


def _editor(request, session, design, tpl, tpl_i=None, bare=False, info=None, words=None):
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
            "verify_key": blocks.verify_key(tpl) if tpl else "",
            "bare": bare,
            "kb": refmatch.kb_view(tpl, blocks.counts(session)) if tpl else None,
            "ref_counts": refmatch.fn_counts(),
            "words": words,
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


@router.get("/blocks/feedback")
def feedback_page():
    """The old Diagram feedback page: now the Requests tab under Site data, filtered to diagram feedback."""
    return RedirectResponse("/manage/requests?kind=diagram", status_code=307)


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
    return RedirectResponse("/manage/requests?kind=diagram", status_code=303)


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
                      sub: str = "", diagram: str = "", part: str = "", anchor: str = "",
                      session: Session = Depends(get_session)):  # fmt: skip
    """Manufacturers' public reference designs, searchable; each function is marked portfolio / gap for us. The
    types view groups them broadly (application type, then voltage class or frequency band); the families view lists
    each product family once, with its member parts and the designs that use them. With no search or filter the
    page opens on the types view. Not in the menu (owner, 25 Oct 2026): the data works behind the library diagrams,
    the gaps and the part pages, which link here with a reproducible list: ?diagram=<library diagram key> (the designs
    the diagram is based on; with &anchor=<part or function> those with that anchor), ?part=<part number>,
    ?fn=<function>."""
    fb = refmatch.token() if diagram else ()
    v = refdesigns.view(q, vendor, market, fn, iso, docs, atype, sub, diagram, part.strip(), anchor, fb)
    tree, rows = v["tree"], v["rows"]
    if not view and not any((q, vendor, market, fn, iso, docs, atype, sub, diagram, part, page > 1)):
        view = "types"
    view = view if view in ("families", "types") else ""
    items = refdesigns.families(list(rows), q) if view == "families" else [] if view == "types" else rows
    per = 50
    pages = max(1, -(-len(items) // per))
    page = min(max(page, 1), pages)
    shown = items[(page - 1) * per : page * per]
    facets = v["facets"]
    fns = (
        {f for d in shown for f in d.get("functions") or []}
        if view != "families"
        else {f for x in shown for f, _ in x["functions"]}
    )
    status = {}
    if view != "types":  # the coloured function chips (the types view shows none)
        mk = op.makers(session)
        mine = op.company("combined")[2]
        status = {f: op.status_of(f, mk, mine) for f in fns}
    fns |= {f for f, _ in facets["function"]}
    ctx = {"rows": shown if not view else [], "fams": shown if view == "families" else [], "view": view,
           "n_items": len(items), "tree": tree, "atype": atype, "sub": sub,
           "family_of": refdesigns.family_of, "grouped": refdesigns.grouped_parts,
           "n": len(rows), "n_all": len(refdesigns.designs()),
           "page": page, "pages": pages, "facets": facets, "sources": refdesigns.sources(),
           "q": q, "vendor": vendor, "market": market, "fn": fn, "iso": iso, "docs": docs,
           "diagram": diagram, "part": part.strip(), "anchor": anchor, "heading": v["heading"],
           "anchors_of": refmatch.anchors_of_design, "design_key": refmatch.design_key,
           "fbe": _fb_view(diagram) if diagram else None,
           "can_answer": bool(diagram) and signed_in_owner(request) is not None,
           "status": status, "label": {f: vocab.fn_label(f) for f in fns},
           "doc_labels": refdesigns.DOC_LABELS}  # fmt: skip
    return templates.TemplateResponse(request, "blocks/reference_designs.html", ctx)


def _fb_view(diagram: str) -> dict | None:
    """The owner's answers on one diagram's list: designs confirmed and removed (removed ones listed to put back)."""
    e = refmatch.entry(diagram)
    if not e:
        return None
    idx = refmatch.index()["by_key"]
    return {"fits": set(e.get("fits") or []), "removed": [idx[k] for k in e.get("removed") or [] if k in idx]}


FB_VERDICTS = {"fits": refmatch.FITS, "nofit": refmatch.NOFIT, "reset": refmatch.RESET}


@router.post("/reference-designs/feedback")
def reference_design_feedback(request: Request, diagram: str = Form(...), item: str = Form(...),
                              verdict: str = Form(...), comment: str = Form(""), back: str = Form(""),
                              session: Session = Depends(get_session)):  # fmt: skip
    """The owner's answer on a matched design ("Fits" / "Doesn't fit" / back to the script's decision) or a
    suggestion ("fn:<function>", "Doesn't fit" = not a block for this diagram). Append-only, the latest counts."""
    me = signed_in_owner(request)
    if me is None:
        raise HTTPException(403, "Only the owner can answer.")
    e = refmatch.data()["by_key"].get(diagram)
    if e is None or verdict not in FB_VERDICTS:
        raise HTTPException(404, "Unknown diagram or answer")
    if item.startswith("fn:"):
        if item[3:] not in blocks.catalogue()["functions"]:
            raise HTTPException(404, "Unknown function")
    elif item not in (e.get("designs") or []):
        raise HTTPException(404, "This design is not matched to the diagram")
    refmatch.record(session, diagram, item, FB_VERDICTS[verdict], comment, me.name or "Owner")
    ok = back.startswith("/") and not back.startswith("//")
    return RedirectResponse(back if ok else f"/reference-designs?diagram={diagram}", status_code=303)
