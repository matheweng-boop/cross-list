"""Opportunities > Automotive map: how far Skyworks + Qorvo are from an automotive product, per application and
function, with the calls a reviewer accepts or rejects."""

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.services import automotive as au
from app.services import scoring, vocab
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
    by_app = {a["id"]: au.by_level(m, a["id"], columns) for a in m["apps"]}  # application -> level -> cells
    counts = {lv: sum(len(by_app[a["id"]].get(lv) or []) for a in m["apps"]) for lv in au.LEVELS}  # letter tabs
    app_id, _, fn = cell.partition(":")
    ctx = {"m": m, "view": view, "columns": columns, "moves": [x for x in m["moves"] if x["fn"] in cols][:12],
           "sel": m["cells"].get((app_id, fn)), "by_app": by_app, "counts": counts, "levels": au.LEVELS,
           "level_label": au.LEVEL_LABEL, "level_help": au.LEVEL_HELP, "label": vocab.fn_label,
           "ladder": scoring.config()["distance"]["ladder"], "dist_label": scoring.distance_label}  # fmt: skip
    return templates.TemplateResponse(request, "business/automotive.html", ctx)


@router.get("/business/car-explorer", response_class=HTMLResponse)
def car_explorer(request: Request, area: str = "", session: Session = Depends(get_session)):
    """Systems & applications > Car explorer (owner, 2 Nov 2026): a see-through 3D car; each area opens the Automotive
    map applications that sit there. ?area=<id> opens one area (also without JavaScript)."""
    from app.services import car_explorer as ce

    zs = ce.areas(session)
    sel = area if any(z["id"] == area for z in zs) else ""
    car = [{"id": z["id"], "title": z["title"], "n": z["n_diagrams"]} for z in zs]  # what the 3D car needs
    ctx = {"areas": zs, "sel": sel, "car": car, "levels": au.LEVELS, "level_label": au.LEVEL_LABEL}
    return templates.TemplateResponse(request, "business/car_explorer.html", ctx)


@router.get("/business/automotive-focus", response_class=HTMLResponse)
def automotive_focus(request: Request, session: Session = Depends(get_session)):
    """Future growth > Automotive focus (owner, 3 Nov 2026): six goals, short to long term, built live from the
    Automotive map, Cross-sell, reference designs, research cases and TAM (app/services/auto_focus.py)."""
    from app.services import auto_focus as af

    ctx = {"f": af.build(session), "horizons": af.HORIZON, "level_label": au.LEVEL_LABEL, "effort": af.EFFORT,
           "dist_label": scoring.distance_label}  # fmt: skip
    return templates.TemplateResponse(request, "business/automotive_focus.html", ctx)


@router.post("/business/automotive/review")
def review(cell: str = Form(...), verdict: str = Form(...), view: str = Form("apps"),
           session: Session = Depends(get_session)):  # fmt: skip
    app_id, _, fn = cell.partition(":")
    if verdict not in ("accept", "reject", "reset") or (app_id, fn) not in au.build(session)["cells"]:
        raise HTTPException(400, "Unknown cell or verdict")
    au.review(session, cell, verdict)
    view = view if view in ("apps", "rf", "all") else "apps"
    return RedirectResponse(f"/business/automotive?view={view}&cell={cell}#detail", 303)
