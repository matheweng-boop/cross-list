"""Technology reviews (Systems & applications): the list with requests, one review per part family, agree / disagree
per item, and the request form."""

import html

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_session
from app.services import how_it_works as hw
from app.services import reviews as rv
from app.services import vocab
from app.web.routes import templates

router = APIRouter()
templates.env.globals["tech_reviews_for"] = rv.for_part
templates.env.globals["tech_reviews_fn"] = rv.for_function
templates.env.globals["tech_reviews_app"] = rv.for_application
# Part knowledge › How it works links (owner, 28 Oct 2026) on the browse page, part pages, reviews and library topics
templates.env.globals["how_for_sub"] = hw.for_sub
templates.env.globals["how_for_part"] = hw.for_part
templates.env.globals["how_for_review"] = hw.for_review
templates.env.globals["how_for_topic"] = hw.for_topic
templates.env.globals["how_groups"] = hw.groups
templates.env.globals["how_href"] = hw.href


def _ctx(**kw) -> dict:
    return {"statuses": rv.STATUSES, "req_statuses": rv.REQUEST_STATUSES, "label": vocab.fn_label, **kw}


@router.get("/reviews", response_class=HTMLResponse)
def review_list(request: Request, q: str = "", part: str = "", session: Session = Depends(get_session)):
    q = q.strip()[:100]
    rows = rv.search(rv.all_reviews(), q)
    errors, warnings = rv.problems()
    reqs = rv.requests(session)
    ctx = _ctx(rows=rows, q=q, n_all=len(rv.all_reviews()), open_reqs=[e for e in reqs if e["status"] in
               ("new", "in_progress")], done_reqs=[e for e in reqs if e["status"] not in ("new", "in_progress")],
               errors=errors, warnings=warnings, part=part.strip()[:100], all_rows=rv.all_reviews(),
               asked=request.query_params.get("asked"))  # fmt: skip
    return templates.TemplateResponse(request, "reviews/list.html", ctx)


@router.get("/reviews/suggest", response_class=HTMLResponse)
def review_suggest(mpn: str = "", session: Session = Depends(get_session)):
    """<option> list for the part-number box of the request form: parts with data, then catalogue records."""
    from app.services import products
    from app.services.queries import normalize_pn, search_parts

    if len(normalize_pn(mpn).replace("*", "")) < 2:
        return HTMLResponse("")
    parts = [p.mpn for p in search_parts(session, mpn, limit=15)]
    cat = [r["mpn"] for r in products.search_catalogue(mpn, {normalize_pn(p) for p in parts}, limit=15)]
    return HTMLResponse("".join(f'<option value="{html.escape(m)}">' for m in [*parts, *cat][:25]))


@router.post("/reviews/request")
def review_request(mpn: str = Form(""), question: str = Form(""), application: str = Form(""),
                   back: str = Form(""), session: Session = Depends(get_session)):  # fmt: skip
    try:
        row = rv.request_review(session, mpn, question, application)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    target = back if back.startswith("/") and not back.startswith("//") else "/reviews"
    sep = "&" if "?" in target else "?"
    return RedirectResponse(f"{target}{sep}asked={row.id}#requested", status_code=303)


@router.post("/reviews/requests/{rid:int}")
def review_request_status(rid: int, status: str = Form(...), review: str = Form(""),
                          session: Session = Depends(get_session)):  # fmt: skip
    try:
        rv.set_request(session, rid, status, review.strip())
    except KeyError:
        raise HTTPException(404, "Request not found") from None
    except ValueError:
        raise HTTPException(400, "Unknown status or review") from None
    return RedirectResponse(f"/reviews#rq-{rid}", status_code=303)


@router.get("/part-knowledge", include_in_schema=False)
def part_knowledge_alias():
    """Owner, 28 Oct 2026: "Part reviews" is now "Part knowledge"; the pages stay at /reviews, so old links work."""
    return RedirectResponse("/reviews", status_code=307)


@router.get("/reviews/how", include_in_schema=False)
def how_index():
    return RedirectResponse("/reviews#how", status_code=307)


@router.get("/reviews/how/{gid}", response_class=HTMLResponse)
def how_group(request: Request, gid: str, session: Session = Depends(get_session)):
    """Part knowledge › How it works for one product group: the part itself, its key values, the app-note details and
    our Skyworks / Qorvo parts; applications only as links."""
    g = hw.group(gid)
    if g is None:
        raise HTTPException(404, "No such product group")
    ctx = _ctx(g=g, table=hw.parts_table(session, g), used_in=hw.used_in(g), used_areas=hw.used_in_areas(g),
               seen_in=hw.seen_in(g), reviews=hw.reviews_of(g),
               spec_link=hw.spec_link, groups=hw.groups())  # fmt: skip
    return templates.TemplateResponse(request, "reviews/how.html", ctx)


@router.get("/reviews/{slug}", response_class=HTMLResponse)
def review_detail(request: Request, slug: str, session: Session = Depends(get_session)):
    r = rv.get(slug)
    if r is None:
        raise HTTPException(404, "Technology review not found")
    ctx = _ctx(r=rv.with_feedback(session, r), live=rv.live_parts(session, r), verdict_label=rv.VERDICT_LABEL,
               reqs=[e for e in rv.requests(session) if e["review"] and e["review"]["slug"] == slug])  # fmt: skip
    return templates.TemplateResponse(request, "reviews/detail.html", ctx)


@router.post("/reviews/{slug}/react")
def review_react(slug: str, key: str = Form(...), verdict: str = Form(...), comment: str = Form(""),
                 author: str = Form(""), session: Session = Depends(get_session)):  # fmt: skip
    try:
        rv.react(session, slug, key, verdict, comment, author)
    except ValueError:
        raise HTTPException(400, "Unknown item or verdict") from None
    return RedirectResponse(f"/reviews/{slug}#i-{key.replace('.', '-')}", status_code=303)
