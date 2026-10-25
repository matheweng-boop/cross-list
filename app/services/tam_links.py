"""Market figures quoted in reports and cases, compared with the current TAM (data/business/tam_links.yaml).

Each linked figure is compared with ``tam.by_function`` for its function (the combined topic's band where there is
one, after owner answers and the biweekly check). It "differs" when its low or high end is more than 15 % away from
the TAM range, when a TAM key it rests on is now left out (owner disagree, or disqualified by the check), when a key
shows a newer figure (check "changed"), or when no market size is left for the function. Differences become to-dos in
the daily inbox section "TAM changes for reports"; the run updates the report and case text. Owner-view notes on the
case and report pages say "Market figure checked <date> · matches TAM" or "· differs, update queued".
"""

from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT
from app.services import tam

LINKS_FILE = PROJECT_ROOT / "data" / "business" / "tam_links.yaml"
APPLIED_FILE = PROJECT_ROOT / "data" / "business" / "tam_applied.yaml"
TOLERANCE = 0.15


def links() -> list[dict]:
    return [x for x in (tam._load(LINKS_FILE).get("links") or []) if isinstance(x, dict) and x.get("id")]


def applied() -> list[dict]:
    """Applied answers (data/business/tam_applied.yaml: key, verdict, date, applied_in, note), when the file exists."""
    data = tam._load(APPLIED_FILE)
    rows = data.get("applied") if isinstance(data, dict) else data
    return [r for r in rows or [] if isinstance(r, dict)]


def _off(quoted: float | None, now: float | None) -> bool:
    return bool(quoted and now) and abs(quoted - now) > TOLERANCE * now


def compare(session: Session) -> list[dict]:
    """Every linked figure with status "matches" or "differs", the reasons and the current TAM range."""
    sizes = tam.by_function(session)
    by_key = {e["key"]: e for e in tam.estimates(session)}
    combined = {t["id"]: t for t in tam.topics(session) if t["is_combined"]}
    day = (tam.check_summary() or {}).get("date")
    out = []
    for lk in links():
        size = sizes.get(lk.get("fn") or "")
        topic = combined.get(lk.get("topic") or "")
        if topic:  # members excluded or recorded inside a combined topic count as the topic says
            members = {e["key"]: e for e in topic["members"]}
        else:
            members = {}
        why, notes = [], []
        for k in lk.get("keys") or []:
            e = members.get(k) or by_key.get(k)
            if e is None:
                why.append(f"{k} is no longer a TAM estimate")
                continue
            if e.get("excluded"):
                why.append(f"rests on {k}, now left out ({e['excluded']})")
            chk = e.get("check") or {}
            if chk.get("status") == "changed" and chk.get("new_value"):
                why.append(f"{k}: the source now shows {chk['new_value']} for {chk.get('new_year')}")
            if e.get("flag"):
                notes.append(f"{k}: {e['flag']}")
        if size is None:
            why.append(f"no market size left for {lk.get('fn')}")
        elif _off(lk.get("low"), size["low"]) or _off(lk.get("high"), size["high"]):
            why.append(f"quoted {tam.band_text(lk.get('low'), lk.get('high'), lk.get('year'))}, TAM now {size['band']}")
        out.append({**lk, "status": "differs" if why else "matches", "why": why, "notes": notes, "date": day,
                    "range": size["band"] if size else "none",
                    "page": f"/business/reports/{lk.get('slug')}"})  # fmt: skip
    return out


def for_slug(session: Session, slug: str) -> dict:
    """The page notes for one report or case: {"market_now": {index: note}, "other": [notes]}."""
    out: dict = {"market_now": {}, "other": []}
    for c in compare(session):
        if c.get("slug") != slug:
            continue
        where = str(c.get("where") or "")
        if where.startswith("case: market_now["):
            out["market_now"][int(where.split("[")[1].rstrip("]"))] = c
        else:
            out["other"].append(c)
    return out


def inbox_lines(session: Session) -> list[str]:
    """The inbox section "TAM changes for reports": one to-do per linked figure that differs."""
    lines = ["\n## TAM changes for reports\n",
             "Update the report or case text (and the figure in data/business/tam_links.yaml), then record the applied "
             "answer in data/business/tam_applied.yaml.\n"]  # fmt: skip
    todo = [c for c in compare(session) if c["status"] == "differs"]
    lines += [f"- {c['id']} · where: {c['page']} {c['where']} · old text: “{c['text']}” · new range: {c['range']} · "
              f"why: {'; '.join(c['why'])}" for c in todo] or ["None."]  # fmt: skip
    return lines
