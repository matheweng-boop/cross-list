"""Parts & components > State of the art (owner, 8 Nov 2026): the best each maker offers per key figure, per part
category and sub-type (app/services/sota.py)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.services import sota
from app.web.routes import templates

router = APIRouter()
templates.env.globals["sota"] = sota  # the "vs best" fold on the part page and Cross a list (_vs_best.html)


def _p1m(request: Request, session: Session):
    """The single price at 1M a year of the part in a cell (owner, 9 Nov 2026); nothing for a part without a model."""
    from app.models import Part
    from app.services import price_model
    from app.web.routes import _owner_view

    singles = price_model.Singles(session, _owner_view(request))
    return lambda part_id: singles(session.get(Part, part_id)) if part_id else None


@router.get("/state-of-the-art", response_class=HTMLResponse)
def page(request: Request, cat: str = "", sub: str = "", session: Session = Depends(get_session)):
    """One category (chip) and one sub-type at a time; an unknown or empty choice falls back to the first with data."""
    table = sota.table(session)
    cats = [c for c in sota.config() if table.get(c["family"])]
    current = next((c for c in cats if c["family"] == cat), cats[0] if cats else None)
    groups = table.get(current["family"], {}) if current else {}
    group = groups.get(sub) or next(iter(groups.values()), None)
    ctx = {"cats": cats, "cat": current, "groups": groups, "g": group, "table": table,
           "figs": current["figures"] if current else [], "gap_line": sota.gap_line(current, group) if group else "",
           "scope_note": sota.SCOPE_NOTE, "mark": sota.TABLE_MARK, "p1m": _p1m(request, session)}  # fmt: skip
    return templates.TemplateResponse(request, "sota.html", ctx)
