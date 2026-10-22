"""Opportunities > Competitive analytics: the list of competitor profiles and one profile per company."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.services import competitors as cp
from app.web.routes import templates

router = APIRouter()


@router.get("/business/competitors", response_class=HTMLResponse)
def competitor_list(request: Request):
    ctx = {"rows": cp.all_profiles(), "errors": cp.problems(), "levels": cp.LEVELS}
    return templates.TemplateResponse(request, "business/competitors.html", ctx)


@router.get("/business/competitors/{slug}", response_class=HTMLResponse)
def competitor_page(request: Request, slug: str):
    row = cp.get(slug)
    if row is None:
        raise HTTPException(404, "No profile for this company yet")
    return templates.TemplateResponse(request, "business/competitor.html", {"c": row, "levels": cp.LEVELS})
