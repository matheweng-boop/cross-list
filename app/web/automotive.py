"""Opportunities > Automotive map: how far Skyworks + Qorvo are from an automotive product, per application and
function, with the calls a reviewer accepts or rejects."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.services import automotive as au
from app.services import vocab
from app.web.routes import templates

router = APIRouter()


@router.get("/business/automotive", response_class=HTMLResponse)
def automotive(request: Request, view: str = "apps", cell: str = "", session: Session = Depends(get_session)):
    m = au.build(session)
    view = view if view in ("apps", "rf", "all") else "apps"
    columns = m["columns"] if view == "all" else [f for f in m["columns"] if f in m["rf"]]
    if view == "apps":  # RF, radio and timing plus the functions a research or platform row names
        named = {c["fn"] for c in m["cells"].values() if c.get("next") or c.get("curated")}
        columns = [f for f in m["columns"] if f in m["rf"] or f in named]
    cols = set(columns)
    by_app = {a["id"]: {} for a in m["apps"]}  # application -> level -> cells, for the default view
    for f in columns:
        for a in m["apps"]:
            c = m["cells"].get((a["id"], f))
            if c and c["status"] != "rejected":
                by_app[a["id"]].setdefault(c["level"], []).append(c)
    app_id, _, fn = cell.partition(":")
    ctx = {"m": m, "view": view, "columns": columns, "moves": [x for x in m["moves"] if x["fn"] in cols][:12],
           "sel": m["cells"].get((app_id, fn)), "by_app": by_app, "levels": au.LEVELS, "level_label": au.LEVEL_LABEL,
           "level_help": au.LEVEL_HELP, "label": vocab.fn_label}  # fmt: skip
    return templates.TemplateResponse(request, "business/automotive.html", ctx)


@router.post("/business/automotive/review")
def review(cell: str = Form(...), verdict: str = Form(...), view: str = Form("apps"),
           session: Session = Depends(get_session)):  # fmt: skip
    app_id, _, fn = cell.partition(":")
    if verdict not in ("accept", "reject", "reset") or (app_id, fn) not in au.build(session)["cells"]:
        raise HTTPException(400, "Unknown cell or verdict")
    au.review(session, cell, verdict)
    view = view if view in ("apps", "rf", "all") else "apps"
    return RedirectResponse(f"/business/automotive?view={view}&cell={cell}#detail", 303)
