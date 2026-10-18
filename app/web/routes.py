"""HTML pages."""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_session
from app.matching.engine import CATEGORY_LABELS, CATEGORY_ORDER, LIFECYCLE_RISK, format_value
from app.matching.rules import get_rules, load_all_rules
from app.models import ChangeEvent, LifecycleStatus, Part
from app.services import export, lifecycle
from app.services.compare import compare_parts
from app.services.queries import crosses_for, parts_by_ids, search_parts, single_cross

router = APIRouter()
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals.update(
    lifecycle_badge=lifecycle.badge,
    category_labels=CATEGORY_LABELS,
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
    role: str = "reference",
    lifecycle_status: str = Query("", alias="lifecycle"),
    session: Session = Depends(get_session),
):
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


@router.get("/parts/{part_id}", response_class=HTMLResponse)
def part_detail(request: Request, part_id: int, hide_eol: bool = False, session: Session = Depends(get_session)):
    part = session.get(Part, part_id)
    if part is None:
        raise HTTPException(404, "Part not found")
    rules = get_rules(part.family)
    crosses = crosses_for(session, part)
    if hide_eol:
        crosses = {c: [r for r in rs if not r.lifecycle_risk] for c, rs in crosses.items()}
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
