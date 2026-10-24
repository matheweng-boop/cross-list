"""Competitive analytics (Opportunities): one high-level profile per competitor company, read from
data/business/competitors/<slug>.yaml (layout in _format.yaml; files starting with "_" are skipped). Public sources
only; every figure carries its source and date.

Since 23 Oct 2026 every profile also has a financial stability section (owner: "how stable a company is, how much
their R&D costs are, ... what that means from a longevity point as well as being a stable supplier")."""

from functools import lru_cache
from pathlib import Path

from app import yamlio
from app.config import PROJECT_ROOT

FOLDER = PROJECT_ROOT / "data" / "business" / "competitors"
LEVELS = {"direct": "Direct", "partial": "Indirect", "none": "None"}

# financial stability: measures per fiscal year (table) and single balance-sheet figures (notes)
TABLE_KEYS = {"revenue": "Revenue", "rnd": "R&D spend", "rnd_pct": "R&D as % of revenue",
              "opex": "Operating expenses", "op_result": "Operating result", "net_result": "Net result",
              "op_cash": "Operating cash flow", "fcf": "Free cash flow"}  # fmt: skip
NOTE_KEYS = {"cash": "Cash and short-term investments", "debt": "Debt", "fcf": "Free cash flow",
             "equity": "Shareholders' equity", "other": ""}  # fmt: skip
TABLE_REQUIRED = ("revenue", "rnd", "rnd_pct", "opex", "op_result")
NOTE_REQUIRED = ("cash", "debt")
RATINGS = {"strong": "Strong", "solid": "Solid", "watch": "Watch", "weak": "Weak"}


def _sourced(x: dict) -> bool:
    return bool(x.get("source") and x.get("date"))


def validate_financials(fin: dict | None, slug: str, public: bool) -> list[str]:
    """The financial stability section: three fiscal years of the main measures, cash and debt, ownership and a
    supplier verdict; every number with its source and date. A listed company also shows free cash flow."""
    if not fin:
        return [f"{slug}: financials is missing (financial stability section)"]
    errs = []
    years = fin.get("years") or []
    if len(years) < 3:
        errs.append(f"{slug}: financials.years needs the last 3 fiscal years")
    rows = fin.get("table") or []
    for r in rows:
        if r.get("key") not in TABLE_KEYS:
            errs.append(f"{slug}: financials.table key must be one of {', '.join(TABLE_KEYS)} ({r.get('key')})")
        if len(r.get("values") or []) != len(years):
            errs.append(f"{slug}: financials.table {r.get('key')} needs one value per year")
        if not _sourced(r):
            errs.append(f"{slug}: financials.table {r.get('key')} needs a source and a date")
    notes = fin.get("notes") or []
    for n in notes:
        if n.get("key") not in NOTE_KEYS or not n.get("value"):
            errs.append(f"{slug}: financials.notes need a known key and a value ({n.get('key')})")
        if not _sourced(n):
            errs.append(f"{slug}: financials.notes {n.get('key')} needs a source and a date")
    have = {r.get("key") for r in rows} | {n.get("key") for n in notes}
    need = (*TABLE_REQUIRED, *NOTE_REQUIRED, *(("fcf",) if public else ()))
    errs += [f"{slug}: financials needs {k}" for k in need if k not in have]
    own = fin.get("ownership") or {}
    if not (own.get("value") and _sourced(own)):
        errs.append(f"{slug}: financials.ownership needs a value, a source and a date")
    v = fin.get("supplier_verdict") or {}
    if v.get("longevity") not in RATINGS or v.get("supply") not in RATINGS or not v.get("text"):
        errs.append(f"{slug}: financials.supplier_verdict needs longevity, supply ({', '.join(RATINGS)}) and text")
    return errs


def validate(data: dict, slug: str) -> list[str]:
    errs = [f"{slug}: {k} is missing" for k in ("name", "summary", "figures") if not data.get(k)]
    for f in data.get("figures") or []:
        if not (f.get("label") and f.get("value") and f.get("source")):
            errs.append(f"{slug}: every figure needs a label, a value and a source ({f})")
        elif not f.get("date"):
            errs.append(f"{slug}: figure {f.get('label')} needs a date")
    for o in data.get("overlap") or []:
        if o.get("level") not in LEVELS:
            errs.append(f"{slug}: overlap level must be one of {', '.join(LEVELS)} ({o.get('area')})")
    if not errs:
        errs += validate_financials(data.get("financials"), slug, public=bool(data.get("ticker")))
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


def all_profiles(folder: Path = FOLDER) -> list[dict]:
    return list(_load(yamlio.folder_signature(folder))[0])


def problems(folder: Path = FOLDER) -> list[str]:
    return list(_load(yamlio.folder_signature(folder))[1])


def get(slug: str) -> dict | None:
    return next((r for r in all_profiles() if r["slug"] == slug), None)
