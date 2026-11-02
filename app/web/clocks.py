"""Clock planner pages (Products > Clock planner; owner, 2 Nov 2026, item 18) and saved plans.

The planner is a GET form: every result is worked out on the server from the query string, so a link is the plan.
Saving follows the radio configurator (app/web/broadcast.py): a JSON API, the owner's save is stored at once, a
guest's is held for the owner's review by the guest-input middleware (app/services/guest_input.py).
"""

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import ClockPlan
from app.services import clock_planner as cp
from app.web.routes import templates

router = APIRouter()


def _form(request: Request) -> dict:
    form: dict = {}
    for k, v in request.query_params.multi_items():
        form.setdefault(k, []).append(v)
    return form


def _page(request: Request, req: dict, plan: ClockPlan | None = None):
    result = cp.run(req) if req["outputs"] else None
    form = cp.to_form(req)
    rows = [{k: form[k][i] for k in ("f", "n", "fmt", "v")} for i in range(len(form["f"]))]
    blanks = max(1, 3 - len(rows))
    return templates.TemplateResponse(
        request,
        "clocks/planner.html",
        {"req": req, "form": form, "rows": rows, "blanks": blanks, "result": result, "cp": cp,
         "presets": cp.presets(), "cbpro": cp.clockbuilder(), "plan": plan, "formats": cp.data().get("formats", []),
         "supplies": cp.data().get("supplies_v", []), "types": cp.FUNCTION_LABELS},
    )  # fmt: skip


@router.get("/clocks", response_class=HTMLResponse)
def planner(request: Request, session: Session = Depends(get_session)):
    form = _form(request)
    req = cp.build_request(form)
    plan = None
    pid = (form.get("plan") or [""])[0]
    if pid.isdigit():
        plan = session.get(ClockPlan, int(pid))
    return _page(request, req, plan)


@router.get("/clocks/plans", response_class=HTMLResponse)
def plans(request: Request, session: Session = Depends(get_session)):
    rows = session.scalars(select(ClockPlan).order_by(ClockPlan.updated_at.desc())).all()
    return templates.TemplateResponse(request, "clocks/plans.html", {"plans": rows, "cp": cp})


@router.get("/clocks/plans/{plan_id:int}", response_class=HTMLResponse)
def open_plan(request: Request, plan_id: int, session: Session = Depends(get_session)):
    plan = session.get(ClockPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")
    return _page(request, cp.build_request(plan.data or {}), plan)


@router.post("/clocks/plans/{plan_id:int}/delete")
def delete_plan(plan_id: int, session: Session = Depends(get_session)):
    plan = session.get(ClockPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")
    session.delete(plan)
    session.commit()
    return RedirectResponse("/clocks/plans", status_code=303)


# --- JSON API used by the Save button ---------------------------------------------------------------------------------


def _data(payload: dict) -> dict:
    """The plan as form values, read back through the planner so only known fields are kept."""
    raw = payload.get("data")
    if not isinstance(raw, dict) or not raw:
        raise HTTPException(400, "Nothing to save: the plan is empty")
    req = cp.build_request({k: v for k, v in raw.items() if isinstance(v, str | list)})
    if not req["outputs"]:
        raise HTTPException(400, "Nothing to save: add at least one output")
    data = cp.to_form(req)
    data.pop("preset", None)
    return data


def _name(payload: dict) -> str:
    return (str(payload.get("name") or "").strip() or "Untitled clock plan")[:200]


@router.post("/api/clocks/plans")
def create_plan(payload: dict = Body(...), session: Session = Depends(get_session)):
    plan = ClockPlan(name=_name(payload), data=_data(payload))
    session.add(plan)
    session.commit()
    return {"id": plan.id, "name": plan.name, "url": f"/clocks/plans/{plan.id}"}


@router.put("/api/clocks/plans/{plan_id:int}")
def update_plan(plan_id: int, payload: dict = Body(...), session: Session = Depends(get_session)):
    plan = session.get(ClockPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")
    plan.name = _name(payload)
    if payload.get("data"):  # a rename alone keeps the saved plan
        plan.data = _data(payload)
    session.commit()
    return {"id": plan.id, "name": plan.name, "url": f"/clocks/plans/{plan.id}"}


@router.get("/api/clocks/plans/{plan_id:int}")
def get_plan(plan_id: int, session: Session = Depends(get_session)):
    plan = session.get(ClockPlan, plan_id)
    if plan is None:
        raise HTTPException(404, "Plan not found")
    return {"id": plan.id, "name": plan.name, "data": plan.data}
