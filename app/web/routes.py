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
from app.matching.engine import CATEGORY_LABELS, CATEGORY_ORDER, FFF_STATUS_LABELS, LIFECYCLE_RISK, format_value
from app.matching.rules import get_rules, load_all_rules
from app.models import ChangeEvent, LifecycleStatus, Part, User
from app.services import export, lifecycle
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


# Order in which a candidate's best category is shown in the per-company rows.
BEST_RANK = {("fff", "auto"): 0, ("fff", "accepted"): 0, ("fff", "review"): 1, "upgrade": 2, "p2p": 3, "downgrade": 4}
BEST_LABEL = {0: "FFF", 1: "FFF – review", 2: "Upgrade", 3: "Pin-to-pin", 4: "Downgrade"}


def by_company(crosses: dict) -> list[tuple[str, list[dict]]]:
    """Each candidate once, under its best category, grouped by manufacturer."""
    best: dict[int, dict] = {}
    for cat, results in crosses.items():
        for r in results:
            rank = BEST_RANK[(cat, r.fff_status)] if cat == "fff" else BEST_RANK[cat]
            cur = best.get(r.candidate.id)
            if cur is None or rank < cur["rank"]:
                best[r.candidate.id] = {"rank": rank, "label": BEST_LABEL[rank], "cat": cat, "r": r}
    groups: dict[str, list[dict]] = {}
    for item in best.values():
        groups.setdefault(item["r"].candidate.manufacturer.name, []).append(item)
    for items in groups.values():
        items.sort(key=lambda i: (i["r"].lifecycle_risk, i["rank"], i["r"].closeness))
    return sorted(groups.items(), key=lambda g: (min(i["rank"] for i in g[1]), g[0]))


@router.get("/parts/{part_id}", response_class=HTMLResponse)
def part_detail(
    request: Request,
    part_id: int,
    hide_eol: bool = False,
    company: str = "",
    scope: str = "auto",
    session: Session = Depends(get_session),
):
    part = session.get(Part, part_id)
    if part is None:
        raise HTTPException(404, "Part not found")
    rules = get_rules(part.family)
    scope = scope if scope in ("auto", "all") else "auto"
    crosses = crosses_for(session, part, scope)
    rejected = [r for r in crosses["p2p"] if r.fff_status == "rejected"]
    if hide_eol:
        crosses = {c: [r for r in rs if not r.lifecycle_risk] for c, rs in crosses.items()}
    companies = by_company(crosses)
    if company:
        crosses = {c: [r for r in rs if r.candidate.manufacturer.name == company] for c, rs in crosses.items()}
    values = part.param_map()
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
        },
    )


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
    """Accept or reject a cross that needs review as FFF ("clear" removes the decision)."""
    if verdict not in ("accept", "reject", "clear"):
        raise HTTPException(400, "verdict must be accept, reject or clear")
    if session.get(Part, reference_id) is None or session.get(Part, candidate_id) is None:
        raise HTTPException(404, "Part not found")
    record_feedback(session, reference_id, candidate_id, None if verdict == "clear" else verdict, note, user.id)
    return RedirectResponse(f"/parts/{reference_id}#fff-{candidate_id}", status_code=303)


@router.get("/suggest", response_class=HTMLResponse)
def suggest(request: Request, q: str = "", session: Session = Depends(get_session)):
    """Live part-number suggestions (HTML fragment for the header search box)."""
    parts = search_parts(session, q, limit=60) if len(normalize_pn(q).replace("*", "")) >= 2 else []
    return templates.TemplateResponse(request, "_suggest.html", {"parts": parts, "q": q})
