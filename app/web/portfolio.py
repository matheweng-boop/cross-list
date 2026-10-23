"""Products > Skyworks + Qorvo: the two product lines side by side, for cross-selling."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.services import portfolio as pf
from app.services import vocab
from app.web.routes import templates

router = APIRouter()


@router.get("/portfolio", response_class=HTMLResponse)
def portfolio(request: Request, session: Session = Depends(get_session)):
    ctx = {"cur": pf.curated(), "ov": pf.overlap(), "bands": pf.rf_bands(), "comp": pf.competitors(session),
           "bundles": pf.bundles(), "label": vocab.fn_label, "cats": pf.product_categories(),
           "syn": pf.synergies(), "matches": pf.pick_matches(), "match_rule": pf.MATCH_RULE}  # fmt: skip
    return templates.TemplateResponse(request, "portfolio.html", ctx)
