"""Competitive analytics (Opportunities): one high-level profile per competitor company, read from
data/business/competitors/<slug>.yaml (layout in _format.yaml; files starting with "_" are skipped). Public sources
only; every figure carries its source and date."""

from functools import lru_cache
from pathlib import Path

from app import yamlio
from app.config import PROJECT_ROOT

FOLDER = PROJECT_ROOT / "data" / "business" / "competitors"
LEVELS = {"direct": "Direct", "partial": "Indirect", "none": "None"}


def validate(data: dict, slug: str) -> list[str]:
    errs = [f"{slug}: {k} is missing" for k in ("name", "summary", "figures") if not data.get(k)]
    for f in data.get("figures") or []:
        if not (f.get("label") and f.get("value") and f.get("source")):
            errs.append(f"{slug}: every figure needs a label, a value and a source ({f})")
    for o in data.get("overlap") or []:
        if o.get("level") not in LEVELS:
            errs.append(f"{slug}: overlap level must be one of {', '.join(LEVELS)} ({o.get('area')})")
    return errs


@lru_cache(maxsize=4)
def _load(sig: tuple[tuple[str, float], ...]) -> tuple[tuple[dict, ...], tuple[str, ...]]:
    rows, errs = [], []
    for name, _ in sig:
        p = Path(name)
        data = yamlio.load(p.read_text()) or {}
        e = validate(data, p.stem)
        errs += e
        if not e:
            rows.append({**data, "slug": p.stem})
    return tuple(sorted(rows, key=lambda r: r["name"].lower())), tuple(errs)


def _sig(folder: Path) -> tuple[tuple[str, float], ...]:
    return tuple(sorted((str(p), p.stat().st_mtime) for p in folder.glob("*.yaml") if not p.name.startswith("_")))


def all_profiles(folder: Path = FOLDER) -> list[dict]:
    return list(_load(_sig(folder))[0])


def problems(folder: Path = FOLDER) -> list[str]:
    return list(_load(_sig(folder))[1])


def get(slug: str) -> dict | None:
    return next((r for r in all_profiles() if r["slug"] == slug), None)
