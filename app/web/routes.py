"""HTML pages."""

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user
from app.config import get_settings
from app.db import get_session
from app.matching.engine import (
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    CATEGORY_SHORT,
    DEFAULT_MAX_DEVIATIONS,
    FFF_STATUS_LABELS,
    LIFECYCLE_RISK,
    format_value,
)
from app.matching.rules import get_rules, load_all_rules
from app.models import ChangeEvent, LifecycleStatus, Package, Part, User
from app.services import engineering, export, lifecycle, mechanical, pricing
from app.services.compare import compare_parts
from app.services.queries import (
    crosses_for,
    normalize_pn,
    parts_by_ids,
    record_feedback,
    search_parts,
    single_cross,
)

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals.update(
    lifecycle_badge=lifecycle.badge,
    category_labels=CATEGORY_LABELS,
    fff_labels=FFF_STATUS_LABELS,
    family_titles=lambda: {k: v.title for k, v in load_all_rules().items()},
    pricing_enabled=pricing.enabled,
    qty_label=pricing.qty_label,
    site_locked=lambda: bool(get_settings().site_password),
    category_short=CATEGORY_SHORT,
)


def _is_new(part: Part) -> bool:
    return lifecycle.is_new(part, get_settings().new_part_days)


templates.env.globals["is_new"] = _is_new


def _has_synthetic() -> bool:
    from app.db import get_engine

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
    matches = search_parts(session, q, limit=500)
    exact = [p for p in matches if normalize_pn(p.mpn) == normalize_pn(q)]
    if len(exact) == 1 or len(matches) == 1:
        return RedirectResponse(f"/parts/{(exact or matches)[0].id}", status_code=303)
    competitors = [p for p in matches if not p.is_reference]
    references = [p for p in matches if p.is_reference]
    return templates.TemplateResponse(
        request, "find_results.html", {"q": q, "competitors": competitors, "references": references}
    )


@router.get("/parts", response_class=HTMLResponse)
def index(
    request: Request,
    q: str = "",
    family: str = "",
    role: str | None = None,
    lifecycle_status: str = Query("", alias="lifecycle"),
    session: Session = Depends(get_session),
):
    # Without a search the list shows the reference parts; a search covers every company.
    role = role if role is not None else ("" if q.strip() else "reference")
    parts = search_parts(session, q, family, role, lifecycle_status)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "parts": parts,
            "q": q,
            "family": family,
            "role": role,
            "lifecycle": lifecycle_status,
            "statuses": list(LifecycleStatus),
        },
    )


CATEGORY_RANK = {c: i for i, c in enumerate(CATEGORY_ORDER)}


def result_rows(crosses: dict) -> list:
    """Each listed candidate once with its verdict, in order of preference: drop-ins,
    functional equivalents (fewest deviations first), package equivalents (pin-to-pin
    first); closest first within each."""
    seen = {}
    for cat in CATEGORY_ORDER:
        for r in crosses.get(cat, []):
            seen.setdefault(r.candidate.id, r)
    rows = [(r, r.verdict()) for r in seen.values()]

    def key(rv):
        r, v = rv
        devs = len(r.deviations) if v.category == "functional" else 0
        return (r.lifecycle_risk, CATEGORY_RANK[v.category], devs, not v.p2p, r.closeness)

    rows.sort(key=key)
    return rows


def _deviations(dev: int) -> int:
    return min(max(dev, 0), 3)


def companies_of(rows: list) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for r, _ in rows:
        counts[r.candidate.manufacturer.name] = counts.get(r.candidate.manufacturer.name, 0) + 1
    return sorted(counts.items())


@router.get("/parts/{part_id}", response_class=HTMLResponse)
def part_detail(
    request: Request,
    part_id: int,
    hide_eol: bool = False,
    company: str = "",
    scope: str = "auto",
    type: str = "",
    dev: int = DEFAULT_MAX_DEVIATIONS,
    session: Session = Depends(get_session),
):
    part = session.get(Part, part_id)
    if part is None:
        raise HTTPException(404, "Part not found")
    rules = get_rules(part.family)
    scope = scope if scope in ("auto", "all") else "auto"
    dev = _deviations(dev)
    crosses = crosses_for(session, part, scope, dev)
    rejected = [r for r in crosses["package"] if r.fff_status == "rejected"]
    if hide_eol:
        crosses = {c: [r for r in rs if not r.lifecycle_risk] for c, rs in crosses.items()}
    companies = companies_of(result_rows(crosses))
    if company:
        crosses = {c: [r for r in rs if r.candidate.manufacturer.name == company] for c, rs in crosses.items()}
    rows = result_rows(crosses)
    type_counts = {c: sum(v.category == c for _, v in rows) for c in CATEGORY_ORDER}
    type = type if type in CATEGORY_ORDER else ""
    if type:
        rows = [(r, v) for r, v in rows if v.category == type]
    values = rules.values(part)
    sources = {pv.key: pv.source for pv in part.params}
    groups = {
        prio: [(p, format_value(p, values.get(p.key)), sources.get(p.key)) for p in rules.by_priority(prio)]
        for prio in (1, 2, 3)
    }
    return templates.TemplateResponse(
        request,
        "part.html",
        {
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
        },
    )


@router.get("/parts/{part_id}/replacements.{fmt}")
def results_download(
    part_id: int, fmt: str, scope: str = "auto", company: str = "", type: str = "",
    dev: int = DEFAULT_MAX_DEVIATIONS, session: Session = Depends(get_session),
):  # fmt: skip
    part = session.get(Part, part_id)
    if part is None:
        raise HTTPException(404, "Part not found")
    crosses = crosses_for(session, part, scope if scope in ("auto", "all") else "auto", _deviations(dev))
    if company:
        crosses = {c: [r for r in rs if r.candidate.manufacturer.name == company] for c, rs in crosses.items()}
    rows = [(r, v) for r, v in result_rows(crosses) if not type or v.category == type]
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
def impact_page(ids: str = ""):
    """Old address of the CMTI explorer: now the CMTI engineering note."""
    return RedirectResponse(f"/engineering/cmti_kv_us?ids={ids}", status_code=307)


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
        },
    )


@router.get("/compare", response_class=HTMLResponse)
def compare_page(
    request: Request,
    ids: str = "",
    baseline: int | None = None,
    family: str = "",
    pick: list[int] = Query(default=[]),
    session: Session = Depends(get_session),
):
    wanted = _parse_ids(ids)
    wanted += [i for i in pick if i not in wanted]
    selected = parts_by_ids(session, wanted)
    comparison = None
    if selected:
        family = family or selected[0].family
        base = next((p for p in selected if p.id == baseline), selected[0])
        comparison = compare_parts(selected, base, get_rules(base.family))
        if pricing.enabled():
            try:
                pricing.add_to_comparison(session, comparison)
                session.commit()
            except pricing.DigiKeyError:
                session.rollback()
    family = family or next(iter(load_all_rules()))
    available = list(session.scalars(select(Part).where(Part.family == family).order_by(Part.mpn)).unique())
    return templates.TemplateResponse(
        request,
        "compare.html",
        {
            "comparison": comparison,
            "selected": selected,
            "available": available,
            "family": family,
            "ids": ",".join(str(p.id) for p in selected),
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


@router.get("/lifecycle", response_class=HTMLResponse)
def lifecycle_page(request: Request, session: Session = Depends(get_session)):
    parts = list(session.scalars(select(Part)).unique())
    new_parts = sorted((p for p in parts if _is_new(p)), key=lambda p: p.release_date, reverse=True)
    at_risk = sorted(
        (p for p in parts if p.lifecycle_status in LIFECYCLE_RISK),
        key=lambda p: (p.lifecycle_status.value, p.mpn),
    )
    events = list(session.scalars(select(ChangeEvent).order_by(ChangeEvent.detected_at.desc()).limit(100)).unique())
    recent_revisions = sorted((p for p in parts if p.datasheet_date), key=lambda p: p.datasheet_date, reverse=True)[:15]
    return templates.TemplateResponse(
        request,
        "lifecycle.html",
        {"new_parts": new_parts, "at_risk": at_risk, "events": events, "recent_revisions": recent_revisions},
    )


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


CURRENCY_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£"}


@router.get("/pricing/{part_id}", response_class=HTMLResponse)
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
    currency = pq.currency if pq else get_settings().digikey_currency
    return templates.TemplateResponse(
        request,
        "_pricing.html",
        {
            "pq": pq,
            "prices": prices[-1:] if compact else prices,
            "compact": compact,
            "error": error,
            "symbol": CURRENCY_SYMBOLS.get(currency, currency + " "),
        },
    )


@router.get("/suggest", response_class=HTMLResponse)
def suggest(request: Request, q: str = "", session: Session = Depends(get_session)):
    """Live part-number suggestions (HTML fragment for the header search box)."""
    parts = search_parts(session, q, limit=60) if len(normalize_pn(q).replace("*", "")) >= 2 else []
    return templates.TemplateResponse(request, "_suggest.html", {"parts": parts, "q": q})
