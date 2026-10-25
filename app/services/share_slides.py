"""Shareable > Download as PowerPoint (owner, 25 Oct 2026: "the creating a PowerPoint version functionality is not
visible"): the slides of each Shareable report, built from the same data and the same values (the owner's edits over
the defaults) the report pages render. Each function takes (data, vals): data is the report's build() and vals its
edited values; it returns slide dicts for app/services/presentation_pptx.build (kinds "title", "glance", "table",
"bullets"). Roughly one slide per page block; a long table continues on a second slide.

The registry in app/services/share_reports.py (REGISTRY) names the slide function of each report."""

from itertools import zip_longest

from app.services.text import round_count

PREFIX = "Skyworks + Qorvo · "
TABLE_ROWS, TABLE_CHARS = 9, 1300  # per table slide before it continues on the next (est: what 16:9 holds readably)


def head_of(vals: dict, fallback: str) -> str:
    """The header band title: the report's header title without the company prefix the slide frame adds."""
    t = str(vals.get("hdr.title") or "").strip() or fallback
    return t[len(PREFIX):] if t.startswith(PREFIX) else t


def paras(vals: dict, section: str) -> str:
    return " ".join(str(p.get("text") or "") for p in vals.get(f"paras.{section}") or [])


def _facts(data: dict, vals: dict) -> list[dict]:
    return [{"num": str(vals.get(f"fact.{f['key']}.num", f["num"])),
             "label": str(vals.get(f"fact.{f['key']}.label", f["label"]))} for f in data["facts"]]  # fmt: skip


def table(head: str, title: str, cols: list[str], rows: list[list[str]], lead: str = "", note: str = "",
          widths: tuple[float, ...] = ()) -> list[dict]:  # fmt: skip
    """One native table slide, continued on more slides when it is long."""
    chunks: list[list] = [[]]
    for r in rows:  # a new slide after TABLE_ROWS rows or about TABLE_CHARS characters of text
        size = sum(len(str(c)) for c in r) + 60
        if chunks[-1] and (len(chunks[-1]) >= TABLE_ROWS or
                           sum(sum(len(str(c)) for c in x) + 60 for x in chunks[-1]) + size > TABLE_CHARS):  # fmt: skip
            chunks.append([])
        chunks[-1].append(r)
    if len(chunks) > 1:  # spread the rows evenly, so no slide carries a lone last row
        per = -(-len(rows) // len(chunks))
        chunks = [rows[i : i + per] for i in range(0, len(rows), per)]
    out = []
    for n, chunk in enumerate(chunks):
        out.append({"kind": "table", "head": head, "title": title + (" (continued)" if n else ""),
                    "body": {"lead": "" if n else lead, "cols": cols, "rows": chunk, "widths": list(widths),
                             "note": note if n == len(chunks) - 1 else ""}})  # fmt: skip
    return out


def _cover(head: str, vals: dict, sub: str, today) -> dict:
    return {"kind": "title", "head": head, "title": str(vals.get("title") or head),
            "body": {"heading": str(vals.get("title") or head), "sub": sub, "date": today}}  # fmt: skip


def _sources(head: str, vals: dict, extra: list[str] = ()) -> dict:
    lines, n = [], 0
    while f"src.{n}" in vals:
        if s := str(vals[f"src.{n}"]).strip():
            lines.append(s)
        n += 1
    return {"kind": "bullets", "head": head, "title": "Sources",
            "body": {"points": [*extra, *lines, "Public information."]}}  # fmt: skip


def _pairs(data: dict, vals: dict, example: str) -> list[list[str]]:
    rows = []
    for i, p in enumerate(data["pairs"], start=1):
        ex = " with ".join(x for x in (p.get("s_ex"), p.get("q_ex")) if x)
        line = str(vals.get(f"pair.{p['key']}.line", p["line"]))
        rows.append([str(i), p["skyworks"], p["qorvo"], str(vals.get(f"pair.{p['key']}.benefit", p["benefit"])),
                     line + (f" {example} {ex}." if ex else "")])  # fmt: skip
    return rows


PAIR_COLS = ["#", "Skyworks", "Qorvo", "Benefit", "What it is useful for"]
PAIR_W = (0.5, 2.4, 2.4, 1.9, 4.9)


def synergies(data: dict, vals: dict, today=None, ip_note: str = "") -> list[dict]:
    h = head_of(vals, "Synergies")
    v = vals.get
    slides = [_cover(h, vals, "Management brief", today),
              {"kind": "glance", "head": h, "title": str(v("sec.glance.heading") or "Combined at a glance"),
               "body": {"lead": paras(vals, "glance"), "facts": _facts(data, vals)}}]  # fmt: skip
    mfg = [[str(v(f"mfg.{i}.label", m.get("label", ""))), str(v(f"mfg.{i}.skyworks", m.get("skyworks", ""))),
            str(v(f"mfg.{i}.qorvo", m.get("qorvo", "")))] for i, m in enumerate(data["mfg"])]  # fmt: skip
    slides += table(h, str(v("sec.manufacturing.heading") or ""), ["Capability", "Skyworks", "Qorvo"], mfg,
                    paras(vals, "manufacturing"), widths=(5.6, 3.0, 3.0))  # fmt: skip
    tech = data["tech"]
    cols = [[p["label"] + (f" ({p['ip']})" if p.get("ip") else "") for p in tech[s]] for s in ("Skyworks", "Both",
                                                                                               "Qorvo")]  # fmt: skip
    slides += table(h, str(v("sec.technologies.heading") or ""),
                    [f"Skyworks ({len(tech['Skyworks'])})", f"Both ({len(tech['Both'])})",
                     f"Qorvo ({len(tech['Qorvo'])})"],
                    [[a or "", b or "", c or ""] for a, b, c in zip_longest(*cols)], paras(vals, "technologies"),
                    ip_note if data.get("ip") else "")  # fmt: skip
    sides = (("Skyworks", "Skyworks only", data["sky"]), ("Both", "Both offer", data["both"]),
             ("Qorvo", "Qorvo only", data["qor"]))  # fmt: skip
    useful = [f"{v(f'ovl.{s.lower()}.line', '')} [{v(f'ovl.{s.lower()}.benefit', '')}]" for s, _, _ in sides]
    fams = [[f"{f['label']} ({round_count(f['total'])})" for f in fs] for _, _, fs in sides]
    slides += table(h, str(v("sec.overlap.heading") or ""),
                    [f"{label} ({round_count(len(fs))} families)" for _, label, fs in sides],
                    [useful, *([a or "", b or "", c or ""] for a, b, c in zip_longest(*fams))], paras(vals, "overlap"),
                    "Active parts per family in the public catalogues, rounded down.")  # fmt: skip
    slides += table(h, str(v("sec.combine.heading") or ""), PAIR_COLS, _pairs(data, vals, "For example"),
                    paras(vals, "combine"), "Continued in: Automotive: technologies and applications.",
                    PAIR_W)  # fmt: skip
    return [*slides, _sources(h, vals)]


def automotive(data: dict, vals: dict, today=None, ip_note: str = "") -> list[dict]:
    h = head_of(vals, "Automotive")
    v = vals.get
    slides = [_cover(h, vals, "Extension of: Skyworks + Qorvo synergies", today),
              {"kind": "glance", "head": h, "title": str(v("sec.offer.heading") or "At a glance"),
               "body": {"lead": paras(vals, "offer"), "facts": _facts(data, vals)}}]  # fmt: skip
    tech = [[t["label"], t["owner"] + (f" · {t['ip']}" if t.get("ip") else ""),
             str(v(f"tech.{t['key']}.car", t["car"]))]
            for t in data["tech"]]  # fmt: skip
    slides += table(h, str(v("sec.technologies.heading") or ""), ["Technology", "Company", "In the car"], tech,
                    paras(vals, "technologies"), ip_note if data.get("ip") else "", (3.4, 2.2, 6.5))  # fmt: skip
    subs = [[str(v(f"sub.{s['key']}.title", s["title"])), str(v(f"sub.{s['key']}.line", s["line"])),
             ", ".join(s["series"])] for s in data["subsystems"]]  # fmt: skip
    slides += table(h, str(v("sec.applications.heading") or ""), ["Sub-system", "What we bring", "AEC-Q series"],
                    subs, paras(vals, "applications"),
                    "All series listed are AEC-Q qualified; an x stands for any character.",
                    (3.6, 5.6, 2.9))  # fmt: skip
    slides += table(h, str(v("sec.pairs.heading") or ""), PAIR_COLS, _pairs(data, vals, "AEC-Q example"),
                    paras(vals, "pairs"), widths=PAIR_W)  # fmt: skip
    std = v("standards") or data.get("standards") or []
    return [*slides, _sources(h, vals, ["Standards: " + " · ".join(std)] if std else [])]


def overview(data: dict, vals: dict, today=None, ip_note: str = "") -> list[dict]:
    h = head_of(vals, "Technology overview")
    v = vals.get
    facts = [{"num": str(v(f"fact.{f['key']}.num", f["num"])), "label": str(v(f"fact.{f['key']}.label", f["label"]))}
             for f in data["facts"]]  # fmt: skip
    slides = [_cover(h, vals, "Technology overview", today),
              {"kind": "glance", "head": h, "title": "At a glance",
               "body": {"lead": paras(vals, "glance"), "facts": facts}}]  # fmt: skip
    mk = data["markets"]
    matrix = [[str(v(f"plat.{r['key']}.label", r["label"])), *(str(v(f"dot.{r['key']}.{m['key']}") or "") for m in mk)]
              for r in data["matrix"]]  # fmt: skip
    slides += table(h, str(v("sec.glance.heading") or "Platforms by market"),
                    ["Platform", *(str(v(f"mkt.{m['key']}.short", m["short"])) for m in mk)], matrix,
                    note="Who offers each platform in each market: Skyworks, Qorvo or Both.")  # fmt: skip
    plats = []
    for p in data["platforms"]:
        k = f"plat.{p['key']}"
        plats.append([str(v(f"{k}.label", p["label"])), str(v(f"{k}.owner", p["owner"])),
                      f"{v(k + '.what', '')} {v(k + '.good_for', '')}".strip()])  # fmt: skip
    slides += table(h, str(v("sec.platforms.heading") or ""), ["Platform", "Company", "What it is and is good for"],
                    plats, paras(vals, "platforms"), widths=(3.4, 1.6, 7.1))  # fmt: skip
    mkts = []
    for m in mk:
        k = f"mkt.{m['key']}"
        parts = [f"{v(f'{k}.part.{i}', name)} ({series})" for i, (name, series) in enumerate(m["parts"])]
        mkts.append([str(v(f"{k}.label", m["label"])), str(v(f"{k}.brings", m["brings"])),
                     ", ".join(v(f"{k}.functions") or m["functions"]), "; ".join(parts)])  # fmt: skip
    slides += table(h, str(v("sec.markets.heading") or ""), ["Market", "What we bring", "Functions", "Example parts"],
                    mkts, paras(vals, "markets"), widths=(2.2, 3.3, 3.2, 3.4))  # fmt: skip
    fams = []
    for f in data["families"]:
        k = f"fam.{f['slug']}"
        figs = ", ".join(f"{v(f'{k}.fig.{i}.text', g['text'])} ({v(f'{k}.fig.{i}.part', g['mpn'])})"
                         for i, g in enumerate(f.get("figures") or []))  # fmt: skip
        fams.append([f["label"], str(v(f"{k}.skyworks", f["Skyworks"])), str(v(f"{k}.qorvo", f["Qorvo"])),
                     str(v(f"{k}.headline", f["headline"])) + (f"; {figs}" if figs else "")])  # fmt: skip
    slides += table(h, str(v("sec.families.heading") or ""), ["Family", "Skyworks", "Qorvo", "Headline capability"],
                    fams, paras(vals, "families"), widths=(3.0, 1.3, 1.3, 6.5))  # fmt: skip
    return [*slides, _sources(h, vals)]
