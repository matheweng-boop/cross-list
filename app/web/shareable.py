"""Shareable: public pages ready to share outside the company or save as PDF (owner, 24 Oct 2026). Guests read them
too (app/auth/access.py does not list /shareable as owner-only)."""

from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.services import tech_overview
from app.web import nav
from app.web.routes import templates

router = APIRouter()

# a line more per card on the landing page than the menu's short description
BLURBS = {"/shareable/technology-overview": "Four A4 pages on the Skyworks + Qorvo portfolio: technology platforms, "
          "end markets and product families."}  # fmt: skip


@router.get("/shareable", response_class=HTMLResponse)
def shareable(request: Request):
    section = next(s for s in nav.NAV if s[0] == "shareable")
    items = [(label, href, BLURBS.get(href, desc)) for label, href, desc in section[2]]
    return templates.TemplateResponse(request, "shareable/index.html", {"items": items})


@router.get("/shareable/technology-overview", response_class=HTMLResponse)
def technology_overview(request: Request):
    ctx = {"t": tech_overview.build(), "today": date.today()}
    return templates.TemplateResponse(request, "shareable/tech_overview.html", ctx)
