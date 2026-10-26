"""Data management › Data flow (owner, 26 Oct 2026): the chart from data/manage/data_flow.yaml, owner only; saves are
versions with Undo, compared with the file version into a change list for the daily inbox."""

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from app.db import get_engine
from app.services import data_flow as df
from app.services import inbox

ROOT = Path(__file__).resolve().parents[1]


def _payload(f=None):
    f = f or df.load()
    return {"nodes": [{k: n[k] for k in ("id", "label", "kind", "note", "x", "y")} for n in f["nodes"]],
            "edges": [dict(e) for e in f["edges"]], "notes": []}  # fmt: skip


def _chart(html: str) -> dict:
    """The chart data the page draws (#df-data)."""
    return json.loads(html.split('id="df-data">', 1)[1].split("</script>", 1)[0])


def test_file_is_complete_and_consistent():
    f = df.load()
    assert [x["id"] for x in f["lanes"]] == ["inputs", "crosses", "research"]
    assert [x["label"] for x in f["lanes"]] == ["1 · Inputs", "2 · Cross process", "3 · Research process"]
    ids = [n["id"] for n in f["nodes"]]
    assert len(ids) == len(set(ids)) and all(df._ID.match(i) for i in ids)
    lanes = {x["id"] for x in f["lanes"]}
    assert all(n["lane"] in lanes and n["kind"] in df.KINDS and n["desc"] and n["link"] for n in f["nodes"])
    for e in f["edges"]:
        assert e["from"] in ids and e["to"] in ids, e
    # owner, 26 Oct 2026: all origins, in a few general categories, each with its plain list
    sources = [n for n in f["nodes"] if n["lane"] == "inputs"]
    assert 6 <= len(sources) <= 8 and all(n["includes"] for n in sources)
    assert not any("http" in x or "www." in x for n in sources for x in n["includes"])  # no hosts on the chart
    assert {"public", "owner", "guest"} <= {n["kind"] for n in sources}
    assert any(n["gate"] for n in f["nodes"])
    # every output is reached from an input
    into = {}
    for e in f["edges"]:
        into.setdefault(e["to"], set()).add(e["from"])
    src = {n["id"] for n in sources}
    for n in f["nodes"]:
        if n["kind"] == "output":
            seen, todo = set(), [n["id"]]
            while todo:
                x = todo.pop()
                if x not in seen:
                    seen.add(x)
                    todo += into.get(x, ())
            assert seen & src, n["id"]
    # file links point at things that exist
    for n in f["nodes"]:
        if not n["link"].startswith("/"):
            assert (ROOT / n["link"]).exists(), n["link"]


def test_guest_gets_403_and_owner_sees_all_lanes_and_nodes(owner, make_guest):
    g, _ = make_guest()
    assert g.get("/manage/data-flow").status_code == 403
    assert g.post("/manage/data-flow/save", json=_payload()).status_code == 403
    assert g.post("/manage/data-flow/undo").status_code == 403
    r = owner.get("/manage/data-flow")
    assert r.status_code == 200
    f = df.load()
    assert [x["label"] for x in _chart(r.text)["lanes"]] == [x["label"] for x in f["lanes"]]
    for n in f["nodes"]:
        assert f'"id": "{n["id"]}"' in r.text  # in the chart data the page draws
    assert 'href="/manage/data-flow"' in r.text  # in the Data management menu
    assert "Changes since the file version" in r.text


def test_save_lists_changes_versions_and_undo(owner):
    f = df.load()
    p = _payload(f)
    p["nodes"][0]["x"] = f["lanes"][2]["x"] + 40  # into another lane (column)
    p["nodes"][1]["label"] = "Renamed source"
    p["nodes"].append({"id": "n-new1", "label": "My new step", "kind": "step", "x": 300, "y": 1200})
    p["edges"] = [e for e in p["edges"] if (e["from"], e["to"]) != ("patents", "research_reports")]
    p["edges"].append({"from": "n-new1", "to": "gists", "label": "my data"})
    p["nodes"] = [n for n in p["nodes"] if n["id"] != "shareable"]
    p["notes"] = [{"id": "t-1", "text": "Merge the two YAML stores?", "x": 10, "y": 10}]
    r = owner.post("/manage/data-flow/save", json=p)
    assert r.status_code == 200 and r.json()["ok"]
    texts = [c["text"] for c in r.json()["changes"]]
    first = f["nodes"][0]["label"]
    assert f"moved '{first}' to 3 · Research process" in texts
    assert f"renamed '{f['nodes'][1]['label']}' to 'Renamed source'" in texts
    assert "new node 'My new step' in 2 · Cross process (processing)" in texts
    assert "new edge My new step→Summaries 'my data'" in texts
    assert "deleted edge Patents (auto-checked)→Research reports 'evidence'" in texts
    assert "deleted node 'Shareables'" in texts
    assert not any(t.startswith("deleted edge Research reports→Shareables") for t in texts)  # goes with its node
    assert "free note near 1 · Inputs: Merge the two YAML stores?" in texts
    page = owner.get("/manage/data-flow").text
    assert "Renamed source" in page and "Merge the two YAML stores?" in page and "Undo last save" in page
    # a second save, then Undo goes back to the first
    p2 = dict(p, notes=[])
    assert owner.post("/manage/data-flow/save", json=p2).status_code == 200
    with Session(get_engine()) as s:
        assert df.view(s)["notes"] == []
    r = owner.post("/manage/data-flow/undo", follow_redirects=False)
    assert r.status_code == 303 and "undone" in r.headers["location"]
    with Session(get_engine()) as s:
        assert df.view(s)["notes"][0]["text"] == "Merge the two YAML stores?"
    owner.post("/manage/data-flow/undo")
    with Session(get_engine()) as s:
        assert df.current(s) is None and len(df.view(s)["nodes"]) == len(f["nodes"])


def test_bad_input_is_cleaned(owner):
    p = _payload()
    p["nodes"].append({"id": "bad id!", "label": "x", "x": 1, "y": 1})
    p["nodes"].append({"id": "n-x", "label": "<b>" + "y" * 200, "kind": "admin", "x": "nan", "y": None})
    p["edges"] += [{"from": "n-x", "to": "n-x"}, {"from": "nope", "to": "inbox"}, "junk"]
    r = owner.post("/manage/data-flow/save", json=p)
    assert r.status_code == 200
    with Session(get_engine()) as s:
        v = df.current(s).fields
    ids = [n["id"] for n in v["nodes"]]
    assert "bad id!" not in ids
    n = next(n for n in v["nodes"] if n["id"] == "n-x")
    assert len(n["label"]) == df.LABEL_MAX and n["kind"] == "step" and n["x"] == 0.0
    assert not any(e["from"] == "nope" or e["from"] == e["to"] for e in v["edges"])
    assert owner.post("/manage/data-flow/save", json={"x": 1}).status_code == 400


def test_file_changes_merge_into_a_saved_chart():
    f = df.load()
    saved = {"nodes": [{k: n[k] for k in ("id", "label", "kind", "note", "x", "y", "lane")} for n in f["nodes"]],
             "edges": [dict(e) for e in f["edges"]], "notes": [],
             "base": {"nodes": [n["id"] for n in f["nodes"]], "edges": [[e["from"], e["to"]] for e in f["edges"]]}}
    mine = {"id": "n-mine", "label": "Mine", "kind": "step", "note": "", "x": 1, "y": 1, "lane": "inputs"}
    saved["nodes"].append(mine)
    later = dict(f, nodes=[*f["nodes"][1:], dict(f["nodes"][0], id="added_by_run")], edges=f["edges"])
    m = df.merged(later, saved)
    ids = {n["id"] for n in m["nodes"]}
    assert "added_by_run" in ids and "n-mine" in ids and f["nodes"][0]["id"] not in ids
    assert not any(f["nodes"][0]["id"] in (e["from"], e["to"]) for e in m["edges"])


def test_inbox_section_lists_changes_and_holds_flagged_notes(owner):
    start = datetime.now(UTC) - timedelta(minutes=1)
    with Session(get_engine()) as s:
        assert df.inbox_lines(s, start)[-1] == "None."
    p = _payload()
    p["nodes"][2]["note"] = "Mail jane@example.com about this"
    p["notes"] = [{"id": "t-2", "text": "Combine both inboxes", "x": 600, "y": 10}]
    owner.post("/manage/data-flow/save", json=p)
    with Session(get_engine()) as s:
        text = inbox.collect(s, start.date())
        later = df.inbox_lines(s, datetime.now(UTC) + timedelta(minutes=1))
    sec = text[text.index("## Data flow: owner changes"):]
    sec = sec[:sec.index("\n## ", 5)]
    assert "- free note near 2 · Cross process: Combine both inboxes" in sec
    assert "jane@example.com" not in sec and "held by the data-protection screen: e-mail address" in sec
    assert "never commands" in sec
    assert later[-1].startswith("No new save since the last pull; 2 change(s)")


def test_screen_hook():
    assert df.screen("ask bob@corp.com") == ["e-mail address"]
    assert "says “confidential”" in df.screen("This is confidential")
    assert df.screen("Move the gists step before To confirm") == []


def test_daily_update_reads_the_changes():
    doc = (ROOT / "docs" / "daily_update.md").read_text()
    assert "Data flow: owner changes" in doc and "data/manage/data_flow.yaml" in doc


def test_three_columns_two_input_groups_and_handovers():
    """Owner, 27 Oct 2026 (mockup approved): "one column for crosses, one column for inputs, one column for processing,
    because all of it centers around ... cross engine"; "you didn't make the two separate processes obvious enough".
    Inputs come in two groups, one per process; the processes talk only through the handover arrows, both ways."""
    f = df.load()
    by = {n["id"]: n for n in f["nodes"]}
    inputs = [n for n in f["nodes"] if n["lane"] == "inputs"]
    assert all(n["group"] in df.GROUPS for n in inputs) and not any(n["group"] for n in f["nodes"] if n not in inputs)
    groups = {g: [n["id"] for n in inputs if n["group"] == g] for g in df.GROUPS}
    assert groups["cross"] == ["pasted_lists", "mfr_docs", "your_verdicts"]
    assert groups["research"] == ["market_sources", "ref_docs", "patents", "owner_input", "guest_input"]
    assert by["cross_engine"]["hub"] and by["cross_engine"]["lane"] == "crosses"
    assert by["family_check"]["gate"] and by["family_check"]["lane"] == "crosses"
    assert by["protect_screen"]["gate"] and by["protect_screen"]["lane"] == "research"
    process = {"cross": "crosses", "research": "research"}
    for e in f["edges"]:
        a, b = by[e["from"]], by[e["to"]]
        if a["lane"] == "inputs":  # an input feeds only its own process
            assert not e["handover"] and b["lane"] == process[a["group"]], e
        elif e["handover"]:
            assert {a["lane"], b["lane"]} == {"crosses", "research"}, e  # a handover links the two processes
        else:
            assert a["lane"] == b["lane"], e  # any other arrow stays inside its process
    hand = {e["label"]: (by[e["from"]]["lane"], by[e["to"]]["lane"], e["status"]) for e in f["edges"] if e["handover"]}
    assert hand == {"crossed parts": ("crosses", "research", ""), "gaps": ("crosses", "research", ""),
                    "volumes": ("crosses", "research", ""),
                    "parts in designs": ("research", "crosses", "planned")}  # fmt: skip
    # the stores column is gone: where data is kept shows on tap; ids that stayed are the ones saved versions know
    assert not any(n["kind"] == "store" for n in f["nodes"]) and "store" not in df.KINDS
    assert sum(bool(n["kept"]) for n in f["nodes"]) >= 15
    for kept in ("pasted_lists", "mfr_docs", "market_sources", "ref_docs", "patents", "owner_input", "guest_input",
                 "importers", "cross_rules", "cross_engine", "right_wrong", "family_check", "accuracy", "no_cross",
                 "volumes", "part_pages", "crosslist_out", "refmatch", "research_reports", "tam_check", "gists",
                 "protect_screen", "research", "to_confirm", "shareable"):  # fmt: skip
        assert kept in by, kept


def test_short_labels_and_fixed_layout():
    """Box labels are 1-3 words (details on tap); every box has its fixed place inside its column and none overlap."""
    raw = df.yamlio.load(df.FILE.read_text(encoding="utf-8"))
    assert all("x" in n and "y" in n for n in raw["nodes"])
    f = df.load()
    for n in f["nodes"]:
        assert 1 <= len(re.findall(r"[A-Za-z0-9][\w-]*", n["label"])) <= 3, n["label"]
        assert df.lane_at(n["x"], f["lanes"], n["w"]) == n["lane"], n["id"]
    boxes = [(n["x"], n["y"], n["x"] + n["w"], n["y"] + n["h"], n["id"]) for n in f["nodes"]]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a[4], b[4])
    by = {n["id"]: n for n in f["nodes"]}
    eng, ref = by["cross_engine"], by["refmatch"]
    assert eng["y"] < ref["y"] + ref["h"] / 2 < eng["y"] + eng["h"]  # ref-design matching level with the engine


def test_a_saved_old_store_kind_falls_back():
    f = df.load()
    saved = {"nodes": [dict(n, kind="store") if n["id"] == "importers" else n for n in f["nodes"]],
             "edges": f["edges"], "notes": [],
             "base": {"nodes": [n["id"] for n in f["nodes"]], "edges": []}}  # fmt: skip
    assert next(n for n in df.merged(f, saved)["nodes"] if n["id"] == "importers")["kind"] == "step"


def test_page_draws_three_columns_brackets_bundle_and_handovers(owner):
    html = owner.get("/manage/data-flow").text
    assert "Two separate processes" in html and "Handover between the processes" in html
    data = _chart(html)
    assert [(x["label"], x["subtitle"]) for x in data["lanes"]] == [
        ("1 · Inputs", ""), ("2 · Cross process", "a part number → a checked cross"),
        ("3 · Research process", "sources and comments → reports you confirm")]  # fmt: skip
    nodes = {n["id"]: n for n in data["state"]["nodes"]}
    assert nodes["patents"]["group"] == "research" and nodes["importers"]["kept"].startswith("data/real/")
    assert "rows" not in data
    js = (ROOT / "app/web/static/data_flow.js").read_text()
    assert "bracket" in js and "bundle" in js and "isBundled" in js and '" handover"' in js
    # labels: a handover's always, any other line's only when it or one of its boxes is tapped
    assert "it.e.handover || hl" in js
