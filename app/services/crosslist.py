"""Products › Cross a list (owner, 26 Oct 2026): a pasted list of part numbers crossed in one go.

Nothing pasted is stored: the list lives in the request, the result in the response and the Excel download (which
re-computes it from the pasted text). Only the owner's Right / Wrong answers on a shown pair are stored (DataReview,
dataset "crosscheck", key "<their mpn>|<our mpn>", append-only, the latest answer wins).

Every part runs through the same cross engine as the single search (app/matching/engine.py, the candidates of
app/services/queries.candidates_for). Two result columns, in a fixed order (owner, 26 Oct 2026):

1. Drop-in: same package and pinout. A direct package equivalent (every priority 1 spec equal or better: the engine's
   drop-in) is preferred; else the package drop-in with the fewest, least severe priority 1 deviations.
2. Best functional fit: the best priority 1 match regardless of package; hidden when it is the column 1 part.

Only priority 1 specs count (owner, 26 Oct 2026: "We will focus on all the priority one specifications, and not all
specifications unless required"); a lower-priority spec is mentioned ("also: …") only when a rule makes it a must.

Light: green = a direct package equivalent whose priority 1 values come from datasheets on both sides; amber = any
other cross, or a missing / estimated priority 1 value; red = no cross, or the part is not recognised.

A ``datasheet_only`` value (the isolator data rate) that is not from a datasheet page on one side is a data gap
("check datasheet"): never a deviation, only a tie-break (owner, 26 Oct 2026: data rate "better researched from the
datasheet").
"""

import bisect
import difflib
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.matching.engine import (
    BETTER,
    DIFFERENT,
    EQUAL,
    UNKNOWN,
    WORSE,
    CrossResult,
    compare_param,
    find_crosses,
    from_datasheet,
    is_estimate_source,
    rank_key,
)
from app.matching.rules import FamilyRules, get_rules, load_all_rules
from app.models import CrossFeedback, DataReview, FeedbackVerdict, Part, VerifyTask
from app.partnumbers import normalize_pn, reel_q1_variants
from app.services import cross_notes, lifecycle
from app.services.queries import candidates_for, feedback_for

MAX_LINES = 500
DATASET = "crosscheck"  # DataReview dataset of the owner's Right / Wrong answers
VERDICTS = ("right", "wrong")
PRIVACY_NOTE = "Paste public part numbers only – no customer names, prices or internal data."
PRECHECK_NOTE = ("Pre-check from public datasheets. Green rows were checked spec by spec; confirm amber and red rows "
                 "before quoting to a customer.")  # fmt: skip
HOW_NOTE = ("Drop-in: same package and pinout. A direct package equivalent (every priority 1 spec equal or better) "
            "comes first; without one, the package drop-in with the fewest and smallest priority 1 deviations. "
            "Best functional fit: the closest priority 1 match in any package; left out when it is the drop-in part. "
            "Other family: for Skyworks isolators, the best Si86 part when an Si86S part is shown, and the other way "
            "round – its package drop-in when it has one, else its best functional fit.")  # fmt: skip
LIGHTS = {"green": "Green", "amber": "Amber", "red": "Red"}
LIGHT_HELP = {
    "green": "direct package equivalent, priority 1 specs from datasheets on both sides",
    "amber": "a cross with deviations, another package, or a missing, estimated or not-from-datasheet value",
    "red": "no cross, or the part is not in our data",
}
OURS = "Skyworks/Qorvo"

# a cell that is a quantity, a price or a plain number, never a part number
_QTY = re.compile(r"^[$€£]?\d[\d.,']*\s*(k|m|pcs?|units?|ea|usd|eur|%|€|\$)?$", re.I)
_PN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9\-_/.#+()]{2,39}$")


# ---------------------------------------------------------------- parsing


@dataclass
class Entry:
    text: str  # as pasted (first time seen)
    key: str  # normalised
    n: int = 1


def looks_like_pn(tok: str) -> bool:
    tok = tok.strip().strip("\"'")
    return bool(_PN.match(tok)) and not _QTY.match(tok) and any(c.isdigit() for c in tok) and any(
        c.isalpha() for c in tok)  # fmt: skip


def _first_pn(cell: str) -> str | None:
    return next((t.strip("\"'") for t in cell.split() if looks_like_pn(t)), None)


def parse(text: str) -> tuple[list[Entry], int]:
    """The part numbers in pasted text, in order, duplicates counted once (×n); and how many lines were left out
    beyond MAX_LINES. A line with tabs is a spreadsheet row: its first part-number-looking cell counts (quantities,
    prices and names are skipped). Other lines may hold several parts separated by commas or semicolons."""
    lines = [ln for ln in (text or "").replace("\r", "\n").split("\n") if ln.strip()]
    over = max(0, len(lines) - MAX_LINES)
    out: dict[str, Entry] = {}
    for line in lines[:MAX_LINES]:
        if "\t" in line:
            found = [next((pn for c in line.split("\t") if (pn := _first_pn(c))), None)]
        else:
            found = [_first_pn(c) for c in re.split(r"[,;]", line)]
        for pn in found:
            if not pn:
                continue
            key = normalize_pn(pn.replace("*", ""))
            if key in out:
                out[key].n += 1
            else:
                out[key] = Entry(pn, key)
    return list(out.values()), over


# ---------------------------------------------------------------- recognising part numbers


@dataclass
class Index:
    by_key: dict[str, list[int]]
    keys: list[str]  # sorted
    catalogue: dict[str, dict]  # Skyworks / Qorvo catalogue records without full data, by normalised mpn


def build_index(session: Session) -> Index:
    by_key: dict[str, list[int]] = {}
    for pid, mpn in session.execute(select(Part.id, Part.mpn)):
        by_key.setdefault(normalize_pn(mpn), []).append(pid)
    try:
        from app.services import products

        cat = {normalize_pn(r["mpn"]): r for r in products._catalogue_index().values()}
    except Exception:  # noqa: BLE001  (the catalogue files are optional here)
        cat = {}
    return Index(by_key, sorted(by_key), cat)


@dataclass
class Match:
    part_id: int | None = None
    how: str = "none"  # exact | variant | catalogue | none
    catalogue: dict | None = None
    suggestion: str | None = None  # did you mean (a known part number)


def _known_prefix(key: str, keys: dict) -> str | None:
    """The longest known part number the pasted one starts with (a reel, grade or package suffix added)."""
    for n in range(len(key) - 1, max(4, len(key) - 8) - 1, -1):
        if key[:n] in keys:
            return key[:n]
    return None


def resolve(ix: Index, key: str, session: Session) -> Match:
    """Exact first; then an ordering-code variant (the pasted number with or without a reel / temperature / package
    suffix of a known one, as the single search finds it by prefix, or the reel "R" before a trailing "Q1"); then
    the catalogue; else a suggestion."""
    if not key:
        return Match()
    if key in ix.by_key:
        return Match(_pick(session, ix.by_key[key]), "exact")
    for alt in reel_q1_variants(key):  # …RQ1 is the reel of …Q1 (TI automotive), and the other way round
        if alt in ix.by_key:
            return Match(_pick(session, ix.by_key[alt]), "variant")
        if alt in ix.catalogue:
            return Match(None, "catalogue", ix.catalogue[alt])
    pre = _known_prefix(key, ix.by_key)
    i = bisect.bisect_left(ix.keys, key)
    longer = []
    while i < len(ix.keys) and ix.keys[i].startswith(key) and len(longer) < 50:
        longer.append(ix.keys[i])
        i += 1
    if longer and len(key) >= 5:
        best = min(longer, key=lambda k: (len(k), k))
        if pre is None or len(best) - len(key) <= len(key) - len(pre):
            return Match(_pick(session, ix.by_key[best]), "variant")
    if pre:
        return Match(_pick(session, ix.by_key[pre]), "variant")
    if dev := _device_q1(ix, key):  # a TI device name such as ADS131B02-Q1 for its orderable ADS131B02QPWRQ1
        return Match(_pick(session, ix.by_key[dev]), "variant")
    if key in ix.catalogue:
        return Match(None, "catalogue", ix.catalogue[key])
    cpre = _known_prefix(key, ix.catalogue)
    if cpre:
        return Match(None, "catalogue", ix.catalogue[cpre])
    pool = [k for k in ix.keys if k[:2] == key[:2]] or ix.keys
    close = difflib.get_close_matches(key, pool, n=1, cutoff=0.75) if len(key) >= 4 else []
    if close:
        p = session.get(Part, ix.by_key[close[0]][0])
        return Match(suggestion=p.mpn if p else close[0])
    return Match()


def _device_q1(ix: Index, key: str) -> str | None:
    """A TI automotive device name pasted without its package code (ADS131B02-Q1 → ADS131B02Q1): the shortest known
    orderable code that starts with the device and ends in Q1 (owner's lookup 1, 26 Oct 2026)."""
    base = key[:-2]
    if not key.endswith("Q1") or len(base) < 5:
        return None
    i = bisect.bisect_left(ix.keys, base)
    hits = []
    while i < len(ix.keys) and ix.keys[i].startswith(base) and len(hits) < 50:
        if ix.keys[i].endswith("Q1"):
            hits.append(ix.keys[i])
        i += 1
    return min(hits, key=lambda k: (len(k), k)) if hits else None


def _pick(session: Session, ids: list[int]) -> int:
    """Several parts with one number (rare): a competitor part first (it is the one to cross)."""
    if len(ids) == 1:
        return ids[0]
    parts = [session.get(Part, i) for i in ids]
    return next((p.id for p in parts if not p.is_reference), ids[0])


# ---------------------------------------------------------------- crossing


def _qual(part: Part) -> str:
    q = next((pv.value for pv in part.params if pv.key == "qualification"), None)
    return "automotive" if q == "automotive" else "industrial" if q in ("industrial", "commercial") else "unknown"


class Crosser:
    """Crosses many parts with the single search's engine: the candidate list of each family is read once and
    candidates that fail a function-defining ("hard") or must-meet categorical spec are skipped before the full
    comparison (the engine would not list them either: the same compare_param decides)."""

    def __init__(self, session: Session):
        self.session = session
        self._cands: dict[tuple, list[Part]] = {}
        self._values: dict[int, dict] = {}

    def _vals(self, rules: FamilyRules, p: Part) -> dict:
        if p.id not in self._values:
            self._values[p.id] = rules.values(p)
        return self._values[p.id]

    def crosses(self, ref: Part) -> dict[str, list[CrossResult]]:
        rules = get_rules(ref.family)
        ck = (ref.family, ref.is_reference, ref.manufacturer_id if ref.is_reference else None)
        if ck not in self._cands:
            self._cands[ck] = candidates_for(self.session, ref)
        cands = [c for c in self._cands[ck] if c.id != ref.id and c.manufacturer_id != ref.manufacturer_id]
        gate = [p for p in rules.params if (p.hard or p.must_meet) and p.kind in ("category", "ordinal", "set", "bool")
                and not (p.at or p.curve or p.band)]  # fmt: skip
        if gate:
            rv = self._vals(rules, ref)
            keep = []
            for c in cands:
                cv = self._vals(rules, c)
                fail = False
                for p in gate:
                    st, _ = compare_param(p, rv.get(p.key), cv.get(p.key))
                    if (p.hard and st in (WORSE, DIFFERENT)) or (
                        p.must_meet and (st in (WORSE, DIFFERENT) or (st == UNKNOWN and rv.get(p.key) is not None))
                    ):
                        fail = True
                        break
                if not fail:
                    keep.append(c)
            cands = keep
        return find_crosses(ref, cands, rules, feedback_for(self.session, ref.id))


def _p1(r: CrossResult) -> list:
    return [d for d in r.diffs if d.priority == 1]


def _worse_score(r: CrossResult) -> float:
    return sum(d.score for d in r.deviations)


def _pool(ref: Part, crosses: dict) -> list[CrossResult]:
    """Every listed candidate once; at-risk (NRND, obsolete) ones only when nothing else is left. An automotive part
    takes automotive crosses only (as on the part page); a non-automotive part prefers non-automotive ones."""
    seen: dict[int, CrossResult] = {}
    for rs in crosses.values():
        for r in rs:
            seen.setdefault(r.candidate.id, r)
    rs = list(seen.values())
    if _qual(ref) == "automotive":
        rs = [r for r in rs if _qual(r.candidate) == "automotive"]
    else:
        rs = [r for r in rs if _qual(r.candidate) != "automotive"] or rs
    return [r for r in rs if not r.lifecycle_risk] or rs


def drop_in_key(r: CrossResult):
    return (r.category != "fff", len(r.deviations), getattr(r, "unverified_worse", 0), _worse_score(r),
            len(r.exceptions), r.closeness,
            r.candidate.mpn)  # fmt: skip


def functional_key(r: CrossResult):
    p1_off = sum(d.score for d in _p1(r) if d.status != EQUAL and d.status != BETTER)
    return (len(r.deviations), getattr(r, "unverified_worse", 0), p1_off, len(r.exceptions), not r.fit.same_package,
            not r.fit.same_pinout, r.closeness, r.candidate.mpn)  # fmt: skip


def columns(ref: Part, crosses: dict) -> tuple[CrossResult | None, CrossResult | None]:
    """(drop-in, best functional fit); the second is None when it is the same part as the first. The other Skyworks
    isolator family (Si86 / Si86S) is offered apart, by ``other_family``."""
    pool = _pool(ref, crosses)
    fits = [r for r in pool if r.fit.fits]
    c1 = min(fits, key=drop_in_key) if fits else None
    c2 = min(pool, key=functional_key) if pool else None
    if c1 is not None and c2 is not None and c2.candidate.id == c1.candidate.id:
        c2 = None
    return c1, c2


def is_si86s(mpn: str) -> bool:
    return mpn.upper().startswith("SI86S")


def is_si86(mpn: str) -> bool:
    """An Si86 part outside the Si86S family (e.g. SI8641ET-IS)."""
    m = mpn.upper()
    return m.startswith("SI86") and not m.startswith("SI86S")


def isolator_family(mpn: str) -> str | None:
    """The family name, Si86S or Si86, for a Skyworks digital isolator of one of the two families, else None."""
    return "Si86S" if is_si86s(mpn) else "Si86" if is_si86(mpn) else None


OTHER_FAMILY = {"Si86S": "Si86", "Si86": "Si86S"}


def other_family(shown: list, pool: list) -> tuple[str, CrossResult] | None:
    """Both Skyworks isolator families wherever a cross is offered (owner, 27 Oct 2026: "always offer both families
    if both families are available"; "just add a third option which shows the family equivalent and same goes if
    there is a package equivalent in another family"). From ``pool`` (the engine's list: it passed the
    function-defining and must-meet checks), never a part in ``shown`` (None entries skipped), with the family's name:

    - the parts shown are all Si86S or all Si86: the other family's best package drop-in or direct package
      equivalent (``drop_in_key``, as column 1), else its best functional fit by the usual order (``rank_key``:
      fewest deviations, then the same package and pinout; owner: "We still follow the same rules for package
      comparisons");
    - both families are shown already: only a package drop-in of the family shown as a functional fit alone (a
      further functional fit of a family already shown adds nothing);
    - None when nothing shown is from either family, or the other family has no suitable part."""
    shown = [r for r in shown if r is not None]
    by: dict[str, list] = {}
    for r in shown:
        f = isolator_family(r.candidate.mpn)
        if f:
            by.setdefault(f, []).append(r)
    if not by:
        return None
    if len(by) == 1:
        want, fit_only = OTHER_FAMILY[next(iter(by))], False
    else:
        lacking = [f for f, rs in by.items() if not any(r.fit.fits for r in rs)]
        if len(lacking) != 1:
            return None
        want, fit_only = lacking[0], True
    ids = {r.candidate.id for r in shown}
    cands = [r for r in pool if r.candidate.id not in ids and isolator_family(r.candidate.mpn) == want]
    fits = [r for r in cands if r.fit.fits]
    if fits:
        return want, min(fits, key=drop_in_key)
    return (want, min(cands, key=rank_key)) if cands and not fit_only else None


# ---------------------------------------------------------------- words


def _is_estimate(src: str | None) -> bool:
    return is_estimate_source(src)


def data_gaps(r: CrossResult) -> list[str]:
    """Priority 1 values not taken from a datasheet on one side: missing, estimated or demo data."""
    gaps = []
    for side, part in (("their", r.reference), ("our", r.candidate)):
        if part.is_synthetic:
            gaps.append(f"{side} values are demo data")
        elif not part.datasheet_url and not part.datasheets:
            gaps.append(f"no datasheet on file for {side} part")
    rules = get_rules(r.reference.family)
    srcs = {"their": {pv.key: pv.source for pv in r.reference.params},
            "our": {pv.key: pv.source for pv in r.candidate.params}}  # fmt: skip
    for d in _p1(r):
        if d.status == UNKNOWN and not d.unknown_ok:
            rv, cv = rules.values(r.reference).get(d.key), rules.values(r.candidate).get(d.key)
            empty = (None, "", [])
            if rv in empty and cv in empty:
                gaps.append(f"{_short(d.label)} in neither datasheet")
            elif rv in empty or cv in empty:
                gaps.append(f"{_short(d.label)} not in {'their' if rv in empty else 'our'} datasheet")
            else:
                gaps.append(f"{_short(d.label)} not comparable ({d.ref_display} vs {d.cand_display})")
        for side in ("their", "our"):
            src = srcs[side].get(d.key)
            if d.unverified and _is_estimate(src):  # a datasheet-only value: it did not decide the ranking
                gaps.append(f"{_short(d.label)} estimated ({side}s): check datasheet")
            elif d.unverified and not from_datasheet(src):
                gaps.append(f"{_short(d.label)} not from {side} datasheet: check datasheet")
            elif _is_estimate(src):
                gaps.append(f"{_short(d.label)} estimated ({side}s)")
    return list(dict.fromkeys(gaps))


def _short(label: str) -> str:
    return re.sub(r"\s*\((typ, else min|min|typ)\)", "", label)


def _tag(d) -> str:
    if d.unverified and d.status != EQUAL:
        return {BETTER: "ours better", WORSE: "ours worse", DIFFERENT: "different"}[d.status] + ", unverified"
    return {BETTER: "ours better", WORSE: "ours worse", DIFFERENT: "different", UNKNOWN: "not stated"}.get(d.status,
                                                                                                          "close")


def comment(r: CrossResult, column: int) -> str:
    """One plain line on the pair: package and pinout, the priority 1 specs that differ (their value vs ours), the
    data gaps, a must-meet lower-priority difference ("also: …"), lifecycle and engineer notes."""
    bits = []
    ref, cand = r.reference, r.candidate
    if r.fit.fits:
        bits.append("Same package and pinout")
    elif r.fit.same_package:
        bits.append(f"Same package ({cand.package.code}), different pinout")
    else:
        bits.append(f"Package {ref.package.code} vs {cand.package.code}"
                    + ("" if r.fit.same_pinout else ", different pinout"))  # fmt: skip
    p1 = _p1(r)
    qual = next((d for d in p1 if d.key == "qualification"), None)
    order = {WORSE: 0, DIFFERENT: 0, UNKNOWN: 1, BETTER: 2, EQUAL: 3}
    shown = [d for d in p1 if d.key != "qualification" and (d.status != EQUAL or d.ref_display != d.cand_display)]
    for d in sorted(shown, key=lambda d: order[d.status])[:5]:
        bits.append(f"{_short(d.label)} {d.ref_display} vs {d.cand_display} ({_tag(d)})")
    if qual is not None and qual.status == EQUAL and _qual(ref) == "automotive" == _qual(cand):
        bits.append("AEC-Q both")
    elif qual is not None and qual.status != EQUAL:
        bits.append(f"grade {qual.ref_display} vs {qual.cand_display} ({_tag(qual)})")
    if not shown and qual is None:
        bits.append("priority 1 specs equal")
    must = [d for d in r.diffs if d.priority > 1 and (d.hard or d.must_meet) and d.status in (WORSE, DIFFERENT)]
    if must:
        bits.append("also: " + ", ".join(f"{_short(d.label)} {d.ref_display} vs {d.cand_display}" for d in must))
    bits += data_gaps(r)
    if r.lifecycle_risk:
        bits.append(f"our part is {lifecycle.badge(cand)[0]}")
    notes = cross_notes.notes_for(ref.mpn, cand.mpn)
    if notes:
        bits.append(f"engineer note: {notes[0]['verdict_label'].lower()}")
    if not get_rules(ref.family).by_priority(1):
        bits.append("(no priority list yet)")
    return "; ".join(bits) + "."


TYPE_KIND = {"Direct package equivalent": "pe", "Package drop-in, deviations": "di"}  # chip colours; others "fn"


def cross_type(r: CrossResult, column: int) -> str:
    """The cross type in the owner's words (mockup, 26 Oct 2026), from the engine's type and how priority 1
    compares: direct package equivalent (the engine's drop-in), package drop-in with deviations, functional fit in
    another package or pinout (marked upgrade / downgrade when every priority 1 spec is better / worse)."""
    v = r.verdict()
    if r.category == "fff":
        return "Direct package equivalent"
    if column == 1 or r.fit.fits:
        return "Package drop-in, deviations"
    base = "Functional · other package" if not r.fit.same_package else "Functional · other pinout"
    return base + {"over": " · upgrade", "under": " · downgrade"}.get(v.spec, "")


def p1_labels(family: str) -> list[str]:
    rules = load_all_rules().get(family)
    return [_short(p.label) for p in rules.by_priority(1)] if rules else []


# ---------------------------------------------------------------- human verification


def _pair_key(their: str, ours: str) -> str:
    return f"{their}|{ours}"[:120]


def answers(session: Session) -> dict[tuple[str, str], DataReview]:
    """The latest Right / Wrong answer per pair (normalised part numbers)."""
    out: dict[tuple[str, str], DataReview] = {}
    for r in session.scalars(select(DataReview).where(DataReview.dataset == DATASET).order_by(DataReview.created_at,
                                                                                             DataReview.id)):
        a, _, b = r.key.partition("|")
        out[(normalize_pn(a), normalize_pn(b))] = r
    return out


def verified_pairs(session: Session) -> set[tuple[int, int]]:
    """(reference id, candidate id) pairs a person confirmed: an accepted cross verdict, a Verify next cross checked
    OK, or a Right answer here (unless a later Wrong replaced it)."""
    pairs = {(f.reference_id, f.candidate_id) for f in
             session.scalars(select(CrossFeedback).where(CrossFeedback.verdict == FeedbackVerdict.accept))}  # fmt: skip
    for t in session.scalars(select(VerifyTask).where(VerifyTask.kind == "cross", VerifyTask.status == "ok")):
        d = t.detail or {}
        if d.get("ref") and d.get("cand"):
            pairs.add((int(d["ref"]), int(d["cand"])))
    right = {k for k, r in answers(session).items() if r.verdict == "right"}
    if right:
        mpns = {normalize_pn(m): i for i, m in session.execute(select(Part.id, Part.mpn))}
        pairs |= {(mpns[a], mpns[b]) for a, b in right if a in mpns and b in mpns}
    return pairs


class Verified:
    """Membership test for (reference id, candidate id): a pair a person confirmed (verified_pairs), or any cross with a
    part of a confirmed datasheet family (app/services/families.py), unless the pair's own latest answer is Wrong."""

    def __init__(self, session: Session):
        from app.services import families

        self.pairs = verified_pairs(session)
        self.family = families.verified_part_ids(session)
        wrong = {k for k, r in answers(session).items() if r.verdict == "wrong"}
        self.wrong: set[tuple[int, int]] = set()
        if wrong and self.family:
            mpns = {normalize_pn(m): i for i, m in session.execute(select(Part.id, Part.mpn))}
            self.wrong = {(mpns[a], mpns[b]) for a, b in wrong if a in mpns and b in mpns}

    def __contains__(self, pair: tuple[int, int]) -> bool:
        if pair in self.pairs:
            return True
        return bool(self.family & set(pair)) and pair not in self.wrong

    def of(self, ref: int) -> "_OfRef":
        """Candidate ids verified for one reference part (the part page)."""
        return _OfRef(self, ref)


@dataclass
class _OfRef:
    verified: Verified
    ref: int

    def __contains__(self, cand: int) -> bool:
        return (self.ref, cand) in self.verified


def record(session: Session, their: str, ours: str, verdict: str, comment_text: str, author: str | None) -> DataReview:
    r = DataReview(dataset=DATASET, key=_pair_key(their.strip(), ours.strip()), verdict=verdict,
                   comment=(comment_text or "").strip()[:2000] or None, author=author)  # fmt: skip
    session.add(r)
    session.commit()
    return r


def inbox_lines(session: Session, start: datetime) -> list[str]:
    """Inbox sections: wrong crosses (to fix data or rules) and confirmed ones (known answers for the accuracy
    check)."""
    rows = session.scalars(select(DataReview).where(DataReview.dataset == DATASET, DataReview.created_at >= start)
                           .order_by(DataReview.created_at)).all()  # fmt: skip

    def line(r):
        when = r.created_at.strftime("%Y-%m-%d %H:%M")
        their, _, ours = r.key.partition("|")
        note = " ".join((r.comment or "").split())
        return f"- {when} {their} -> {ours}{' · ' + note if note else ''}{' · ' + r.author if r.author else ''}"

    out = ["\n## Cross list: wrong crosses\n",
           "Marked Wrong on Products › Cross a list. Check both datasheets; fix the data file or the rule "
           "(rules/<family>.yaml) and add the pair to data/manage/cross_known_pairs.yaml (expect: wrong).\n"]
    out += [line(r) for r in rows if r.verdict == "wrong"] or ["None."]
    out += ["\n## Cross list: confirmed crosses\n",
            "Marked Right: add each to data/manage/cross_known_pairs.yaml (expect: right).\n"]
    out += [line(r) for r in rows if r.verdict == "right"] or ["None."]
    return out


# ---------------------------------------------------------------- one row per pasted part


@dataclass
class Column:
    result: CrossResult
    type: str
    comment: str
    verified: bool = False
    answer: str | None = None  # latest Right / Wrong

    @property
    def part(self) -> Part:
        return self.result.candidate


@dataclass
class Row:
    n: int
    text: str
    count: int
    key: str = ""  # normalised part number
    part: Part | None = None
    how: str = "none"
    catalogue: dict | None = None
    suggestion: str | None = None
    drop_in: Column | None = None
    functional: Column | None = None
    light: str = "red"
    reason: str = ""
    reason_link: str | None = None
    checked_on: list[str] = field(default_factory=list)
    other: Column | None = None  # third column: the other Skyworks isolator family's best part (Si86 / Si86S)

    @property
    def maker(self) -> str:
        if self.part:
            return self.part.manufacturer.name
        return self.catalogue["manufacturer"] if self.catalogue else ""

    @property
    def status(self) -> str:
        if self.part:
            return lifecycle.badge(self.part)[0]
        return lifecycle.CLASS_LABELS.get(self.catalogue["lifecycle"], "") if self.catalogue else ""

    @property
    def verified(self) -> bool:
        """Any cross of the selection confirmed, the other-family row included."""
        return any(c and c.verified for c in (self.drop_in, self.functional, self.other))

    @property
    def main_verified(self) -> bool:
        """The part's own row (drop-in or functional fit) confirmed."""
        return any(c and c.verified for c in (self.drop_in, self.functional))


def _no_cross(session: Session, part: Part, any_ours: bool) -> tuple[str, str | None]:
    from app.models import Case
    from app.services import pipeline, vocab

    fn = pipeline.fn_for_part(part)
    what = vocab.fn_label(fn) if fn else vocab.family_title(part.family)
    if not any_ours:  # e.g. an isolated DC-DC module (owner, 26 Oct 2026: UCC12051QDVERQ1)
        form = next((pv.value for pv in part.params if pv.key == "construction"), None)
        what = f"{what}, {form}" if form else what
        return f"Function known ({what}), no {OURS} part in our data.", (f"/business/evidence/{fn}" if fn else None)
    case = session.scalar(select(Case.id).where(Case.fn == fn).order_by(Case.id.desc()).limit(1)) if fn else None
    link = f"/business/cases/{case}" if case else (f"/business/evidence/{fn}" if fn else "/business/opportunities")
    return f"Function known ({what}), no cross yet – see Opportunities › Gaps.", link


def cross_list(session: Session, entries: list[Entry]) -> list[Row]:
    ix = build_index(session)
    crosser = Crosser(session)
    verified = Verified(session)
    said = answers(session)
    rows = []
    for i, e in enumerate(entries, 1):
        m = resolve(ix, e.key, session)
        row = Row(i, e.text, e.n, e.key, how=m.how, catalogue=m.catalogue, suggestion=m.suggestion)
        rows.append(row)
        if m.part_id is None:
            if m.catalogue:
                row.light, row.reason = "green", f"Already a {m.catalogue['manufacturer']} part – nothing to cross."
            else:
                row.reason = (f"Not in our data – did you mean {m.suggestion}?" if m.suggestion
                              else "Not in our data.")  # fmt: skip
                if m.suggestion:
                    row.reason_link = f"/find?q={m.suggestion}"
            continue
        part = session.get(Part, m.part_id)
        row.part = part
        row.checked_on = p1_labels(part.family)
        if part.is_reference:
            row.light, row.reason = "green", f"Already a {part.manufacturer.name} part – nothing to cross."
            continue
        crosses = crosser.crosses(part)
        c1, c2 = columns(part, crosses)
        alt = other_family([c1, c2], _pool(part, crosses))
        for col, r in ((1, c1), (2, c2), (3, alt[1] if alt else None)):
            if r is None:
                continue
            a = said.get((normalize_pn(part.mpn), normalize_pn(r.candidate.mpn)))
            note = comment(r, col) if col < 3 else f"{alt[0]} family · {comment(r, col)}"
            c = Column(r, cross_type(r, col), note, (part.id, r.candidate.id) in verified, a.verdict if a else None)
            if c.answer == "wrong":
                c.verified = False
            if col == 1:
                row.drop_in = c
            elif col == 2:
                row.functional = c
            else:
                row.other = c
        if c1 is None and c2 is None:
            row.reason, row.reason_link = _no_cross(session, part, bool(crosser._cands.get(
                (part.family, False, None))))  # fmt: skip
        elif any(c is not None and c.category == "fff" and not data_gaps(c) and not c.lifecycle_risk
                 for c in (c1, alt[1] if alt else None)):  # fmt: skip
            row.light = "green"
        else:
            row.light = "amber"
    return rows


EXPORT_HEADER = ["#", "Your part", "Maker", "Status", "Light", "Drop-in part", "Drop-in maker", "Drop-in type",
                 "Drop-in comment", "Functional fit part", "Functional fit maker", "Functional fit type",
                 "Functional fit comment", "Checked on (P1 specs)", "Verified", "Your comment"]  # fmt: skip
OTHER_LINE = "↳ other family"  # first cell of the other-family line under a part's line


def export_cells(r: Row) -> list:
    """One exported row, as the page shows it: the Excel download and the copied table use the same cells."""
    def col(c):
        return [c.part.mpn, c.part.manufacturer.name, c.type, c.comment] if c else ["", "", "", ""]

    if r.drop_in is None and r.functional is None:
        first, second = ["No drop-in", "", "", ""], ["No functional fit", "", "", r.reason]
    else:
        first = col(r.drop_in) if r.drop_in else ["No drop-in", "", "", ""]
        second = col(r.functional) if r.functional else ["= Drop-in", "", "", ""]
    part = r.text + (f" ×{r.count}" if r.count > 1 else "")
    return [r.n, part, r.maker or ("not recognised" if r.part is None and not r.catalogue else ""), r.status,
            LIGHTS[r.light], *first, *second, ", ".join(r.checked_on), "✓ Verified" if r.main_verified else "", ""]


def other_cells(r: Row) -> list:
    """The other-family line under a part's line (owner, 27 Oct 2026: "a third row ... that becomes part of each
    selection"): "↳ other family", the part's light, the cross in the Drop-in cells when it fits, else in the
    Functional fit cells."""
    c = r.other
    cells = [c.part.mpn, c.part.manufacturer.name, c.type, c.comment]
    first, second = (cells, ["", "", "", ""]) if c.result.fit.fits else (["", "", "", ""], cells)
    return [OTHER_LINE, "", "", "", LIGHTS[r.light], *first, *second, ", ".join(r.checked_on),
            "✓ Verified" if c.verified else "", ""]  # fmt: skip


def export_lines(r: Row) -> list[list]:
    """A part's exported lines: its own, plus the other-family line when there is one."""
    return [export_cells(r)] + ([other_cells(r)] if r.other else [])


def tsv(rows: list[Row]) -> str:
    """The table as tab-separated text (pastes into Excel, Outlook, PowerPoint as a table)."""
    def clean(v):
        return " ".join(str(v).split())

    lines = [EXPORT_HEADER, *(x for r in rows for x in export_lines(r))]
    return "\n".join("\t".join(clean(v) for v in line) for line in lines) + "\n"


def crossed(r: Row) -> bool:
    """A successful cross: the row has a drop-in or a functional fit ("Only crossed parts", owner, 27 Oct 2026)."""
    return bool(r.drop_in or r.functional)


CROSSED_NOTE = ("Only crossed parts: the Excel download and Copy table keep only the parts with a drop-in or a "
                "functional fit (no red, no-cross or not-in-our-data rows).")  # fmt: skip


def summary(rows: list[Row]) -> dict:
    n = len(rows)
    counts = {k: sum(r.light == k for r in rows) for k in LIGHTS}
    covered = counts["green"] + counts["amber"]
    return {"n": n, **counts, "coverage": round(100 * covered / n) if n else 0,
            "verified": sum(r.verified for r in rows)}  # fmt: skip


KNOWN_FILE = "cross_known_pairs.yaml"
ACCURACY_FILE = "cross_accuracy.yaml"


def known_pairs() -> list[dict]:
    """The known answers: pairs a person marked Right or Wrong (data/manage/cross_known_pairs.yaml, kept by the daily
    run from the inbox) and the engineer notes on specific crosses (data/cross_notes.yaml: best / next best /
    acceptable count as right, not recommended as wrong). Part numbers match by prefix, as the notes do."""
    from app import yamlio
    from app.config import PROJECT_ROOT

    f = PROJECT_ROOT / "data" / "manage" / KNOWN_FILE
    own = (yamlio.load(f.read_text()) or {}).get("pairs") or [] if f.exists() else []
    out = [{"their": p["their"], "ours": p["ours"], "expect": p.get("expect", "right"),
            "source": p.get("source", "Right / Wrong on Cross a list")} for p in own]  # fmt: skip
    for n in cross_notes._notes():
        out.append({"their": n["reference"], "ours": n["candidate"],
                    "expect": "wrong" if n.get("verdict") == "not_recommended" else "right",
                    "source": f"engineer note ({n.get('author') or 'data/cross_notes.yaml'})"})  # fmt: skip
    return out


def check_accuracy(session: Session, pairs: list[dict]) -> dict:
    """Re-cross every known pair's part: a Right pair counts as a hit when ours is shown (either column or the other
    Skyworks isolator family option), a Wrong pair when it is not. Pairs whose part is not in the data are counted
    apart, never as misses."""
    ix, crosser = build_index(session), Crosser(session)
    hits, misses, skipped = 0, [], []
    for p in pairs:
        m = resolve(ix, normalize_pn(p["their"]), session)
        part = session.get(Part, m.part_id) if m.part_id and m.how in ("exact", "variant") else None
        if part is None or part.is_reference:
            skipped.append(p["their"])
            continue
        crosses = crosser.crosses(part)
        cols = list(columns(part, crosses))
        alt = other_family(cols, _pool(part, crosses))
        shown = [c.candidate.mpn for c in [*cols, alt[1] if alt else None] if c is not None]
        found = any(normalize_pn(s).startswith(normalize_pn(p["ours"])) for s in shown)
        if found == (p["expect"] == "right"):
            hits += 1
        else:
            misses.append(f"{p['their']} -> {p['ours']} (expected {p['expect']}; shown: {', '.join(shown) or 'none'})")
    n = hits + len(misses)
    return {"checked": today(), "n": n, "hits": hits, "rate": round(100 * hits / n) if n else 0,
            "misses": misses, "not_in_data": skipped}  # fmt: skip


def accuracy() -> dict | None:
    """The latest daily accuracy check (scripts/check_cross_accuracy.py), if any."""
    from app import yamlio
    from app.config import PROJECT_ROOT

    f = PROJECT_ROOT / "data" / "manage" / ACCURACY_FILE
    try:
        return yamlio.load(f.read_text()) if f.exists() else None
    except Exception:  # noqa: BLE001
        return None


def today() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")
