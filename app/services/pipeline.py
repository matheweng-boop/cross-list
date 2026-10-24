"""Part → application → parts in the design → numbers → business case: one guided path that carries a part (and its
cross, or the lack of one) through the block diagram, the cross-sell and into a business case, step by step.

The draft state (PipelineDraft.state) is plain JSON so every step can be revisited:
  part:        the part the path started from {id, mpn, manufacturer, reference}
  competitor:  the competitor part {id, mpn, manufacturer} or None (started from a part of ours)
  ours:        our part for it {id, mpn} or None (no cross found: a gap)
  fn, fn_label the function in the block catalogue
  diagram_id:  the block diagram the part was placed in (a copy of a reference design, or a new one)
  application: its name
  lines:       [{key, role, fn, label, competitor_mpn, our_mpn, qty, volume, price, price_source, include}]
Volumes and prices are the user's assumptions and are labelled so everywhere.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BlockDiagram, Case, CaseLine, CaseNote, Part, ShortlistItem, VolumeRequest
from app.services import blocks, vocab

STEPS = [
    ("part", "Part"),
    ("application", "Application"),
    ("design", "Parts in the design"),
    ("numbers", "Volume & price"),
    ("case", "Prelim case"),
]
ROLE_LABEL = {"cross": "Cross", "design": "Also in the design", "gap": "Gap: no part of ours"}


def fn_for_family(family: str) -> str | None:
    """The block-catalogue function a BizDev part family fills (the function named like the family first)."""
    fns = blocks.catalogue()["functions"]
    if family in fns:
        return family
    return next((k for k, f in fns.items() if (f.get("source") or {}).get("family") == family), None)


# Families that hold several block-diagram functions; each part says which one in this parameter (timing: clock
# generator, jitter attenuator, buffers, oscillators share one rules family).
FUNCTION_PARAM = "function_type"


def fn_for_part(part: Part) -> str | None:
    """The block-catalogue function a BizDev part fills: its own function_type when its family holds several
    functions (timing), else the function of its family."""
    own = next((pv.value for pv in part.params if pv.key == FUNCTION_PARAM), None)
    if own and own in blocks.catalogue()["functions"]:
        return own
    return fn_for_family(part.family)


def _part(p: Part | None) -> dict | None:
    return {"id": p.id, "mpn": p.mpn, "manufacturer": p.manufacturer.name} if p else None


def start(session: Session, part_id: int, our_id: int | None = None) -> dict:
    part = session.get(Part, part_id)
    if part is None:
        raise ValueError("unknown part")
    if part.is_reference:  # started from a part of ours: no competitor
        competitor, ours = None, part
    else:
        competitor = part
        ours = session.get(Part, our_id) if our_id else None
        if ours is not None and not ours.is_reference:
            ours = None
    fn = fn_for_part(part)
    label = vocab.fn_label(fn) if fn else vocab.family_title(part.family)
    return {
        "part": {**_part(part), "reference": part.is_reference},
        "competitor": _part(competitor),
        "ours": _part(ours),
        "fn": fn,
        "fn_label": label,
        "diagram_id": None,
        "application": None,
        "lines": [],
    }


def applications_for(session: Session, fn: str | None) -> dict:
    """Reference designs and saved diagrams that contain the function."""
    if not fn:
        return {"templates": [], "saved": []}
    tpls = [
        {"i": i, "name": blocks.display_name(t), "blocks": len(blocks.template_functions(t)), "source": t.get("source")}
        for i, t in enumerate(blocks.templates())
        if fn in blocks.template_functions(t)
    ]
    saved = [
        {"id": d.id, "name": d.name}
        for d in session.scalars(select(BlockDiagram).order_by(BlockDiagram.updated_at.desc()))
        if any(b.get("fn") == fn for g in (d.data or {}).get("groups", []) for b in g.get("blocks", []))
    ]
    return {"templates": tpls, "saved": saved}


def _uid(prefix: str, n: int) -> str:
    return f"{prefix}p{n}"


def diagram_from_template(t: dict, fn: str | None, our_mpn: str | None) -> dict:
    """The editor's data for a reference design (same shape as blocks.js fromTemplate), our part in its block(s)."""
    n = 0
    groups = []
    for g in t.get("groups") or []:
        bl = []
        for b in g.get("blocks") or []:
            n += 1
            if isinstance(b, dict):
                f, label, qty = b["fn"], b.get("label", ""), b.get("qty", 1)
            else:
                f, _, q = str(b).partition(" x")
                label, qty = "", int(q) if q.strip().isdigit() else 1
            bl.append({"id": _uid("b", n), "fn": f, "label": label, "qty": qty,
                       "part": our_mpn if (our_mpn and f == fn) else None})  # fmt: skip
        groups.append({"id": g["id"], "label": g["label"], "col": g.get("col", 0), "row": g.get("row", 0),
                       "w": g.get("w", 1), "blocks": bl})  # fmt: skip
    return {"groups": groups, "links": [list(x) for x in t.get("links") or []],
            "questions": t.get("questions") or [], "sources": t.get("sources") or [], "req": {}, "qa": {}}  # fmt: skip


def new_diagram(fn: str | None, label: str, our_mpn: str | None) -> dict:
    blk = [{"id": "bp1", "fn": fn, "label": "", "qty": 1, "part": our_mpn}] if fn else []
    return {"groups": [{"id": "g1", "label": label, "col": 0, "row": 0, "w": 1, "blocks": blk}], "links": [],
            "req": {}, "qa": {}}  # fmt: skip


def design_rows(session: Session, data: dict, fn: str | None) -> list[dict]:
    """Every block of the diagram with what fills it: our chosen part, parts we could offer, a gap, or a customer
    part (not ours to sell)."""
    counts = blocks.counts(session)
    rows = []
    for g in data.get("groups") or []:
        for b in g.get("blocks") or []:
            n = counts.get(b.get("fn"))
            status = "chosen" if b.get("part") else ("customer" if n is None else "have" if n else "gap")
            rows.append({"group": g.get("label", ""), "block": b["id"], "fn": b.get("fn"), "qty": b.get("qty") or 1,
                         "label": b.get("label") or vocab.fn_label(b.get("fn")),
                         "part": b.get("part"), "status": status, "candidates": n or 0,
                         "is_cross": b.get("fn") == fn})  # fmt: skip
    return rows


def pick_all(session: Session, data: dict) -> list[str]:
    """Fill every block that has candidates and no part with the best-ranked part (as 'pick the best match')."""
    counts, picked = blocks.counts(session), []
    best: dict[str, str | None] = {}
    for g in data.get("groups") or []:
        for b in g.get("blocks") or []:
            f = b.get("fn")
            if b.get("part") or not counts.get(f):
                continue
            if f not in best:
                ms = blocks.parts_for(session, f, answers=(data.get("req") or {}).get(f) or {})["manufacturers"]
                best[f] = ms[0]["best"][0]["mpn"] if ms and ms[0]["best"] else None
            if best[f]:
                b["part"] = best[f]
                picked.append(
                    f"{b.get('label') or (blocks.catalogue()['functions'].get(f) or {}).get('label', f)}: {best[f]}"
                )
    return picked


def build_lines(state: dict, rows: list[dict]) -> list[dict]:
    """Business-case lines from the design: the cross first, then our parts elsewhere in the design, then the gaps.
    Customer parts are left out. Volumes and prices already entered are kept."""
    old = {x["key"]: x for x in state.get("lines") or []}
    comp, ours = state.get("competitor"), state.get("ours")
    lines = [{
        "key": "cross", "role": "cross" if ours else "gap", "fn": state.get("fn"), "label": state.get("fn_label") or "",
        "competitor_mpn": comp["mpn"] if comp else None, "our_mpn": ours["mpn"] if ours else None,
        "qty": next((r["qty"] for r in rows if r["is_cross"]), 1),
    }]  # fmt: skip
    seen = {state.get("fn")}
    for r in rows:
        if r["is_cross"] or r["status"] == "customer":
            continue
        key = f"{r['fn']}|{r['label']}"
        if key in seen:
            continue
        seen.add(key)
        lines.append({"key": key, "role": "design" if r["part"] else "gap", "fn": r["fn"], "label": r["label"],
                      "competitor_mpn": None, "our_mpn": r["part"], "qty": r["qty"]})  # fmt: skip
    for x in lines:
        o = old.get(x["key"], {})
        x.update(volume=o.get("volume"), price=o.get("price"), price_source=o.get("price_source"),
                 include=o.get("include", True))  # fmt: skip
    return lines


def form_number(v, cast):
    """A volume or price typed in a form ("1,000", "$0.45"): commas and $ ignored; None when blank or not a number."""
    try:
        v = str(v).replace(",", "").replace("$", "").strip()
        return cast(float(v)) if v else None
    except ValueError:
        return None


def revenue(line: dict) -> float | None:
    if line.get("volume") is None or line.get("price") is None or not line.get("our_mpn"):
        return None
    return line["volume"] * (line.get("qty") or 1) * line["price"]


def apply_numbers(state: dict, form) -> None:
    """Volume (systems / year), target price (USD) and include per line, from the numbers step."""
    volume_all = form_number(form.get("volume_all"), int)
    for x in state.get("lines") or []:
        k = x["key"]
        x["volume"] = form_number(form.get(f"vol:{k}"), int) if form.get(f"vol:{k}") not in (None, "") else volume_all
        x["price"] = form_number(form.get(f"price:{k}"), float)
        src = str(form.get(f"src:{k}") or "").strip()[:200]
        x["price_source"] = src or ("assumed" if x["price"] is not None else None)
        x["include"] = bool(form.get(f"inc:{k}"))


def _summary(state: dict) -> str:
    out = []
    for x in state.get("lines") or []:
        if not x.get("include"):
            continue
        r = revenue(x)
        out.append(f"- {x['label']}: {x.get('our_mpn') or 'no part of ours'}"
                   + (f" (vs {x['competitor_mpn']})" if x.get("competitor_mpn") else "")
                   + (f", {x['volume']:,}/yr × {x.get('qty') or 1}" if x.get("volume") else "")
                   + (f" at ${x['price']:.2f}" if x.get("price") is not None else "")
                   + (f" = ${r:,.0f}/yr" if r else ""))  # fmt: skip
    return "\n".join(out)


def finish(session: Session, state: dict, form) -> Case:
    """Create the business case, or add the lines to an existing one."""
    target = str(form.get("target") or "new")
    if target == "existing":
        target = str(form.get("existing") or "")
    comp, ours = state.get("competitor"), state.get("ours")
    case = session.get(Case, int(target)) if target.isdigit() else None
    if case is None:
        title = str(form.get("title") or "").strip()[:200] or f"{(ours or comp or {}).get('mpn', 'Part')} business case"
        inputs = {
            "question": f"Should we pursue {state.get('application') or 'this design'}"
                        + (f" with {ours['mpn']} against {comp['mpn']}" if ours and comp else "")
                        + (f" – no part of ours for {comp['mpn']} yet" if comp and not ours else "") + "?",
            "applications": state.get("application") or "",
            "competitors": comp["mpn"] + f" ({comp['manufacturer']})" if comp else "",
            "markets": str(form.get("markets") or "").strip(),
            "notes": ("Customer: " + str(form.get("customer")).strip() + "\n" if form.get("customer") else "")
                     + "Parts from the guided path (volumes and prices are assumptions):\n" + _summary(state),
        }  # fmt: skip
        case = Case(title=title, fn=state.get("fn"), inputs={k: v for k, v in inputs.items() if v})
        session.add(case)
        session.flush()
    else:
        case.notes.append(CaseNote(kind="comment", text="Added from the guided path"
                                   + (f" ({state.get('application')})" if state.get("application") else "")
                                   + ":\n" + _summary(state)))  # fmt: skip
    for x in state.get("lines") or []:
        if not x.get("include"):
            continue
        session.add(CaseLine(case_id=case.id, role=x["role"], fn=x.get("fn"), label=x["label"][:200],
                             competitor_mpn=x.get("competitor_mpn"), our_mpn=x.get("our_mpn"), qty=x.get("qty") or 1,
                             volume=x.get("volume"), price=x.get("price"),
                             price_source=x.get("price_source")))  # fmt: skip
    return case


def lines_of(session: Session, case_id: int) -> list[CaseLine]:
    return list(session.scalars(select(CaseLine).where(CaseLine.case_id == case_id).order_by(CaseLine.id)))


def totals(lines: list[CaseLine]) -> dict:
    rev = [ln.volume * ln.qty * ln.price for ln in lines if ln.volume and ln.price is not None and ln.our_mpn]
    return {"revenue": sum(rev), "priced": len(rev), "lines": len(lines)}


def merge(session: Session, source: Case, target: Case) -> None:
    """Move everything of one case into another: part lines, discussion notes, linked candidates; the source keeps
    its title and is marked merged (nothing is deleted)."""
    for ln in lines_of(session, source.id):
        ln.case_id = target.id
    for n in list(source.notes):
        n.case_id = target.id
    for it in session.scalars(select(ShortlistItem).where(ShortlistItem.case_id == source.id)):
        it.case_id = target.id
    text = "\n".join(f"{k}: {v}" for k, v in (source.inputs or {}).items() if v and k != "merged_into")
    session.add(CaseNote(case_id=target.id, kind="comment", text=f"Merged from “{source.title}”"
                         + (f":\n{text}" if text else "")))  # fmt: skip
    source.status = "merged"
    source.inputs = {**(source.inputs or {}), "merged_into": str(target.id)}


# ---- requests for a case: the volume asked for a part accrues over every request ------------------------------
def requested(session: Session, mpn: str | None) -> dict:
    """Every request for a case on the part: how many, the total volume asked (pieces a year) and who asked."""
    rows = list(session.scalars(select(VolumeRequest).where(VolumeRequest.mpn == mpn).order_by(VolumeRequest.id)))
    names = [x.strip() for r in rows for x in (r.customer or "").split(";") if x.strip()]
    markets = [x.strip() for r in rows for x in (r.market or "").split(";") if x.strip()]
    return {"n": len(rows), "total": sum(r.volume or 0 for r in rows), "customers": list(dict.fromkeys(names)),
            "markets": list(dict.fromkeys(markets)), "last": rows[-1].created_at if rows else None}  # fmt: skip


def request_volume(state: dict) -> int | None:
    """Pieces of the part a year: the systems a year of its line times the parts per system."""
    x = next((x for x in state.get("lines") or [] if x.get("key") == "cross"), None)
    return x["volume"] * (x.get("qty") or 1) if x and x.get("volume") else None


def form_list(form, key: str, limit: int = 20) -> list[str]:
    """A repeated field (customer, market): the filled values in order, each once."""
    vals = [str(v).strip()[:120] for v in form.getlist(key)] if hasattr(form, "getlist") else []
    return list(dict.fromkeys(v for v in vals if v))[:limit]


def record_request(session: Session, state: dict, source: str) -> VolumeRequest | None:
    """One row per request for a case on the part (never merged): the total volume accrues across requests."""
    mpn = (state.get("competitor") or state.get("part") or {}).get("mpn")
    if not mpn:
        return None
    r = VolumeRequest(mpn=mpn, volume=request_volume(state), source=source[:60],
                      customer="; ".join(state.get("customers") or [])[:500] or None,
                      market="; ".join(state.get("markets") or [])[:500] or None)  # fmt: skip
    session.add(r)
    return r


def prelim_note(state: dict, description: str = "") -> str:
    """What the review queue gets with the prelim case: the application, who asks, the design and the numbers."""
    comp, ours = state.get("competitor"), state.get("ours")
    bits = [
        f"Part: {comp['mpn']} ({comp['manufacturer']})" if comp else f"Part: {(ours or {}).get('mpn', '')}",
        f"Our cross: {ours['mpn']}" if comp and ours else ("No part of ours: a new development" if comp else ""),
        f"Application: {state['application']}" if state.get("application") else "",
        f"Description: {description or state.get('description')}" if description or state.get("description") else "",
        "Customers: " + ", ".join(state["customers"]) if state.get("customers") else "",
        "Markets: " + ", ".join(state["markets"]) if state.get("markets") else "",
        "Check: is there a real market behind it (volume, customers, competition)?",
        "Parts in the design (volumes and prices are assumptions):\n" + _summary(state) if state.get("lines") else "",
    ]
    return "\n".join(b for b in bits if b)[:4000]


def search_applications(session: Session, q: str, fn: str | None, limit: int = 10) -> list[dict]:
    """Library and saved diagrams for a free-text application description, best match first (diagrams with the
    part's function before others at the same score); with no text, the diagrams that have the function."""
    from app.services.opportunity import market_of

    rows = []
    for i, t in enumerate(blocks.templates()):
        has = bool(fn) and fn in blocks.template_functions(t)
        idx = blocks.template_index(t, market_of(t.get("name", ""), t.get("category") or "Other"))
        rows.append({"kind": "template", "i": i, "name": blocks.display_name(t), "has": has, "index": idx,
                     "blocks": len(blocks.template_functions(t)), "tags": idx["tags"]})  # fmt: skip
    for d in session.scalars(select(BlockDiagram).order_by(BlockDiagram.updated_at.desc()).limit(300)):
        fns = [b.get("fn") for g in (d.data or {}).get("groups") or [] for b in g.get("blocks") or []]
        idx = blocks.search_index(d.name, "", " ".join(g.get("label", "") for g in (d.data or {}).get("groups") or []))
        rows.append({"kind": "saved", "id": d.id, "name": d.name, "has": bool(fn) and fn in fns, "index": idx,
                     "blocks": len(set(fns)), "tags": idx["tags"]})  # fmt: skip
    if blocks.query_words(q):
        for r in rows:
            r["score"] = blocks.search_score(r["index"], q)
        rows = [r for r in rows if r["score"]]
    else:
        rows = [{**r, "score": 0} for r in rows if r["has"]]
    rows.sort(key=lambda r: (-r["score"], not r["has"], r["kind"] != "template", r["name"]))
    labels = {c["key"]: c["label"] for c in blocks.categories()}
    return [{k: v for k, v in r.items() if k != "index"} | {"tags": [labels[t] for t in r["tags"]]}
            for r in rows[:limit]]  # fmt: skip


def suggestions(session: Session, rows: list[dict], per_block: int = 3) -> dict[str, list[dict]]:
    """Up to three Skyworks / Qorvo parts per open block of the design, with the reason each is listed (the block
    catalogue's ranking: lifecycle, grade, requirements, data depth)."""
    from app.services import opportunity as op

    mine = op.company("combined")[2]
    out: dict[str, list[dict]] = {}
    for r in rows:
        f = r.get("fn")
        if not f or f in out or r["status"] != "have":
            continue
        picks = []
        for m in blocks.parts_for(session, f, top=2)["manufacturers"]:
            if m["manufacturer"] in mine:
                picks += [{"mpn": p["mpn"], "url": p["url"], "manufacturer": m["manufacturer"],
                           "why": "; ".join(p["why"].split("; ")[:3]),  # rank, requirements / lifecycle, grade
                           "detail": p.get("detail") or ""} for p in m["best"]]  # fmt: skip
        out[f] = picks[:per_block]
    return out
