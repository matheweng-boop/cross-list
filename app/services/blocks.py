"""Block-diagram generator: system functions, templates, and the Skyworks parts in Cross List that fill them.

data/blocks/functions.yaml maps each function to a source (a Cross List family, a broadcast role, an external
customer part, or nothing yet = opportunity); data/blocks/templates.yaml holds starting diagrams.
"""

from functools import lru_cache
from pathlib import Path

import yaml
from sqlalchemy import func, select
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


def counts(session: Session) -> dict[str, int | None]:
    """Skyworks parts per function; None for external (customer) functions."""
    fam = dict(
        session.execute(
            select(Part.family, func.count(Part.id))
            .join(Part.manufacturer)
            .where(Manufacturer.role == ManufacturerRole.reference)
            .group_by(Part.family)
        ).all()
    )
    roles: dict[str, int] = {}
    for d in broadcast.catalog():
        roles[d["role"]] = roles.get(d["role"], 0) + 1
    out = {}
    for key, f in catalogue()["functions"].items():
        src = f.get("source")
        if src == "external":
            out[key] = None
        elif isinstance(src, dict) and "family" in src:
            out[key] = fam.get(src["family"], 0)
        elif isinstance(src, dict) and "broadcast" in src:
            out[key] = roles.get(src["broadcast"], 0)
        else:
            out[key] = 0
    return out


# parameters shown next to a part in the picker, with their unit
SHOWN = {"channel_config": "", "isolation_rating_kvrms": " kVrms", "configuration": "", "freq_range_ghz": " GHz",
         "peak_source_a": " A", "qualification": ""}  # fmt: skip


def parts_for(session: Session, key: str, q: str = "", limit: int = 60) -> dict:
    f = catalogue()["functions"].get(key) or {}
    src = f.get("source")
    items = []
    if isinstance(src, dict) and "family" in src:
        for p in session.scalars(_reference_parts(session, src["family"])).unique():
            values = {pv.key: pv.value for pv in p.params}
            bits = [p.package.code]
            for k, unit in SHOWN.items():
                v = values.get(k)
                if v not in (None, "", []):
                    bits.append(f"{'-'.join(map(str, v)) if isinstance(v, list) else v}{unit}")
            items.append({"mpn": p.mpn, "url": f"/parts/{p.id}", "detail": " · ".join(bits)})
    elif isinstance(src, dict) and "broadcast" in src:
        for d in broadcast.catalog():
            if d["role"] != src["broadcast"]:
                continue
            feats = d.get("features") or [*d["analog"], *d["digital_iq"], *d["digital_decode"]]
            size = f"{d['tuners']}T" if d.get("tuners") else f"{d['channels']} ch" if d.get("channels") else ""
            items.append(
                {"mpn": d["mpn"], "url": "/broadcast", "detail": " · ".join(x for x in (size, " ".join(feats)) if x)}
            )
    if q:
        qq = q.upper().replace("-", "")
        items = [i for i in items if qq in i["mpn"].upper().replace("-", "") or q.lower() in i["detail"].lower()]
    return {"total": len(items), "parts": items[:limit]}
