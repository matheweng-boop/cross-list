"""Shared database queries."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.matching.engine import CrossResult, cross, find_crosses
from app.matching.rules import get_rules
from app.models import LifecycleStatus, Manufacturer, ManufacturerRole, Part


def search_parts(
    session: Session,
    q: str = "",
    family: str = "",
    role: str = "",
    lifecycle: str = "",
    limit: int = 200,
) -> list[Part]:
    stmt = select(Part).join(Part.manufacturer)
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Part.mpn.ilike(like), Part.description.ilike(like), Manufacturer.name.ilike(like)))
    if family:
        stmt = stmt.where(Part.family == family)
    if role:
        stmt = stmt.where(Manufacturer.role == ManufacturerRole(role))
    if lifecycle:
        stmt = stmt.where(Part.lifecycle_status == LifecycleStatus(lifecycle))
    stmt = stmt.order_by(Manufacturer.role, Part.family, Part.mpn).limit(limit)
    return list(session.scalars(stmt).unique())


def candidates_for(session: Session, ref: Part) -> list[Part]:
    stmt = select(Part).where(Part.family == ref.family, Part.id != ref.id, Part.manufacturer_id != ref.manufacturer_id)
    return list(session.scalars(stmt).unique())


def crosses_for(session: Session, ref: Part) -> dict[str, list[CrossResult]]:
    return find_crosses(ref, candidates_for(session, ref), get_rules(ref.family))


def single_cross(session: Session, ref_id: int, cand_id: int) -> CrossResult | None:
    ref, cand = session.get(Part, ref_id), session.get(Part, cand_id)
    if ref is None or cand is None or ref.family != cand.family:
        return None
    return cross(ref, cand, get_rules(ref.family))


def parts_by_ids(session: Session, ids: list[int]) -> list[Part]:
    found = {p.id: p for p in session.scalars(select(Part).where(Part.id.in_(ids))).unique()}
    return [found[i] for i in ids if i in found]
