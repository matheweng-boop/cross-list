"""Cross-list lookups (owner, 26 Oct 2026): "Update cross-lists" on Products › Cross a list sends the parts that came
out "Not in our data" for a lookup, plus the list's part numbers so it can be crossed again later.

- The site stores each send as a CrossListLookup (public part numbers only).
- The inbox (GET /api/inbox) has a section "Cross-list lookups (queued parts)", and GET /api/inbox/crosslist-lookups
  gives the same queued parts as JSON: this is all the hourly lookup run pulls (docs/daily_update.md).
- The run cannot write the live database: it records each answer in data/manage/crosslist_lookups.yaml (lookup, part,
  status found | not_found, source, date, note), which the site reads to show per-part status. A part recorded there
  is no longer queued; it goes live with the next approved release.
"""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CrossListLookup, aware, utcnow
from app.partnumbers import normalize_pn

FILE = "crosslist_lookups.yaml"
STATUSES = {"queued": "Queued", "found": "Found", "not_found": "Not found"}
MAX_PARTS = 500


def _file():
    from app.config import PROJECT_ROOT

    return PROJECT_ROOT / "data" / "manage" / FILE


def results() -> dict[str, dict]:
    """The run's answers by normalised part number. A part answered once counts for every lookup that sent it (the
    lookup id in the file is for the record)."""
    from app import yamlio

    f = _file()
    try:
        rows = (yamlio.load(f.read_text()) or {}).get("parts") or [] if f.exists() else []
    except Exception:  # noqa: BLE001 - a broken file must not break the page
        rows = []
    return {normalize_pn(str(r["part"])): r for r in rows
            if isinstance(r, dict) and r.get("part") and r.get("status") in ("found", "not_found")}  # fmt: skip


def _url(u) -> str:
    u = str(u or "").strip()
    return u if u.startswith(("https://", "http://")) else ""


@dataclass
class View:
    """One lookup as the Requests page shows it."""

    row: CrossListLookup
    parts: list[dict] = field(default_factory=list)  # part, status, note, source, date

    @property
    def id(self) -> int:
        return self.row.id

    @property
    def created_at(self) -> datetime:
        return self.row.created_at

    def n(self, status: str) -> int:
        return sum(1 for p in self.parts if p["status"] == status)

    @property
    def status(self) -> str:
        return "queued" if self.n("queued") else "done"

    @property
    def progress(self) -> str:
        total, found, nf = len(self.parts), self.n("found"), self.n("not_found")
        text = f"{found} of {total} found"
        if nf:
            text += f", {nf} not found"
        if self.n("queued"):
            text += f", {self.n('queued')} queued"
        return text


def view(row: CrossListLookup, answers: dict | None = None) -> View:
    answers = results() if answers is None else answers
    parts = []
    for p in row.unknown_parts or []:
        key = normalize_pn(p["part"])
        a = answers.get(key)
        if a:
            parts.append({"part": p["part"], "status": a["status"], "note": a.get("note") or "",
                          "source": _url(a.get("source")), "date": str(a.get("date") or "")})  # fmt: skip
        else:
            parts.append({"part": p["part"], "status": p.get("status") or "queued", "note": p.get("note") or "",
                          "source": p.get("source") or "", "date": ""})  # fmt: skip
    return View(row, parts)


def views(session: Session) -> list[View]:
    answers = results()
    out = [view(r, answers) for r in session.scalars(select(CrossListLookup).order_by(CrossListLookup.id))]
    changed = False
    for v in out:  # remember when a lookup was completed
        if v.status == "done" and v.row.done_at is None:
            v.row.done_at, changed = utcnow(), True
    if changed:
        session.commit()
    return out


def create(session: Session, list_parts: list[str], unknown: list[str], author: str | None) -> CrossListLookup:
    """Store a send: the unknown part numbers normalised and de-duplicated, the list's part numbers as parsed."""
    seen, parts = set(), []
    for u in unknown:
        key = normalize_pn(u)
        if key and key not in seen:
            seen.add(key)
            parts.append({"part": key, "status": "queued"})
    row = CrossListLookup(author=author, list_parts=[p[:60] for p in list_parts[:MAX_PARTS]],
                          unknown_parts=parts[:MAX_PARTS])  # fmt: skip
    session.add(row)
    session.commit()
    return row


def queued(session: Session) -> list[dict]:
    """Every part still queued, oldest lookup first: what the hourly lookup run pulls."""
    out = []
    for v in views(session):
        for p in v.parts:
            if p["status"] == "queued":
                out.append({"part": p["part"], "lookup": v.id, "date": aware(v.created_at).strftime("%Y-%m-%d")})
    return out


def inbox_lines(session: Session) -> list[str]:
    q = queued(session)
    out = ["\n## Cross-list lookups (queued parts)\n",
           "Parts sent with \"Update cross-lists\" on Products › Cross a list. For each: find the maker's public "
           "datasheet (polite rules), add the part to data/real, record found / not found in "
           "data/manage/crosslist_lookups.yaml (docs/daily_update.md, step \"Cross-list lookups\"). "
           "JSON: GET /api/inbox/crosslist-lookups.\n"]  # fmt: skip
    out += [f"- {p['part']} · lookup {p['lookup']} · {p['date']}" for p in q] or ["None."]
    return out


def is_unknown(row) -> bool:
    """A Cross a list row whose part number is not in our data at all (not a known part without a cross)."""
    return row.part is None and not row.catalogue


def is_gap(row) -> bool:
    """A Cross a list row for a known part with no Skyworks/Qorvo cross (the red "Function known …, no cross" rows):
    not looked up (it is known), but the owner can record a lifetime volume for it (app/services/demand.py)."""
    return (row.part is not None and not row.part.is_reference and row.drop_in is None and row.functional is None
            and row.light == "red")  # fmt: skip


def volume_rows(rows) -> list:
    """The rows that get a volume step select: unknown parts and gap parts."""
    return [r for r in rows if is_unknown(r) or is_gap(r)]
