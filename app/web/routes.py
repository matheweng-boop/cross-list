"""HTML pages."""

import re
import urllib.parse
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session, lazyload

from app.auth.deps import get_current_user
from app.config import get_settings
from app.db import get_engine, get_session
from app.matching.engine import (
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    CATEGORY_SHORT,
    DEFAULT_MAX_DEVIATIONS,
    FFF_STATUS_LABELS,
    format_value,
    ranked,
)
from app.matching.rules import get_rules, load_all_rules
from app.models import Package, Part, User
from app.services import (
    alternates,
    cross_notes,
    engineering,
    export,
    lifecycle,
    mechanical,
    notes_search,
    price_builder,
    price_model,
    pricing,
    text,
    vocab,
)
from app.services.compare import compare_parts
from app.services.queries import (
    crosses_for,
    normalize_pn,
    parts_by_ids,
    record_feedback,
    search_parts,
    single_cross,
)
from app.web import labels, nav

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals.update(
    lifecycle_badge=lifecycle.badge,
    category_labels=CATEGORY_LABELS,
    fff_labels=FFF_STATUS_LABELS,
    family_titles=lambda: {k: v.title for k, v in load_all_rules().items()},
    pricing_enabled=pricing.enabled,
    has_list_price=price_model.has_list_price,
    qty_label=pricing.qty_label,
    site_locked=lambda: bool(get_settings().site_password),
    signed_in=lambda request: getattr(request.state, "principal", None),
    category_short=CATEGORY_SHORT,
)


def family_support(session: Session) -> dict[str, dict]:
    """Every product family with matching rules, and how many parts BizDev holds for it: one list for Parts
    and Compare. A family with rules but no parts cannot be compared or crossed yet."""
    from sqlalchemy import func

    from app.models import Manufacturer

    rows = session.execute(
        select(Part.family, Manufacturer.role, func.count(Part.id))
        .join(Part.manufacturer)
        .group_by(Part.family, Manufacturer.role)
    ).all()
    out = {k: {"title": r.title, "parts": 0, "reference": 0, "competitor": 0} for k, r in load_all_rules().items()}
    for fam, role, n in rows:
        e = out.setdefault(fam, {"title": fam, "parts": 0, "reference": 0, "competitor": 0})
        e["parts"] += n
        e[role.value] = e.get(role.value, 0) + n
    return out


def _is_new(part: Part) -> bool:
    return lifecycle.is_new(part, get_settings().new_part_days)


templates.env.globals["is_new"] = _is_new

PASSKEY_NUDGE_COOKIE = "crosslist_pk_nudge"


def _passkey_nudge(request: Request) -> bool:
    """The "Set up a passkey on this device" banner: an owner who signed in with the password and has no passkey yet,
    unless dismissed for this browser session (a session cookie set by the banner's close button)."""
    p = getattr(request.state, "principal", None)
    if p is None or not p.is_owner or not p.id or not get_settings().site_password:
        return False
    if request.cookies.get(PASSKEY_NUDGE_COOKIE) == "off" or request.url.path == "/owner/passkeys":
        return False
    from app.auth import stepup

    with Session(get_engine()) as s:
        return stepup.owner_passkey_count(s, p.id) == 0


templates.env.globals["passkey_nudge"] = _passkey_nudge
labels.register(templates.env)
templates.env.globals.update(fn_label=vocab.fn_label, family_title=vocab.family_title)


# Navigation: task-based sections (app/web/nav.py); every existing URL keeps working
def _market_groups(names):
    from app.services.opportunity import market_subgroups

    return market_subgroups(names)


templates.env.globals.update(
    market_groups=_market_groups,
    nav_state=nav.state,
    nav_sections=nav.NAV,
    nav_utility=nav.UTILITY,
    nav_icons=nav.ICONS,
    page_title=nav.page_title,
    page_label=nav.page_label,
    owner_page=nav.owner_page,
)

# grade filter on the cross results: the keys grade_of() returns, worded as everywhere else (app/web/labels.py)
GRADE_LABELS = {"automotive": labels.GRADE_LABELS["automotive"], "industrial": labels.GRADE_LABELS["not_automotive"],
                "unknown": labels.GRADE_LABELS["unknown"]}  # fmt: skip


def grade_of(part: Part) -> str:
    """'automotive' (AEC-Q100 stated), 'industrial' (industrial / commercial stated) or 'unknown' (not stated):
    a missing qualification is never treated as a confirmed non-automotive grade."""
    q = next((pv.value for pv in part.params if pv.key == "qualification"), None)
    return "automotive" if q == "automotive" else "industrial" if q in ("industrial", "commercial") else "unknown"


def _grade_badge(part: Part) -> tuple[str, str] | None:
    q = next((pv.value for pv in part.params if pv.key == "qualification"), None)
    return labels.GRADE_BADGES.get(q)


def _part_summary(part: Part) -> str:
    """Function · key specs · package · grade, from the part's parameters (app/services/text.py)."""
    params = {pv.key: pv.value for pv in part.params}
    return text.short_description(part.family, part.package.code if part.package else "", grade_of(part), params=params)


templates.env.globals["grade_badge"] = _grade_badge
templates.env.globals["part_summary"] = _part_summary
templates.env.globals["grade_of"] = grade_of
templates.env.globals["grade_labels"] = GRADE_LABELS


def _has_synthetic() -> bool:
    with Session(get_engine()) as s:
        return s.scalar(select(Part.id).where(Part.is_synthetic.is_(True)).limit(1)) is not None


templates.env.globals["synthetic_banner"] = _has_synthetic


def _parse_ids(ids: str) -> list[int]:
    out = []
    for chunk in ids.replace(" ", "").split(","):
        if chunk.isdigit() and int(chunk) not in out:
            out.append(int(chunk))
    return out


def _download(content, filename: str, media: str) -> Response:
    return Response(content, media_type=media, headers={"Content-Disposition": f'attachment; filename="{filename}"'})


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/", response_class=HTMLResponse)
def finder(request: Request, session: Session = Depends(get_session)):
    """Start page: enter a competitor part number to find a Skyworks part."""
    examples = [p for p in search_parts(session, "ISO7741", role="competitor", limit=1)] + [
        p for p in search_parts(session, "NSI8241", role="competitor", limit=1)
    ]
    return templates.TemplateResponse(request, "finder.html", {"examples": examples, "hide_header_search": True})


@router.get("/find", response_class=HTMLResponse)
def find(request: Request, q: str = "", session: Session = Depends(get_session)):
    """A full part number opens its page; a partial one lists the matches."""
    q = q.strip()
    if not q:
        return RedirectResponse("/", status_code=303)
    from app.services import products

    matches = search_parts(session, q, limit=500)
    # the manufacturer catalogues (all public Skyworks and Qorvo parts) are searched too: most of them have no
    # parameters or crosses here, so they are listed with their catalogue data and a link to the manufacturer page
    catalogue = products.search_catalogue(q, {normalize_pn(p.mpn) for p in matches})
    exact = [p for p in matches if normalize_pn(p.mpn) == normalize_pn(q)]
    if len(exact) == 1 or (len(matches) == 1 and not catalogue):
        return RedirectResponse(f"/parts/{(exact or matches)[0].id}", status_code=303)
    competitors = [p for p in matches if not p.is_reference]
    references = [p for p in matches if p.is_reference]
    return templates.TemplateResponse(
        request,
        "find_results.html",
        {
            "q": q,
            "competitors": competitors,
            "references": references,
            "catalogue": catalogue,
            "life_label": lifecycle.CLASS_LABELS,
            "qual_label": labels.GRADE_LABELS,
        },  # fmt: skip
    )


@router.get("/parts", response_class=HTMLResponse)
def index(
    request: Request,
    q: str = "",
    cat: str = "",
    sub: str = "",
    company: str = "",
    qual: str = "",
    life: str = "",
    cap: str = "",
    role: str = "",
    limit: int = 200,
    family: str = "",
    catalog: str = "",
    lifecycle_status: str = Query("", alias="lifecycle"),
    session: Session = Depends(get_session),
):
    """Browse products through one functional taxonomy (catalogue records and BizDev parts together), with
    capability badges that say what each record supports. Old links (family=, catalog=, lifecycle=) still work."""
    from app.services import products

    tax = products.taxonomy()
    if family and not sub:  # old BizDev family link
        sub = tax["families"].get(family, "")
    if catalog and not cat:  # old catalogue category link: its first functional category
        cat = next((cid for c, _rx, cid, _sid in tax["rules"] if c == catalog), "")
    if lifecycle_status and not life:
        life = lifecycle.status_class(lifecycle_status)
    if sub in tax["subs"] and not cat:
        cat = tax["subs"][sub]["category"]
    if company == "*":
        company = ""
    res = products.browse(session, q=q, cat=cat, sub=sub, company=company, qual=qual, life=life, cap=cap, role=role)
    limit = max(50, min(limit, 5000))
    params = {"q": q, "cat": cat, "sub": sub, "company": company, "qual": qual, "life": life, "cap": cap, "role": role}
    ctx = {**params, "params": params, "res": res, "rows": res["rows"][:limit], "limit": limit, "tax": tax,
           "qual_label": labels.GRADE_LABELS, "cap_label": products.CAPABILITIES,
           "life_label": lifecycle.CLASS_LABELS}  # fmt: skip
    return templates.TemplateResponse(request, "index.html", ctx)


CATEGORY_RANK = {c: i for i, c in enumerate(CATEGORY_ORDER)}


def result_rows(crosses: dict) -> list:
    """Each listed candidate once with its verdict, best first: drop-ins, then the fewest deviations, the same package
    before another package and pin-to-pin before another pinout (app/matching/engine.py, rank_key)."""
    return [(r, r.verdict()) for r in ranked(crosses)]


def electrical_verdict(v) -> str:
    """How the priority 1 parameters compare, package and pinout left out (they have their own line)."""
    if v.worse:
        n, labels = len(v.worse), ", ".join(d.label for d in v.worse)
        return f"{n} priority 1 deviation{'s' if n > 1 else ''} ({labels})"
    return "priority 1 equal or better" if v.better else "priority 1 equal"


def fit_verdict(r, v) -> str:
    """Package and pinout in words: "same package, pin-to-pin" or "larger package, different pinout"."""
    pkg = "same package" if r.fit.same_package else f"{r.fit.package_relation} package"
    return f"{pkg}, {'pin-to-pin' if v.p2p else 'different pinout'}"


def rank_reason(r, v) -> str:
    """One line on why a result ranks where it does."""
    bits = [f"Electrical: {electrical_verdict(v)}", fit_verdict(r, v)]
    if v.exceptions:
        bits.append("exception: " + ", ".join(f"{d.label} {d.cand_display} vs {d.ref_display}" for d in v.exceptions))
    if r.lifecycle_risk:
        bits.append("lifecycle risk")
    return " · ".join(bits)


def _deviations(dev: int) -> int:
    return min(max(dev, 0), 3)


def companies_of(rows: list) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for r, _ in rows:
        counts[r.candidate.manufacturer.name] = counts.get(r.candidate.manufacturer.name, 0) + 1
    return sorted(counts.items())


def _part_context(
    session: Session, part: Part, hide_eol: bool, company: str, scope: str, type: str, dev: int, grade: str, all: bool
) -> dict:
    """Everything the part page shows; also used by the fragments that load on demand (grouped view, row detail)."""
    rules = get_rules(part.family)
    # grade is always one of the two: an automotive part only takes automotive crosses (AEC-Q100 is a hard
    # requirement); a non-automotive part shows non-automotive crosses unless automotive is chosen
    grade = "automotive" if grade_of(part) == "automotive" else (grade if grade in GRADE_LABELS else "industrial")
    scope = scope if scope in ("auto", "all") else "auto"
    dev = _deviations(dev)
    crosses = crosses_for(session, part, scope, dev)
    # the part counts as crossed only with an active drop-in of the grade (owner, 22 Oct 2026; filters on the page
    # aside). Without one it gets "Start a prelim case"; with no cross of any type it is the strongest case.
    graded = [r for r in ranked(crosses) if not r.lifecycle_risk and grade_of(r.candidate) == grade]
    cross_ok = next((r.candidate for r in graded if r.category == "fff"), None)
    closest = graded[0].candidate if graded and cross_ok is None else None
    rejected = [r for r in crosses["package"] if r.fff_status == "rejected"]
    if hide_eol:
        crosses = {c: [r for r in rs if not r.lifecycle_risk] for c, rs in crosses.items()}
    companies = companies_of([(r, v) for r, v in result_rows(crosses) if grade_of(r.candidate) == grade])
    if company:
        crosses = {c: [r for r in rs if r.candidate.manufacturer.name == company] for c, rs in crosses.items()}
    # facet counts: crosses per grade with every other active filter applied (lifecycle, company), before type
    grade_counts = {g: sum(grade_of(r.candidate) == g for r, _ in result_rows(crosses)) for g in GRADE_LABELS}
    crosses = {c: [r for r in rs if grade_of(r.candidate) == grade] for c, rs in crosses.items()}
    rows = result_rows(crosses)
    type_counts = {c: sum(v.category == c for _, v in rows) for c in CATEGORY_ORDER}
    type = type if type in CATEGORY_ORDER else ""
    if type:
        rows = [(r, v) for r, v in rows if v.category == type]
    # best and next best option per cross type; the rest only on request
    best, top = {}, []
    # (two different devices: an output-state or rating variant of the best part is not the next best)
    for cat in CATEGORY_ORDER:
        devices: set[str] = set()
        for rv in [rv for rv in rows if rv[1].category == cat]:
            dev_key = alternates.device_of(rv[0].candidate.mpn)
            if dev_key in devices:
                continue
            devices.add(dev_key)
            best[rv[0].candidate.id] = len(devices) - 1
            top.append(rv)
            if len(devices) == 2:
                break
    rest = [rv for rv in rows if rv[0].candidate.id not in best]
    top = [rv for rv in rows if rv[0].candidate.id in best]  # in the overall ranking, not grouped by type
    rows = top + (rest if all else [])
    values = rules.values(part)
    sources = {pv.key: pv.source for pv in part.params}
    groups = {
        prio: [(p, format_value(p, values.get(p.key)), sources.get(p.key)) for p in rules.by_priority(prio)]
        for prio in (1, 2, 3)
    }
    return {
        "part": part,
        "pinout_source": part.pinout_source,
        "rules": rules,
        "groups": groups,
        "crosses": crosses,
        "order": CATEGORY_ORDER,
        "hide_eol": hide_eol,
        "rejected": rejected,
        "companies": companies,
        "company": company,
        "scope": scope,
        "rows": rows,
        "type": type,
        "type_counts": type_counts,
        "dev": dev,
        "ranked": best,
        "n_top": len(top),
        "n_rest": len(rest),
        "show_all": all,
        "alternates": alternates.alternates(session, part),
        "alts_for": lambda p: alternates.alternates(session, p, limit=1),
        "pkg_options": lambda p: alternates.package_options(session, p),
        "out_variants": lambda p: alternates.output_variants(session, p),
        "rank_reason": rank_reason,
        "electrical_verdict": electrical_verdict,
        "fit_verdict": fit_verdict,
        "cross_notes": cross_notes.notes_for,
        "position_note": cross_notes.position_note,
        "grade": grade,
        "grade_counts": grade_counts,
        "ref_grade": grade_of(part),
        "cross_ok": cross_ok,
        "closest_cross": closest,
        "no_cross": not graded,
        "requested": _requested(session, part.mpn),
    }


def _requested(session: Session, mpn: str) -> dict:
    """Requests for a case on the part so far, with the volume asked in total (Business case from a part)."""
    from app.services.pipeline import requested

    return requested(session, mpn)


def _part_or_404(session: Session, part_id: int) -> Part:
    part = session.get(Part, part_id)
    if part is None:
        raise HTTPException(404, "Part not found")
    return part


@router.get("/parts/{part_id}", response_class=HTMLResponse)
def part_detail(
    request: Request,
    part_id: int,
    hide_eol: bool = False,
    company: str = "",
    scope: str = "auto",
    type: str = "",
    dev: int = DEFAULT_MAX_DEVIATIONS,
    grade: str = "",
    all: bool = False,
    session: Session = Depends(get_session),
):
    part = _part_or_404(session, part_id)
    ctx = _part_context(session, part, hide_eol, company, scope, type, dev, grade, all)
    return templates.TemplateResponse(request, "part.html", ctx)


@router.get("/parts/{part_id}/walk", response_class=HTMLResponse)
def part_walk(request: Request, part_id: int, upto: int = 2, q: str = "", session: Session = Depends(get_session)):
    """Walk-through from the part: replacement, sell around it, best of ours, make it better, future. Only the steps
    asked for so far (1..upto) are computed; data they lack is recorded once as site feedback for the next review."""
    from app.services import opportunity as op
    from app.services import walk

    part = _part_or_404(session, part_id)
    ctx = _part_context(session, part, False, "", "auto", "", DEFAULT_MAX_DEVIATIONS, "", False)
    upto = min(max(upto, 2), 5)
    w = walk.walk(session, part, ctx["rows"], upto)
    w["gaps"] = [g for g in w["gaps"] if g[0] <= upto]
    added = walk.record_gaps(session, part, w["gaps"])
    ctx.update(w=w, steps=walk.STEPS, added=added, crowding_label=op.CROWDING_LABEL, path_label=op.PATH_LABEL)
    if w.get("cards") is not None:  # step 2 seen from the customer, searchable by general category
        q = q.strip()[:200]
        shown = {id(c) for c in walk.filter_cards(w["cards"], q)}
        ctx.update(q=q, shown=[id(c) in shown for c in w["cards"]], cats=walk.category_counts(w["cards"]),
                   phrases=walk.search_phrases())  # fmt: skip
    return templates.TemplateResponse(request, "walk.html", ctx)


@router.get("/parts/{part_id}/grouped", response_class=HTMLResponse)
def part_grouped(request: Request, part_id: int, hide_eol: bool = False, company: str = "", scope: str = "auto",
                 type: str = "", dev: int = DEFAULT_MAX_DEVIATIONS, grade: str = "",
                 session: Session = Depends(get_session)):  # fmt: skip
    """The 'grouped by cross type' view, loaded when it is opened (it repeats every table)."""
    part = _part_or_404(session, part_id)
    ctx = _part_context(session, part, hide_eol, company, scope, type, dev, grade, True)
    return templates.TemplateResponse(request, "_grouped.html", ctx)


@router.get("/parts/{part_id}/detail/{cand_id}", response_class=HTMLResponse)
def part_cross_detail(request: Request, part_id: int, cand_id: int, hide_eol: bool = False, company: str = "",
                      scope: str = "auto", type: str = "", dev: int = DEFAULT_MAX_DEVIATIONS, grade: str = "",
                      session: Session = Depends(get_session)):  # fmt: skip
    """One result row's details (differences, overlay, variants), loaded when the row is opened."""
    part = _part_or_404(session, part_id)
    ctx = _part_context(session, part, hide_eol, company, scope, type, dev, grade, True)
    hit = next(((r, v) for r, v in ctx["rows"] if r.candidate.id == cand_id), None)
    if hit is None:
        raise HTTPException(404, "Not a cross of this part with these filters")
    r, v = hit
    ctx.update(r=r, v=v, c=r.candidate, notes=cross_notes.notes_for(part.mpn, r.candidate.mpn))
    return templates.TemplateResponse(request, "_cross_detail.html", ctx)


@router.get("/parts/{part_id}/replacements.{fmt}")
def results_download(
    part_id: int, fmt: str, scope: str = "auto", company: str = "", type: str = "",
    dev: int = DEFAULT_MAX_DEVIATIONS, grade: str = "", session: Session = Depends(get_session),
):  # fmt: skip
    part = session.get(Part, part_id)
    if part is None:
        raise HTTPException(404, "Part not found")
    crosses = crosses_for(session, part, scope if scope in ("auto", "all") else "auto", _deviations(dev))
    if company:
        crosses = {c: [r for r in rs if r.candidate.manufacturer.name == company] for c, rs in crosses.items()}
    rows = [(r, v) for r, v in result_rows(crosses) if not type or v.category == type]
    if grade in GRADE_LABELS:
        rows = [(r, v) for r, v in rows if grade_of(r.candidate) == grade]
    if fmt == "xlsx":
        return _download(export.results_xlsx(part, rows), f"replacements_{part.mpn}.xlsx", XLSX)
    if fmt == "csv":
        return _download(export.results_csv(rows), f"replacements_{part.mpn}.csv", "text/csv")
    raise HTTPException(404, "Unknown format")


@router.get("/cross/{ref_id}/{cand_id}.{fmt}")
def cross_download(ref_id: int, cand_id: int, fmt: str, session: Session = Depends(get_session)):
    result = single_cross(session, ref_id, cand_id)
    if result is None:
        raise HTTPException(404, "Cross not found")
    name = f"cross_{result.reference.mpn}_vs_{result.candidate.mpn}"
    if fmt == "xlsx":
        return _download(export.cross_xlsx(result), name + ".xlsx", XLSX)
    if fmt == "csv":
        return _download(export.cross_csv(result), name + ".csv", "text/csv")
    raise HTTPException(404, "Unknown format")


def _overlay(ref_pkg: Package, cand_pkg: Package, ref_label: str, cand_label: str, lp: int):
    ref = mechanical.outline(ref_pkg, ref_label, lp)
    cand = mechanical.outline(cand_pkg, cand_label, lp if ref_pkg.code == cand_pkg.code else 0)
    return mechanical.compare(ref, cand)


def _overlay_page(request: Request, ov, ref_pkg: Package, base: str, lp: int, parts=(None, None)):
    return templates.TemplateResponse(
        request,
        "overlay.html",
        {
            "ov": ov,
            "svg": mechanical.svg(ov),
            "ref_part": parts[0],
            "cand_part": parts[1],
            "land_patterns": ov.ref.mech.land_patterns if ov.ref.mech else (),
            "lp": lp,
            "base": base,
        },
    )


@router.get("/overlay/{ref_id}/{cand_id}.svg")
def overlay_svg(ref_id: int, cand_id: int, lp: int = 0, session: Session = Depends(get_session)):
    ref, cand = session.get(Part, ref_id), session.get(Part, cand_id)
    if ref is None or cand is None or ref.package is None or cand.package is None:
        raise HTTPException(404, "Part or package not found")
    ov = _overlay(ref.package, cand.package, ref.mpn, cand.mpn, lp)
    return _download(
        mechanical.svg(ov, standalone=True).encode(), f"overlay_{ref.mpn}_vs_{cand.mpn}.svg", "image/svg+xml"
    )


@router.get("/overlay/{ref_id}/{cand_id}", response_class=HTMLResponse)
def overlay_page(request: Request, ref_id: int, cand_id: int, lp: int = 0, session: Session = Depends(get_session)):
    """Package outline, leads and pads of a cross drawn on top of each other."""
    ref, cand = session.get(Part, ref_id), session.get(Part, cand_id)
    if ref is None or cand is None or ref.package is None or cand.package is None:
        raise HTTPException(404, "Part or package not found")
    ov = _overlay(ref.package, cand.package, ref.mpn, cand.mpn, lp)
    return _overlay_page(request, ov, ref.package, f"/overlay/{ref_id}/{cand_id}", lp, (ref, cand))


@router.get("/packages/{a_id}/overlay/{b_id}", response_class=HTMLResponse)
def package_overlay(request: Request, a_id: int, b_id: int, lp: int = 0, session: Session = Depends(get_session)):
    """The same drawing for two packages, without parts (used by the static preview)."""
    a, b = session.get(Package, a_id), session.get(Package, b_id)
    if a is None or b is None:
        raise HTTPException(404, "Package not found")
    ov = _overlay(a, b, a.code, b.code, lp)
    return _overlay_page(request, ov, a, f"/packages/{a_id}/overlay/{b_id}", lp)


@router.get("/impact")
def impact_page(ids: str = "", ref: str = "", cand: str = ""):
    """Old address of the CMTI explorer: now the CMTI engineering note (its ids, or a reference and candidate)."""
    ids = ids or ",".join(x for x in (ref, cand) if x)
    return RedirectResponse(f"/engineering/cmti_kv_us?ids={urllib.parse.quote(ids, safe=',')}", status_code=307)


@router.get("/notes", include_in_schema=False)
def notes_moved(q: str = ""):
    return RedirectResponse("/technical" + (f"?q={urllib.parse.quote(q)}" if q else ""), status_code=307)


@router.get("/technical", response_class=HTMLResponse)
def notes_search_page(request: Request, q: str = ""):
    """Keyword search over the Skyworks application notes and the engineering notes (local only)."""
    hits = notes_search.search(q[:200], limit=60)
    per_doc: dict[str, int] = {}
    shown = []
    for h in hits:  # at most three passages per document, so one long note does not fill the page
        per_doc[h.ref] = per_doc.get(h.ref, 0) + 1
        if per_doc[h.ref] <= 3:
            shown.append(h)
    notes, pages = notes_search.count()
    return templates.TemplateResponse(
        request,
        "notes_search.html",
        {"q": q, "hits": shown[:25], "n_notes": notes, "n_pages": pages, "n_ti": notes_search.count_ti()},
    )


@router.get("/rf-bands", response_class=HTMLResponse)
def rf_bands_page(request: Request, band: str = ""):
    from app.services import rf_bands

    d = rf_bands.data()
    ctx = {"groups": d["groups"], "bands": d["bands"], "band": band if rf_bands.band(band) else "",
           "counts": rf_bands.band_counts(), "types": d.get("types") or [],
           "apps": d.get("applications") or []}  # fmt: skip
    return templates.TemplateResponse(request, "engineering/rf_bands.html", ctx)


@router.get("/rf-bands/{band_id}", response_class=HTMLResponse)
def rf_band_detail(request: Request, band_id: str):
    """The details panel of one band: what it is, the front-end parts it calls for, and our parts that cover it."""
    from app.services import rf_bands

    b = rf_bands.band(band_id)
    if b is None:
        raise HTTPException(404, "Unknown band")
    g = b["group"]
    ctx = {"b": b, "group": rf_bands.data()["groups"].get(g, ""), "note": rf_bands.GROUP_NOTES.get(g, ""),
           "parts": rf_bands.parts_for(band_id), "rivals": rf_bands.parts_for(band_id, competitors=True)}  # fmt: skip
    return templates.TemplateResponse(request, "engineering/_rf_band.html", ctx)


@router.get("/visuals", response_class=HTMLResponse)
def visuals_page(request: Request, session: Session = Depends(get_session)):
    """Interactive visuals: sliders, live graphs and equations; reference lines from the cross lists."""
    from app.services import visuals

    data = {**visuals.reference_values(session), "creepage": visuals.package_creepage(session)}
    return templates.TemplateResponse(request, "engineering/visuals.html", {"data": data})


@router.get("/api/visuals/rf-parts")
def visuals_rf_parts():
    """Active Skyworks / Qorvo RF parts with gain, NF, IP3, P1dB, loss and band, for the receiver visuals."""
    from app.services import visuals

    return {"parts": visuals.rf_parts()}


@router.get("/library", response_class=HTMLResponse)
def library_index(request: Request):
    """Full systems (owner, 23 Oct 2026): each system is a header with its sub-systems, their diagram counts and deep
    dives; topics not yet in a system follow at the end."""
    from app.services import library
    from app.services import systems as sy

    topics = library.topics()
    by_key = {t["key"]: t for t in topics}
    tree = [{**s, "subs": [{**x, "deep": [by_key[k] for k in x["topics"] if k in by_key]} for x in s["subsystems"]]}
            for s in sy.systems()]  # fmt: skip
    for s in tree:
        s["deep"] = [t for x in s["subs"] for t in x["deep"]]
        s["n"] = len({i for x in s["subs"] for i in x["idx"]})
    placed = {t["key"] for s in tree for t in s["deep"]}
    ctx = {"tree": tree, "topics": topics, "other": [t for t in topics if t["key"] not in placed],
           "n_other_diagrams": len(sy.unassigned()), "n_sources": len(library.sources())}  # fmt: skip
    return templates.TemplateResponse(request, "library/index.html", ctx)


@router.get("/library/sources", response_class=HTMLResponse)
def library_sources(request: Request):
    from app.services import library

    return templates.TemplateResponse(request, "library/sources.html", {"sources": library.sources(),
                                                                        "feas": library.FEASIBILITY})  # fmt: skip


@router.get("/library/{key}", response_class=HTMLResponse)
def library_topic(request: Request, key: str, session: Session = Depends(get_session)):
    from app.services import library

    if library.topic(key) is None:
        raise HTTPException(404, "Topic not found")
    t = library.reviewed(session, key)
    ctx = {"t": t, "key": key, "refs": library.refs_by_id(t), "horizon": library.HORIZON, "label": vocab.fn_label,
           "notes": library.notes(key), "cases": library.cases_using(key), "related": library.related(key),
           "rule_links": library.rule_links}  # fmt: skip
    return templates.TemplateResponse(request, "library/topic.html", ctx)


@router.post("/library/{key}/react")
def library_react(key: str, item: str = Form(...), verdict: str = Form(...), comment: str = Form(""),
                  author: str = Form(""), session: Session = Depends(get_session)):  # fmt: skip
    """A reviewer agrees or disagrees with a design rule or trend; a disagreement lowers its confidence one step."""
    from app.services import library

    try:
        library.react(session, key, item, verdict, comment, author)
    except ValueError as e:
        raise HTTPException(400, "Unknown item or verdict") from e
    return RedirectResponse(f"/library/{key}#i-{item}", status_code=303)


@router.get("/knowledge", response_class=HTMLResponse)
def general_knowledge(request: Request):
    """General knowledge: the background the systems library builds on (RF fundamentals, specification guides,
    technology platforms) and the search over all of it."""
    from app.services import knowledge, library, rf_notes

    ctx = {"rf": rf_notes.by_category(), "guides": engineering.index(), "topics": library.topics(),
           "products": knowledge.by_product(), "kinds": knowledge.KINDS}  # fmt: skip
    return templates.TemplateResponse(request, "engineering/knowledge.html", ctx)


@router.get("/rf-notes", response_class=HTMLResponse)
def rf_notes_page(request: Request):
    from app.services import rf_notes
    from app.services.knowledge import KINDS

    ctx = {"groups": rf_notes.by_category(), "links": rf_notes.links, "kinds": KINDS}
    return templates.TemplateResponse(request, "engineering/rf_notes.html", ctx)


@router.get("/engineering", response_class=HTMLResponse)
def engineering_index(request: Request):
    return templates.TemplateResponse(request, "engineering/index.html", {"notes": engineering.index()})


@router.get("/engineering/{key}", response_class=HTMLResponse)
def engineering_note(
    request: Request, key: str, ref: int | None = None, cand: int | None = None, ids: str = "",
    session: Session = Depends(get_session),
):  # fmt: skip
    """One engineering note. ``ref``/``cand`` come from a result row; ``ids`` lists parts for
    the calculators (reference first, four at most)."""
    from app.services import knowledge

    note = engineering.note_key(key)
    reference = session.get(Part, ref) if ref else None
    candidate = session.get(Part, cand) if cand else None
    param = engineering.param_def(key, reference.family if reference else None)
    if param is None and note not in engineering.NOTES:
        raise HTTPException(404, "No such specification")
    wanted = _parse_ids(ids) or [p for p in (ref, cand) if p]
    parts = parts_by_ids(session, wanted)[:4]
    title, summary = engineering.NOTES.get(note, (param.label if param else key, ""))
    return templates.TemplateResponse(
        request,
        "engineering/note.html",
        {
            "key": note,
            "title": title,
            "summary": summary,
            "param": param,
            "families": engineering.families_using(key),
            "ctx": engineering.context(key, reference, candidate),
            "body": f"engineering/notes/{note}.html" if engineering.has_body(note) else None,
            "parts": parts,
            "devices": [engineering.device(p) for p in parts],
            "others": [n for n in engineering.index() if n["key"] != note],
            "why": knowledge.why(note),
            "kinds": knowledge.KINDS,
        },
    )


def series_of(mpn: str) -> str:
    """Product series for grouping: the part number up to its last base digit, with that digit as x
    (SI8641BD-IS -> SI864x, SI86S641BE-IS2 -> SI86S64x, ISO7741DWR -> ISO774x)."""
    m = re.match(r"[A-Z]+\d+(?:[A-Z]\d{2,})?", re.split(r"[-.]", mpn.upper())[0])
    return f"{m.group(0)[:-1]}x" if m and m.group(0)[-1].isdigit() else mpn.upper()


@router.get("/compare", response_class=HTMLResponse)
def compare_page(
    request: Request,
    ids: str = "",
    baseline: int | None = None,
    family: str = "",
    add: str = "",
    alt: int = 1,
    pick: list[int] = Query(default=[]),
    session: Session = Depends(get_session),
):
    wanted = _parse_ids(ids)
    wanted += [i for i in pick if i not in wanted]
    # typed part numbers: exact matches are added, a prefix with several matches is offered to pick from
    matches, not_found, ambiguous = [], [], []
    for token in [t for t in re.split(r"[,;\s]+", add) if t][:20]:
        key = normalize_pn(token)
        hits = [p for p in search_parts(session, token) if normalize_pn(p.mpn).startswith(key)]
        exact = [p for p in hits if normalize_pn(p.mpn) == key]
        if exact or len(hits) == 1:
            wanted += [p.id for p in (exact or hits) if p.id not in wanted]
        elif hits:
            matches += [p for p in hits if p not in matches]
            ambiguous.append(token)
        else:
            not_found.append(token)
    selected = parts_by_ids(session, wanted)
    # Si86 / Si86S: add the best alternate of each selected part
    alt_of = {}
    if alt:
        for p in list(selected):
            for a in alternates.alternates(session, p, limit=1):
                if a.part.id not in [x.id for x in selected]:
                    selected.append(a.part)
                    alt_of[a.part.id] = (p.mpn, a)
    comparison = None
    if selected:
        family = selected[0].family if add or not family else family
        base = next((p for p in selected if p.id == baseline), selected[0])
        comparison = compare_parts(selected, base, get_rules(base.family))
        if pricing.enabled():
            try:
                pricing.add_to_comparison(session, comparison)
                session.commit()
            except pricing.DigiKeyError:
                session.rollback()
    if matches and add:
        family = matches[0].family
    support = family_support(session)
    family = family or next((k for k, e in support.items() if e["parts"]), next(iter(support)))
    # the series list shows part number, maker and package only: parameters are not loaded
    q = select(Part).where(Part.family == family).order_by(Part.mpn).options(lazyload(Part.params))
    available = list(session.scalars(q).unique())
    series: dict[str, list[Part]] = {}
    for p in available:
        series.setdefault(series_of(p.mpn), []).append(p)
    return templates.TemplateResponse(
        request,
        "compare.html",
        {
            "comparison": comparison,
            "selected": selected,
            "series": series,
            "family": family,
            "ids": ",".join(str(p.id) for p in selected if p.id not in alt_of),
            "add": add,
            "matches": matches,
            "ambiguous": ambiguous,
            "not_found": not_found,
            "alt": alt,
            "alt_of": alt_of,
            "support": support,
        },
    )


@router.get("/compare.{fmt}")
def compare_download(fmt: str, ids: str, baseline: int | None = None, session: Session = Depends(get_session)):
    selected = parts_by_ids(session, _parse_ids(ids))
    if not selected:
        raise HTTPException(400, "No parts selected")
    base = next((p for p in selected if p.id == baseline), selected[0])
    comparison = compare_parts(selected, base, get_rules(base.family))
    if pricing.enabled():
        try:
            pricing.add_to_comparison(session, comparison)
            session.commit()
        except pricing.DigiKeyError:
            session.rollback()
    if fmt == "xlsx":
        return _download(export.comparison_xlsx(comparison), "comparison.xlsx", XLSX)
    if fmt == "csv":
        return _download(export.comparison_csv(comparison), "comparison.csv", "text/csv")
    raise HTTPException(404, "Unknown format")


@router.get("/rules", response_class=HTMLResponse)
def rules_page(request: Request):
    return templates.TemplateResponse(request, "rules.html", {"all_rules": load_all_rules()})


@router.post("/feedback")
def feedback(
    reference_id: int = Form(...),
    candidate_id: int = Form(...),
    verdict: str = Form(...),
    note: str = Form(""),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    """Reject an FFF cross (it is then listed as a package equivalent); "clear" undoes it."""
    if verdict not in ("reject", "clear"):
        raise HTTPException(400, "verdict must be reject or clear")
    if session.get(Part, reference_id) is None or session.get(Part, candidate_id) is None:
        raise HTTPException(404, "Part not found")
    record_feedback(session, reference_id, candidate_id, None if verdict == "clear" else verdict, note, user.id)
    return RedirectResponse(f"/parts/{reference_id}#row-{candidate_id}", status_code=303)




@router.get("/pricing/{part_id:int}", response_class=HTMLResponse)
def pricing_line(
    request: Request,
    part_id: int,
    ref: int | None = None,
    compact: bool = False,
    session: Session = Depends(get_session),
):
    """Price and stock from DigiKey (cached), loaded into the part page as it scrolls into view."""
    part = session.get(Part, part_id)
    if part is None:
        raise HTTPException(404, "Part not found")
    error, pq, ref_pq = None, None, None
    try:
        pq = pricing.quote_for(session, part)
        if ref is not None and (ref_part := session.get(Part, ref)) is not None:
            ref_pq = pricing.quote_for(session, ref_part)
        session.commit()
    except pricing.DigiKeyError as e:
        session.rollback()
        error = str(e)
    prices = [
        (q, pricing.price_at(pq, q), pricing.delta_pct(ref_pq, pq, q) if ref_pq else None) for q in pricing.QUANTITIES
    ]
    return templates.TemplateResponse(
        request,
        "_pricing.html",
        {
            "pq": pq,
            "prices": prices[-1:] if compact else prices,
            "compact": compact,
            "error": error,
            "symbol": "$",  # price_at converts every quote to USD
        },
    )


@router.get("/pricing/{part_id}/model", response_class=HTMLResponse)
def price_model_panel(request: Request, part_id: int, sop: int = 0, gm: int = 0,
                      session: Session = Depends(get_session)):  # fmt: skip
    """Rough price band at 10k / 100k / 1M a year from the cached DigiKey breaks and a cost floor (estimate). Every
    wafer-source scenario is worked out; the reader switches between them in the browser only."""
    part = _part_or_404(session, part_id)
    try:
        pq = pricing.quote_for(session, part)
        session.commit()
    except pricing.DigiKeyError:
        session.rollback()
        pq = pricing.quote_for(session, part, fetch=False)
    scenarios = []
    for fab in price_model.fab_scenarios():
        m = price_model.model(session, part, pq, gm / 100 if gm else None, fab)
        m["oem"] = price_model.oem_path(m, sop if 2020 <= sop <= 2050 else None,
                                        released=part.release_date.year if part.release_date else None)
        scenarios.append((fab, m))
    ctx = {"part": part, "m": scenarios[0][1], "scenarios": scenarios, "calls": price_model.CALLS,
           "cfg": price_model.config(),
           "symbol": "$"}  # fmt: skip  # every model price is in USD
    return templates.TemplateResponse(request, "_price_model.html", ctx)


@router.get("/pricing/estimate", response_class=HTMLResponse)
def price_estimate(request: Request, family: str = "", breaks: str = "", package: str = "", pins: int = 0,
                   automotive: bool = False, name: str = "", currency: str = "USD",
                   sop: int = 0, gm: int = 0,
                   released: int = 0, bq: list[str] = Query([]), bp: list[str] = Query([]),
                   session: Session = Depends(get_session)):  # fmt: skip
    """A rough price band for any part from a few pasted distributor price breaks (same model as the part pages).
    A part number the site knows sets the family, package, pins and channels; otherwise they are entered freely.
    Several orderable variants of the part number are offered to pick from. SOP defaults to the year of the
    datasheet's first revision when the site knows it. Price breaks come as volume / price rows, pasted text or
    both."""
    cfg = price_model.config()
    known = price_builder.site_info(session, name.strip()) if name.strip() else {}
    variants = price_builder.variants(session, name) if name.strip() else []
    rows = [(q.strip(), p.strip()) for q, p in zip(bq, bp, strict=False) if q.strip() or p.strip()]
    pasted = breaks
    breaks = "\n".join([breaks.strip(), *(f"{q} {p}" for q, p in rows if q and p)]).strip()
    family = family if family in cfg["families"] else (known.get("family") or "")
    package, pins = (known["package"], known["pins"] or pins) if known.get("package") else (package, pins)
    units = known.get("units") or 0  # channels / tuners: read from the part number, used by the model only
    released = released or (known.get("released") or 0)
    automotive = automotive or bool(known.get("automotive"))
    pts = price_model.parse_breaks(breaks)
    currency = currency if currency in price_model.config()["fx"]["usd_per"] else "USD"
    gm_f = price_model.margin(gm / 100 if gm else None)
    sop_from = "entered" if 1980 <= sop <= 2050 else ""
    if not sop_from and known.get("released"):
        sop, sop_from = known["released"], "datasheet"  # the year of the datasheet's first revision
    sop = sop if 1980 <= sop <= 2050 else cfg["oem"]["default_sop"]
    released = released if 1980 <= released <= 2050 else None
    scenarios = []
    for fab in price_model.fab_scenarios() if (family and pts) else []:
        m = price_model.estimate(session, family, pts, package, pins, automotive, name or "estimate", currency,
                                 gm_f, fab, units or None)  # fmt: skip
        m["oem"] = price_model.oem_path(m, sop, released=released)
        m["name"] = name.strip()[:60]
        scenarios.append((fab, m))
    m = scenarios[0][1] if scenarios else None
    ctx = {"cfg": cfg, "m": m, "scenarios": scenarios,
           "known": known, "suggest": price_builder.suggestions(), "variants": variants, "sop_from": sop_from,
           "rows": rows or [("", "")], "pasted": pasted,
           "f": {"family": family, "breaks": breaks, "package": package, "pins": pins or "",
                 "automotive": automotive, "name": name, "currency": currency, "sop": sop, "gm": round(gm_f * 100),
                 "released": released or ""},
           "symbol": "$", "estimate": True, "part": None,
           "calls": price_model.CALLS}  # fmt: skip
    return templates.TemplateResponse(request, "price_estimate.html", ctx)


@router.api_route("/pricing/builder", methods=["GET", "POST"], response_class=HTMLResponse)
async def price_builder_page(request: Request, session: Session = Depends(get_session)):
    """Solution price builder: add parts (or load a radio preset or a saved diagram), paste DigiKey prices, set the
    assumptions with sliders and see each part and the system total. Posted, never stored or put in the link."""
    form = await request.form() if request.method == "POST" else request.query_params
    cfg = price_model.config()
    rows = price_builder.rows_from_form(form)
    if form.get("do") == "load" and form.get("load"):
        rows += price_builder.load(session, str(form["load"]))
    vols = [int(v) for v in cfg["volumes"]]
    vol = int(form.get("vol") or 0) if str(form.get("vol") or "").isdigit() else 0
    vol = vol if vol in vols else vols[-1]
    gm = price_model.margin(int(form.get("gm") or 0) / 100 if str(form.get("gm") or "").isdigit() else None)
    adj = min(max(int(form.get("adj") or 100) if str(form.get("adj") or "").isdigit() else 100, 50), 150)
    sop = int(form.get("sop") or 0) if str(form.get("sop") or "").isdigit() else 0
    sop = sop if 2020 <= sop <= 2050 else cfg["oem"]["default_sop"]
    result = price_builder.solution(session, rows, vol, gm, adj / 100, sop) if rows else None
    ctx = {"cfg": cfg, "rows": rows, "result": result, "vols": vols,
           "g": {"vol": vol, "gm": round(gm * 100), "adj": adj, "sop": sop},
           "presets": price_builder.presets(session), "suggest": price_builder.suggestions(),
           "scenarios": [(f, None) for f in price_model.fab_scenarios()]}  # fmt: skip
    return templates.TemplateResponse(request, "price_builder.html", ctx)


@router.post("/pricing/{part_id}/call")
def price_model_call(part_id: int, verdict: str = Form(...), comment: str = Form(""), author: str = Form(""),
                     session: Session = Depends(get_session)):  # fmt: skip
    """The owner's call: real prices of this part sit at the low end, in the band or at the high end."""
    part = _part_or_404(session, part_id)
    try:
        price_model.record(session, part.mpn, verdict, comment, author)
    except ValueError as e:
        raise HTTPException(400, "Unknown call") from e
    return RedirectResponse(f"/parts/{part.id}?price=open#price-model", status_code=303)


@router.get("/suggest", response_class=HTMLResponse)
def suggest(request: Request, q: str = "", session: Session = Depends(get_session)):
    """Live part-number suggestions (HTML fragment for the header search box)."""
    from app.services import products

    parts = search_parts(session, q, limit=60) if len(normalize_pn(q).replace("*", "")) >= 2 else []
    catalogue = products.search_catalogue(q, {normalize_pn(p.mpn) for p in parts}, limit=max(0, 60 - len(parts)))
    return templates.TemplateResponse(request, "_suggest.html", {"parts": parts, "catalogue": catalogue, "q": q})
