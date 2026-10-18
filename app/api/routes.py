"""JSON API (same logic as the pages, for scripts and future clients)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_session
from app.matching.engine import CrossResult
from app.matching.rules import get_rules
from app.models import Part
from app.services.compare import compare_parts
from app.services.queries import crosses_for, parts_by_ids, search_parts

router = APIRouter()


def part_json(p: Part) -> dict:
    return {
        "id": p.id,
        "mpn": p.mpn,
        "manufacturer": p.manufacturer.name,
        "role": p.manufacturer.role.value,
        "family": p.family,
        "description": p.description,
        "package": p.package.code,
        "pinout": p.pinout,
        "package_locked": p.package_locked,
        "lifecycle": {
            "status": p.lifecycle_status.value,
            "release_date": p.release_date.isoformat() if p.release_date else None,
            "datasheet_revision": p.datasheet_revision,
            "datasheet_date": p.datasheet_date.isoformat() if p.datasheet_date else None,
            "source": p.lifecycle_source,
        },
        "synthetic": p.is_synthetic,
        "params": p.param_map(),
    }


def cross_json(r: CrossResult) -> dict:
    return {
        "candidate": {
            "id": r.candidate.id,
            "label": r.candidate.label,
            "lifecycle": r.candidate.lifecycle_status.value,
        },
        "categories": r.categories,
        "fit": {
            "same_package": r.fit.same_package,
            "package_relation": r.fit.package_relation,
            "same_pinout": r.fit.same_pinout,
        },
        "hard_fail": r.hard_fail,
        "incomplete": r.incomplete,
        "top_differences": [d.summary() for d in r.top_differences()],
        "differences": [
            {
                "key": d.key,
                "label": d.label,
                "priority": d.priority,
                "status": d.status,
                "reference": d.ref_display,
                "candidate": d.cand_display,
            }
            for d in r.all_diffs
        ],
    }


@router.get("/parts")
def list_parts(q: str = "", family: str = "", role: str = "", session: Session = Depends(get_session)):
    return [part_json(p) for p in search_parts(session, q, family, role)]


@router.get("/parts/{part_id}")
def get_part(part_id: int, session: Session = Depends(get_session)):
    part = session.get(Part, part_id)
    if part is None:
        raise HTTPException(404, "Part not found")
    return part_json(part)


@router.get("/parts/{part_id}/crosses")
def get_crosses(part_id: int, session: Session = Depends(get_session)):
    part = session.get(Part, part_id)
    if part is None:
        raise HTTPException(404, "Part not found")
    return {cat: [cross_json(r) for r in results] for cat, results in crosses_for(session, part).items()}


@router.get("/compare")
def compare(ids: str, baseline: int | None = None, session: Session = Depends(get_session)):
    selected = parts_by_ids(session, [int(i) for i in ids.split(",") if i.strip().isdigit()])
    if not selected:
        raise HTTPException(400, "No parts selected")
    base = next((p for p in selected if p.id == baseline), selected[0])
    c = compare_parts(selected, base, get_rules(base.family))
    return {
        "baseline": base.id,
        "parts": [p.label for p in c.parts],
        "rows": [
            {
                "priority": r.param.priority,
                "parameter": r.param.label,
                "values": [{"value": cell.display, "status": cell.status, "best": cell.best} for cell in r.cells],
            }
            for r in c.rows
        ],
    }
