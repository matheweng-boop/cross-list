"""Verify next: a small batch for the owner instead of a long queue (Data management > Verify next).

Each task stands for many items, so a few checks vouch for the rest:
- crosses: one cross per pair of datasheets, the pairs that carry the most parts first (if the values read from a
  datasheet are right for one part, they are very likely right for every part on it), spread over the families;
- block diagrams: a typical-size unverified diagram of the biggest categories (diagrams of one kind were drawn alike);
- data items: the competition, market-trend and path entries of the most-needed functions (each file was researched
  the same way).

A kind gets its next batch only when its open tasks are done, so crosses can move on while a diagram waits.
A task marked wrong is also sent to Site feedback, so the fix is part of the next feedback run.
"""

from collections import Counter, defaultdict
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.matching.engine import CATEGORY_LABELS, CATEGORY_ORDER
from app.models import DataReview, Manufacturer, ManufacturerRole, Part, SiteFeedback, VerifyTask
from app.services import blocks, scoring, vocab
from app.services import opportunity as op
from app.services.queries import crosses_for

BATCH = {"cross": 6, "diagram": 2, "data": 3}
KINDS = {"cross": "Crosses", "diagram": "Block diagrams", "data": "Other data"}
AUTHOR = "Verify next"
DATA_TOPICS = {"competition": "Competition", "trends": "Market trend", "path": "Path to product"}


def _open(session: Session, kind: str) -> list[VerifyTask]:
    q = select(VerifyTask).where(VerifyTask.kind == kind, VerifyTask.status == "open").order_by(VerifyTask.id)
    return list(session.scalars(q))


def _used(session: Session, kind: str) -> set[str]:
    return set(session.scalars(select(VerifyTask.key).where(VerifyTask.kind == kind)))


def _datasheet_groups(session: Session) -> tuple[dict, dict]:
    """(competitor groups, our groups): datasheet URL -> its parts."""
    comp, ours = defaultdict(list), defaultdict(list)
    q = select(Part, Manufacturer.role).join(Manufacturer).where(Part.datasheet_url.is_not(None),
                                                                 Part.datasheet_url != "")  # fmt: skip
    for p, role in session.execute(q):
        (ours if role == ManufacturerRole.reference else comp)[p.datasheet_url].append(p)
    return comp, ours


def _crosses(session: Session, n: int, per_family: int = 3) -> list[VerifyTask]:
    """The best cross of the biggest competitor datasheets of each family, then picked by how many parts the two
    datasheets carry: first the best of each family, then the rest; never the same datasheet of ours twice."""
    comp, ours = _datasheet_groups(session)
    used = _used(session, "cross")
    done_comp = {k.split(" | ")[0] for k in used}
    by_family: dict[str, list] = defaultdict(list)
    for url, ps in comp.items():
        if url not in done_comp:
            by_family[ps[0].family].append((len(ps), url))
    options = []
    for fam, groups in by_family.items():
        for size, url in sorted(groups, reverse=True)[:per_family]:
            ref = sorted(comp[url], key=lambda p: p.mpn)[0]
            res = crosses_for(session, ref)
            hit = next(((r, c) for c in CATEGORY_ORDER for r in res.get(c, []) if r.candidate.datasheet_url), None)
            if hit is None or f"{url} | {hit[0].candidate.datasheet_url}" in used:
                continue
            n_ours = len(ours.get(hit[0].candidate.datasheet_url, []))
            options.append((size * max(n_ours, 1), fam, url, ref, hit[0].candidate, hit[1], size, n_ours))
    options.sort(key=lambda o: -o[0])
    firsts = list({o[1]: o for o in reversed(options)}.values())  # the best option of each family
    picked, seen = [], set()
    for o in sorted(firsts, key=lambda o: -o[0]) + options:
        if len(picked) < n and o not in picked and o[4].datasheet_url not in seen:
            picked.append(o)
            seen.add(o[4].datasheet_url)
    out = []
    for covers, fam, url, ref, cand, cat, size, n_ours in picked:
        out.append(VerifyTask(
            kind="cross", key=f"{url} | {cand.datasheet_url}"[:600], covers=covers,
            title=f"{ref.mpn} ({ref.manufacturer.name}) → {cand.mpn} ({cand.manufacturer.name})",
            detail={"ref": ref.id, "cand": cand.id, "family": fam, "type": CATEGORY_LABELS[cat],
                    "ref_ds": url, "cand_ds": cand.datasheet_url, "n_ref": size, "n_cand": n_ours,
                    "why": f"{size} {ref.manufacturer.name} part{'s' if size != 1 else ''} and {n_ours} of ours "
                           f"are read from these two datasheets"}))  # fmt: skip
    return out


def _diagrams(session: Session, n: int) -> list[VerifyTask]:
    done = set(blocks.verifications(session)) | _used(session, "diagram")
    ts = blocks.templates()
    cats = Counter(t.get("category") or "Other" for t in ts)
    out: list[VerifyTask] = []
    for cat, size in cats.most_common():
        if len(out) >= n:
            break
        cands = [(sum(len(g.get("blocks") or []) for g in t.get("groups") or []), i, t) for i, t in enumerate(ts)
                 if (t.get("category") or "Other") == cat and blocks.verify_key(t) not in done]  # fmt: skip
        if not cands:
            continue
        sizes = sorted(sum(len(g.get("blocks") or []) for g in x.get("groups") or []) for x in ts
                       if (x.get("category") or "Other") == cat)  # fmt: skip
        typical = sizes[len(sizes) // 2]  # a typical diagram of the kind stands for the others best
        nb, i, t = min(cands, key=lambda c: (abs(c[0] - typical), c[1]))
        out.append(VerifyTask(kind="diagram", key=blocks.verify_key(t), covers=size, title=blocks.display_name(t),
                              detail={"i": i, "category": cat, "blocks": nb,
                                      "why": f"a typical-size unverified one of {size} '{cat}' diagrams"}))  # fmt: skip
    return out


def _claim(topic: str, e: dict) -> str:
    if topic == "competition":
        vendors = ", ".join(e.get("vendors") or [])
        return f"{op.CROWDING_LABEL.get(e.get('crowding'), e.get('crowding'))}: {vendors}"
    if topic == "trends":
        return f"{e.get('outlook') or 'regulation: ' + str(e.get('regulation'))} · {e.get('note') or ''}".strip(" ·")
    return f"{op.PATH_LABEL.get(e.get('path'), e.get('path'))} · {e.get('base') or ''}".strip(" ·")


def _library_rule(session: Session) -> VerifyTask | None:
    """The least certain design rule of the technical library that nobody has reviewed or been given yet."""
    from app.services import library

    used = _used(session, "data")
    reviewed = {(d, k) for d, k in session.execute(select(DataReview.dataset, DataReview.key))}
    rank = {"low": 0, "med": 1, "medium": 1, "high": 2}
    cands = [(rank.get(r.get("conf"), 1), t["order"] if "order" in t else 99, t, r) for t in library.topics()
             for r in t.get("design_rules") or []
             if f"library:{t['key']}:{r['id']}" not in used and (library.dataset(t["key"]), r["id"]) not in reviewed]
    if not cands:
        return None
    _, _, tp, r = min(cands, key=lambda c: c[:2])
    refs = library.refs_by_id(tp)
    sources = [f"{refs[i]['title']} ({refs[i]['publisher']})" for i in r.get("refs") or [] if i in refs]
    n_rules = sum(len(x.get("design_rules") or []) for x in library.topics())
    return VerifyTask(kind="data", key=f"library:{tp['key']}:{r['id']}", covers=n_rules,
                      title=f"Design rule: {r['area']} ({tp['title'].split(':')[0].split('(')[0].strip()})",
                      detail={"topic": "library", "library": tp["key"], "item": r["id"], "fn": "",
                              "claim": f"{r['rule']} Why: {r.get('why') or ''}"[:600], "sources": sources,
                              "why": f"the least certain of {n_rules} library design rules read from the same "
                                     f"kind of references"})  # fmt: skip


def _data(session: Session, n: int) -> list[VerifyTask]:
    """Evidence entries behind the scores (the types rotate from batch to batch) and one library design rule."""
    rule = _library_rule(session)
    n_evidence = n - 1 if rule else n
    tab = scoring.combined(session)
    need = sorted((u["raw"], fn) for fn, u in tab["usage"].items() if fn in tab["rows"])
    order = [fn for _, fn in reversed(need)]
    used = _used(session, "data")
    reviewed = {(d, k) for d, k in session.execute(select(DataReview.dataset, DataReview.key))}
    out: list[VerifyTask] = []
    kinds = list(DATA_TOPICS.items())
    start = len(used) // max(n, 1) % len(kinds)  # rotate which evidence comes first in each new batch
    for topic, label in kinds[start:] + kinds[:start]:
        if len(out) >= n_evidence:
            break
        entries = op.competition() if topic == "competition" else op.evidence(topic)
        taken = {x.detail["fn"] for x in out}  # a different function per item
        fresh = [f for f in order if f in entries and f not in taken and f"{topic}:{f}" not in used
                 and (topic, f) not in reviewed]  # fmt: skip
        fn = fresh[0] if fresh else None
        if fn is None:
            continue
        e = entries[fn]
        why = f"the most-needed of {len(entries)} functions researched the same way"
        out.append(VerifyTask(kind="data", key=f"{topic}:{fn}", covers=len(entries),
                              title=f"{label} of {vocab.fn_label(fn)}",
                              detail={"fn": fn, "topic": topic, "claim": _claim(topic, e)[:400],
                                      "sources": (e.get("sources") or [])[:4],
                                      "why": why}))  # fmt: skip
    return out + ([rule] if rule else [])


PICK = {"cross": _crosses, "diagram": _diagrams, "data": _data}


def assign(session: Session) -> list[str]:
    """A new batch for each kind with nothing open; returns the kinds that got one."""
    new = []
    for kind, n in BATCH.items():
        if _open(session, kind):
            continue
        tasks = PICK[kind](session, n)
        if tasks:
            session.add_all(tasks)
            new.append(kind)
    if new:
        session.commit()
    return new


def board(session: Session) -> dict:
    """Open tasks per kind and what the done ones vouch for."""
    rows = list(session.scalars(select(VerifyTask).order_by(VerifyTask.id)))
    done = [r for r in rows if r.status != "open"]
    return {"open": {k: [r for r in rows if r.kind == k and r.status == "open"] for k in BATCH},
            "done": {k: [r for r in done if r.kind == k] for k in BATCH},
            "vouched": {k: sum(r.covers for r in done if r.kind == k and r.status == "ok") for k in BATCH}}  # fmt: skip


def complete(session: Session, task_id: int, ok: bool, note: str = "", author: str = "") -> VerifyTask:
    t = session.get(VerifyTask, task_id)
    if t is None or t.status != "open":
        raise ValueError("no open task")
    t.status, t.note, t.author = ("ok" if ok else "wrong"), note.strip()[:2000] or None, author.strip()[:100] or None
    t.done_at = datetime.now(UTC)
    d = t.detail or {}
    if t.kind == "diagram" and ok:
        blocks.set_verified(session, d["i"], True, author, note)
    if t.kind == "data" and d.get("topic") == "library":
        from app.services import library

        session.add(DataReview(dataset=library.dataset(d["library"]), key=d["item"],
                               verdict="correct" if ok else "wrong", comment=t.note, author=t.author))  # fmt: skip
    elif t.kind == "data":
        session.add(DataReview(dataset=d["topic"], key=d["fn"], verdict="correct" if ok else "wrong",
                               comment=t.note, author=t.author))  # fmt: skip
    if not ok:
        page = f"Data management › Verify next › {KINDS[t.kind]}"
        session.add(SiteFeedback(text=f"Verification found an error: {t.title}. {t.note or ''}".strip(), kind="data",
                                 author=AUTHOR, path="/manage/verify", page=page))  # fmt: skip
    session.commit()
    return t
