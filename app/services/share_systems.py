"""Shareable system briefs (owner, 27 Oct 2026): "For the shareables, create a portion for UWB and for V2X and GNSS and
for Automotive Radio (AM/FM/DAB) with Block Diagrams and listing some parts from both Skyworks and Qorvo that's 4
different Docs." Each brief: a short intro, the block diagram of the system (from a library diagram, drawn by
app/services/share_diagram.py), the parts split into the core solution (AEC-Q qualified only) and the peripherals
around it (automotive or not, as bundle options; owner, 27 Oct 2026: "differentiate between automotive and
non-automotive ... as long as the core solution is still automotive qualified"), and 2-3 talking points.

Words: data/business/share_systems.yaml, taken from the site's reports and library topics only (no new research).
Parts: only active Skyworks / Qorvo catalogue parts (tech_overview.active_rows); the grade comes from the data
(autograde). Each brief is one share_reports.REGISTRY entry, so it gets the page, the A4 PDF and the PowerPoint, with
the same editing (paragraphs, headings, slide texts, notes, sources) and word check as the other reports."""

import re
from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT
from app.services import share_diagram as sdg
from app.services import share_doc as sd
from app.services import share_slides as ss
from app.services import tech_overview as to
from app.services import tech_overview_edit as te

FILE = PROJECT_ROOT / "data" / "business" / "share_systems.yaml"
KEYS = ("uwb", "v2x", "gnss", "radio")
SECTIONS = ("intro", "diagram", "core", "peripherals", "talk")
LIMITS = {"intro": (3, 640), "diagram": (1, 280), "core": (1, 200), "peripherals": (1, 240), "talk": (3, 560)}
AUTO, NOT_AUTO = "Automotive (AEC-Q)", "Not automotive"
COLS = ["Part", "Block", "Key specs", "Automotive grade"]
WIDTHS = [2.8, 2.1, 4.1, 2.2]


@lru_cache
def curated() -> dict:
    return (yamlio.load(FILE.read_text()) if FILE.exists() else None) or {}


def cur(key: str) -> dict:
    """One brief's words, with the shared defaults (section headings, notes, sources) filled in."""
    base = curated().get("defaults") or {}
    c = dict(curated().get(key) or {})
    secs = {}
    for s in SECTIONS:
        secs[s] = {**((base.get("sections") or {}).get(s) or {}), **((c.get("sections") or {}).get(s) or {})}
    c["sections"] = secs
    for k in ("core_note", "peripheral_note", "sources"):
        c.setdefault(k, base.get(k))
    return c


# ---- the diagram: a library diagram, simplified --------------------------------------------------------------------
def source(ref: str) -> dict:
    """The library diagram a brief is drawn from: "template:<name>" (data/blocks/templates.yaml) or "topic:<key>"
    (the block diagram of a Systems library topic)."""
    kind, _, name = str(ref).partition(":")
    if kind == "template":
        from app.services import blocks

        return next((t for t in blocks.templates() if t.get("name") == name), {}) or {}
    if kind == "topic":
        from app.services import library

        return (library.topic(name) or {}).get("block_diagram") or {}
    return {}


def _blocks(g: dict) -> list[tuple[str, str]]:
    """(function, label) of each block of a library group; "fn x2" becomes the label with "×2"."""
    out = []
    for b in g.get("blocks") or []:
        if isinstance(b, dict):
            fn, label, qty = b.get("fn", ""), b.get("label") or "", int(b.get("qty") or 1)
        else:
            m = re.fullmatch(r"(\S+)(?:\s+x(\d+))?", str(b).strip())
            fn, label, qty = (m.group(1), "", int(m.group(2) or 1)) if m else (str(b), "", 1)
        out.append((fn, label, qty))
    return out


def diagram(key: str) -> dict:
    """{"title", "from", "groups", "links", "layout", "svg", "at": {"gid.fn": label}} of one brief."""
    from app.services import vocab

    c = cur(key)
    dg = c.get("diagram") or {}
    src = source(dg.get("from", ""))
    drop, place = set(dg.get("drop") or []), dg.get("place") or {}
    labels, short = dg.get("labels") or {}, dg.get("short") or {}
    parts = c.get("parts") or {}
    marks = {p["at"]: "peripheral" for p in parts.get("peripherals") or []}
    marks.update({p["at"]: "core" for p in parts.get("core") or []})
    groups, at = [], {}
    for g in src.get("groups") or []:
        gid = g.get("id")
        if not gid or gid in drop:
            continue
        col, row = place.get(gid, (g.get("col", 0), g.get("row", 0)))
        blocks, seen = [], set()
        for fn, label, qty in _blocks(g):
            ref = f"{gid}.{fn}"
            text = short.get(ref) or label or vocab.fn_label(fn)
            if ref not in short and qty > 1:
                text += f" ×{qty}"
            if text in seen:
                continue
            seen.add(text)
            at.setdefault(ref, text)
            blocks.append({"label": text, "mark": marks.get(ref, ""), "fn": fn})
        groups.append({"id": gid, "label": labels.get(gid) or " ".join(str(g.get("label", "")).split()),
                       "col": int(col), "row": int(row), "blocks": blocks})  # fmt: skip
    ids = {g["id"] for g in groups}
    links = [(a, b) for a, b, *_ in (dg.get("links") or src.get("links") or []) if a in ids and b in ids]
    title = dg.get("title") or ""
    lay = sdg.layout(groups, links, title)
    return {"title": title, "from": dg.get("from", ""), "groups": groups, "links": links, "layout": lay,
            "svg": sdg.svg(lay), "at": at}  # fmt: skip


# ---- the parts ------------------------------------------------------------------------------------------------------
@lru_cache
def _rows() -> dict[str, dict]:
    return {r["mpn"].upper(): r for r in to.active_rows()}


def _grade(p: dict, row: dict) -> tuple[str, bool]:
    from app.services import autograde

    aec = row.get("automotive") is True or autograde.is_aec(row)
    if not aec:
        return NOT_AUTO, False
    return str(p.get("grade") or AUTO), True


def parts(key: str, at: dict) -> dict:
    """{"core": [...], "peripherals": [...], "left_out": [mpn]}: each part {mpn, who, block, spec, grade, aec,
    preview}. A part that is not active in the catalogue is left out; a core part that is not AEC-Q qualified is
    left out too (the core must be automotive)."""
    from app.services import lifecycle

    c = cur(key).get("parts") or {}
    rows = _rows()
    out: dict = {"core": [], "peripherals": [], "left_out": []}
    for side in ("core", "peripherals"):
        for p in c.get(side) or []:
            mpn = str(p["mpn"])
            row = rows.get(mpn.upper())
            if row is None:
                out["left_out"].append(mpn)
                continue
            grade, aec = _grade(p, row)
            if side == "core" and not aec:
                out["left_out"].append(mpn)
                continue
            out[side].append({"mpn": row["mpn"], "who": row["manufacturer"], "at": p["at"],
                              "block": at.get(p["at"], ""), "spec": " ".join(str(p.get("spec") or "").split()),
                              "grade": grade, "aec": aec,
                              "preview": lifecycle.status_class(row["status"]) == "preview"})  # fmt: skip
    return out


# ---- coverage: every block checked for both companies (owner, 27 Oct 2026: "this is the sort of depth I expect") -----
COMPANIES = ("skyworks", "qorvo")
KINDS = ("auto", "bundle", "none")
_SEG = re.compile(r";\s*(?=(?:auto|bundle|none):)")


def finding(text: str) -> list[dict]:
    """One company's finding for a block, "auto: MPN[, MPN] - why", "bundle: ...", "none: why" (several joined by
    "; "), as [{"kind", "mpns", "why"}]. A malformed entry gives kind ""."""
    out = []
    for seg in _SEG.split(str(text or "").strip()):
        kind, _, rest = seg.partition(":")
        kind, rest = kind.strip(), rest.strip()
        if kind not in KINDS or not rest:
            out.append({"kind": "", "mpns": [], "why": seg})
            continue
        if kind == "none":
            out.append({"kind": kind, "mpns": [], "why": rest})
            continue
        names, _, why = rest.partition(" - ")
        out.append({"kind": kind, "mpns": [m.strip() for m in names.split(",") if m.strip()], "why": why.strip()})
    return out


def coverage(key: str) -> dict[str, dict]:
    """{"gid.fn": {"skyworks": [finding], "qorvo": [finding], "note": str}} from the brief's coverage: entries."""
    raw = cur(key).get("coverage") or {}
    return {ref: {**{co: finding((v or {}).get(co, "")) for co in COMPANIES}, "note": str((v or {}).get("note") or "")}
            for ref, v in raw.items()}  # fmt: skip


def gaps(key: str, at: dict) -> list[str]:
    """Labels of the diagram blocks for which neither company has a part (auto or bundle), in diagram order; the
    outside device (the phone) is not counted."""
    cov = coverage(key)
    out: list[str] = []
    for ref, label in at.items():
        if ref.endswith(".external_block"):
            continue
        found = cov.get(ref)
        if found and all(f["kind"] == "none" for co in COMPANIES for f in found[co]) and label not in out:
            out.append(label)
    return out


def gap_line(labels: list[str]) -> str:
    return f"Blocks without a Skyworks or Qorvo part: {', '.join(labels)}." if labels else ""


def build(key: str) -> dict:
    c = cur(key)
    d = diagram(key)
    ps = parts(key, d["at"])
    every = ps["core"] + ps["peripherals"]
    return {"cur": c, "key": key, "diagram": d, "core": ps["core"], "peripherals": ps["peripherals"],
            "left_out": ps["left_out"], "companies": sorted({p["who"] for p in every}),
            "core_companies": sorted({p["who"] for p in ps["core"]}),
            "gaps": gap_line(gaps(key, d["at"]))}  # fmt: skip


def builder(key: str):
    @lru_cache
    def make() -> dict:
        return build(key)

    return make


# ---- editing (same storage and word check as the other reports) ----------------------------------------------------
def specs(key: str) -> dict:
    from app.services import share_reports as sr

    c = cur(key)
    out: dict = {}
    add = sr._adder(out)
    sr._common(out, c, add)
    add("note.core", "text", c.get("core_note") or "", 160, "Note under the core parts")
    add("note.peripherals", "text", c.get("peripheral_note") or "", 200, "Note under the peripherals")
    for i, s in enumerate(c.get("sources") or []):
        add(f"src.{i}", "text", s, 200, "Source line")
    return out


def report(key: str) -> te.Report:
    c = cur(key)

    def default_paras(section: str) -> list[dict]:
        sec = cur(key)["sections"].get(section) or {}
        return [{"id": p["id"], "text": " ".join(str(p["text"]).split())} for p in sec.get("paragraphs") or []]

    return te.Report(key, f"share_{key}", c.get("title", key), f"/shareable/{key}", lru_cache(lambda: specs(key)),
                     lambda: SECTIONS, default_paras, lambda s: LIMITS.get(s, (2, 420)), to.share_problems,
                     "3 A4 pages")  # fmt: skip


REPORTS = {k: report(k) for k in KEYS}


# ---- the content model (PDF and slides) -----------------------------------------------------------------------------
def _table(rows: list[dict], note: str) -> dict:
    out = []
    for p in rows:
        grade = sd.cell(p["grade"])
        out.append([sd.cell(p["mpn"], (p["who"], "who")), sd.cell(p["block"]),
                    sd.cell(p["spec"] + (" (preview)" if p["preview"] and "preview" not in p["spec"] else "")),
                    grade])  # fmt: skip
    return {"kind": "table", "cols": list(COLS), "widths": list(WIDTHS), "rows": out, "note": note,
            "compact": True, "keep_cols": [1, 2, 3],
            "facts": [p["grade"] for p in rows]}  # fmt: skip


def content(key: str):
    def make(data: dict, vals: dict, today=None) -> dict:
        v = vals.get
        c = data["cur"]
        dg = data["diagram"]
        h = {s: str(v(f"sec.{s}.heading") or "") for s in SECTIONS}
        dia = {"kind": "diagram", "title": dg["title"], "layout": dg["layout"],
               "note": "Solid: core solution. Outline: peripherals. Simplified from public reference designs."}
        core = _table(data["core"], str(v("note.core", "")))
        peri = _table(data["peripherals"], " ".join(x for x in (str(v("note.peripherals", "")), data["gaps"]) if x))
        talk = {"kind": "bullets", "items": sd.paras(vals, "talk")}
        prepared = f"Prepared {sd.date_text(today)}. Public information."
        return {"key": key, "title": str(v("title") or c.get("title", "")),
                "head": sd.head_of(vals, c.get("label", key)), "subtitle": str(v("hdr.subtitle") or ""),
                "kicker": c.get("kicker", ""),
                "sections": [sd._sec(vals, "intro", h["intro"], []),
                             sd._sec(vals, "diagram", h["diagram"], [dia]),
                             sd._sec(vals, "core", h["core"], [core], True),
                             sd._sec(vals, "peripherals", h["peripherals"], [peri]),
                             {**sd._sec(vals, "talk", h["talk"], [talk]), "paras": []}],
                "sources": sd._src(vals), "prepared": prepared}  # fmt: skip

    return make


def slides_of(key: str):
    """The brief as 5 slides: cover, block diagram (with the intro's message), core parts, peripherals, talking points
    with the sources underneath."""

    def make(data: dict, vals: dict, today=None, ip_note: str = "") -> list[dict]:
        d = content(key)(data, vals, today)
        secs = {s["id"]: s for s in d["sections"]}
        h = d["head"]
        out = [{"kind": "title", "head": h, "title": d["title"],
                "body": {"heading": d["title"], "sub": d["kicker"], "date": today}}]  # fmt: skip
        dg = secs["diagram"]
        out.append({"kind": "sysdiagram", "head": h, "title": dg["heading"] or d["title"],
                    "body": {"lead": secs["intro"]["slide"], "layout": data["diagram"]["layout"]}})  # fmt: skip
        for sid in ("core", "peripherals"):
            s = secs[sid]
            out += ss._block(h, s["heading"], s["slide"], s["blocks"][0])
        talk = secs["talk"]
        out.append({"kind": "bullets", "head": h, "title": talk["heading"] or "Talking points",
                    "body": {"lead": "", "points": talk["blocks"][0]["items"],
                             "note": [*d["sources"], d["prepared"]]}})  # fmt: skip
        return out

    return make
