"""Broadcast section: device overview, saved configurations and the block-diagram editor."""

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import BroadcastConfig
from app.services import broadcast
from app.web.routes import templates

router = APIRouter()


@router.get("/broadcast", response_class=HTMLResponse)
def overview(request: Request):
    devices = broadcast.catalog()
    by_role = {role: [d for d in devices if d["role"] == role] for role in broadcast.ROLES}
    return templates.TemplateResponse(
        request,
        "broadcast/index.html",
        {"by_role": by_role, "roles": broadcast.ROLES, "standards_of": broadcast.standards_of,
         "documents": broadcast.documents(), "tf": broadcast.tuner_features(),
         "by_mpn": {d["mpn"]: d for d in devices}},
    )  # fmt: skip


@router.get("/broadcast/configurations", response_class=HTMLResponse)
def configurations(request: Request, session: Session = Depends(get_session)):
    configs = session.scalars(select(BroadcastConfig).order_by(BroadcastConfig.updated_at.desc())).all()
    return templates.TemplateResponse(request, "broadcast/configurations.html", {"configs": configs})


@router.get("/broadcast/configurations/new", response_class=HTMLResponse)
def new_configuration(request: Request):
    return _editor(request, None)


@router.get("/broadcast/configurations/{config_id}", response_class=HTMLResponse)
def edit_configuration(request: Request, config_id: int, session: Session = Depends(get_session)):
    config = session.get(BroadcastConfig, config_id)
    if config is None:
        raise HTTPException(404, "Configuration not found")
    return _editor(request, config)


def _editor(request: Request, config: BroadcastConfig | None):
    return templates.TemplateResponse(
        request,
        "broadcast/editor.html",
        {
            "config": config,
            "catalog": broadcast.catalog(),
            "presets": broadcast.configurations(),
            "guidance": broadcast.guidance(),
            "explanations": broadcast.explanations(),
            "features": broadcast.tuner_features(),
        },
    )


@router.post("/broadcast/configurations/{config_id}/delete")
def delete_configuration(config_id: int, session: Session = Depends(get_session)):
    config = session.get(BroadcastConfig, config_id)
    if config is not None:
        session.delete(config)
        session.commit()
    return RedirectResponse("/broadcast/configurations", status_code=303)


# --- JSON API used by the editor ---------------------------------------------------------


@router.get("/api/broadcast/devices")
def devices_json():
    return broadcast.catalog()


@router.post("/api/broadcast/configs")
def create_config(payload: dict = Body(...), session: Session = Depends(get_session)):
    config = BroadcastConfig(name=_name(payload), data=payload.get("data") or {})
    session.add(config)
    session.commit()
    return {"id": config.id, "name": config.name}


@router.put("/api/broadcast/configs/{config_id}")
def update_config(config_id: int, payload: dict = Body(...), session: Session = Depends(get_session)):
    config = session.get(BroadcastConfig, config_id)
    if config is None:
        raise HTTPException(404, "Configuration not found")
    config.name = _name(payload)
    config.data = payload.get("data") or {}
    session.commit()
    return {"id": config.id, "name": config.name}


@router.get("/api/broadcast/configs/{config_id}")
def get_config(config_id: int, session: Session = Depends(get_session)):
    config = session.get(BroadcastConfig, config_id)
    if config is None:
        raise HTTPException(404, "Configuration not found")
    return {"id": config.id, "name": config.name, "data": config.data}


def _name(payload: dict) -> str:
    return (str(payload.get("name") or "").strip() or "Untitled configuration")[:200]
