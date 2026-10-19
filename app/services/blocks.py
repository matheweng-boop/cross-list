"""Block-diagram generator: system functions, templates, and the Skyworks parts in Cross List that fill them.

data/blocks/functions.yaml maps each function to a source (a Cross List family, a broadcast role, an external
customer part, or nothing yet = opportunity); data/blocks/templates.yaml holds starting diagrams.
"""

import re
from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT
from app.models import Manufacturer, ManufacturerRole, Part
from app.services import broadcast

BLOCKS_DIR = PROJECT_ROOT / "data" / "blocks"


def _yaml(name: str):
    path: Path = BLOCKS_DIR / name
    return yaml.safe_load(path.read_text()) if path.exists() else None


@lru_cache
def catalogue() -> dict:
    return _yaml("functions.yaml") or {"categories": {}, "functions": {}}


@lru_cache
def templates() -> list[dict]:
    return _yaml("templates.yaml") or []


def _reference_parts(session: Session, family: str):
    return (
        select(Part)
        .join(Part.manufacturer)
        .where(Part.family == family, Manufacturer.role == ManufacturerRole.reference)
        .order_by(Part.mpn)
    )


# parameters shown next to a part in the picker, with their unit
SHOWN = {"channel_config": "", "isolation_rating_kvrms": " kVrms", "configuration": "", "freq_range_ghz": " GHz",
         "peak_source_a": " A", "qualification": ""}  # fmt: skip


def _series(mpn: str) -> str:
    """Base part number without grade / package letters (SI8234AB-AM -> SI8234), so the best options are
    different parts, not variants of one."""
    m = re.match(r"[A-Z]+\d+(?:[A-Z]\d{2,})?", re.split(r"[-.]", mpn.upper())[0])
    return m.group(0) if m else mpn.upper()


def _candidates(session: Session, key: str) -> list[dict] | None:
    """Every part that can fill a function, with the values the requirements look at; None for customer parts."""
    f = catalogue()["functions"].get(key) or {}
    src = f.get("source")
    if src == "external":
        return None
    out = []
    if isinstance(src, dict) and "family" in src:
        for p in session.scalars(_reference_parts(session, src["family"])).unique():
            values = {pv.key: pv.value for pv in p.params}
            bits = [p.package.code]
            for k, unit in SHOWN.items():
                v = values.get(k)
                if v not in (None, "", []):
                    bits.append(f"{'-'.join(map(str, v)) if isinstance(v, list) else v}{unit}")
            out.append({"mpn": p.mpn, "manufacturer": p.manufacturer.name, "url": f"/parts/{p.id}",
                        "detail": " · ".join(bits), "values": values,
                        "risk": p.lifecycle_status.value not in ("active", "preview")})  # fmt: skip
    elif isinstance(src, dict) and "broadcast" in src:
        for d in broadcast.catalog():
            if d["role"] != src["broadcast"]:
                continue
            feats = d.get("features") or [*d["analog"], *d["digital_iq"], *d["digital_decode"]]
            size = f"{d['tuners']}T" if d.get("tuners") else f"{d['channels']} ch" if d.get("channels") else ""
            values = {
                "tuners": d.get("tuners"),
                "channels": d.get("channels"),
                "feature": feats,
                "decode": d["digital_decode"],
            }
            detail = " · ".join(x for x in (size, " ".join(feats)) if x)
            out.append(
                dict(mpn=d["mpn"], manufacturer="Skyworks", url="/broadcast", values=values, risk=False, detail=detail)
            )
    return out


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def meets(values: dict, r: dict, answer) -> bool:
    """Does a part meet one requirement? A part without the value does not (unknown is not assumed)."""
    v = values.get(r["param"])
    if v in (None, "", []):
        return False
    op = r.get("op", "eq")
    if op == "contains":
        items = v if isinstance(v, list) else [v]
        return any(str(answer).lower() in str(x).lower() for x in items)
    if op == "gte":
        a, b = _num(v[0] if isinstance(v, list) else v), _num(answer)
        return a is not None and b is not None and a >= b
    if isinstance(v, list):
        return str(answer) in map(str, v)
    a, b = _num(v), _num(answer)
    return a == b if a is not None and b is not None else str(v).lower() == str(answer).lower()


def _filter(cands: list[dict], key: str, answers: dict) -> list[dict]:
    reqs = {r["id"]: r for r in catalogue()["functions"].get(key, {}).get("requirements") or []}
    for rid, ans in (answers or {}).items():
        r = reqs.get(rid)
        if r is None or ans in (None, "", False):
            continue
        want = r.get("value", ans) if ans is True else ans
        cands = [c for c in cands if meets(c["values"], r, want)]
    return cands


def requirements(session: Session) -> dict[str, list[dict]]:
    """Requirement questions per function, with 'auto' choices resolved from the parts in Cross List."""
    out = {}
    for key, f in catalogue()["functions"].items():
        reqs = f.get("requirements") or []
        if not reqs:
            continue
        cands = None
        resolved = []
        for r in reqs:
            r = dict(r)
            if r.get("choices") == "auto":
                cands = cands if cands is not None else (_candidates(session, key) or [])
                vals = set()
                for c in cands:
                    v = c["values"].get(r["param"])
                    for x in v if isinstance(v, list) else [v]:
                        if x not in (None, ""):
                            vals.add(str(x))
                r["choices"] = sorted(vals, key=lambda x: (_num(x) is None, _num(x) or 0, x))
            resolved.append(r)
        out[key] = resolved
    return out


def counts(session: Session, answers: dict | None = None) -> dict[str, int | None]:
    """Parts per function that meet the answered requirements; None for customer parts."""
    answers = answers or {}
    out = {}
    for key in catalogue()["functions"]:
        cands = _candidates(session, key)
        out[key] = None if cands is None else len(_filter(cands, key, answers.get(key) or {}))
    return out


def parts_for(session: Session, key: str, q: str = "", answers: dict | None = None, top: int = 2) -> dict:
    """Matching parts per manufacturer: the best `top` distinct series first (active before NRND /
    obsolete), then all of them."""
    cands = _filter(_candidates(session, key) or [], key, answers or {})
    if q:
        qq = q.upper().replace("-", "")
        cands = [c for c in cands if qq in c["mpn"].upper().replace("-", "") or q.lower() in c["detail"].lower()]
    groups = {}
    for c in sorted(cands, key=lambda c: (c["risk"], c["mpn"])):
        groups.setdefault(c["manufacturer"], []).append(c)
    result = []
    for mfr, items in groups.items():
        best, seen = [], set()
        for c in items:
            s = _series(c["mpn"])
            if s not in seen:
                seen.add(s)
                best.append(c)
            if len(best) == top:
                break
        strip = lambda c: {k: c[k] for k in ("mpn", "url", "detail", "risk")}  # noqa: E731
        result.append(
            {
                "manufacturer": mfr,
                "best": [strip(c) for c in best],
                "all": [strip(c) for c in items[:200]],
                "total": len(items),
            }
        )
    return {"total": len(cands), "manufacturers": result}
