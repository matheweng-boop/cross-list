"""One content model per Shareable report, laid out three ways (owner, 26 Oct 2026: "make distinct versions but that
are more cleanly formatted"): the A4 PDF (app/services/share_pdf.py), the PowerPoint (app/services/share_slides.py)
and the page on screen (the report templates) show the SAME facts, numbers, part names, categories and sources; only
the wording length and the arrangement differ per medium.

doc(key, data, vals) turns a report's build() and its shown values (the owner's edits over the defaults, read fresh
on every request) into:

    {"key", "title", "head", "kicker", "sections": [section], "sources": [line], "prepared": line}
    section = {"id", "heading", "paras": [full text], "slide": short text, "new_page": bool, "blocks": [block]}

Blocks: "facts" (number tiles), "table" (columns and rows; a cell may carry right-aligned marks), "cols" (three
company columns), "pairs" (Skyworks + Qorvo pairs), "links" (learn-more lines). facts_of(doc) lists the facts every
version must carry (tests/test_share_versions.py).

The short slide text of a section is the owner's "slide.<section>" field (editable next to its paragraphs), else the
YAML's "slide:" of that section, else the first sentence of its paragraphs."""

import re
from datetime import date
from itertools import zip_longest
from urllib.parse import urlparse

from app.services.text import round_count

PREFIX = "Skyworks + Qorvo · "
SLIDE_MAX = 160  # characters of a slide's short text (tech_overview_edit.SLIDE_MAX)
WHO = ("Skyworks", "Both", "Qorvo")


def date_text(d) -> str:
    return f"{d.day} {d:%b %Y}" if isinstance(d, date) else str(d or "")


def head_of(vals: dict, fallback: str) -> str:
    """The header title without the company prefix the PDF header and slide frame add."""
    t = str(vals.get("hdr.title") or "").strip() or fallback
    return t[len(PREFIX) :] if t.startswith(PREFIX) else t


def first_sentence(text: str, most: int = SLIDE_MAX) -> str:
    """The first sentence of a text, trimmed at a word to at most `most` characters."""
    t = " ".join(str(text or "").split())
    m = re.search(r"^(.+?[.!?])(?:\s|$)", t)
    s = m.group(1) if m else t
    if len(s) > most:
        s = s[: most - 1].rsplit(" ", 1)[0].rstrip(",;:") + "…"
    return s


def paras(vals: dict, section: str) -> list[str]:
    return [" ".join(str(p.get("text") or "").split()) for p in vals.get(f"paras.{section}") or [] if p.get("text")]


def slide_text(vals: dict, section: str) -> str:
    """The section's short slide text: the owner's slide field, else the first sentence of its paragraphs."""
    own = " ".join(str(vals.get(f"slide.{section}") or "").split())
    return own or first_sentence(" ".join(paras(vals, section)))


def _src(vals: dict) -> list[str]:
    out, n = [], 0
    while f"src.{n}" in vals:
        if s := str(vals[f"src.{n}"]).strip():
            out.append(s)
        n += 1
    return out


def _sec(vals: dict, sid: str, heading: str, blocks: list, new_page: bool = False, para_key: str = "") -> dict:
    pk = para_key or sid
    return {"id": sid, "heading": heading, "paras": paras(vals, pk), "slide": slide_text(vals, pk),
            "new_page": new_page, "blocks": blocks}  # fmt: skip


def _facts(data: dict, vals: dict, notes: bool = False) -> dict:
    items = []
    for f in data["facts"]:
        k = f"fact.{f['key']}"
        items.append({"num": str(vals.get(f"{k}.num", f["num"])), "label": str(vals.get(f"{k}.label", f["label"])),
                      "note": str(vals.get(f"{k}.note", f.get("note", ""))) if notes else ""})  # fmt: skip
    return {"kind": "facts", "items": items}


def _pairs(data: dict, vals: dict, ex_word: str) -> dict:
    items = []
    for i, p in enumerate(data["pairs"], start=1):
        items.append({"n": i, "skyworks": p["skyworks"], "qorvo": p["qorvo"],
                      "benefit": str(vals.get(f"pair.{p['key']}.benefit", p["benefit"])),
                      "line": str(vals.get(f"pair.{p['key']}.line", p["line"])),
                      "ex": [x for x in (p.get("s_ex"), p.get("q_ex")) if x], "ex_word": ex_word})  # fmt: skip
    return {"kind": "pairs", "items": items}


def cell(text: str, *marks: tuple[str, str], code: list[str] | None = None) -> dict:
    """A table cell: text, right-aligned marks (("Skyworks", "who"), ("IP: both", "ip"), ("Market access", "ben")),
    and part series shown in a fixed-width font."""
    return {"t": str(text or ""), "marks": [m for m in marks if m[0]], "code": list(code or [])}


# ---- the reports -----------------------------------------------------------------------------------------------------
def synergies(data: dict, vals: dict, today=None) -> dict:
    v = vals.get
    mfg = {"kind": "table", "cols": ["Capability", "Skyworks", "Qorvo"], "widths": [5.2, 2.4, 2.4],
           "rows": [[cell(v(f"mfg.{i}.label", m.get("label", ""))), cell(v(f"mfg.{i}.skyworks", m.get("skyworks", ""))),
                     cell(v(f"mfg.{i}.qorvo", m.get("qorvo", "")))] for i, m in enumerate(data["mfg"])],
           "note": ""}  # fmt: skip
    tech = data["tech"]
    techcols = {"kind": "cols", "cols": [
        {"who": s, "head": s, "count": str(len(tech[s])), "line": "", "tag": "",
         "items": [cell(p["label"], (p.get("ip", ""), "ip")) for p in tech[s]]} for s in WHO],
        "note": data.get("ip_note", "") if data.get("ip") else ""}  # fmt: skip
    sides = (("Skyworks", "Skyworks only", data["sky"]), ("Both", "Both offer", data["both"]),
             ("Qorvo", "Qorvo only", data["qor"]))  # fmt: skip
    overlap = {"kind": "cols", "cols": [
        {"who": s, "head": label, "count": f"{round_count(len(fs))} families",
         "line": str(v(f"ovl.{s.lower()}.line", "")), "tag": str(v(f"ovl.{s.lower()}.benefit", "")),
         "items": [cell(f["label"], (round_count(f["total"]), "num")) for f in fs]} for s, label, fs in sides],
        "note": "Active parts per family in the public catalogues, rounded down."}  # fmt: skip
    pairs = _pairs(data, vals, "For example")
    pairs["note"] = "Continued in: Automotive: technologies and applications."
    cat = data.get("catalogue_date")
    return {"key": "synergies", "title": str(v("title") or "Skyworks + Qorvo synergies"),
            "head": head_of(vals, "Synergies"), "subtitle": str(v("hdr.subtitle") or ""),
            "kicker": f"Management brief · {date_text(today)}",
            "sections": [_sec(vals, "glance", str(v("sec.glance.heading") or ""), [_facts(data, vals)]),
                         _sec(vals, "manufacturing", str(v("sec.manufacturing.heading") or ""), [mfg]),
                         _sec(vals, "technologies", str(v("sec.technologies.heading") or ""), [techcols], True),
                         _sec(vals, "overlap", str(v("sec.overlap.heading") or ""), [overlap]),
                         _sec(vals, "combine", str(v("sec.combine.heading") or ""), [pairs], True)],
            "sources": _src(vals),
            "prepared": f"Prepared {date_text(today)}" + (f"; catalogue as of {date_text(cat)}" if cat else "")
            + ". Public information."}  # fmt: skip


def automotive(data: dict, vals: dict, today=None) -> dict:
    v = vals.get
    tech = {"kind": "table", "cols": ["Technology", "In the car", "Company"], "widths": [3.0, 4.6, 2.8],
            "rows": [[cell(t["label"]), cell(v(f"tech.{t['key']}.car", t["car"])),
                      cell("", (t["owner"], "who"), (t.get("ip", ""), "ip"))] for t in data["tech"]],
            "note": data.get("ip_note", "") if data.get("ip") else "", "compact": True}  # fmt: skip
    subs = {"kind": "table", "cols": ["Sub-system", "What we bring", "AEC-Q series"], "widths": [3.0, 4.8, 2.6],
            "rows": [[cell(v(f"sub.{s['key']}.title", s["title"])), cell(v(f"sub.{s['key']}.line", s["line"])),
                      cell("", code=s["series"])] for s in data["subsystems"]],
            "note": "All series listed are AEC-Q qualified; an x stands for any character.",
            "compact": True}  # fmt: skip
    pairs = _pairs(data, vals, "AEC-Q example")
    std = v("standards") or data.get("standards") or []
    pairs["note"] = ("Standards: " + " · ".join(std)) if std else ""
    return {"key": "automotive", "title": str(v("title") or "Automotive"), "head": head_of(vals, "Automotive"),
            "subtitle": str(v("hdr.subtitle") or ""), "kicker": "Extension of: Skyworks + Qorvo synergies",
            "sections": [_sec(vals, "offer", str(v("sec.offer.heading") or ""), [_facts(data, vals)]),
                         _sec(vals, "technologies", str(v("sec.technologies.heading") or ""), [tech]),
                         _sec(vals, "applications", str(v("sec.applications.heading") or ""), [subs], True),
                         _sec(vals, "pairs", str(v("sec.pairs.heading") or ""), [pairs], True)],
            "sources": _src(vals), "standards": list(std),
            "prepared": f"Prepared {date_text(today)}. Public information."}  # fmt: skip


def overview(data: dict, vals: dict, today=None) -> dict:
    v = vals.get
    mk = data["markets"]
    matrix = {"kind": "table", "cols": ["Platform", *(str(v(f"mkt.{m['key']}.short", m["short"])) for m in mk)],
              "widths": [3.6, *([1.1] * len(mk))], "dots": True,
              "rows": [[cell(v(f"plat.{r['key']}.label", r["label"])),
                        *(cell(str(v(f"dot.{r['key']}.{m['key']}") or "")) for m in mk)] for r in data["matrix"]],
              "note": "Who offers each platform in each market: Skyworks, Qorvo or Both. Markets: "
              + ", ".join(f"{v(f'mkt.{m['key']}.short', m['short'])} = {v(f'mkt.{m['key']}.label', m['label'])}"
                          for m in mk) + "."}  # fmt: skip
    plats = {"kind": "table", "cols": ["Platform", "What it is and is good for", "Company"], "widths": [2.7, 6.1, 1.6],
             "compact": True,
             "rows": [[cell(v(f"plat.{p['key']}.label", p["label"])),
                       cell(f"{v(f'plat.{p['key']}.what', p['what'])} {v(f'plat.{p['key']}.good_for', p['good_for'])}"),
                       cell("", (str(v(f"plat.{p['key']}.owner", p["owner"])), "who"))] for p in data["platforms"]],
             "note": ""}  # fmt: skip
    mrows = []
    for m in mk:
        k = f"mkt.{m['key']}"
        parts = [f"{v(f'{k}.part.{i}', name)} ({series})" for i, (name, series) in enumerate(m["parts"])]
        mrows.append([cell(v(f"{k}.label", m["label"])), cell(v(f"{k}.brings", m["brings"])),
                      cell(", ".join(v(f"{k}.functions") or m["functions"])), cell("; ".join(parts))])  # fmt: skip
    # slides keep the functions and example parts whole (they are facts) and show 3 markets per slide
    mkts = {"kind": "table", "cols": ["Market", "What we bring", "Functions", "Example parts"],
            "widths": [1.8, 2.9, 2.7, 3.0], "rows": mrows, "note": "", "compact": True, "keep_cols": [2, 3],
            "slide_rows": 3, "facts": [series for m in mk for _, series in m["parts"]]}  # fmt: skip
    frows = []
    for f in data["families"]:
        k = f"fam.{f['slug']}"
        figs = ", ".join(f"{v(f'{k}.fig.{i}.text', g['text'])} ({v(f'{k}.fig.{i}.part', g['mpn'])})"
                         for i, g in enumerate(f.get("figures") or []))  # fmt: skip
        frows.append([cell(f["label"]), cell(str(v(f"{k}.skyworks", f["Skyworks"]))),
                      cell(str(v(f"{k}.qorvo", f["Qorvo"]))),
                      cell(str(v(f"{k}.headline", f["headline"])) + (f"; {figs}" if figs else ""))])  # fmt: skip
    fams = {"kind": "table", "cols": ["Family", "Skyworks", "Qorvo", "Headline capability"],
            "widths": [2.6, 1.2, 1.0, 5.6], "num_cols": [1, 2], "rows": frows, "note": "", "compact": True,
            "keep_cols": [3], "slide_rows": 5,
            "facts": [str(v(f"fam.{f['slug']}.fig.{i}.part", g["mpn"])) for f in data["families"]
                      for i, g in enumerate(f.get("figures") or [])]}  # fmt: skip
    links, n = [], 0
    while f"learn.{n}.label" in vals:
        host = urlparse(str(vals.get(f"learn.{n}.url") or "")).netloc.removeprefix("www.")
        links.append(f"{vals[f'learn.{n}.label']}" + (f" ({host})" if host else ""))
        n += 1
    cat = data.get("catalogue_date")
    extra = f"{round_count(data['unclassified'])} catalogue parts without a family are counted in the total only." \
        if data.get("unclassified") else ""  # fmt: skip
    return {"key": "overview", "title": str(v("title") or "Technology overview"),
            "head": head_of(vals, "Technology overview"), "subtitle": str(v("hdr.subtitle") or ""),
            "kicker": f"Technology overview · {date_text(today)}",
            "sections": [_sec(vals, "glance", "", [_facts(data, vals, notes=True)], para_key="glance"),
                         {**_sec(vals, "matrix", str(v("sec.glance.heading") or "Platforms by market"), [matrix]),
                          "paras": [], "slide": ""},
                         _sec(vals, "platforms", str(v("sec.platforms.heading") or ""), [plats], True),
                         _sec(vals, "markets", str(v("sec.markets.heading") or ""), [mkts], True),
                         _sec(vals, "families", str(v("sec.families.heading") or ""),
                              [fams, {"kind": "links", "head": "Learn more", "items": links}], True)],
            "sources": [*_src(vals), *([extra] if extra else [])],
            "prepared": f"Prepared {date_text(today)}" + (f"; catalogue as of {date_text(cat)}" if cat else "")
            + ". Public information."}  # fmt: skip


BUILDERS = {"synergies": synergies, "automotive": automotive, "overview": overview}


def doc(key: str, data: dict, vals: dict, today=None, ip_note: str = "") -> dict:
    """The content model of one report (key from the share_reports registry)."""
    return BUILDERS[key]({**data, "ip_note": ip_note}, vals, today or date.today())


def facts_of(d: dict) -> list[str]:
    """The facts every version of a report carries: numbers, categories, part names, benefit and IP tags, sources."""
    out: list[str] = []
    for s in d["sections"]:
        for b in s["blocks"]:
            if b["kind"] == "facts":
                out += [x for f in b["items"] for x in (f["num"], f["label"])]
            elif b["kind"] == "table":
                for r in b["rows"]:
                    out.append(r[0]["t"])
                    out += [m[0] for c in r for m in c["marks"]] + [x for c in r for x in c["code"]]
                out += b.get("facts") or []
            elif b["kind"] == "cols":
                for c in b["cols"]:
                    out += [c["head"], *(i["t"] for i in c["items"]), *(m[0] for i in c["items"] for m in i["marks"])]
                    out += [c["tag"]] if c["tag"] else []
            elif b["kind"] == "pairs":
                out += [x for p in b["items"] for x in (p["skyworks"], p["qorvo"], p["benefit"], *p["ex"])]
            elif b["kind"] == "diagram":
                out.append(b["title"])
    out += d["sources"]
    return [x for x in dict.fromkeys(out) if x]


def all_text(d: dict) -> str:
    """Every text of the model, for the word check."""
    parts = [d["title"], d["head"], d.get("subtitle", ""), d["kicker"], *d["sources"], d["prepared"]]
    for s in d["sections"]:
        parts += [s["heading"], s["slide"], *s["paras"]]
        for b in s["blocks"]:
            parts.append(b.get("note", ""))
            if b["kind"] == "table":
                parts += b["cols"] + [c["t"] for r in b["rows"] for c in r]
            elif b["kind"] == "cols":
                parts += [x for c in b["cols"] for x in (c["head"], c["line"], *(i["t"] for i in c["items"]))]
            elif b["kind"] == "pairs":
                parts += [p["line"] for p in b["items"]]
            elif b["kind"] in ("links", "bullets"):
                parts += b["items"]
            elif b["kind"] == "diagram":
                parts += [b["title"], *b["layout"]["labels"]]
    parts += facts_of(d)
    return "\n".join(str(p) for p in parts if p)


def zipped(cols: list[list]) -> list[list]:
    return [list(r) for r in zip_longest(*cols)]
