"""Shared database queries."""

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.matching.engine import DEFAULT_MAX_DEVIATIONS, CrossResult, cross, find_crosses
from app.matching.rules import get_rules
from app.models import CrossFeedback, FeedbackVerdict, LifecycleStatus, Manufacturer, ManufacturerRole, Part
from app.partnumbers import SEPARATORS, normalize_pn, reel_q1_variants  # noqa: F401  (re-exported for callers)


def _pn_column():
    """The part number as normalize_pn compares it, in SQL."""
    col = func.upper(Part.mpn)
    for ch in SEPARATORS:
        col = func.replace(col, ch, "")
    return col


def search_parts(
    session: Session,
    q: str = "",
    family: str = "",
    role: str = "",
    lifecycle: str = "",
    limit: int = 200,
    company: str = "",
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
    if company:
        stmt = stmt.where(Manufacturer.name == company)
    stmt = stmt.order_by(*order, Manufacturer.role, Part.family, Part.mpn).limit(limit)
    found = list(session.scalars(stmt).unique())
    if not found and q.strip():  # a TI automotive reel code: …RQ1 is the reel of …Q1 (and the other way round)
        for alt in reel_q1_variants(normalize_pn(q)):
            if found := search_parts(session, alt, family, role, lifecycle, limit, company):
                break
    return found


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


def crosses_for(
    session: Session, ref: Part, scope: str = "auto", max_deviations: int = DEFAULT_MAX_DEVIATIONS
) -> dict[str, list[CrossResult]]:
    candidates = candidates_for(session, ref, scope)
    return find_crosses(ref, candidates, get_rules(ref.family), feedback_for(session, ref.id), max_deviations)


def single_cross(
    session: Session, ref_id: int, cand_id: int, max_deviations: int = DEFAULT_MAX_DEVIATIONS
) -> CrossResult | None:
    ref, cand = session.get(Part, ref_id), session.get(Part, cand_id)
    if ref is None or cand is None or ref.family != cand.family:
        return None
    return cross(ref, cand, get_rules(ref.family), feedback_for(session, ref_id).get(cand_id), max_deviations)


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
