"""Answers to the "Questions to ask" (owner, 2 Nov 2026): what the business unit and customers said, recorded on the
report or case page under each question, with who answered (optional) and the date (automatic).

The questions: the business unit's first question of every report and case (bu_opener in reports.yaml, id
q-bu-opener), a case's own business-unit and customer questions (data/business/cases/<slug>.yaml) and a research
report's (data/business/questions_to_ask.yaml).

Sharing, chosen per answer by the owner (the default is internal):
- 🔒 Internal only: on the site for the owner only. Never in a Shareable (pages, PDF, PowerPoint), an export (Excel,
  CSV, text, any download), the Telegram summary, a guest's view or the review history; the daily-run inbox
  (/api/inbox) gets a count only, so an internal answer is never used to revise a report.
- ✅ Can be shared: in full in the inbox, so the next revision can use it; guests see it (without who answered, as they
  see no author names elsewhere). The data-protection screen (docs/plan_data_protection.md, 2b) runs on it like on any
  free text: a flagged answer is held (the owner sees why; guests and the inbox do not get its text) until the owner
  releases it.

Edits keep the earlier versions (AnswerVersion, shown on demand). Guests may send an answer: it waits for the owner's
review like all guest input and lands as internal. Retention: 12 months after an answer's last change, then deleted
with its versions (purge, at start-up and on every read). Answers saved before 2 Nov 2026 (DataReview rows with the
verdict "answered") are moved in as internal by ``migrate``.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from functools import lru_cache

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import Answer, AnswerVersion, DataReview, aware

FILE = PROJECT_ROOT / "data" / "business" / "questions_to_ask.yaml"
INTERNAL, SHARED = "internal", "shared"
SHARING = {INTERNAL: "🔒 Internal only", SHARED: "✅ Can be shared"}
WARNING = "Don't record confidential figures or plans; summarise instead"
RETENTION_MONTHS = 12
TEXT_MAX, WHO_MAX = 4000, 200
NO_TEXT = "Marked as answered; no text was recorded."  # an old "answered" mark without words (before 2 Nov 2026)


# ---- the questions ---------------------------------------------------------------------------------------------------
@lru_cache
def _file() -> dict:
    return (yamlio.load(FILE.read_text()) or {}).get("reports") or {} if FILE.exists() else {}


def groups(case: bool = True) -> tuple[tuple[str, str], ...]:
    """The question groups with their headings: a case asks OEMs and Tier-1s, a research report also partners."""
    from app.services import prelim

    return prelim.QUESTION_GROUPS if case else (prelim.QUESTION_GROUPS[0], ("customer", "Customers and partners"))


def questions(slug: str) -> list[dict]:
    """A report's questions in page order: the business unit's first question, then the business-unit and customer
    questions of its case (or, for a research report, of questions_to_ask.yaml). Each: id, text, group (bu |
    customer), ask (whom to ask), why, opener."""
    from app.services import prelim
    from app.services import reports as rp

    r = rp.report(slug)
    if r is None:
        return []
    out = []
    if o := r.get("bu_opener"):
        out.append({"id": rp.OPENER_ID, "text": str(o.get("question") or ""), "group": "bu", "ask": "", "why": "",
                    "opener": True})  # fmt: skip
    case = prelim.raw(slug)
    src = (case.get("questions") if case is not None else _file().get(slug)) or {}
    for g, _ in groups():
        for q in src.get(g) or []:
            if q.get("id"):
                out.append({"id": str(q["id"]), "text": str(q.get("text") or ""), "group": g,
                            "ask": str(q.get("who") or ""), "why": str(q.get("why") or ""),
                            "opener": False})  # fmt: skip
    return out


def question(slug: str, qid: str) -> dict | None:
    return next((q for q in questions(slug) if q["id"] == qid), None)


def is_question(slug: str, qid: str) -> bool:
    return question(slug, qid) is not None


def all_questions() -> list[dict]:
    """Every report's questions, each with its report (slug, title), in the order of Research & ideas."""
    from app.services import reports as rp

    return [{**q, "slug": r["slug"], "title": r["title"]} for r in rp.reports() for q in questions(r["slug"])]


# ---- the data-protection screen --------------------------------------------------------------------------------------
_PRICE = re.compile(r"[$€£]\s?\d|\b\d+(?:[.,]\d+)?\s?(?:usd|eur|cents?)\b|\bper (?:unit|piece|part)\b"
                    r"|\bquot(?:e|es|ed)\b|\basps?\b", re.I)  # fmt: skip
_FIGURE = re.compile(r"\b\d[\d.,]*\s?(?:k|m|million|bn|billion)?\s?(?:units|pcs|pieces|wafers)\b|\brevenue\b|\bforecast"
                     r"|\bdesign[- ]wins?\b|\bbacklog\b", re.I)  # fmt: skip
_WORDS = re.compile(r"\b(preliminary|under development|tape-?out|launch date)\b", re.I)


def screen(text: str, who: str = "") -> list[str]:
    """Why an answer must wait for the owner before it is shared: the site's screen for free text (patterns of
    docs/plan_data_protection.md, 2b: sites, e-mail, phone, "confidential" / "internal" ...) plus prices, figures and
    plans. Empty when nothing is found."""
    from app.services import data_flow

    why = data_flow.screen(f"{text}\n{who}")
    if _PRICE.search(text):
        why.append("looks like a price or quote")
    if _FIGURE.search(text):
        why.append("volume, revenue, forecast or design-win figure")
    if m := _WORDS.search(text):
        why.append(f"says “{m.group(1).lower()}”")
    return why


# ---- reading ---------------------------------------------------------------------------------------------------------
def is_held(a: Answer) -> bool:
    """A shareable answer the screen flagged and the owner has not released: owner only, its text not in the inbox."""
    return a.sharing == SHARED and bool(a.flags) and a.released_at is None


def guest_visible(a: Answer) -> bool:
    return a.sharing == SHARED and not is_held(a)


@dataclass
class View:
    """One answer as a page shows it. A guest's view has no who, author, flags or versions."""

    id: int
    slug: str
    question: str
    question_text: str
    text: str
    who: str
    sharing: str
    held: bool
    flags: list[str]
    author: str
    created: datetime
    updated: datetime
    edited: bool
    versions: list[dict] = field(default_factory=list)

    @property
    def internal(self) -> bool:
        return self.sharing != SHARED


def _versions(session: Session, ids: list[int]) -> dict[int, list[AnswerVersion]]:
    out: dict[int, list[AnswerVersion]] = {}
    if ids:
        q = select(AnswerVersion).where(AnswerVersion.answer_id.in_(ids)).order_by(AnswerVersion.id.desc())
        for v in session.scalars(q):
            out.setdefault(v.answer_id, []).append(v)
    return out


def views(session: Session, rows: list[Answer], owner: bool) -> list[View]:
    """The answers a viewer may see: the owner all of them, anyone else only the shareable, released ones."""
    rows = [a for a in rows if owner or guest_visible(a)]
    old = _versions(session, [a.id for a in rows]) if owner else {}
    out = []
    for a in rows:
        vs = old.get(a.id, [])
        out.append(View(id=a.id, slug=a.slug, question=a.question, question_text=a.question_text or "", text=a.text,
                        who=(a.who or "") if owner else "", sharing=a.sharing, held=is_held(a) and owner,
                        flags=list(a.flags or []) if owner else [], author=(a.author or "") if owner else "",
                        created=aware(a.created_at), updated=aware(a.updated_at),
                        edited=any(v.change == "edited" for v in vs),
                        versions=[{"text": v.text, "who": (v.who or ""), "sharing": v.sharing, "change": v.change,
                                   "saved": aware(v.saved_at), "replaced": aware(v.created_at)}
                                  for v in vs]))  # fmt: skip
    return out


def for_slug(session: Session, slug: str) -> list[Answer]:
    purge(session)
    return list(session.scalars(select(Answer).where(Answer.slug == slug).order_by(Answer.created_at, Answer.id)))


def owner_view(request) -> bool:
    """The owner's own view of a page: the signed-in owner (everyone in local use without a password), never a
    Shareable output, an API call, a replayed guest item or a page rendered without a request (PDF packs)."""
    if request is None:
        return False
    from app.auth.session import REPLAY, signed_in_owner

    try:
        if signed_in_owner(request) is None or request.scope.get(REPLAY):
            return False
        return not request.url.path.startswith(("/shareable", "/api/"))
    except Exception:  # noqa: BLE001 - no request state: the guest version
        return False


def page(session: Session, request, slug: str) -> dict:
    """Everything a report or case page needs for its questions: per question id the answers the viewer may see."""
    from app.auth.session import principal

    owner = owner_view(request)
    p = principal(request) if request is not None else None
    by_q: dict[str, list[View]] = {}
    for v in views(session, for_slug(session, slug), owner):
        by_q.setdefault(v.question, []).append(v)
    from app.services import prelim

    return {"owner": owner, "guest": bool(p and p.is_guest), "by_q": by_q, "questions": questions(slug),
            "warning": WARNING, "sharing": SHARING, "slug": slug,
            "groups": groups(prelim.raw(slug) is not None)}  # fmt: skip


# ---- writing ---------------------------------------------------------------------------------------------------------
def _clean(text: str, who: str) -> tuple[str, str | None]:
    text = (text or "").replace("\r\n", "\n").strip()[:TEXT_MAX]
    if not text:
        raise ValueError("Write the answer first.")
    return text, " ".join((who or "").split())[:WHO_MAX] or None


def _sharing(value: str) -> str:
    value = (value or INTERNAL).strip()
    if value not in SHARING:
        raise ValueError("Choose Internal only or Can be shared.")
    return value


def add(session: Session, slug: str, qid: str, text: str, who: str = "", sharing: str = INTERNAL,
        author: str | None = None, when: datetime | None = None) -> Answer:  # fmt: skip
    """A new answer (internal unless the owner chose otherwise). KeyError for an unknown report or question."""
    q = question(slug, qid)
    if q is None:
        raise KeyError(f"{slug}/{qid}")
    text, who_ = _clean(text, who)
    now = when or datetime.now(UTC)
    a = Answer(slug=slug, question=qid, question_text=q["text"], text=text, who=who_, sharing=_sharing(sharing),
               flags=screen(text, who_ or "") or None, author=(author or "").strip()[:100] or None, created_at=now,
               updated_at=now)  # fmt: skip
    session.add(a)
    session.commit()
    return a


def _keep(session: Session, a: Answer, change: str) -> None:
    session.add(AnswerVersion(answer_id=a.id, text=a.text, who=a.who, sharing=a.sharing, change=change,
                              saved_at=a.updated_at or a.created_at))  # fmt: skip


def edit(session: Session, aid: int, text: str, who: str = "", sharing: str | None = None) -> Answer:
    """The owner's edit: the version before is kept; a new text is screened again (a release does not carry over)."""
    a = session.get(Answer, aid)
    if a is None:
        raise KeyError(aid)
    text, who_ = _clean(text, who)
    sharing = _sharing(sharing) if sharing else a.sharing
    if (text, who_, sharing) == (a.text, a.who, a.sharing):
        return a
    new_words = (text, who_) != (a.text, a.who)
    _keep(session, a, "edited" if new_words else f"switched to {SHARING[sharing]}")
    a.flags = screen(text, who_ or "") or None
    if new_words:
        a.released_at = None
    a.text, a.who, a.sharing, a.updated_at = text, who_, sharing, datetime.now(UTC)
    session.commit()
    return a


def set_sharing(session: Session, aid: int, sharing: str) -> Answer:
    """The owner's switch. The version before is kept, so the history shows when it changed."""
    a = session.get(Answer, aid)
    if a is None:
        raise KeyError(aid)
    sharing = _sharing(sharing)
    if sharing != a.sharing:
        _keep(session, a, f"switched to {SHARING[sharing]}")
        a.sharing, a.updated_at = sharing, datetime.now(UTC)
        a.flags = screen(a.text, a.who or "") or None  # the screen as it is today
        session.commit()
    return a


def release(session: Session, aid: int) -> Answer:
    """The owner read a flagged shareable answer and lets it be shared as it stands."""
    a = session.get(Answer, aid)
    if a is None:
        raise KeyError(aid)
    if a.flags and a.released_at is None:
        a.released_at = datetime.now(UTC)
        session.commit()
    return a


# ---- retention and the move of the old answers -----------------------------------------------------------------------
def cutoff(today: date | None = None) -> datetime:
    """The oldest time kept: the same day 12 months ago (28 Feb for 29 Feb), at midnight UTC."""
    from app.services import demand

    d = demand.cutoff(today)
    return datetime(d.year, d.month, d.day, tzinfo=UTC)


def purge(session: Session, today: date | None = None) -> int:
    """Answers whose last change is older than 12 months go, with their versions; older versions of newer answers
    too. A write only when there is something to delete (a read must not hold the database's write lock)."""
    cut = cutoff(today)
    old = list(session.scalars(select(Answer.id).where(Answer.updated_at < cut)))
    n_old_versions = session.scalar(select(func.count(AnswerVersion.id)).where(AnswerVersion.created_at < cut)) or 0
    if not old and not n_old_versions:
        return 0
    session.execute(delete(AnswerVersion).where(or_(AnswerVersion.answer_id.in_(old), AnswerVersion.created_at < cut)))
    session.execute(delete(Answer).where(Answer.id.in_(old)))
    session.commit()
    return len(old)


def migrate(session: Session) -> int:
    """Answers saved before 2 Nov 2026 (an "answer" on a question: DataReview rows of dataset case:<slug> with the
    verdict "answered") move in as internal answers, with their author and date; the old rows are removed so the review
    history and the review queue no longer show them. Safe to run again: a moved row is gone."""
    from app.services import prelim
    from app.services import reports as rp

    moved = 0
    for r in rp.reports():
        qs = {q["id"]: q for q in questions(r["slug"])}
        if not qs:
            continue
        rows = session.scalars(select(DataReview).where(DataReview.dataset == prelim.dataset(r["slug"]),
                                                        DataReview.key.in_(list(qs)),
                                                        DataReview.verdict == "answered")
                               .order_by(DataReview.id)).all()  # fmt: skip
        for row in rows:  # added and removed in one transaction, so a row is moved exactly once
            when = aware(row.created_at) or datetime.now(UTC)
            text = (row.comment or "").strip()[:TEXT_MAX] or NO_TEXT
            session.add(Answer(slug=r["slug"], question=row.key, question_text=qs[row.key]["text"], text=text,
                               sharing=INTERNAL, flags=screen(text) or None, author=row.author, from_review=row.id,
                               created_at=when, updated_at=when))  # fmt: skip
            session.delete(row)
            moved += 1
    if moved:
        session.commit()
    return moved


# ---- the overview (Data management › Answers) and the inbox ---------------------------------------------------------
def overview(session: Session, sharing: str = "", slug: str = "") -> dict:
    """Every answer across all reports, newest first, filtered by sharing (internal | shared | held) and report; the
    questions still open (no answer yet) first."""
    from app.services import reports as rp

    purge(session)
    rows = list(session.scalars(select(Answer).order_by(Answer.updated_at.desc(), Answer.id.desc())))
    answered = {(a.slug, a.question) for a in rows}
    counts = {"all": len(rows), INTERNAL: sum(a.sharing == INTERNAL for a in rows),
              SHARED: sum(a.sharing == SHARED for a in rows), "held": sum(is_held(a) for a in rows)}  # fmt: skip
    if slug:
        rows = [a for a in rows if a.slug == slug]
    if sharing == "held":
        rows = [a for a in rows if is_held(a)]
    elif sharing in SHARING:
        rows = [a for a in rows if a.sharing == sharing]
    qs = [q for q in all_questions() if not slug or q["slug"] == slug]
    open_by: dict[str, dict] = {}
    for q in qs:
        if (q["slug"], q["id"]) not in answered:
            open_by.setdefault(q["slug"], {"slug": q["slug"], "title": q["title"], "rows": []})["rows"].append(q)
    titles = {r["slug"]: r["title"] for r in rp.reports()}
    texts = {(q["slug"], q["id"]): q["text"] for q in all_questions()}
    vs = views(session, rows, owner=True)
    for v in vs:
        v.question_text = texts.get((v.slug, v.question)) or v.question_text  # today's wording when it still exists
    return {"answers": vs, "titles": titles, "open": list(open_by.values()), "n_open": sum(len(g["rows"])
            for g in open_by.values()), "n_questions": len(qs), "counts": counts,
            "gone": {(v.slug, v.question) for v in vs if (v.slug, v.question) not in texts},
            "reports": [(r["slug"], r["title"]) for r in rp.reports() if questions(r["slug"])]}  # fmt: skip


def _one_line(text: str | None) -> str:
    return " ".join((text or "").split())


def changed_since(session: Session, start: datetime) -> bool:
    return session.scalar(select(Answer.id).where(Answer.updated_at >= start).limit(1)) is not None


def inbox_lines(session: Session, start: datetime) -> list[str]:
    """Inbox section: shareable answers new or changed since ``start`` in full (held ones without their text);
    internal answers as counts only (owner, 2 Nov 2026: never used to revise a report)."""
    purge(session)
    out = ["\n## Questions to ask: answers\n",
           "Shareable answers (the owner chose “Can be shared”), in full: use them in the report's or case's next "
           "revision (reports.yaml, questions_to_ask.yaml, data/business/cases/<slug>.yaml) as owner input. Internal "
           "answers are counted only: never ask for their text and never use them.\n"]  # fmt: skip
    changed = list(session.scalars(select(Answer).where(Answer.updated_at >= start)
                                   .order_by(Answer.updated_at, Answer.id)))  # fmt: skip
    shared = [a for a in changed if a.sharing == SHARED]
    for a in shared:
        state = "new" if aware(a.created_at) >= start else "changed"
        head = (f"- {aware(a.updated_at):%Y-%m-%d %H:%M} {a.slug} / {a.question} ({state}): "
                f"“{_one_line(a.question_text)}”")
        if is_held(a):
            out.append(f"{head} · [held by the data-protection screen: {', '.join(a.flags or [])}; the owner reads it "
                       "on the page first]")  # fmt: skip
        else:
            out.append(f"{head} · answer: {_one_line(a.text)}{' · from: ' + _one_line(a.who) if a.who else ''}")
    if not shared:
        out.append("None.")
    new_int = sum(1 for a in changed if a.sharing == INTERNAL and aware(a.created_at) >= start)
    edited_int = sum(1 for a in changed if a.sharing == INTERNAL and aware(a.created_at) < start)
    out.append(f"\nInternal answers (owner only, the text stays on the site): {new_int} new, {edited_int} changed "
               "since the last pull.")  # fmt: skip
    return out
