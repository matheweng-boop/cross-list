"""HTML pages."""

import re
import urllib.parse
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
from app.services import alternates, cross_notes, engineering, export, lifecycle, mechanical, notes_search, pricing
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

# Site sections: header -> sub-headers (label, path). A page belongs to the section whose
# prefixes match its path; the part pages, overlays and downloads all sit under Crosses.
SECTIONS = (
    ("crosses", "Crosses", "/", [("Find", "/"), ("Parts", "/parts"), ("Compare", "/compare"),
                                 ("Lifecycle", "/lifecycle"), ("Rules", "/rules"),
                                 ("Requests", "/requests")]),
    ("technical", "Technical discussions", "/technical", [("Technical", "/technical"),
                                                         ("Engineering notes", "/engineering"),
                                                         ("Broadcast", "/broadcast"),
                                                         ("Broadcast configurations", "/broadcast/configurations")]),
    ("blocks", "Block diagrams", "/blocks", [("Generator", "/blocks"), ("Coverage", "/blocks/coverage"),
                                             ("Feedback", "/blocks/feedback")]),
    ("business", "Business opportunity", "/business", [("Overview", "/business"),
                                                       ("Applications", "/business/applications"),
                                                       ("Markets", "/business/markets"),
                                                       ("Attach", "/business/attach"),
                                                       ("Gaps & ranking", "/business/gaps"),
                                                       ("Technology fit", "/business/technology"),
                                                       ("Technology base", "/business/capabilities"),
                                                       ("Where to hunt", "/business/customers"),
                                                       ("Case analysis", "/business/cases"),
                                                       ("TAM data", "/business/data"),
                                                       ("How it works", "/business/method")]),
)  # fmt: skip
SECTION_PREFIXES = {
    "technical": ("/technical", "/engineering", "/impact", "/broadcast"),
    "blocks": ("/blocks",),
    "business": ("/business",),
}


def section_of(path: str) -> str:
    return next((k for k, prefixes in SECTION_PREFIXES.items() if path.startswith(prefixes)), "crosses")


def _sub_active(path: str, href: str, subs: list) -> bool:
    """The longest sub-header path that prefixes the page path (Find only on / and /find)."""
    if href == "/":
        return path in ("/", "/find")
    best = max((h for _, h in subs if h != "/" and path.startswith(h)), key=len, default=None)
    return href == best


templates.env.globals["sections"] = SECTIONS
templates.env.globals["section_of"] = section_of
templates.env.globals["sub_active"] = _sub_active

GRADES = {"automotive": ("AEC-Q100", "auto"), "industrial": ("Industrial", "ind"), "commercial": ("Commercial", "ind")}


def grade_of(part: Part) -> str:
    """'automotive' for AEC-Q100 parts, 'industrial' for everything else (grade unknown included)."""
    q = next((pv.value for pv in part.params if pv.key == "qualification"), None)
    return "automotive" if q == "automotive" else "industrial"


def _grade_badge(part: Part) -> tuple[str, str] | None:
    q = next((pv.value for pv in part.params if pv.key == "qualification"), None)
    return GRADES.get(q)


templates.env.globals["grade_badge"] = _grade_badge
templates.env.globals["grade_of"] = grade_of


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
    role: str = "",
    company: str = "",
    catalog: str = "",
    sub: str = "",
    lifecycle_status: str = Query("", alias="lifecycle"),
    session: Session = Depends(get_session),
):
    """Browse without listing everything: pick a product category, then a company; chips filter by role and
    lifecycle. A search lists matches directly. Catalogue categories (full Skyworks / Qorvo portfolio) browse the
    product pages; Cross List families open the crosses."""
    from sqlalchemy import func

    from app.models import Manufacturer
    from app.services import blocks

    ctx = {"q": q, "family": family, "role": role, "company": company, "catalog": catalog, "sub": sub,
           "lifecycle": lifecycle_status, "statuses": list(LifecycleStatus), "parts": None, "rows": None}  # fmt: skip
    # tiles: Cross List families with counts per company, catalogue categories per manufacturer
    counts = session.execute(
        select(Part.family, Manufacturer.name, Manufacturer.role, func.count(Part.id))
        .join(Part.manufacturer)
        .group_by(Part.family, Manufacturer.name, Manufacturer.role)
    ).all()
    fam: dict[str, dict] = {}
    for f, mname, mrole, n in counts:
        e = fam.setdefault(f, {"total": 0, "companies": {}, "reference": 0})
        e["total"] += n
        e["companies"][mname] = (n, mrole.value)
        e["reference"] += n if mrole.value == "reference" else 0
    cat: dict[str, dict] = {}
    for r in blocks.catalog_rows():
        e = cat.setdefault(r["category"], {"total": 0, "companies": {}})
        e["total"] += 1
        e["companies"][r["manufacturer"]] = e["companies"].get(r["manufacturer"], 0) + 1
    ctx.update(families=fam, catalog_cats=dict(sorted(cat.items(), key=lambda kv: -kv[1]["total"])))
    if q.strip() or (family and company):
        who = company if company and company != "*" else ""
        found = search_parts(session, q, family, role, lifecycle_status, limit=10000, company=who)
        if family and not q.strip():
            everything = search_parts(session, "", family, role, "", limit=10000, company=who)
            ctx["life_counts"] = _life_counts(everything, "")
            ctx["series"] = {}
            for p in everything:
                ctx["series"][_series_of(p.mpn)] = ctx["series"].get(_series_of(p.mpn), 0) + 1
            ctx["series"] = dict(sorted(ctx["series"].items()))
        if sub:
            found = [p for p in found if _series_of(p.mpn) == sub]
        ctx["parts"] = found[:1000]
        ctx["n_found"] = len(found)
    if catalog:
        rows = [r for r in blocks.catalog_rows() if r["category"] == catalog]
        ctx["subs"] = sorted({r["sub"] for r in rows if r["sub"] and (not company or r["manufacturer"] == company)})
        ctx["cat_life"] = {}
        for r in rows:
            if (not company or r["manufacturer"] == company) and (not sub or r["sub"] == sub):
                ctx["cat_life"][r["status"]] = ctx["cat_life"].get(r["status"], 0) + 1
        if company:
            rows = [r for r in rows if company == "*" or r["manufacturer"] == company]
            rows = [
                r
                for r in rows
                if (not sub or r["sub"] == sub) and (not lifecycle_status or r["status"] == lifecycle_status)
            ]
            ctx["rows"] = sorted(rows, key=lambda r: (r["sub"], r["mpn"]))[:1000]
    return templates.TemplateResponse(request, "index.html", ctx)


def _series_of(mpn: str) -> str:
    """Product series for browsing: SI8641BD-IS -> SI86, SI86S641EC-IS1 -> SI86S, ISO7741DBQR -> ISO77."""
    m = re.match(r"[A-Z]+\d{2}(?:S(?=\d))?", (mpn or "").upper())
    return m.group(0) if m else (mpn or "")[:4].upper()


def _life_counts(parts: list, company: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for p in parts:
        if company and company != "*" and p.manufacturer.name != company:
            continue
        out[p.lifecycle_status.value] = out.get(p.lifecycle_status.value, 0) + 1
    return out


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
        # fewest priority 1 deviations first (pin-to-pin first among package equivalents), then exceptions
        if v.category == "package":
            return (
                r.lifecycle_risk,
                CATEGORY_RANK[v.category],
                not v.p2p,
                len(r.deviations),
                len(r.exceptions),
                r.closeness,
            )
        return (
            r.lifecycle_risk,
            CATEGORY_RANK[v.category],
            len(r.deviations),
            len(r.exceptions),
            not v.p2p,
            r.closeness,
        )

    rows.sort(key=key)
    return rows


def rank_reason(r, v) -> str:
    """One line on why a result ranks where it does."""
    bits = [v.label]
    bits.append("pin-to-pin" if v.p2p else "not pin-to-pin")
    if v.worse:
        n, labels = len(v.worse), ", ".join(d.label for d in v.worse)
        bits.append(f"{n} priority 1 deviation{'s' if n > 1 else ''} ({labels})")
    elif v.better:
        bits.append("priority 1 equal or better")
    else:
        bits.append("priority 1 equal")
    if v.exceptions:
        bits.append("exception: " + ", ".join(f"{d.label} {d.cand_display} vs {d.ref_display}" for d in v.exceptions))
    if r.lifecycle_risk:
        bits.append("lifecycle risk")
    return "; ".join(bits)


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
    grade: str = "",
    all: bool = False,
    session: Session = Depends(get_session),
):
    part = session.get(Part, part_id)
    if part is None:
        raise HTTPException(404, "Part not found")
    rules = get_rules(part.family)
    # grade is always one of the two: an automotive part only takes automotive crosses (AEC-Q100 is a hard
    # requirement); a non-automotive part shows non-automotive crosses unless automotive is chosen
    grade = (
        "automotive"
        if grade_of(part) == "automotive"
        else (grade if grade in ("automotive", "industrial") else "industrial")
    )
    scope = scope if scope in ("auto", "all") else "auto"
    dev = _deviations(dev)
    crosses = crosses_for(session, part, scope, dev)
    rejected = [r for r in crosses["package"] if r.fff_status == "rejected"]
    if hide_eol:
        crosses = {c: [r for r in rs if not r.lifecycle_risk] for c, rs in crosses.items()}
    grade_counts = {
        g: sum(grade_of(r.candidate) == g for r, _ in result_rows(crosses)) for g in ("automotive", "industrial")
    }
    crosses = {c: [r for r in rs if grade_of(r.candidate) == grade] for c, rs in crosses.items()}
    companies = companies_of(result_rows(crosses))
    if company:
        crosses = {c: [r for r in rs if r.candidate.manufacturer.name == company] for c, rs in crosses.items()}
    rows = result_rows(crosses)
    type_counts = {c: sum(v.category == c for _, v in rows) for c in CATEGORY_ORDER}
    type = type if type in CATEGORY_ORDER else ""
    if type:
        rows = [(r, v) for r, v in rows if v.category == type]
    # best and next best option per cross type; the rest only on request
    ranked, top = {}, []
    # (two different devices: an output-state or rating variant of the best part is not the next best)
    for cat in CATEGORY_ORDER:
        devices: set[str] = set()
        for rv in [rv for rv in rows if rv[1].category == cat]:
            dev_key = alternates.device_of(rv[0].candidate.mpn)
            if dev_key in devices:
                continue
            devices.add(dev_key)
            ranked[rv[0].candidate.id] = len(devices) - 1
            top.append(rv)
            if len(devices) == 2:
                break
    rest = [rv for rv in rows if rv[0].candidate.id not in ranked]
    rows = top + (rest if all else [])
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
            "ranked": ranked,
            "n_top": len(top),
            "n_rest": len(rest),
            "show_all": all,
            "alternates": alternates.alternates(session, part),
            "alts_for": lambda p: alternates.alternates(session, p, limit=1),
            "pkg_options": lambda p: alternates.package_options(session, p),
            "out_variants": lambda p: alternates.output_variants(session, p),
            "rank_reason": rank_reason,
            "cross_notes": cross_notes.notes_for,
            "position_note": cross_notes.position_note,
            "grade": grade,
            "grade_counts": grade_counts,
            "ref_grade": grade_of(part),
        },
    )


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
    if grade in ("automotive", "industrial"):
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
def impact_page(ids: str = ""):
    """Old address of the CMTI explorer: now the CMTI engineering note."""
    return RedirectResponse(f"/engineering/cmti_kv_us?ids={ids}", status_code=307)


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


def series_of(mpn: str) -> str:
    """Product series for grouping: the part number up to its last base digit, with that digit as x
    (SI8641BD-IS -> SI864x, SI86S641BE-IS2 -> SI86S64x, ISO7741DWR -> ISO774x)."""
    m = re.match(r"[A-Z]+\d+(?:[A-Z]\d{2,})?", re.split(r"[-.]", mpn.upper())[0])
    return f"{m.group(0)[:-1]}x" if m and m.group(0)[-1].isdigit() else mpn.upper()


def _norm_mpn(s: str) -> str:
    return re.sub(r"[\s\-–]", "", s or "").upper()


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
        key = _norm_mpn(token)
        hits = [p for p in search_parts(session, token) if _norm_mpn(p.mpn).startswith(key)]
        exact = [p for p in hits if _norm_mpn(p.mpn) == key]
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
    family = family or next(iter(load_all_rules()))
    available = list(session.scalars(select(Part).where(Part.family == family).order_by(Part.mpn)).unique())
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
