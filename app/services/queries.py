"""Shared database queries."""

import re

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.matching.engine import CrossResult, cross, find_crosses
from app.matching.rules import get_rules
from app.models import CrossFeedback, FeedbackVerdict, LifecycleStatus, Manufacturer, ManufacturerRole, Part


def normalize_pn(text: str) -> str:
    """Part numbers compare without case, dashes, spaces or slashes; ``*`` is a wildcard."""
    return re.sub(r"[\s\-_/]", "", text).upper()


def _pn_column():
    col = func.upper(Part.mpn)
    for ch in ("-", " ", "_", "/"):
        col = func.replace(col, ch, "")
    return col


def search_parts(
    session: Session,
    q: str = "",
    family: str = "",
    role: str = "",
    lifecycle: str = "",
    limit: int = 200,
) -> list[Part]:
    stmt = select(Part).join(Part.manufacturer)
    order = []
    if q.strip():
        pn = normalize_pn(q).replace("*", "%")
        pn_col = _pn_column()
        text = f"%{q.strip()}%"
        stmt = stmt.where(or_(pn_col.like(f"%{pn}%"), Part.description.ilike(text), Manufacturer.name.ilike(text)))
        # Part numbers that start with the query first, then other part-number hits.
        order.append(case((pn_col.like(f"{pn}%"), 0), (pn_col.like(f"%{pn}%"), 1), else_=2))
    if family:
        stmt = stmt.where(Part.family == family)
    if role:
        stmt = stmt.where(Manufacturer.role == ManufacturerRole(role))
    if lifecycle:
        stmt = stmt.where(Part.lifecycle_status == LifecycleStatus(lifecycle))
    stmt = stmt.order_by(*order, Manufacturer.role, Part.family, Part.mpn).limit(limit)
    return list(session.scalars(stmt).unique())


def candidates_for(session: Session, ref: Part, scope: str = "auto") -> list[Part]:
    """Parts of other manufacturers in the same family.

    ``scope="auto"``: a reference (Skyworks) part is crossed against every competitor;
    a competitor part against the reference manufacturer only (finding a Skyworks
    replacement). ``scope="all"``: every other manufacturer.
    """
    stmt = select(Part).where(Part.family == ref.family, Part.id != ref.id, Part.manufacturer_id != ref.manufacturer_id)
    if scope == "auto" and not ref.is_reference:
        stmt = stmt.join(Part.manufacturer).where(Manufacturer.role == ManufacturerRole.reference)
    return list(session.scalars(stmt).unique())


def feedback_for(session: Session, ref_id: int) -> dict[int, CrossFeedback]:
    rows = session.scalars(select(CrossFeedback).where(CrossFeedback.reference_id == ref_id)).unique()
    return {fb.candidate_id: fb for fb in rows}


def crosses_for(session: Session, ref: Part, scope: str = "auto") -> dict[str, list[CrossResult]]:
    candidates = candidates_for(session, ref, scope)
    return find_crosses(ref, candidates, get_rules(ref.family), feedback_for(session, ref.id))


def single_cross(session: Session, ref_id: int, cand_id: int) -> CrossResult | None:
    ref, cand = session.get(Part, ref_id), session.get(Part, cand_id)
    if ref is None or cand is None or ref.family != cand.family:
        return None
    return cross(ref, cand, get_rules(ref.family), feedback_for(session, ref_id).get(cand_id))


def record_feedback(
    session: Session, ref_id: int, cand_id: int, verdict: str | None, note: str, user_id: int | None
) -> CrossFeedback | None:
    """Store (or replace) the FFF decision for a cross; ``verdict=None`` clears it."""
    existing = session.scalar(
        select(CrossFeedback).where(CrossFeedback.reference_id == ref_id, CrossFeedback.candidate_id == cand_id)
    )
    if verdict is None:
        if existing:
            session.delete(existing)
        session.commit()
        return None
    fb = existing or CrossFeedback(reference_id=ref_id, candidate_id=cand_id)
    fb.verdict, fb.note, fb.user_id = FeedbackVerdict(verdict), note.strip()[:2000], user_id
    session.add(fb)
    session.commit()
    return fb


def parts_by_ids(session: Session, ids: list[int]) -> list[Part]:
    found = {p.id: p for p in session.scalars(select(Part).where(Part.id.in_(ids))).unique()}
    return [found[i] for i in ids if i in found]
