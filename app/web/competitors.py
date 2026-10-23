"""Opportunities > Competitive analytics: the list of competitor profiles and one profile per company; and
Opportunities > Risks."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.services import competitors as cp
from app.web.routes import templates

router = APIRouter()


@router.get("/business/competitors", response_class=HTMLResponse)
def competitor_list(request: Request):
    ctx = {"rows": cp.all_profiles(), "errors": cp.problems(), "levels": cp.LEVELS, "ratings": cp.RATINGS}
    return templates.TemplateResponse(request, "business/competitors.html", ctx)


@router.get("/business/risks", response_class=HTMLResponse)
def risks_page(request: Request):
    """Opportunities > Risks: competing technologies and products that could endanger our solutions."""
    from app.services import risks

    data = risks.load()
    ctx = {"d": data, "urgent": risks.urgent(data), "likelihood": risks.LIKELIHOOD, "when": risks.WHEN,
           "kinds": risks.KINDS}  # fmt: skip
    return templates.TemplateResponse(request, "business/risks.html", ctx)


@router.get("/business/competitors/{slug}", response_class=HTMLResponse)
def competitor_page(request: Request, slug: str):
    row = cp.get(slug)
    if row is None:
        raise HTTPException(404, "No profile for this company yet")
    ctx = {"c": row, "levels": cp.LEVELS, "table_keys": cp.TABLE_KEYS, "note_keys": cp.NOTE_KEYS,
           "ratings": cp.RATINGS}  # fmt: skip
    return templates.TemplateResponse(request, "business/competitor.html", ctx)
