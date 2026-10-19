"""Case analysis: what BizDev knows about a function (occurrence, door openers, competition, technology
proximity, portfolio parts) and a market-analysis brief an AI assistant can run. The app sends nothing anywhere: the
brief is copied by the user, and the result is pasted back."""

from sqlalchemy.orm import Session

from app.services import blocks
from app.services import opportunity as op

STATUSES = {"collecting": "Collecting inputs", "analysing": "Analysis running", "discussing": "Discussing",
            "decided": "Decided"}  # fmt: skip
NOTE_KINDS = {"upside": "Upside", "risk": "Risk", "feature": "Feature idea", "comment": "Comment"}
FIELDS = [  # (key, label, help, rows)
    ("question", "Decision to support", "What should the analysis decide? e.g. a 5 GHz BAW filter for Wi-Fi 7?", 2),
    ("markets", "Target markets", "Automotive, industrial, RF & connectivity…, one per line", 3),
    ("applications", "Target applications", "Where the part would go, one per line", 3),
    ("features", "Features", "One per line: feature – why it matters to the customer", 5),
    ("specs", "Target specifications", "Key numbers: voltage, current, frequency, package, qualification…", 4),
    ("price", "Target price / ASP", "If known, with the volume it applies to", 1),
    ("volume", "Volume", "Units per year, per market if known", 1),
    ("timeframe", "Timeframe", "When it should be in production", 1),
    ("competitors", "Known competitors and parts", "Pre-filled from public catalogues; add part numbers you know", 3),
    ("notes", "Other context", "Customer feedback, constraints, open questions", 4),
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
    cat = blocks.catalogue()["functions"]
    return {
        "fn": fn,
        "label": cat[fn].get("label", fn),
        "portfolio": label,
        "status": op.status_of(fn, mk, mine),
        "parts": {k: v for k, v in (mk.get(fn) or {}).items()},
        "apps": using,
        "n_apps": len(apps),
        "sockets": sockets,
        "door": len(door),
        "markets": sorted({a.market for a in using}),
        "nearby": sorted(((cat.get(f, {}).get("label", f), n) for f, n in nearby.items()), key=lambda x: -x[1])[:8],
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
        "1. Market today and where it is heading in 3-5 years (size, growth, technology shifts), per target market.",
        "2. Demand drivers and the applications that pull volume.",
        "3. Competitive landscape: leading suppliers and parts, how they differentiate, price level, commoditisation.",
        "4. Feature check: which of the listed features matter most, which are table stakes, what is missing.",
        "5. Upside for Skyworks / Qorvo: attach with existing products, technology reuse, sockets per system, "
        "realistic share for a new entrant.",
        "6. Risks: qualification effort (e.g. AEC-Q100), time to market, price pressure, technology risk.",
        "7. Recommendation (pursue / watch / drop) with the three assumptions it depends on, and the open questions.",
        "",
        "Keep it under two pages; use tables where they help.",
    ]  # fmt: skip
    return "\n".join(lines)
