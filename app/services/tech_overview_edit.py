"""The owner's edits to Shareable > Technology overview (owner, 24 Oct 2026: "make it editable"; "numbers and data
should be editable"; "text broken into paragraphs that can be edited via text or comments").

Every text and number on the page is a field with an id. Its default comes from data/business/tech_overview.yaml
(words) or from the catalogue (numbers: "automatic"); the owner's changes are overrides stored in the database as
versions (models.PageTextVersion), never in the repo. The newest version that is not undone is the page. Paragraphs
are lists per section; the owner can add, remove and move them. Comments (models.PageComment) are instructions on a
paragraph or text for the daily run, which answers them in data/business/tech_overview_answers.yaml; the site applies
an answer (public-safe check first) as a new version and marks the comment done with the reply.

The same machinery serves every Shareable report (owner, 25 Oct 2026: Skyworks + Qorvo synergies, Automotive): a
``Report`` names its storage key, fields, paragraph sections and word check; every function takes ``rep`` (default:
the Technology overview). Comment ids are unique across reports, so one answers file serves them all.
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import PageComment, PageTextVersion, aware
from app.services import tech_overview as to
from app.services.text import rounded_count_text

PAGE = "tech_overview"
ANSWERS = PROJECT_ROOT / "data" / "business" / "tech_overview_answers.yaml"
OWNERS = ("Skyworks", "Qorvo", "Both")
MAIN_SECTIONS = ("glance", "platforms", "markets", "families")
# Length limits: what the A4 layout holds (tests/test_browser.py prints the page with every field at its limit and
# checks it still fits on 4 pages). Paragraphs: at most PARA_COUNT per section and PARA_TOTAL characters together.
# The market focus page 5 was removed (owner, 25 Oct 2026: the Automotive report and the Presentation builder cover
# it); old "focus.*" and "paras.focus-*" overrides stay stored but are no longer read.
PARA_COUNT = {"glance": 2, "platforms": 2, "markets": 2, "families": 2}
PARA_TOTAL = {"glance": 560, "platforms": 160, "markets": 160, "families": 220}
CHIP_MAX, CHIPS = 30, 6
# watermark choices (owner, 24 Oct 2026): key -> the word on the page; "custom" uses the owner's text
WATERMARKS = {"none": "", "draft": "Draft", "confidential": "Confidential", "discussion": "For discussion",
              "custom": ""}  # fmt: skip
WM_ALLOW = ("confidential",)  # the watermark may say "Confidential": marking the page is the owner's choice
LOGO_ALIGN, LOGO_SIZE = ("left", "right"), ("small", "medium")


@dataclass
class Field:
    id: str
    kind: str  # line | text | chips | data (automatic) | owner | dot | choice | logo
    default: object
    max: int = 0
    label: str = ""
    options: tuple = ()
    exact: str = ""  # a count: the exact automatic value (the default shows it rounded, "4,500+")

    @property
    def auto(self) -> bool:
        return self.kind in ("data", "owner", "dot")


@dataclass(frozen=True)
class Report:
    """One editable Shareable report: its storage key (PageTextVersion.page, PageComment.page), fields, paragraph
    sections and limits, and the word check that runs on every save."""

    key: str
    page: str
    label: str
    url: str
    specs: Callable[[], dict]
    sections: Callable[[], tuple]
    default_paras: Callable[[str], list]
    para_limits: Callable[[str], tuple]
    problems: Callable[..., list]
    pages_note: str = "4 A4 pages"


@lru_cache
def overview() -> Report:
    return Report("overview", PAGE, "Technology overview", "/shareable/technology-overview", lambda: specs(),
                  lambda: sections(), lambda s: default_paras(s), lambda s: para_limits(s),
                  to.share_problems)  # fmt: skip


def sections() -> tuple[str, ...]:
    """The paragraph sections: one per page."""
    return MAIN_SECTIONS


def para_limits(section: str) -> tuple[int, int]:
    return PARA_COUNT[section], PARA_TOTAL[section]


@lru_cache
def specs() -> dict[str, Field]:
    """Every editable field of the page, in page order, with its default (words from the YAML, numbers computed)."""
    b = to.build()
    cur = b["cur"]
    out: dict[str, Field] = {}

    def add(fid, kind, default, mx=0, label="", options=()):
        exact = ""
        if kind == "data" and rounded_count_text(default) != default:  # a count: shown rounded (owner, 25 Oct 2026)
            exact, default = default, rounded_count_text(default)
        out[fid] = Field(fid, kind, default, mx, label, tuple(options), exact)

    hdr = cur.get("header") or {}
    add("hdr.title", "line", hdr.get("title", ""), 60, "Header title")
    add("hdr.subtitle", "line", hdr.get("subtitle", ""), 60, "Header subtitle (optional)")
    add("hdr.logo", "logo", "", 0, "Logo")
    add("hdr.logo_align", "choice", "left", 0, "Logo position", LOGO_ALIGN)
    add("hdr.logo_size", "choice", "small", 0, "Logo size", LOGO_SIZE)
    add("wm.default", "choice", "none", 0, "Watermark by default", tuple(WATERMARKS))
    add("wm.custom", "line", "", 30, "Custom watermark text")
    add("title", "line", cur.get("title", ""), 70, "Title")
    for s in MAIN_SECTIONS:
        add(f"sec.{s}.heading", "line", ((cur.get("sections") or {}).get(s) or {}).get("heading", ""), 50, "Heading")
    for f in b["facts"]:
        k = f["key"]
        add(f"fact.{k}.num", "data", f["num"], 14, "Number")
        add(f"fact.{k}.label", "line", f["label"], 40, "Label")
        add(f"fact.{k}.note", "data" if f["auto_note"] else "line", f["note"], 52, "Note")
    for p in b["platforms"]:
        k = p["key"]
        add(f"plat.{k}.label", "line", p["label"], 38, "Platform")
        add(f"plat.{k}.owner", "owner", p["owner"], 0, "Who holds it")
        add(f"plat.{k}.what", "text", p["what"], 100, "What it is")
        add(f"plat.{k}.good_for", "text", p["good_for"], 100, "Good for")
    for m in b["markets"]:
        k = m["key"]
        add(f"mkt.{k}.label", "line", m["label"], 36, "Market")
        add(f"mkt.{k}.short", "line", m.get("short") or m["label"], 10, "Short name (matrix)")
        add(f"mkt.{k}.brings", "text", m["brings"], 105, "What it brings")
        add(f"mkt.{k}.functions", "chips", list(m.get("functions") or []), CHIP_MAX, "Functions (one per line)", (5,))
        for i, (name, _series) in enumerate(m.get("parts") or []):
            add(f"mkt.{k}.part.{i}", "line", name, 36, "Part family")
    for r in b["matrix"]:
        for m in b["markets"]:
            add(f"dot.{r['key']}.{m['key']}", "dot", "", 0, f"{r['label']} in {m['label']}")  # default set below
    for f in b["families"]:
        k = f["slug"]
        add(f"fam.{k}.skyworks", "data", f"{f['Skyworks']:,}" if f["Skyworks"] else "–", 7, "Skyworks parts")
        add(f"fam.{k}.qorvo", "data", f"{f['Qorvo']:,}" if f["Qorvo"] else "–", 7, "Qorvo parts")
        add(f"fam.{k}.headline", "text", f["headline"], 105, "Headline")
        for i, g in enumerate(f["figures"]):
            add(f"fam.{k}.fig.{i}.text", "data", g["text"], 24, "Figure")
            add(f"fam.{k}.fig.{i}.part", "data", g["mpn"], 18, "Part holding it")
    for i, (label, url) in enumerate(cur.get("learn_more") or []):
        add(f"learn.{i}.label", "line", label, 60, "Link text")
        add(f"learn.{i}.url", "line", url, 200, "Address (https://...)")
    for i, s in enumerate(cur.get("sources") or []):
        add(f"src.{i}", "text", s, 230, "Source line")
    return out


def default_paras(section: str) -> list[dict]:
    secs = to.curated().get("sections") or {}
    paras = (secs.get(section) or {}).get("paragraphs") or []
    return [{"id": p["id"], "text": " ".join(str(p["text"]).split())} for p in paras]


# ---- versions --------------------------------------------------------------------------------------------------------
def current(session: Session, rep: Report | None = None) -> PageTextVersion | None:
    page = (rep or overview()).page
    q = select(PageTextVersion).where(PageTextVersion.page == page, PageTextVersion.undone_at.is_(None))
    return session.scalars(q.order_by(PageTextVersion.id.desc()).limit(1)).first()


def overrides(session: Session, rep: Report | None = None) -> dict:
    v = current(session, rep)
    return dict(v.fields) if v else {}


def history(session: Session, limit: int = 12, rep: Report | None = None) -> list[PageTextVersion]:
    page = (rep or overview()).page
    return list(session.scalars(select(PageTextVersion).where(PageTextVersion.page == page)
                                .order_by(PageTextVersion.id.desc()).limit(limit)))  # fmt: skip


def values(ov: dict, rep: Report | None = None) -> dict:
    """field id -> shown value, after overrides; dots follow the (possibly overridden) owner of their platform."""
    rep = rep or overview()
    sp = rep.specs()
    out = {fid: ov.get(fid, f.default) for fid, f in sp.items()}
    for fid, f in sp.items():
        if f.kind == "dot":
            out[fid] = ov.get(fid, auto_value(fid, out))
    for s in rep.sections():
        out[f"paras.{s}"] = ov.get(f"paras.{s}", rep.default_paras(s))
    return out


def auto_value(fid: str, shown: dict | None = None, rep: Report | None = None) -> object:
    """The automatic value of a number, owner or dot (what it would be without the owner's override)."""
    sp = (rep or overview()).specs()
    if not fid.startswith("dot.") or rep not in (None, overview()):
        return sp[fid].default if fid in sp else ""
    _, plat, mkt = fid.split(".", 2)
    m = next((m for m in to.build()["markets"] if m["key"] == mkt), None)
    if not m or plat not in (m.get("platforms") or []):
        return ""
    owner = (shown or {}).get(f"plat.{plat}.owner") or sp[f"plat.{plat}.owner"].default
    return owner


def _norm(f: Field | None, raw: object) -> object:
    if f is not None and f.kind == "chips":
        items = raw if isinstance(raw, list) else str(raw or "").splitlines()
        return [" ".join(str(x).split()) for x in items if str(x).strip()]
    return " ".join(str(raw or "").split())


def check(fid: str, value: object, rep: Report | None = None) -> str:
    """Why a value cannot be saved ("" when it can): length, public-safe words, allowed choices, link form."""
    rep = rep or overview()
    sp = rep.specs()
    if fid.startswith("paras."):
        s = fid.split(".", 1)[1]
        texts = [p["text"] for p in value]
        most, total = rep.para_limits(s)
        if len(texts) > most:
            return f"At most {most} paragraphs here, so the page stays within its A4 page."
        if sum(map(len, texts)) > total:
            return f"Too long: {sum(map(len, texts))} characters, at most {total} here (one A4 page)."
        text = " ".join(texts)
    else:
        f = sp[fid]
        if f.kind in ("owner", "dot"):
            ok = OWNERS if f.kind == "owner" else ("", *OWNERS)
            return "" if value in ok else "Choose one of the listed options."
        if f.kind == "choice":
            return "" if value in f.options else "Choose one of the listed options."
        if f.kind == "logo":
            return "" if value == "" or str(value).isdigit() else "Upload the logo with “Add logo”."
        if fid == "wm.custom":
            if len(str(value)) > f.max:
                return f"Too long: at most {f.max} characters."
            return " ".join(rep.problems(str(value), allow=WM_ALLOW))
        if f.kind == "chips":
            most = f.options[0] if f.options else CHIPS
            if len(value) > most:
                return f"At most {most} lines here."
            long = [x for x in value if len(x) > CHIP_MAX]
            if long:
                return f"“{long[0]}” is too long: at most {CHIP_MAX} characters each."
            text = " · ".join(value)
        else:
            text = str(value)
            if f.max and len(text) > f.max:
                return f"Too long: {len(text)} characters, at most {f.max} here ({rep.pages_note})."
            if fid.endswith(".url") and not text.startswith("https://"):
                return "A link must start with https://."
    problems = rep.problems(text)
    return " ".join(problems)


def _save(session: Session, new: dict, note: str, author: str, rep: Report | None = None) -> PageTextVersion:
    rep = rep or overview()
    sp = rep.specs()
    shown = values(new, rep)
    auto = {fid: auto_value(fid, shown, rep) for fid in new if fid in sp and sp[fid].auto}
    v = PageTextVersion(page=rep.page, fields=new, auto=auto, note=note[:500], author=author[:100])
    session.add(v)
    session.flush()
    return v


def save(session: Session, form: dict[str, list[str]], op: str = "", author: str = "Owner",
         rep: Report | None = None) -> dict:  # fmt: skip
    """Apply the edit form: changed fields, paragraph lists and an optional paragraph operation ("del:<section>:<id>",
    "up:...", "down:..."). Returns {"errors": {id: why}, "saved": version or None, "message": text, "values": shown}.
    Nothing is saved when any value fails its check."""
    rep = rep or overview()
    sp = rep.specs()
    old = overrides(session, rep)
    new = dict(old)
    shown_before = values(old, rep)
    for fid, f in sp.items():
        if fid not in form:
            continue
        raw = form[fid] if f.kind == "chips" and len(form[fid]) > 1 else form[fid][0]
        value = _norm(f, raw)
        if f.kind not in ("owner", "dot") and value in ("", []):
            new.pop(fid, None)  # cleared: back to the default
            continue
        base = auto_value(fid, shown_before, rep) if f.kind == "dot" else f.default
        if value == base:
            new.pop(fid, None)
        else:
            new[fid] = value
    for s in rep.sections():
        key = f"paras.{s}"
        if key not in form:
            continue
        ids = form.get(f"pid.{s}", [])
        texts = form[key]
        paras = [{"id": (ids[i] if i < len(ids) and ids[i] else new_id()), "text": _norm(None, t)}
                 for i, t in enumerate(texts)]  # fmt: skip
        paras = [p for p in paras if p["text"]]
        paras = _apply_op(paras, op, s)
        if paras == rep.default_paras(s):
            new.pop(key, None)
        else:
            new[key] = paras
    errors = {fid: why for fid in set(new) | set(old) if fid in new and new[fid] != old.get(fid)
              and (why := check(fid, new[fid], rep))}  # fmt: skip
    if errors:
        return {"errors": errors, "saved": None, "message": "Not saved: please fix the marked texts.", "new": new}
    changed = sorted(k for k in set(new) | set(old) if new.get(k) != old.get(k))
    if not changed:
        return {"errors": {}, "saved": None, "message": "Nothing changed.", "new": new}
    v = _save(session, new, "Changed: " + ", ".join(changed), author, rep)
    return {"errors": {}, "saved": v, "message": f"Saved: {len(changed)} change{'s' if len(changed) != 1 else ''}.",
            "new": new}  # fmt: skip


def new_id() -> str:
    return "p-" + secrets.token_hex(4)


def _apply_op(paras: list[dict], op: str, section: str) -> list[dict]:
    parts = (op or "").split(":")
    if len(parts) != 3 or parts[1] != section:
        return paras
    kind, _, pid = parts
    i = next((n for n, p in enumerate(paras) if p["id"] == pid), None)
    if i is None:
        return paras
    paras = list(paras)
    if kind == "del":
        paras.pop(i)
    elif kind == "up" and i > 0:
        paras[i - 1], paras[i] = paras[i], paras[i - 1]
    elif kind == "down" and i < len(paras) - 1:
        paras[i + 1], paras[i] = paras[i], paras[i + 1]
    return paras


def view_options(vals: dict, q) -> dict:
    """Watermark for this view: the address (?wm=, ?wmt=) first, else the owner's saved default. Unknown values are
    ignored (the default applies); a custom watermark with a blocked word shows no watermark and says why. The old
    ?focus= and ?include= of the removed market focus page are ignored (owner, 25 Oct 2026)."""
    wm = q.get("wm")
    from_url = wm in WATERMARKS
    if not from_url:
        wm = vals.get("wm.default") or "none"
    text, error = WATERMARKS.get(wm, ""), ""
    if wm == "custom":
        text = " ".join(str((q.get("wmt") if from_url and q.get("wmt") is not None else vals.get("wm.custom")) or "")
                        .split())[:60]  # fmt: skip
        error = check("wm.custom", text) if text else ""
        if error:
            text = ""
    return {"wm": wm, "wm_text": text, "wm_error": error, "pages": 4}


def logo_of(session: Session, vals: dict):
    """The header logo shown now (an Upload), or None."""
    from app.services import logo

    ref = str(vals.get("hdr.logo") or "")
    return logo.get(session, int(ref)) if ref.isdigit() else None


def set_logo(session: Session, upload_id: int | None, author: str = "Owner") -> None:
    """Put a stored logo in the header (or take it out with None) as a new version, so Undo and Reset work on it."""
    new = dict(overrides(session))
    if upload_id is None:
        new.pop("hdr.logo", None)
    else:
        new["hdr.logo"] = str(upload_id)
    _save(session, new, "Logo removed" if upload_id is None else "Changed: hdr.logo", author)


def undo(session: Session, rep: Report | None = None) -> str:
    v = current(session, rep)
    if v is None:
        return "Nothing to undo: the page shows the defaults."
    v.undone_at = datetime.now(UTC)
    session.flush()
    return f"Undone: {v.note or 'the last change'}."


def reset(session: Session, fid: str = "", everything: bool = False, author: str = "Owner",
          rep: Report | None = None) -> str:  # fmt: skip
    old = overrides(session, rep)
    if everything:
        if not old:
            return "Nothing to reset: the page shows the defaults."
        _save(session, {}, "Reset all to the defaults", author, rep)
        return "Everything is back to the defaults and the automatic numbers (Undo brings your edits back)."
    if fid not in old:
        return "That text already shows its default."
    new = {k: v for k, v in old.items() if k != fid}
    _save(session, new, f"Reset {fid} to default", author, rep)
    f = (rep or overview()).specs().get(fid)
    return "Back to the automatic value." if f and f.auto else "Back to the default text."


# ---- comments --------------------------------------------------------------------------------------------------------
def block_text(shown: dict, block: str, rep: Report | None = None) -> str | None:
    """The current text of a block (field id or para.<id>); None for an unknown block."""
    rep = rep or overview()
    if block.startswith("para."):
        pid = block.split(".", 1)[1]
        return next((p["text"] for s in rep.sections() for p in shown[f"paras.{s}"] if p["id"] == pid), None)
    if block in rep.specs():
        v = shown[block]
        return " · ".join(v) if isinstance(v, list) else str(v)
    return None


def add_comment(session: Session, block: str, text: str, author: str = "Owner", rep: Report | None = None) -> str:
    rep = rep or overview()
    text = " ".join((text or "").split())
    shown = values(overrides(session, rep), rep)
    current_text = block_text(shown, block, rep)
    if current_text is None:
        return "That paragraph is gone; reload the page."
    if not text:
        return "Write what should change, for example “make this shorter”."
    if len(text) > 1000:
        return "Keep the comment under 1,000 characters."
    session.add(PageComment(page=rep.page, block=block, text=text, block_text=current_text, author=author[:100]))
    session.flush()
    return "Comment saved: the next daily run rewrites this text as asked."


def resolve(session: Session, cid: int, reply: str = "", rep: Report | None = None) -> str:
    c = session.get(PageComment, cid)
    if c is None or c.page != (rep or overview()).page:
        return "That comment no longer exists."
    c.status, c.resolved_at = "done", datetime.now(UTC)
    c.reply = " ".join(reply.split()) or "Resolved by the owner"
    session.flush()
    return "Comment resolved."


def comments(session: Session, status: str = "open", rep: Report | None = None) -> list[PageComment]:
    q = select(PageComment).where(PageComment.page == (rep or overview()).page)
    if status:
        q = q.where(PageComment.status == status)
    return list(session.scalars(q.order_by(PageComment.id)))


def answers() -> list[dict]:
    if not ANSWERS.exists():
        return []
    return list((yamlio.load(ANSWERS.read_text()) or {}).get("answers") or [])


def set_block(new: dict, shown: dict, block: str, text: str, rep: Report | None = None) -> str:
    """Put text into a block of the override set; returns the field id it went to ("" for an unknown block)."""
    rep = rep or overview()
    if block.startswith("para."):
        pid = block.split(".", 1)[1]
        for s in rep.sections():
            paras = [dict(p) for p in shown[f"paras.{s}"]]
            for p in paras:
                if p["id"] == pid:
                    p["text"] = " ".join(text.split())
                    new[f"paras.{s}"] = paras
                    return f"paras.{s}"
        return ""
    f = rep.specs().get(block)
    if f is None:
        return ""
    new[block] = _norm(f, text.splitlines() if f.kind == "chips" else text)
    return block


def apply_answers(session: Session, rep: Report | None = None) -> int:
    """The daily run's answers to open comments (data/business/tech_overview_answers.yaml): each one that passes the
    checks becomes a new version and closes its comment with the reply. Answers that fail stay unapplied (the comment
    stays open, with the reason as its reply draft)."""
    todo = answers()
    if not todo:
        return 0
    rep = rep or overview()
    done = 0
    for a in todo:
        c = session.get(PageComment, int(a.get("comment") or 0))
        if c is None or c.page != rep.page or c.status != "open" or not str(a.get("text") or "").strip():
            continue
        old = overrides(session, rep)
        new = dict(old)
        fid = set_block(new, values(old, rep), str(a.get("block") or c.block), str(a["text"]), rep)
        why = check(fid, new[fid], rep) if fid else "unknown block"
        if why:
            c.reply = f"Answer not applied: {why}"
            continue
        _save(session, new, f"Comment #{c.id} answered by the daily run", "Daily run", rep)
        c.status, c.reply, c.resolved_at = "done", str(a.get("reply") or "Done."), datetime.now(UTC)
        done += 1
    session.flush()
    return done


# ---- the daily inbox -------------------------------------------------------------------------------------------------
def inbox_lines(session: Session, start: datetime, rep: Report | None = None) -> list[str]:
    """For the daily run: what the owner edited since start, overridden numbers whose automatic value changed since,
    and every open comment with its paragraph."""
    rep = rep or overview()
    out = []
    where = "" if rep == overview() else f"{rep.label}: "  # the other reports name themselves
    recent = [v for v in history(session, 200, rep) if aware(v.created_at) >= start and v.undone_at is None]
    changed = sorted({x.strip() for v in recent if v.note.startswith("Changed: ")
                      for x in v.note.removeprefix("Changed: ").split(",")})  # fmt: skip
    if changed:
        out.append(f"- {rep.label}: {len(changed)} text{'s' if len(changed) != 1 else ''} edited by the "
                   f"owner: {', '.join(changed)}. Keep them (they live in the database).")  # fmt: skip
    v = current(session, rep)
    if v:
        shown = values(v.fields, rep)
        for fid, at_save in sorted((v.auto or {}).items()):
            if fid not in rep.specs():  # a retired field (e.g. the removed market focus page): nothing to compare
                continue
            now = auto_value(fid, shown, rep)
            if now != at_save:
                out.append(f"- {where}{fid}: overridden value differs from the new automatic value (shown "
                           f"{v.fields.get(fid)!r}; automatic was {at_save!r}, is now {now!r}). "
                           "Ask the owner.")  # fmt: skip
    answered = {int(a.get("comment") or 0) for a in answers()}
    for c in comments(session, rep=rep):
        if c.id in answered:
            out.append(
                f"- {where}Comment #{c.id} on {c.block}: answered in the repo; the site applies it when the page opens."
            )
            continue
        cur = block_text(values(overrides(session, rep), rep), c.block, rep)
        out.append(f"- {where}Comment #{c.id} on {c.block} ({c.created_at:%Y-%m-%d %H:%M}): “{c.text}”. Current text: "
                   f"“{cur if cur is not None else c.block_text}”")  # fmt: skip
    return out
