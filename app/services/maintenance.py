"""Requests & reviews: one queue over the existing records (cross requests, cross verdicts, diagram feedback, part
mappings, data reviews, technology feedback), grouped by issue type. Read-only: every record stays in its own table,
nothing is copied or migrated. Each item says how it is resolved and which analyses it affects, so a vote is never
mistaken for a correction of the underlying fact."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AreaRequest, BlockFeedback, CrossFeedback, CrossRequest, DataReview, PartMapping, TechFeedback

ISSUE_TYPES = {
    "missing_product": ("Missing product", "A part to add or cross that BizDev does not cover yet."),
    "specification": ("Incorrect specification or cross", "A cross verdict or parameter that looks wrong."),
    "mapping": ("Product-to-function mapping", "Whether a catalogue part fills a function, or the path to a product."),
    "qualification": ("Qualification uncertainty", "Automotive grade not stated or in doubt."),
    "architecture": ("Application architecture", "Feedback on a block diagram, a block or a template."),
    "evidence": (
        "Technology or market evidence",
        "Ratings, competitors, customers, trends, platforms, patents, foundry.",
    ),
    "commercial": ("Market size (TAM)", "TAM estimates per product or technology and their sources."),
    "area": ("Application area request", "Another application area asked for in the Application library."),
}

# what a data review affects, per dataset
AFFECTS = {
    "technology": "Opportunity explorer fit score (where no path is assessed)",
    "competition": "Opportunity explorer fit score and competition column",
    "path": "Gap type and fit score in the Opportunity explorer",
    "trends": "Opportunity explorer fit score",
    "customers": "Customers page and business-case briefs",
    "capabilities": "Technology platforms page",
    "patents": "Evidence page only (not scored)",
    "foundry": "Evidence page only (not scored)",
    "competitor_tech": "Evidence page only (not scored)",
    "new_markets": "Ideas page only (not scored)",
    "auto_reach": "Automotive map and its Top moves (applied immediately)",
    "case": "Preliminary case: the case is revised from it",
    "application": "Application library: technically verified flag (applied immediately)",
    "library": "Systems library: the item's confidence (applied immediately); the topic is revised from it",
    "tam": "TAM estimates page (not in any score)",
}
FILE_UPDATE = (
    "Flag only: the data file must be corrected in the repository (Data quality → to-do); the vote changes no result."
)


def items(session: Session) -> list[dict]:
    out = []
    for r in session.scalars(select(CrossRequest)):
        out.append(
            {
                "type": "missing_product",
                "title": f"{r.mpn}" + (f" ({r.manufacturer})" if r.manufacturer else ""),
                "detail": r.note or "",
                "author": None,
                "date": r.created_at,
                "status": r.status,
                "link": "/manage/requests?kind=part",
                "resolution": "Needs a part import (repository update).",
                "affects": "Search & replacements, Browse products",
            }
        )
    for f in session.scalars(select(CrossFeedback)):
        out.append(
            {
                "type": "specification",
                "title": f"Cross verdict: part {f.reference_id} → {f.candidate_id}",
                "detail": f.note or "",
                "author": f.user.display_name if f.user else None,
                "date": f.created_at,
                "status": str(f.verdict.value if hasattr(f.verdict, "value") else f.verdict),
                "link": f"/parts/{f.reference_id}#row-{f.candidate_id}",
                "resolution": "Applied immediately: a rejected drop-in is shown as a package equivalent.",
                "affects": "Cross results for that reference",
            }
        )
    for m in session.scalars(select(PartMapping)):
        out.append(
            {
                "type": "mapping",
                "title": f"{m.mpn} ({m.manufacturer}) fills {m.fn}?",
                "detail": "",
                "author": m.author,
                "date": m.created_at,
                "status": "confirmed" if m.verdict == "yes" else "rejected",
                "link": f"/business/evidence/{m.fn}#existing",
                "resolution": "Applied immediately: a confirmed part counts as a portfolio part.",
                "affects": "Candidate coverage, gap lists, Opportunity explorer, Markets",
            }
        )
    for r in session.scalars(select(DataReview)):
        kind = "mapping" if r.dataset == "path" else "commercial" if r.dataset == "tam" else "evidence"
        if r.comment and any(w in r.comment.lower() for w in ("aec", "automotive", "qualif")):
            kind = "qualification"
        out.append(
            {
                "type": kind,
                "title": f"{r.dataset}: {r.key} marked {r.verdict}",
                "detail": r.comment or "",
                "author": r.author,
                "date": r.created_at,
                "status": "confirmed" if r.verdict == "correct" else "open",
                "link": f"/business/automotive?cell={r.key}#detail"
                if r.dataset == "auto_reach"
                else f"/business/tam#t-{r.key}"
                if r.dataset == "tam"
                else f"/business/reports/{r.dataset[5:]}#i-{r.key}"
                if r.dataset.startswith("case:")
                else f"/library/{r.dataset[8:]}#i-{r.key}"
                if r.dataset.startswith("library:")
                else "/blocks?verified=yes"
                if r.dataset == "application"
                else f"/business/evidence/{r.key}",
                "resolution": FILE_UPDATE,
                "affects": AFFECTS.get(r.dataset.split(":")[0], ""),
            }
        )
    for f in session.scalars(select(TechFeedback)):
        out.append(
            {
                "type": "evidence",
                "title": f"{f.kind}: {f.topic or 'technology'}",
                "detail": f.text,
                "author": f.author,
                "date": f.created_at,
                "status": f.status,
                "link": "/business/capabilities/feedback.txt",
                "resolution": FILE_UPDATE,
                "affects": "Technology platforms, technology ratings",
            }
        )
    for b in session.scalars(select(BlockFeedback)):
        out.append(
            {
                "type": "architecture",
                "title": b.target or b.diagram_name or "Block diagram",
                "detail": b.message,
                "author": None,
                "date": b.created_at,
                "status": b.status,
                "link": "/manage/requests?kind=diagram",
                "resolution": "Needs a template update in the repository.",
                "affects": "Application library and every analysis using that architecture",
            }
        )
    for a in session.scalars(select(AreaRequest)):
        out.append(
            {
                "type": "area",
                "title": a.area,
                "detail": a.why or "",
                "author": a.author,
                "date": a.created_at,
                "status": a.status,
                "link": "/manage/requests?kind=area",
                "resolution": "The daily update researches it a few documents per run and adds diagrams.",
                "affects": "Application library",
            }
        )
    out.sort(key=lambda i: i["date"], reverse=True)
    return out
