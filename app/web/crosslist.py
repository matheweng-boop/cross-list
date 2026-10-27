"""Products › Cross a list: paste part numbers, get the two result columns per part and an Excel download. Nothing
pasted is stored (app/services/crosslist.py); only the owner's Right / Wrong answers on a shown pair are, and, when
the owner taps "Update cross-lists", the list's part numbers and the unknown ones
(app/services/crosslist_lookups.py)."""

from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.auth.session import principal, signed_in_owner
from app.db import get_session
from app.matching.rules import load_all_rules
from app.models import CrossListLookup
from app.services import crosslist as cl
from app.services import crosslist_lookups as lk
from app.services import demand, export
from app.web.routes import XLSX, templates

router = APIRouter()
MAX_CHARS = 60_000
templates.env.globals["demand_seen"] = demand.seen  # owner-only volume totals (None for guests and Shareable)
templates.env.globals["demand_fmt"] = demand.fmt


def _ctx(request: Request, text: str, session: Session, sent: int | None = None) -> dict:
    entries, over = cl.parse(text)
    rows = cl.cross_list(session, entries) if entries else []
    families = sorted({r.part.family for r in rows if r.part})
    owner = signed_in_owner(request) is not None
    return {"text": text, "unknown": sum(1 for r in rows if lk.is_unknown(r)), "sent": sent,
            "vol_rows": {r.n for r in lk.volume_rows(rows)} if owner else set(), "steps": demand.CHOICES,
            "gaps": sum(1 for r in rows if lk.is_gap(r)),
            "rows": rows, "sum": cl.summary(rows), "over": over, "max_lines": cl.MAX_LINES,
            "submitted": bool(text.strip()), "owner": signed_in_owner(request) is not None,
            "privacy": cl.PRIVACY_NOTE, "precheck": cl.PRECHECK_NOTE, "how": cl.HOW_NOTE, "lights": cl.LIGHTS,
            "light_help": cl.LIGHT_HELP, "accuracy": cl.accuracy(), "header": cl.EXPORT_HEADER,
            "lines": cl.export_lines, "kinds": cl.TYPE_KIND,
            "p1": {f: cl.p1_labels(f) for f in families},
            "p1_all": {f: cl.p1_labels(f) for f in load_all_rules()}}  # fmt: skip


@router.get("/cross-list", response_class=HTMLResponse)
def page(request: Request, lookup: int | None = None, sent: int = 0, session: Session = Depends(get_session)):
    """With ?lookup=<id> ("Cross this list again" on Requests, owner only): the stored list, pre-filled and crossed."""
    text, n_sent = "", None
    if lookup is not None:
        if signed_in_owner(request) is None:
            raise HTTPException(403, "Only the owner can open a sent list.")
        row = session.get(CrossListLookup, lookup)
        if row is None:
            raise HTTPException(404, "Lookup not found")
        text = "\n".join(row.list_parts or [])
        n_sent = len(row.unknown_parts or []) if sent else None
    ctx = _ctx(request, text, session, n_sent)
    if n_sent is not None:
        ctx["sent_vols"] = len(demand.seen(request).lookup(row.id))
    return templates.TemplateResponse(request, "cross_list.html", ctx)


@router.post("/cross-list", response_class=HTMLResponse)
def run(request: Request, parts: str = Form(""), session: Session = Depends(get_session)):
    """Compute only: the pasted list is read, crossed and shown; nothing is written."""
    ctx = _ctx(request, parts[:MAX_CHARS], session)
    return templates.TemplateResponse(request, "cross_list.html", ctx)


async def _form(request: Request) -> dict:
    return dict((await request.form()).multi_items())


@router.post("/cross-list/lookup")
def send_lookup(request: Request, form: dict = Depends(_form), session: Session = Depends(get_session)):
    """"Update cross-lists" (owner only): stores the unknown part numbers and the list's part numbers, as parsed
    (no quantities, prices, names or other columns), for the hourly lookup run; plus, per unknown or gap row with a
    volume step chosen (field v<row number>), one lifetime demand entry (app/services/demand.py). Any other field or
    value is refused (owner's safeguard, 26 Oct 2026: no other information)."""
    if signed_in_owner(request) is None:
        raise HTTPException(403, "Only the owner can send parts for lookup.")
    text = str(form.get("parts") or "")[:MAX_CHARS]
    entries, _ = cl.parse(text)
    rows = cl.cross_list(session, entries) if entries else []
    eligible = {f"v{r.n}": r for r in lk.volume_rows(rows)}
    extra = set(form) - {"parts"} - set(eligible)
    if extra:
        raise HTTPException(400, "Only a volume step per unknown or gap part can be sent.")
    vols = []
    for name, r in eligible.items():
        try:
            v = demand.parse_step(str(form.get(name) or ""))
        except ValueError:
            raise HTTPException(400, "Choose a volume from the list.") from None
        if v is not None:
            from app.services import pipeline

            vols.append((r.part.mpn if r.part else r.key, pipeline.fn_for_part(r.part) if r.part else None, v))
    unknown = [r.key for r in rows if lk.is_unknown(r)]
    if not unknown and not vols:
        raise HTTPException(400, "No unknown parts and no volumes in this list.")
    p = principal(request)
    row = lk.create(session, [e.text for e in entries], unknown, p.name if p else None)
    if vols:
        demand.record(session, row.id, vols)
    return RedirectResponse(f"/cross-list?lookup={row.id}&sent=1", status_code=303)  # a reload does not send twice


@router.post("/cross-list.xlsx")
def download(parts: str = Form(""), lights: str = Form(""), session: Session = Depends(get_session)):
    """The table as shown: every row, or only the rows of the light chosen on the page ("Export shown rows")."""
    entries, over = cl.parse(parts[:MAX_CHARS])
    rows = cl.cross_list(session, entries)
    sm = cl.summary(rows)
    want = lights if lights in cl.LIGHTS else ""
    if want:
        rows = [r for r in rows if r.light == want]
    name = f"cross-list-{date.today():%Y-%m-%d}.xlsx"
    body = export.cross_list_xlsx(rows, sm, over, cl.accuracy(), cl.LIGHTS.get(want, ""))
    return Response(body, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/cross-list/feedback", response_class=HTMLResponse)
def feedback(request: Request, their: str = Form(...), ours: str = Form(...), verdict: str = Form(...),
             comment: str = Form(""), session: Session = Depends(get_session)):  # fmt: skip
    """The owner's Right / Wrong on one shown pair (guests never get here: an owner action, app/auth/access.py)."""
    if signed_in_owner(request) is None:
        raise HTTPException(403, "Only the owner can mark a cross right or wrong.")
    if verdict not in cl.VERDICTS or not their.strip() or not ours.strip():
        raise HTTPException(400, "Choose Right or Wrong.")
    if verdict == "wrong" and not comment.strip():  # nothing stored; the form stays
        return HTMLResponse('<span class="cx-need">Say what is wrong in the comment, then press Wrong again.</span>')
    p = principal(request)
    cl.record(session, their, ours, verdict, comment, p.name if p else None)
    msg = "✓ Verified – thanks." if verdict == "right" else "Marked wrong – sent to the next daily update."
    return HTMLResponse(f'<span class="cx-saved">{msg}</span>')


@router.post("/manage/demand/scoring")
def demand_scoring(request: Request, on: str = Form("0"), session: Session = Depends(get_session)):
    """The owner-only switch "Use demand seen in scoring" (default off): owner pages then add a score "with demand
    seen"; the shared Opportunity score never changes (app/services/demand.py)."""
    if signed_in_owner(request) is None:
        raise HTTPException(403, "Only the owner can change this.")
    demand.set_scoring(session, on == "1")
    return RedirectResponse("/business/reports#demand-seen", status_code=303)
