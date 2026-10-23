"""Opportunities > Risks: competing technologies and products that could endanger our current solutions, grouped
by our product family. Read from data/business/risks.yaml (layout at the top of that file). Public sources only;
likelihood and timing are BizDev's own reading ("est")."""

from functools import lru_cache
from pathlib import Path

from app import yamlio
from app.config import PROJECT_ROOT

FILE = PROJECT_ROOT / "data" / "business" / "risks.yaml"
LIKELIHOOD = {"high": "Likely", "medium": "Possible", "low": "Unlikely"}
WHEN = {"now": "Already happening", "1-2 years": "In 1–2 years", "3-5 years": "In 3–5 years",
        "5+ years": "In 5+ years"}  # fmt: skip
KINDS = {"technology": "Technology", "competitor": "Competitor", "market": "Market"}
REQUIRED = ("id", "threat", "who", "impact", "signs", "sources")


def validate(data: dict) -> list[str]:
    errs, seen = [], set()
    for g in data.get("groups") or []:
        if not (g.get("id") and g.get("name") and g.get("ours") and g.get("risks")):
            errs.append(f"group {g.get('id')}: needs id, name, ours and risks")
        for r in g.get("risks") or []:
            rid = r.get("id")
            errs += [f"{rid}: {k} is missing" for k in REQUIRED if not r.get(k)]
            if rid in seen:
                errs.append(f"{rid}: id used twice")
            seen.add(rid)
            if r.get("likelihood") not in LIKELIHOOD:
                errs.append(f"{rid}: likelihood must be one of {', '.join(LIKELIHOOD)}")
            if r.get("when") not in WHEN:
                errs.append(f"{rid}: when must be one of {', '.join(WHEN)}")
            if r.get("kind") not in KINDS:
                errs.append(f"{rid}: kind must be one of {', '.join(KINDS)}")
            for ln in r.get("links") or []:
                if not (ln.get("label") and str(ln.get("href", "")).startswith(("/", "https://"))):
                    errs.append(f"{rid}: link needs a label and a /path or https:// address ({ln})")
    if not data.get("groups"):
        errs.append("no groups")
    return errs


@lru_cache(maxsize=2)
def _load(path: str, mtime: float) -> tuple[dict, tuple[str, ...]]:
    data = yamlio.load(Path(path).read_text()) or {}
    return data, tuple(validate(data))


def load(path: Path = FILE) -> dict:
    data, errs = _load(str(path), path.stat().st_mtime)
    return {**data, "errors": list(errs)}


def urgent(data: dict) -> list[dict]:
    """Likely and already happening: the risks to act on first."""
    return [{**r, "group": g["name"]} for g in data.get("groups") or [] for r in g.get("risks") or []
            if r.get("likelihood") == "high" and r.get("when") == "now"]  # fmt: skip
