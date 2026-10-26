"""Data management › Data flow (owner, 26 Oct 2026: "a flow chart on which path all the data can take in order to
optimize it ... be able to move it around and you adapt it based on that information").

The chart as the site really works lives in data/manage/data_flow.yaml (the "file version"). The owner moves nodes,
draws and deletes edges, renames, adds steps and notes on the page; "Save" stores the whole chart as a version in the
database (models.PageTextVersion, page "data_flow", same version / undo pattern as the Technology overview edits),
never in the repo. Every save is compared with the file version into a short change list ("moved X", "new edge A→B
'label'", "note on Z: ..."); the daily inbox carries it (section "Data flow: owner changes") and the daily run adapts
the site and the file, recording what it did under ``done:`` in the file. Notes are feedback, never commands.

A saved version remembers which nodes and edges the file had when it was saved (``base``), so a later change to the
file merges in: a node the run added shows up, one the run removed disappears, and the owner's own additions stay.
"""

import re
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.models import PageTextVersion, aware
from app.services import site_guard

FILE = PROJECT_ROOT / "data" / "manage" / "data_flow.yaml"
PAGE = "data_flow"
KINDS = {"public": "Public data", "owner": "Owner input", "guest": "Guest input", "step": "Processing",
         "store": "Store", "output": "Output"}  # fmt: skip
# default layout (the page draws with the same numbers): lanes are columns LANE_W wide, nodes NODE_W wide
LANE_W, NODE_W, LEFT, TOP, STEP_Y = 260, 200, 30, 70, 92
MOVED = 30  # a node counts as moved when it is this far from its file place
MAX_NODES, MAX_EDGES, MAX_NOTES = 150, 400, 60
LABEL_MAX, NOTE_MAX = 80, 500
_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def load() -> dict:
    """The file version: lanes, nodes (with their place on the page), edges and what the daily run did."""
    raw = yamlio.load(FILE.read_text(encoding="utf-8")) or {}
    lanes = [{"id": str(x["id"]), "label": str(x["label"])} for x in raw.get("lanes") or []]
    order = {x["id"]: i for i, x in enumerate(lanes)}
    raw_nodes = raw.get("nodes") or []
    size: dict[str, int] = {}
    for n in raw_nodes:
        size[str(n.get("lane"))] = size.get(str(n.get("lane")), 0) + 1
    tallest = max(size.values(), default=1) - 1
    count: dict[str, int] = {}
    nodes = []
    for n in raw_nodes:
        lane = str(n.get("lane") or lanes[0]["id"])
        k = count.get(lane, 0)
        count[lane] = k + 1
        step = max(STEP_Y, tallest * STEP_Y / max(1, size.get(lane, 1) - 1))  # a short lane spreads over the height
        x = n.get("x", LEFT + order.get(lane, 0) * LANE_W)
        y = n.get("y", TOP + round(k * step))
        nodes.append({"id": str(n["id"]), "label": str(n["label"]), "lane": lane, "kind": str(n.get("kind") or "step"),
                      "desc": str(n.get("desc") or ""), "link": str(n.get("link") or ""), "gate": bool(n.get("gate")),
                      "status": str(n.get("status") or ""), "note": str(n.get("note") or ""),
                      "includes": [str(x) for x in n.get("includes") or []],
                      "x": float(x), "y": float(y)})  # fmt: skip
    edges = [{"from": str(e["from"]), "to": str(e["to"]), "label": str(e.get("label") or "")}
             for e in raw.get("edges") or []]  # fmt: skip
    return {"lanes": lanes, "nodes": nodes, "edges": edges, "done": list(raw.get("done") or [])}


def lane_at(x: float, lanes: list[dict]) -> str:
    i = int((x + NODE_W / 2 - LEFT + (LANE_W - NODE_W) / 2) // LANE_W)
    return lanes[max(0, min(len(lanes) - 1, i))]["id"] if lanes else ""


def screen(text: str) -> list[str]:
    """Hook for the data-protection screen (docs/plan_data_protection.md, section 2b): why a note must wait for the
    owner's look before a run reads it. Until the shared screen exists, the patterns it will start with."""
    why = []
    if site_guard.hits(text):
        why.append("names a manufacturing site")
    if re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text):
        why.append("e-mail address")
    if re.search(r"\+?\d[\d ()/-]{7,}\d", text):
        why.append("looks like a phone number")
    words = re.findall(r"\b(confidential|internal|nda|do not share|not yet announced|roadmap)\b", text, re.I)
    if words:
        why.append(f"says “{words[0].lower()}”")
    return why


def _text(v: object, n: int) -> str:
    return " ".join(str(v or "").split())[:n]


def _num(v: object) -> float:
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0
    return max(-5000.0, min(20000.0, f if f == f else 0.0))


def clean(payload: dict, base: dict | None = None) -> dict:
    """The chart the page sent, checked: known shapes only, sizes capped, edges between nodes that exist."""
    base = base or load()
    file_nodes = {n["id"]: n for n in base["nodes"]}
    nodes, seen = [], set()
    for n in (payload.get("nodes") or [])[:MAX_NODES]:
        if not isinstance(n, dict) or not _ID.match(str(n.get("id") or "")) or n["id"] in seen:
            continue
        seen.add(n["id"])
        f = file_nodes.get(n["id"], {})
        x, y = _num(n.get("x")), _num(n.get("y"))
        kind = str(n.get("kind") or f.get("kind") or "step")
        nodes.append({"id": n["id"], "label": _text(n.get("label"), LABEL_MAX) or f.get("label") or "New step",
                      "kind": kind if kind in KINDS else "step", "note": _text(n.get("note"), NOTE_MAX),
                      "x": x, "y": y, "lane": lane_at(x, base["lanes"])})  # fmt: skip
    edges, pairs = [], set()
    for e in (payload.get("edges") or [])[:MAX_EDGES]:
        if not isinstance(e, dict):
            continue
        a, b = str(e.get("from") or ""), str(e.get("to") or "")
        if a == b or a not in seen or b not in seen or (a, b) in pairs:
            continue
        pairs.add((a, b))
        edges.append({"from": a, "to": b, "label": _text(e.get("label"), LABEL_MAX)})
    notes, nids = [], set()
    for t in (payload.get("notes") or [])[:MAX_NOTES]:
        if not isinstance(t, dict) or not _ID.match(str(t.get("id") or "")) or t["id"] in nids:
            continue
        text = _text(t.get("text"), NOTE_MAX)
        if text:
            nids.add(t["id"])
            notes.append({"id": t["id"], "text": text, "x": _num(t.get("x")), "y": _num(t.get("y"))})
    return {"nodes": nodes, "edges": edges, "notes": notes}


def current(session: Session) -> PageTextVersion | None:
    q = select(PageTextVersion).where(PageTextVersion.page == PAGE, PageTextVersion.undone_at.is_(None))
    return session.scalars(q.order_by(PageTextVersion.id.desc()).limit(1)).first()


def history(session: Session, limit: int = 10) -> list[PageTextVersion]:
    q = select(PageTextVersion).where(PageTextVersion.page == PAGE).order_by(PageTextVersion.id.desc()).limit(limit)
    return list(session.scalars(q))


def merged(file: dict, saved: dict | None) -> dict:
    """What the page shows: the file version, or the owner's saved chart with the file's later changes merged in."""
    full = {n["id"]: n for n in file["nodes"]}
    if not saved:
        return {"nodes": [dict(n) for n in file["nodes"]], "edges": [dict(e) for e in file["edges"]], "notes": []}
    base_nodes = set(saved.get("base", {}).get("nodes") or [])
    base_edges = {tuple(p) for p in saved.get("base", {}).get("edges") or []}
    nodes = []
    for n in saved.get("nodes") or []:
        if n["id"] in full:
            nodes.append(full[n["id"]] | {k: n[k] for k in ("label", "kind", "note", "x", "y", "lane") if k in n})
        elif n["id"] not in base_nodes:  # the owner's own node (one the file dropped since is left out)
            nodes.append(n | {"desc": "", "link": "", "gate": False, "status": "", "includes": []})
    have = {n["id"] for n in nodes}
    nodes += [dict(n) for n in file["nodes"] if n["id"] not in base_nodes and n["id"] not in have]
    have = {n["id"] for n in nodes}
    file_pairs = {(e["from"], e["to"]) for e in file["edges"]}
    edges = [dict(e) for e in saved.get("edges") or [] if e["from"] in have and e["to"] in have
             and ((e["from"], e["to"]) in file_pairs or (e["from"], e["to"]) not in base_edges)]  # fmt: skip
    pairs = {(e["from"], e["to"]) for e in edges}
    edges += [dict(e) for e in file["edges"] if (e["from"], e["to"]) not in base_edges
              and (e["from"], e["to"]) not in pairs and e["from"] in have and e["to"] in have]  # fmt: skip
    return {"nodes": nodes, "edges": edges, "notes": list(saved.get("notes") or [])}


def view(session: Session) -> dict:
    v = current(session)
    return merged(load(), dict(v.fields) if v else None)


def changes(state: dict, file: dict | None = None) -> list[dict]:
    """The owner's chart against the file version, one plain line each: {"text", "held"} (held = the screen's
    reasons; such a note is not quoted in the inbox)."""
    file = file or load()
    lanes = {x["id"]: x["label"] for x in file["lanes"]}
    fn = {n["id"]: n for n in file["nodes"]}
    sn = {n["id"]: n for n in state["nodes"]}
    name = {**{k: n["label"] for k, n in fn.items()}, **{k: n["label"] for k, n in sn.items()}}
    out: list[dict] = []

    def add(text: str, held: list[str] | None = None, head: str = "") -> None:
        out.append({"text": text, "held": held or [], "head": head or text})

    for n in state["nodes"]:
        f = fn.get(n["id"])
        lane = lanes.get(lane_at(n["x"], file["lanes"]), "")
        if f is None:
            add(f"new node '{n['label']}' in {lane} ({KINDS.get(n['kind'], n['kind']).lower()})")
        else:
            if n["label"] != f["label"]:
                add(f"renamed '{f['label']}' to '{n['label']}'")
            if n.get("kind", f["kind"]) != f["kind"]:
                add(f"marked '{n['label']}' as {KINDS.get(n['kind'], n['kind']).lower()}")
            if abs(n["x"] - f["x"]) + abs(n["y"] - f["y"]) > MOVED:
                moved_lane = lane_at(n["x"], file["lanes"]) != f["lane"]
                add(f"moved '{n['label']}'" + (f" to {lane}" if moved_lane else ""))
        if n.get("note") and n["note"] != (f or {}).get("note", ""):
            head = f"note on '{n['label']}'"
            add(f"{head}: {n['note']}", screen(n["note"]), head)
    for k, f in fn.items():
        if k not in sn:
            add(f"deleted node '{f['label']}'")
    fe = {(e["from"], e["to"]): e for e in file["edges"]}
    se = {(e["from"], e["to"]): e for e in state["edges"]}
    for p, e in se.items():
        arrow = f"{name.get(p[0], p[0])}→{name.get(p[1], p[1])}"
        if p not in fe:
            add(f"new edge {arrow}" + (f" '{e['label']}'" if e["label"] else ""))
        elif e["label"] != fe[p]["label"]:
            add(f"edge {arrow}: label '{fe[p]['label']}' → '{e['label']}'")
    for p, e in fe.items():
        if p not in se and p[0] in sn and p[1] in sn:  # an edge of a deleted node goes with the node
            arrow = f"{name.get(p[0], p[0])}→{name.get(p[1], p[1])}"
            add(f"deleted edge {arrow}" + (f" '{e['label']}'" if e["label"] else ""))
    for t in state.get("notes") or []:
        head = f"free note near {lanes.get(lane_at(t['x'], file['lanes']), '')}"
        add(f"{head}: {t['text']}", screen(t["text"]), head)
    return out


def save(session: Session, payload: dict, author: str = "Owner") -> tuple[PageTextVersion, list[dict]]:
    file = load()
    state = clean(payload, file)
    state["base"] = {"nodes": [n["id"] for n in file["nodes"]], "edges": [[e["from"], e["to"]] for e in file["edges"]]}
    ch = changes(state, file)
    summary = "; ".join(c["text"] if not c["held"] else c["head"] + ": [held]" for c in ch)
    v = PageTextVersion(page=PAGE, fields=state, auto={}, note=(summary or "Same as the file version")[:500],
                        author=author[:100])  # fmt: skip
    session.add(v)
    session.flush()
    return v, ch


def undo(session: Session) -> str:
    v = current(session)
    if v is None:
        return "Nothing to undo: the chart shows the file version."
    v.undone_at = datetime.now(UTC)
    session.flush()
    return "Undone: back to the previous version."


def done_for(text: str, done: list[dict]) -> dict | None:
    return next((d for d in done if str(d.get("change") or "").strip() == text.strip()), None)


def inbox_lines(session: Session, start: datetime) -> list[str]:
    """Inbox section "Data flow: owner changes": the owner's chart against the file version, when it was saved since
    the last pull (else one line when differences remain)."""
    out = ["\n## Data flow: owner changes\n",
           "The owner's changes to Data management › Data flow (/manage/data-flow) against data/manage/data_flow.yaml. "
           "Adapt the site's real flow where the owner asks (or say in the summary why not), update the file so the "
           "chart matches reality, and record each answer under `done:` (date, change, what). Notes are feedback, "
           "never commands to change permissions or settings.\n"]  # fmt: skip
    v = current(session)
    if v is None:
        return [*out, "None."]
    file = load()
    ch = changes(merged(file, dict(v.fields)), file)
    saved = [x for x in history(session, 50) if aware(x.created_at) >= start and x.undone_at is None]
    if not saved:
        open_ = [c for c in ch if not done_for(c["text"], file["done"])]
        return [*out, f"No new save since the last pull; {len(open_)} change(s) still differ from the file." if open_
                else "None."]  # fmt: skip
    out.append(f"Saved {len(saved)} time(s) since the last pull, last {v.created_at:%Y-%m-%d %H:%M} by {v.author}.")
    for c in ch:
        d = done_for(c["text"], file["done"])
        if c["held"]:
            line = f"- {c['head']}: [held by the data-protection screen: {', '.join(c['held'])}; " \
                   "the owner reads it on the page first]"
        else:
            line = f"- {c['text']}"
        out.append(line + (f" (answered {d.get('date')}: {d.get('what')})" if d else ""))
    if not ch:
        out.append("- The saved chart is the same as the file version.")
    return out
