"""Block-diagram generator pages and API."""

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import BlockDiagram
from app.services import blocks
from app.web.routes import templates

router = APIRouter()


@router.get("/blocks", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_session)):
    designs = session.scalars(select(BlockDiagram).order_by(BlockDiagram.updated_at.desc())).all()
    return templates.TemplateResponse(
        request, "blocks/index.html", {"designs": designs, "templates_": blocks.templates()}
    )


@router.get("/blocks/coverage", response_class=HTMLResponse)
def coverage(request: Request, session: Session = Depends(get_session)):
    cat = blocks.catalogue()
    return templates.TemplateResponse(request, "blocks/coverage.html", {"cat": cat, "counts": blocks.counts(session)})


@router.get("/blocks/new", response_class=HTMLResponse)
def new(request: Request, template: int | None = None, session: Session = Depends(get_session)):
    tpl = blocks.templates()[template] if template is not None and 0 <= template < len(blocks.templates()) else None
    return _editor(request, session, None, tpl)


@router.get("/blocks/{design_id}", response_class=HTMLResponse)
def edit(request: Request, design_id: int, session: Session = Depends(get_session)):
    d = session.get(BlockDiagram, design_id)
    if d is None:
        raise HTTPException(404, "Block diagram not found")
    return _editor(request, session, d, None)


def _editor(request, session, design, tpl):
    info = {"id": None, "name": (tpl or {}).get("name", ""), "data": None}
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
def parts(fn: str, q: str = "", session: Session = Depends(get_session)):
    return blocks.parts_for(session, fn, q)


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
