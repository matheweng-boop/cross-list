"""Systems & applications > Cross-sell > Skyworks + Qorvo portfolio (moved from Products, owner 25 Oct 2026): the two
product lines side by side, for cross-selling. The URL stays /portfolio."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.services import portfolio as pf
from app.services import systems as sy
from app.services import vocab
from app.web.routes import templates

router = APIRouter()


@router.get("/portfolio", response_class=HTMLResponse)
def portfolio(request: Request, system: str = "", sub: str = "", session: Session = Depends(get_session)):
    ctx = {"cur": pf.curated(), "ov": pf.overlap(), "bands": pf.rf_bands(), "comp": pf.competitors(session),
           "bundles": pf.bundles(), "label": vocab.fn_label, "cats": pf.product_categories(),
           "syn": pf.synergies(), "matches": pf.pick_matches(), "match_rule": pf.MATCH_RULE}  # fmt: skip
    ctx["bundles_total"] = len(pf.bundles(limit=10_000))  # the same count as "both lines supply blocks" on By system
    # from a pair to the systems where it applies, and back: the system picked on Cross-sell › By system (?system=)
    ctx["places"] = {(x["skyworks"], x["qorvo"]): sy.places(x["idx"]) for x in ctx["syn"]}
    ctx["bundle_places"] = {x["application"]: sy.places([x["i"]])[:1]
                            for x in pf.curated_bundles() if x["i"] is not None}  # fmt: skip
    picked = sy.selection(system, sub)
    ctx["sel"] = {**picked, "system": system, "sub": sub if picked["level"] == "subsystem" else "",
                  "here": {(x["skyworks"], x["qorvo"]) for x in ctx["syn"] if set(picked["idx"]) & set(x["idx"])}
                  } if picked["idx"] else None  # fmt: skip
    return templates.TemplateResponse(request, "portfolio.html", ctx)
