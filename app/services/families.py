"""Datasheet families: check the whole family, then batch confirm (owner, 26 Oct 2026: "Do we have a system when
enough crosses are flagged or confirmed that we will check the whole product family and therefore batch confirm?"
– "Build it").

A family is every code whose values come from one datasheet (the `datasheet:` field in data/real/*.yaml, kept as the
part's Datasheet; the file name of ``datasheet_url`` when there is none). A cross belongs to two families: their part's
and ours.

1. Wrong answers flag a family. The owner's Right / Wrong answers on Products › Cross a list (DataReview "crosscheck",
   the latest answer per pair wins) are counted per family. ``WRONG_TO_FLAG`` open Wrongs (newer than the family's last
   re-read) flag it "re-read from the datasheet": a section of the daily inbox. The daily run re-reads every
   priority-1 value of every code and records it in data/manage/family_checks.yaml.
2. Right answers offer a batch confirm. A family that was re-read (or whose priority-1 values all carry a datasheet
   page or an "est" marker), has ``RIGHT_TO_OFFER`` crosses marked Right and no open Wrong is one item in Data
   management › To confirm (type "family"). Confirming it is a DataReview row (dataset "crossfamily", key = the
   datasheet file, append-only); every cross with a part of a confirmed family then shows as Verified.
3. A Wrong newer than the confirmation reopens the family: no longer Verified, and flagged again.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import DataReview, Datasheet, Part, aware, part_datasheets
from app.partnumbers import normalize_pn

# Thresholds (owner, 26 Oct 2026: stricter at first). They will be adjusted from the owner's feedback.
WRONG_TO_FLAG = 2  # open Wrong answers in one family before it is flagged for a re-read
RIGHT_TO_OFFER = 3  # Right answers in one family before it is offered as a batch confirm

DATASET = "crossfamily"  # DataReview dataset of the family verdicts (key = datasheet file name)
CONFIRMED, OPEN = "confirmed", "open"
CHECKS_FILE = PROJECT_ROOT / "data" / "manage" / "family_checks.yaml"


# ---- names ---------------------------------------------------------------------------------------------------------
def family_name(sheet: str) -> str:
    """A short, readable name from the datasheet file: si861x-2x-datasheet.pdf -> Si861x/2x, iso776x-q1.pdf ->
    ISO776x-Q1, NSI822x_Datasheet_2.0_EN.pdf -> NSI822x, SKY13317-373LF_200914L.pdf -> SKY13317-373LF."""
    s = re.sub(r"(\.pdf)+$", "", sheet, flags=re.I)
    s = re.sub(r"^infineon-(datasheet-|eicedriver-)?", "", s, flags=re.I)
    s = re.sub(r"[-_ ]?(data[-_ ]?sheet|ds-v|product-summary).*$", "", s, flags=re.I)
    s = re.sub(r"_\d{6}[A-Z]?\b.*$", "", s)  # Skyworks document numbers
    s = re.sub(r"(?<=\d)ds$", "", s)  # pSemi pe42020ds
    segs = [x for x in re.split(r"[-_]", s) if x] or [sheet]
    lower = s == s.lower()
    out = ""
    for i, x in enumerate(segs):
        if lower:
            if i == 0:
                x = "Si" + x[2:] if x.startswith("si") else re.sub(r"^[a-z]+", lambda m: m.group().upper(), x)
            elif re.fullmatch(r"q1|ep|sep", x):
                x = x.upper()
        sep = "/" if re.fullmatch(r"\d{1,2}[a-z]?|\d+Mbps", x) else "-"
        out += (sep if i else "") + x
    return out


# ---- the families behind the answers -------------------------------------------------------------------------------
@dataclass
class Family:
    sheet: str
    name: str
    part_ids: set[int] = field(default_factory=set)
    right: list[DataReview] = field(default_factory=list)  # latest answer Right
    wrong: list[DataReview] = field(default_factory=list)  # latest answer Wrong
    reread: datetime | None = None  # UTC time of the last re-read
    reread_note: str = ""
    confirmed_at: datetime | None = None
    sourced: bool = False  # every priority-1 value has a datasheet page or an est marker (checked only when needed)

    @property
    def key(self) -> str:
        return f"family:{self.sheet}"[:120]

    @property
    def open_wrong(self) -> list[DataReview]:
        """Wrongs not covered by the last re-read (all of them before the first one)."""
        if self.reread is None:
            return self.wrong
        end = self.reread  # a Wrong counts as handled only when it is older than the re-read
        return [w for w in self.wrong if aware(w.created_at) > end]

    @property
    def reopened(self) -> bool:
        return self.confirmed_at is not None and any(aware(w.created_at) > aware(self.confirmed_at)
                                                     for w in self.wrong)  # fmt: skip

    @property
    def confirmed(self) -> bool:
        return self.confirmed_at is not None and not self.reopened

    @property
    def flagged(self) -> bool:
        return len(self.open_wrong) >= WRONG_TO_FLAG or self.reopened

    @property
    def candidate(self) -> bool:
        return (not self.confirmed and not self.open_wrong and len(self.right) >= RIGHT_TO_OFFER
                and (self.reread is not None or self.sourced))  # fmt: skip


def checks() -> dict[str, dict]:
    """datasheet file -> the latest re-read recorded by the daily run (data/manage/family_checks.yaml)."""
    if not CHECKS_FILE.exists():
        return {}
    out: dict[str, dict] = {}
    for c in (yamlio.load(CHECKS_FILE.read_text()) or {}).get("checks") or []:
        d = reread_time(c.get("reread_at") or c.get("date"))
        if c.get("datasheet") and d and (c["datasheet"] not in out or out[c["datasheet"]]["reread_at"] <= d):
            out[c["datasheet"]] = {**c, "reread_at": d}
    return out


def reread_time(v) -> datetime | None:
    """A re-read time as UTC: an ISO timestamp (2026-10-27T18:55:00Z); an old date-only entry is the start of that
    day (so a Wrong given that day still counts as open)."""
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.astimezone(UTC) if v.tzinfo else v.replace(tzinfo=UTC)
    if isinstance(v, date):
        return datetime.combine(v, time.min, tzinfo=UTC)
    t = str(v).strip().replace("Z", "+00:00")
    return reread_time(datetime.fromisoformat(t) if "T" in t or ":" in t else date.fromisoformat(t[:10]))


def sheets(session: Session) -> dict[int, str]:
    """Part id -> its datasheet file (real parts only; demo parts belong to no family)."""
    real = {i for i, syn in session.execute(select(Part.id, Part.is_synthetic)) if not syn}
    out: dict[int, str] = {}
    q = (select(part_datasheets.c.part_id, Datasheet.filename)
         .join(Datasheet, Datasheet.id == part_datasheets.c.datasheet_id).order_by(Datasheet.id))  # fmt: skip
    for pid, name in session.execute(q):
        if pid in real:
            out.setdefault(pid, name)
    for pid, url in session.execute(select(Part.id, Part.datasheet_url).where(Part.datasheet_url.is_not(None))):
        name = url.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
        if pid in real and pid not in out and name.lower().endswith(".pdf"):
            out[pid] = name
    return out


def _sourced(session: Session, part_ids: set[int]) -> bool:
    """Every priority-1 value of every code has a datasheet page reference or an est marker."""
    from app.matching.engine import from_datasheet, is_estimate_source
    from app.matching.rules import load_all_rules

    rules = load_all_rules()
    for p in session.scalars(select(Part).where(Part.id.in_(part_ids))).unique():
        r = rules.get(p.family)
        src = {pv.key: pv.source for pv in p.params}
        for d in r.by_priority(1) if r else ():
            if d.key in src and not (from_datasheet(src[d.key]) or is_estimate_source(src[d.key])):
                return False
    return True


def status(session: Session) -> dict[str, Family]:
    """Every family with an answer or a family verdict, by datasheet file."""
    from app.services import crosslist

    said = crosslist.answers(session)
    verdicts: dict[str, DataReview] = {}
    for r in session.scalars(select(DataReview).where(DataReview.dataset == DATASET)
                             .order_by(DataReview.created_at, DataReview.id)):  # fmt: skip
        verdicts[r.key] = r
    if not said and not verdicts:
        return {}
    sheet_of = sheets(session)
    by_pn: dict[str, list[int]] = {}
    for pid, mpn in session.execute(select(Part.id, Part.mpn)):
        if pid in sheet_of:
            by_pn.setdefault(normalize_pn(mpn), []).append(pid)
    reread = checks()
    fams: dict[str, Family] = {}

    def fam(sheet: str) -> Family:
        if sheet not in fams:
            c = reread.get(sheet) or {}
            fams[sheet] = Family(sheet, c.get("family") or family_name(sheet), reread=c.get("reread_at"),
                                 reread_note=c.get("done") or "")  # fmt: skip
        return fams[sheet]

    for (their, ours), r in said.items():
        hit = {sheet_of[i] for i in (*by_pn.get(their, ()), *by_pn.get(ours, ()))}
        for s in hit:
            (fam(s).right if r.verdict == "right" else fam(s).wrong).append(r)
    for s, r in verdicts.items():
        if s in fams or r.verdict == CONFIRMED:
            fam(s).confirmed_at = r.created_at if r.verdict == CONFIRMED else None
    for pid, s in sheet_of.items():
        if s in fams:
            fams[s].part_ids.add(pid)
    for f in fams.values():
        if not f.confirmed and not f.open_wrong and len(f.right) >= RIGHT_TO_OFFER and f.reread is None:
            f.sourced = _sourced(session, f.part_ids)
    return fams


def verified_part_ids(session: Session) -> set[int]:
    """Parts of a confirmed family (not reopened): every cross with one of them shows as Verified."""
    return {i for f in status(session).values() if f.confirmed for i in f.part_ids}


def confirm(session: Session, sheet: str, verdict: str = CONFIRMED, author: str | None = None) -> DataReview:
    """Record a family verdict (confirmed, or open to undo it); append-only, the latest row wins."""
    r = DataReview(dataset=DATASET, key=sheet[:120], verdict=verdict, author=author or None)
    session.add(r)
    session.commit()
    return r


# ---- To confirm and the daily inbox --------------------------------------------------------------------------------
def _pair(r: DataReview) -> str:
    their, _, ours = r.key.partition("|")
    return f"{their} → {ours}"


def gist(f: Family) -> str:
    how = f"re-read {f.reread.day} {f.reread:%b}" if f.reread else "all values from the datasheet"
    return f"{f.name}: {len(f.part_ids)} codes, {how}, {len(f.right)} crosses confirmed. Confirm the family?"


def digest_items(session: Session) -> list[dict]:
    """The To confirm items: families offered for a batch confirm, and confirmed ones (for the Confirmed tab)."""
    from app.services import digest

    out = []
    for f in status(session).values():
        if not (f.candidate or f.confirmed):
            continue
        when = max([aware(r.created_at) for r in f.right], default=None)
        when = max(d for d in (when and when.date(), f.reread and f.reread.date(),
                              f.confirmed_at and aware(f.confirmed_at).date()) if d)
        rights = "; ".join(_pair(r) for r in f.right[:3]) + (f" and {len(f.right) - 3} more" if len(f.right) > 3
                                                               else "")  # fmt: skip
        checked = (f"Re-read from {f.sheet} on {f.reread:%d %b %Y}." if f.reread
                   else f"Every priority 1 value has a page in {f.sheet} or is marked an estimate.")  # fmt: skip
        out.append({"key": f.key, "type": "family", "type_label": digest.TYPES["family"], "id": f.sheet,
                    "title": f"Datasheet family {f.name} ({f.sheet})", "href": "/cross-list", "date": when,
                    "gist": gist(f), "abstract": [checked, f"Marked Right: {rights}.",
                                                  "Confirming marks every cross of these codes Verified; a later "
                                                  "Wrong reopens the family."],
                    "auto": False, "elsewhere": (), "confirmed": f.confirmed})  # fmt: skip
    return out


def inbox_lines(session: Session, start: datetime) -> list[str]:
    """Inbox section: families flagged for a re-read (every one still open), and family verdicts since the pull."""
    fams = status(session)
    out = ["\n## Cross list: datasheet families to re-read\n",
           f"{WRONG_TO_FLAG} or more crosses of one datasheet family marked Wrong (or a Wrong after the family was "
           "confirmed). Re-read every priority-1 value of every code from that datasheet and record it in "
           "data/manage/family_checks.yaml (docs/daily_update.md).\n"]  # fmt: skip
    lines = []
    for f in sorted(fams.values(), key=lambda f: f.name):
        if not f.flagged:
            continue
        why = " (reopened: Wrong after the family was confirmed)" if f.reopened else ""
        lines.append(f"- {f.name} · datasheet {f.sheet} · {len(f.part_ids)} codes · {len(f.open_wrong)} Wrong{why}")
        for w in f.open_wrong:
            note = " ".join((w.comment or "").split())
            lines.append(f"  - {aware(w.created_at):%Y-%m-%d} {_pair(w)}{' · ' + note if note else ''}")
    out += lines or ["None."]
    new = session.scalars(select(DataReview).where(DataReview.dataset == DATASET, DataReview.created_at >= start)
                          .order_by(DataReview.created_at)).all()  # fmt: skip
    if new:
        out.append("\nFamily verdicts since the last pull:")
        out += [f"- {aware(r.created_at):%Y-%m-%d %H:%M} {family_name(r.key)} ({r.key}): {r.verdict}" for r in new]
    return out
