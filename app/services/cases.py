"""Case analysis: what BizDev knows about a function (occurrence, door openers, competition, technology
proximity, portfolio parts) and a market-analysis brief an AI assistant can run. The app sends nothing anywhere: the
brief is copied by the user, and the result is pasted back."""

import re

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.matching.engine import format_value
from app.matching.rules import get_rules
from app.models import Part
from app.services import blocks, tam, vocab
from app.services import opportunity as op

STATUSES = {"collecting": "Collecting inputs", "analysing": "Analysis running", "discussing": "Discussing",
            "decided": "Decided"}  # fmt: skip
NOTE_KINDS = {"upside": "Upside", "risk": "Risk", "feature": "Feature idea", "comment": "Comment"}
FIELDS = [  # (key, label, help, rows); owner, 22 Oct 2026: feasibility, price, manufacturing, markets, competition
    ("question", "Decision to support", "What should the analysis decide? e.g. a 5 GHz BAW filter for Wi-Fi 7?", 2),
    ("feasibility", "Is the technology feasible?",
     "Existing dies and processes, a new die, or new technology? What is new: die, package, qualification", 3),
    ("features", "Features", "One per line: feature – why it matters to the customer", 5),
    ("specs", "Target specifications", "Key numbers: voltage, current, frequency, package, qualification…", 4),
    ("price", "Potential price / ASP",
     "With the volume it applies to", 2),
    ("manufacturing", "Manufacturing capability",  # owner, 25 Oct 2026: capability only, never a site or fab name
     "Which capability could make it, e.g. in-house BAW wafer processing or in-house assembly and test; no sites", 2),
    ("inhouse", "In house or external?", "Own fab and assembly, foundry or subcontractor; public information only", 1),
    ("markets", "Target markets", "One main market or several? One per line", 3),
    ("market_size", "How big are these markets?",
     "Public market size per market, with source and year", 3),
    ("applications", "Target applications", "Where the part would go, one per line", 3),
    ("volume", "Volume", "Units per year, per market if known", 1),
    ("timeframe", "Timeframe", "When it should be in production", 1),
    ("competitors", "Competition: who and how many?", "Pre-filled from public catalogues; add part numbers you know",
     3),
    ("competitor_prices", "What do competitors sell for?", "Public list prices of their parts, with quantity and date",
     3),
    ("competitor_share", "How much of the market do they have?",
     "Their business in this market compared with the total, where public", 2),
    ("notes", "Other context", "Customer feedback, constraints, open questions", 4),
    ("anything_else", "Anything else to add?",
     "What else should a business case cover? Write it here; it is reviewed for the template", 2),
]  # fmt: skip


def context(session: Session, fn: str | None, co: str = "combined") -> dict | None:
    """BizDev facts for a function across all diagrams (library and background)."""
    if not fn or fn not in blocks.catalogue()["functions"]:
        return None
    _, label, mine = op.company(co)
    mk = op.makers(session)
    apps = op.with_status(op.applications(), mk, mine)
    using = [a for a in apps if any(p.fn == fn for p in a.positions)]
    sockets = sum(p.qty for a in using for p in a.positions if p.fn == fn)
    door = [a for a in using if any(p.status == "supported" and p.fn != fn for p in a.positions)]
    nearby: dict[str, int] = {}
    for a in using:
        for f in {p.fn for p in a.positions if p.status == "supported" and p.fn != fn}:
            nearby[f] = nearby.get(f, 0) + 1
    return {
        "fn": fn,
        "label": vocab.fn_label(fn),
        "portfolio": label,
        "status": op.status_of(fn, mk, mine),
        "parts": {k: v for k, v in (mk.get(fn) or {}).items()},
        "apps": using,
        "n_apps": len(apps),
        "sockets": sockets,
        "door": len(door),
        "markets": sorted({a.market for a in using}),
        "nearby": sorted(((vocab.fn_label(f), n) for f, n in nearby.items()), key=lambda x: -x[1])[:8],
        "competition": op.competition().get(fn),
        "technology": op.technology().get(fn),
        "hunt": op.hunt_for_function(apps, fn)[:12],
        "platforms": op.platforms_for(fn),
    }


def prefill(ctx: dict | None) -> dict:
    if not ctx:
        return {}
    c = ctx["competition"] or {}
    return {
        "markets": "\n".join(ctx["markets"]),
        "applications": "\n".join(sorted({a.name for a in ctx["apps"]})[:12]),
        "competitors": ", ".join(c.get("vendors") or []),
    }


def brief(case, ctx: dict | None, parts: list | None = None) -> str:
    """A self-contained market-analysis task for an AI assistant (Markdown)."""
    i = case.inputs or {}
    lines = [
        f"# Market analysis task: {case.title}",
        "",
        "You are a semiconductor market analyst. Analyse the market for the product below and the potential benefit of "
        "designing a new part for the combined Skyworks + Qorvo portfolio. Use only public information and cite every "
        "source (title, publisher, date, URL). Mark estimates as estimates and give ranges, not single numbers. Where "
        "information is missing, say so instead of guessing.",
        "",
        "## Inputs from the team",
    ]
    for key, label, _, _ in FIELDS:
        v = str(i.get(key) or "").strip()
        if v:
            lines += [f"**{label}:**", v, ""]
    if parts:  # part lines from the guided path; volumes and prices are the team's assumptions
        lines += ["## Parts in this business case (volumes and prices are assumptions)"]
        for ln in parts:
            lines.append(f"- {ln.label}: {ln.our_mpn or 'no Skyworks / Qorvo part yet'}"
                         + (f" vs {ln.competitor_mpn}" if ln.competitor_mpn else "")
                         + (f", {ln.qty} per system" if ln.qty and ln.qty > 1 else "")
                         + (f", {ln.volume:,} systems/year" if ln.volume else "")
                         + (f", target ${ln.price:.2f}" if ln.price is not None else ""))  # fmt: skip
        lines.append("")
    if ctx:
        t, c = ctx["technology"] or {}, ctx["competition"] or {}
        lines += [
            "## What BizDev knows (block-diagram library, public sources)",
            f"- Function: {ctx['label']} · portfolio status for {ctx['portfolio']}: {op.STATUS_LABEL[ctx['status']]}",
            f"- Appears in {len(ctx['apps'])} of {ctx['n_apps']} application diagrams ({ctx['sockets']} sockets), "
            f"markets: {', '.join(ctx['markets']) or 'n/a'}",
            f"- {ctx['door']} of those applications already use another Skyworks / Qorvo part (door openers)",
        ]
        if ctx["nearby"]:
            lines.append("- Our products most often next to it: " + ", ".join(f"{n} ({k})" for n, k in ctx["nearby"]))
        if c:
            lines.append(f"- Established suppliers (indicative): {', '.join(c.get('vendors') or []) or 'none known'}")
        if t:
            lines.append(f"- Technology proximity: {op.PROXIMITY_LABEL.get(t.get('proximity'), '?')} "
                         f"({', '.join(t.get('tech') or [])}). {t.get('reasoning', '')}")  # fmt: skip
        if ctx["platforms"]:
            lines.append(
                "- Our technology platforms that serve it: " + ", ".join(p["name"] for _, p in ctx["platforms"])
            )
        if ctx["hunt"]:
            lines.append("- Companies building these systems (public, indicative): "
                         + ", ".join(f"{c['name']} ({c.get('type', '')})" for c in ctx["hunt"]))  # fmt: skip
        lines.append("- Applications: " + "; ".join(sorted({a.name for a in ctx["apps"]})[:25]))
        lines.append("")
    lines += [
        "## Deliver",
        "1. Feasibility: can it be built from existing dies and processes, or what is new (die, package, "
        "qualification).",
        "2. Market today and where it is heading in 3-5 years (public size, growth, technology shifts), per target "
        "market: one main market or several.",
        "3. Demand drivers and the applications that pull volume.",
        "4. Competitive landscape: who and how many suppliers, their parts and public prices, their share of the "
        "market where public, how they differentiate, commoditisation.",
        "5. Manufacturing: which public information says where such parts are made and whether in house or "
        "subcontracted. Make no claim that is not in a public source.",
        "6. Feature check: which of the listed features matter most, which are table stakes, what is missing.",
        "7. Price: a potential price range with the volume it applies to, against the public competitor prices.",
        "8. Upside for Skyworks / Qorvo: attach with existing products, technology reuse, sockets per system, "
        "realistic share for a new entrant.",
        "9. Risks: qualification effort (e.g. AEC-Q100), time to market, price pressure, technology risk.",
        "10. Recommendation (pursue / watch / drop) with the three assumptions it depends on, and the open questions.",
        "11. Anything else a business case for this product should cover.",
        "",
        "Keep it under two pages; use tables where they help.",
    ]  # fmt: skip
    return "\n".join(lines)


# ---- what BizDev knows, per input field (shown next to the field being typed in) -----------------------------------
OURS = frozenset({"Skyworks", "Qorvo"})
_MPN = re.compile(r"\b[A-Z0-9]*[A-Z][A-Z0-9]*\d[A-Z0-9-]{3,}\b")


def _rules(family: str):
    try:
        return get_rules(family)
    except KeyError:
        return None


def _parts(session: Session, mpns: list[str]) -> list[Part]:
    seen, out = set(), []
    for m in mpns:
        m = (m or "").strip().upper()
        if not m or m in seen:
            continue
        seen.add(m)
        p = session.scalars(select(Part).where(func.upper(Part.mpn) == m)).unique().first()
        if p is not None:
            out.append(p)
    return out


def _spec_line(p: Part) -> str:
    """Package and the priority 1 and 2 parameters of a part, on one line."""
    rules = _rules(p.family)
    vals = rules.values(p) if rules else p.param_map()
    bits = [f"package {p.package.code}"] if p.package else []
    for d in rules.by_priority(1, 2) if rules else []:
        v = vals.get(d.key)
        if v not in (None, "", []):
            bits.append(f"{d.label} {format_value(d, v)}")
    return f"{p.label}: " + "; ".join(bits[:10])


def _closest(session: Session, p: Part, n: int = 3) -> tuple[list, list]:
    """The closest crosses of a competitor part: ours, and other suppliers', closest first."""
    from app.services.queries import crosses_for

    if _rules(p.family) is None:
        return [], []
    found = crosses_for(session, p, "all")
    seen, rows = set(), []
    for cat in ("fff", "functional", "package"):
        for r in found.get(cat, []):
            if r.candidate.id not in seen:
                seen.add(r.candidate.id)
                rows.append(r)
    ours = [r for r in rows if r.candidate.manufacturer.name in OURS][:n]
    others = [r for r in rows if r.candidate.manufacturer.name not in OURS | {p.manufacturer.name}][:n]
    return ours, others


def _diff_text(r) -> str:
    return "; ".join(f"{d.label} {d.cand_display} vs {d.ref_display}" for d in r.top_differences(4)
                     if d.priority == 1)  # fmt: skip


def suggestions(session: Session, case, ctx: dict | None, lines: list, sched=None,
                title: str = "") -> dict[str, list[dict]]:
    """Per case field: texts BizDev already has that fit it, each {"src": where it comes from, "text": the text}.
    Sources: the scheduled topic, the case's parts and their crosses, the function's applications and markets, and
    the matching research reports with their preliminary cases."""
    from app.services import prelim, schedule
    from app.services import reports as rp
    from app.services.pipeline import fn_for_part

    out: dict[str, list[dict]] = {k: [] for k in ("title", *(f[0] for f in FIELDS))}

    def add(field: str, src: str, text) -> None:
        text = str(text or "").strip()
        if text and len(out[field]) < 8 and all(x["text"] != text for x in out[field]):
            out[field].append({"src": src, "text": text})

    title = title or (case.title if case else "") or (sched.title if sched else "")
    inputs = (case.inputs or {}) if case else {}
    if sched is not None:  # the scheduled topic the case started from
        src = f"Scheduled topic ({schedule.source_label(sched.source)})"
        add("title", src, sched.title)
        add("notes", src, sched.note)
        add("volume", src, sched.volume)
    mpns = [x for ln in lines for x in (ln.competitor_mpn, ln.our_mpn)]
    mpns += [sched.part] if sched is not None and sched.part else []
    mpns += _MPN.findall(f"{title} {inputs.get('competitors', '')}".upper())
    parts = _parts(session, mpns)[:4]
    fn = (case.fn if case else None) or (ctx or {}).get("fn")
    from app.services import price_model as pm

    lp = pm.list_prices()
    for p in parts:  # the parts: specs, description, list price, crosses
        src = f"Part {p.mpn}"
        add("specs", src, _spec_line(p))
        for k in [k for k in lp if k.upper().startswith(p.mpn.upper())][:2]:
            e, brk = lp[k], sorted(lp[k].get("breaks") or [])
            if brk:
                qty, price = max((b for b in brk if b[0] <= 1000), default=brk[0])
                where = e.get("source") or f"{e.get('maker', '')} list price"
                line = (f"{k}: {price:.2f} {e.get('currency', 'USD')} at {qty:,} units"
                        f" ({where}, {e.get('retrieved', '')})")  # fmt: skip
                add("price", "Public list price", line)
                if p.manufacturer.name not in OURS:
                    add("competitor_prices", "Public list price", line)
        if p.description:
            add("notes", src, f"{p.label}: {p.description}")
        if p.manufacturer.name not in OURS:
            add("competitors", src, p.label)
            ours, others = _closest(session, p)
            for r in ours:
                diff = _diff_text(r)
                add("specs", f"Our closest cross to {p.mpn}", _spec_line(r.candidate))
                add("features", f"Our closest cross to {p.mpn}",
                    f"{r.candidate.label} against {p.mpn}" + (f": {diff}" if diff else ": no priority 1 differences"))
            for r in others:
                other = f"{r.candidate.label}: {_diff_text(r) or 'close match'}"
                add("competitors", f"Other crosses of {p.mpn}", other)
        fn = fn or fn_for_part(p)
    if ctx is None and fn:
        ctx = context(session, fn)
    if ctx:  # the function in the block-diagram library
        src = f"Block-diagram library ({ctx['label']})"
        add("markets", src, "\n".join(ctx["markets"]))
        apps = sorted({a.name for a in ctx["apps"]})
        hot = [a for a in apps if re.search(r"charg|\bEV\b|automotive|inverter|vehicle", a, re.I)]
        if hot:
            add("applications", src + ": vehicles and charging", "\n".join(hot[:10]))
        add("applications", src, "\n".join(apps[:12]))
        c = ctx["competition"] or {}
        if c.get("vendors"):
            add("competitors", src, ", ".join(c["vendors"]))
        if ctx["nearby"]:
            door = f"in {ctx['door']} of the {len(ctx['apps'])} designs that use it, we already sell another part"
            add("features", src, "Sold together with our " + ", ".join(n for n, _ in ctx["nearby"][:5]) + f" ({door})")
        if (ctx["technology"] or {}).get("reasoning"):
            add("notes", src, ctx["technology"]["reasoning"])
        t = ctx["technology"] or {}
        if t:
            tech = f" ({', '.join(t['tech'])})" if t.get("tech") else ""
            why = f". {t['reasoning']}" if t.get("reasoning") else ""
            prox = op.PROXIMITY_LABEL.get(t.get("proximity"), "?")
            add("feasibility", src, f"Technology proximity: {prox}{tech}{why}")
        if ctx["platforms"]:
            names = ", ".join(x["name"] for _, x in ctx["platforms"])
            add("inhouse", src + ": our technology platforms (public)", names)
        if c.get("vendors"):
            n = len(c["vendors"])
            crowd = f", {c['crowding']}" if c.get("crowding") else ""
            note = f". {c['note']}" if c.get("note") else ""
            add("competitors", src + ": how many", f"{n} established supplier{'s' if n != 1 else ''}{crowd}{note}")
        size = tam.by_function(session).get(ctx["fn"])
        if size:
            year = f", {size['year']}" if size.get("year") else ""
            add("market_size", "TAM estimates (public)",
                f"{ctx['label']}: about ${size['usd'] / 1e6:,.0f} M a year (range ${size['low'] / 1e6:,.0f}–"
                f"{size['high'] / 1e6:,.0f} M, {size['n']} source{'s' if size['n'] != 1 else ''}{year})")  # fmt: skip
        else:
            add("market_size", "TAM estimates", f"No public market-size estimate for {ctx['label']} yet: add one on "
                "TAM estimates")  # fmt: skip
    research = (sched.source or "").startswith("research:") if sched is not None else False
    slugs = (sched.source.split(":", 1)[1],) if research else ()
    for r in rp.related(" ".join([title, *(p.mpn for p in parts)]), fn, slugs)[:3]:  # research and prelim cases
        src = f"Research: {r['title']}"
        o = r.get("bu_opener") or {}
        add("title", src, r["title"])
        add("question", src, r.get("question"))
        add("feasibility", src, r.get("feasibility_why"))
        add("question", src + " (first question to the business unit)", o.get("question"))
        add("markets", src, r.get("area"))
        add("notes", src, " ".join(str(r.get("summary") or "").split()))
        if o.get("cons"):
            add("notes", src + ": against us", "\n".join(f"- {x}" for x in o["cons"]))
        c = prelim.raw(r["slug"]) or {}
        spec = {k: v for k, v in (c.get("product") or {}).get("spec") or []}
        if spec:
            add("specs", src, "\n".join(f"{k}: {v}" for k, v in spec.items() if k != "Delivery (est)"))
            add("timeframe", src, spec.get("Delivery (est)"))
        if c.get("features"):
            add("features", src, "\n".join(f"{f['feature']} – {f.get('benefit', '')}" for f in c["features"][:6]))
        for x in ((c.get("prices") or {}).get("anchors") or [])[:6]:
            if not str(x.get("part", "")).startswith(("Skyworks", "Qorvo")):
                add("competitor_prices", src, f"{x.get('part')}: {x.get('price')} at {x.get('qty')}")
        if (c.get("prices") or {}).get("items"):
            rows = [f"{x['item']}: ${x['entry']:.2f} / ${x['target']:.2f} / ${x['premium']:.2f}"
                    for x in c["prices"]["items"][:4]]  # fmt: skip
            add("price", src + " (entry / target / premium, est)", "\n".join(rows))
        if c.get("volumes"):
            add("volume", src, "\n".join(v["label"] for v in c["volumes"][:4]))
        if (c.get("architecture") or {}).get("columns", [])[1:]:
            add("competitors", src, "\n".join(c["architecture"]["columns"][1:]))
        if c.get("risks"):
            add("notes", src + ": risks", "\n".join(f"- {x}" for x in c["risks"][:4]))
    for ln in lines:  # numbers already entered on the case's part lines
        if ln.price is not None and ln.our_mpn:
            add("price", "Parts in this case", f"{ln.our_mpn}: target ${ln.price:.2f}"
                + (f" ({ln.price_source})" if ln.price_source else ""))  # fmt: skip
        if ln.volume:
            add("volume", "Parts in this case", f"{ln.label}: {ln.volume:,} systems a year × {ln.qty}")
    return {k: v for k, v in out.items() if v}
