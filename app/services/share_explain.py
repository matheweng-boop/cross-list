"""Shareable > Explanation (owner, 27 Oct 2026: "another button next to the shareable pages where I can click preview or
I can read the explanation ... similar to what you just gave me for all the depth checks").

INTERNAL and owner only (/shareable/<key>/explain, app/auth/access.py): a plain-language note on how a shareable
document was made. It is never part of the shared page, the PDF, the PowerPoint or the combined file: nothing here is
called by share_doc, share_pdf, share_slides or presentation_pptx.

The four system briefs (share_systems.KEYS) get the full view, built from data/business/share_systems.yaml: in short,
block by block (the coverage: findings for Skyworks and Qorvo), what changed and why (changes:), blocks without a part,
limits and open points, sources. Every other document gets what it is built from, its checks and known limits, from
data/business/share_explain.yaml. Missing words read "No technical notes yet"; nothing is made up here.
"""

import re
from datetime import date
from functools import lru_cache

from app import yamlio
from app.config import PROJECT_ROOT

FILE = PROJECT_ROOT / "data" / "business" / "share_explain.yaml"
NONE_YET = "No technical notes yet."
KIND_LABEL = {"auto": "Automotive", "bundle": "Bundle option", "none": "Nothing that fits", "": "Unclear entry"}
_EST = re.compile(r"\best\b")
_UNSURE = re.compile(r"snippet|not confirmed", re.I)


@lru_cache
def curated() -> dict:
    return (yamlio.load(FILE.read_text()) if FILE.exists() else None) or {}


def _lines(v) -> list[str]:
    return [" ".join(str(x).split()) for x in (v or []) if str(x).strip()]


def _date_text(v) -> str:
    if isinstance(v, date):
        return f"{v.day} {v:%b %Y}"
    try:
        return _date_text(date.fromisoformat(str(v)))
    except ValueError:
        return str(v or "")


def _count(n: int, word: str, tail: str = "") -> str:
    """'1 block', '3 blocks', '2 findings our own estimate'; '' for none when a tail is given."""
    if n == 0 and tail:
        return ""
    plural = {"status": "statuses"}.get(word, word + "s")
    return " ".join(x for x in (str(n), word if n == 1 else plural, tail) if x)


def _sentences(text: str, pat: re.Pattern) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=\.)\s+", text) if pat.search(s)]


def _report_links(slugs) -> list[dict]:
    from app.services import reports as rp

    out = []
    for s in slugs or []:
        r = rp.report(str(s))
        out.append({"text": f"Research report: {r['title']}" if r else f"Research report {s} (not found)",
                    "href": f"/business/reports/{s}" if r else ""})  # fmt: skip
    return out


def _diagram_source(ref: str) -> dict:
    kind, _, name = str(ref).partition(":")
    if kind == "topic":
        from app.services import library

        t = library.topic(name) or {}
        title = t.get("title") or name
        return {"text": f"Library diagram: Systems library topic “{title}”", "href": f"/library/{name}"}
    if kind == "template":
        return {"text": f"Library diagram: block-editor template “{name}”", "href": ""}
    return {"text": f"Library diagram: {ref}", "href": ""} if ref else {}


# ---- the system briefs: from coverage: and changes: ------------------------------------------------------------------
def _cell(found: list[dict], shown: set[str]) -> dict:
    """One company's finding for one block: its best kind and the findings with each part marked shown or not."""
    kinds = [f["kind"] for f in found]
    best = next((k for k in ("auto", "bundle", "none") if k in kinds), "")
    items = [{"kind": f["kind"], "label": KIND_LABEL.get(f["kind"], ""), "why": f["why"],
              "parts": [{"mpn": m, "shown": m.upper() in shown} for m in f["mpns"]]} for f in found]  # fmt: skip
    return {"kind": best, "items": items}


def _system(key: str) -> dict:
    from app.services import share_reports as sr
    from app.services import share_slides as ss
    from app.services import share_systems as sy

    entry = sr.registry()[key]
    c, data = sy.cur(key), entry.build()
    cov = sy.coverage(key)
    every = data["core"] + data["peripherals"]
    shown = {p["mpn"].upper() for p in every}
    rows, recorded, est, unsure = [], [], [], []
    for ref, label in data["diagram"]["at"].items():
        found = cov.get(ref)
        if found is None:
            rows.append({"ref": ref, "label": label, "kind": "", "skyworks": None, "qorvo": None,
                         "note": "Not checked yet."})  # fmt: skip
            continue
        cells = {co: _cell(found[co], shown) for co in sy.COMPANIES}
        kinds = {cells[co]["kind"] for co in sy.COMPANIES}
        kind = next((k for k in ("auto", "bundle", "none") if k in kinds), "")
        if ref.endswith(".external_block"):
            kind = "outside"
        rows.append({"ref": ref, "label": label, "kind": kind, **cells, "note": found["note"]})
        for co in sy.COMPANIES:
            who = co.capitalize()
            for f in found[co]:
                recorded += [(m, label) for m in f["mpns"] if m.upper() not in shown]
                if _EST.search(f["why"]):
                    est.append(f"{label} ({who}): {f['why']}")
        if _EST.search(found["note"]):
            est += [f"{label}: {s}" for s in _sentences(found["note"], _EST)]
        texts = [found["note"], *(f["why"] for co in sy.COMPANIES for f in found[co])]
        unsure += [f"{label}: {s}" for t in texts for s in _sentences(t, _UNSURE)]
    gaps = [{"label": r["label"], "skyworks": "; ".join(f["why"] for f in r["skyworks"]["items"]),
             "qorvo": "; ".join(f["why"] for f in r["qorvo"]["items"])}
            for r in rows if r["kind"] == "none"]  # fmt: skip
    seen: dict[str, list[str]] = {}
    for m, label in recorded:
        if label not in seen.setdefault(m, []):
            seen[m].append(label)
    n_blocks = sum(1 for r in rows if r["kind"] != "outside")
    n_auto = sum(1 for r in rows if r["kind"] == "auto")
    n_bundle = sum(1 for r in rows if r["kind"] == "bundle")
    checked = _date_text(c.get("checked"))
    core_who = " and ".join(data["core_companies"]) or "no company"

    def verb(n: int) -> str:
        return "is" if n == 1 else "are"

    open_points = [t for t in (_count(len(est), "finding", f"{verb(len(est))} our own estimate (est)"),
                               _count(len(unsure), "status", f"{verb(len(unsure))} not confirmed")) if t]  # fmt: skip
    short = [
        f"Claims: Skyworks and Qorvo together have parts for {n_auto + n_bundle} of the {n_blocks} blocks of the "
        f"“{data['diagram']['title']}” diagram: {n_auto} with an automotive (AEC-Q) part, {n_bundle} only with a "
        f"non-automotive bundle option. The core solution is {_count(len(data['core']), 'AEC-Q part')} from "
        f"{core_who}.",
        "Confidence: parts, grades and specs as the public catalogues and data sheets state them"
        + (f", every block checked for both companies on {checked}" if checked else "")
        + (f"; {' and '.join(open_points)}." if open_points else "; no estimates and no unconfirmed statuses."),
    ]
    if gaps:
        short.append(f"No part from either company for {_count(len(gaps), 'block')}: "
                     + ", ".join(g["label"] for g in gaps) + ".")  # fmt: skip
    limits = [f"At most {ss.TABLE_ROWS} rows per slide table: the brief shows {len(data['core'])} core and "
              f"{len(data['peripherals'])} peripheral parts; up to {entry.pages} A4 pages."]  # fmt: skip
    if seen:
        limits.append("Recorded but not shown: " + "; ".join(f"{m} ({', '.join(ls)})" for m, ls in seen.items()) + ".")
    if data["left_out"]:
        limits.append("Left out (not active in the catalogue, or a core part without AEC-Q): "
                      + ", ".join(data["left_out"]) + ".")  # fmt: skip
    limits += [f"Not confirmed: {u}" for u in unsure]
    limits += [f"Estimate (est): {e}" for e in est]
    x = curated().get(key) or {}
    sources = [s for s in (_diagram_source(data["diagram"]["from"]), *_report_links(x.get("reports"))) if s]
    sources += [{"text": s, "href": ""} for s in _lines(c.get("sources"))]
    return {"short": short, "rows": rows, "changes": _lines(c.get("changes")), "checked": checked, "gaps": gaps,
            "limits": limits, "sources": sources}  # fmt: skip


def build(key: str) -> dict:
    """Everything the explanation page shows for one share_reports.REGISTRY entry."""
    from app.services import share_reports as sr
    from app.services import share_systems as sy

    entry = sr.registry()[key]
    x = curated().get(key) or {}
    out = {"key": key, "label": entry.label, "url": entry.url, "pages": entry.pages, "system": key in sy.KEYS,
           "built_from": _lines(x.get("built_from")), "checks": _lines(curated().get("checks")),
           "limits": _lines(x.get("limits")), "none_yet": NONE_YET}  # fmt: skip
    if out["system"]:
        sysx = _system(key)
        out.update({k: v for k, v in sysx.items() if k != "limits"})
        out["limits"] = sysx["limits"] + out["limits"]
    else:
        out["sources"] = _report_links(x.get("reports"))
    return out
