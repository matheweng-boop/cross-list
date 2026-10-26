"""Data management › Data flow (owner, 26 Oct 2026): the chart from data/manage/data_flow.yaml, owner only; saves are
versions with Undo, compared with the file version into a change list for the daily inbox."""

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


def test_file_is_complete_and_consistent():
    f = df.load()
    assert [x["id"] for x in f["lanes"]] == ["sources", "processing", "stores", "outputs"]
    ids = [n["id"] for n in f["nodes"]]
    assert len(ids) == len(set(ids)) and all(df._ID.match(i) for i in ids)
    lanes = {x["id"] for x in f["lanes"]}
    assert all(n["lane"] in lanes and n["kind"] in df.KINDS and n["desc"] and n["link"] for n in f["nodes"])
    for e in f["edges"]:
        assert e["from"] in ids and e["to"] in ids, e
    # owner, 26 Oct 2026: all origins, in a few general categories, each with its plain list
    sources = [n for n in f["nodes"] if n["lane"] == "sources"]
    assert 6 <= len(sources) <= 8 and all(n["includes"] for n in sources)
    assert not any("http" in x or "www." in x for n in sources for x in n["includes"])  # no hosts on the chart
    assert {"public", "owner", "guest"} <= {n["kind"] for n in sources}
    assert any(n["gate"] for n in f["nodes"])
    # every store and output is reached from a source category
    into = {}
    for e in f["edges"]:
        into.setdefault(e["to"], set()).add(e["from"])
    src = {n["id"] for n in sources}
    for n in f["nodes"]:
        if n["lane"] in ("stores", "outputs"):
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
    for x in f["lanes"]:
        assert x["label"] in r.text
    for n in f["nodes"]:
        assert f'"id": "{n["id"]}"' in r.text  # in the chart data the page draws
    assert 'href="/manage/data-flow"' in r.text  # in the Data management menu
    assert "Changes since the file version" in r.text


def test_save_lists_changes_versions_and_undo(owner):
    f = df.load()
    p = _payload(f)
    p["nodes"][0]["x"] += 2 * df.LANE_W  # into another lane
    p["nodes"][1]["label"] = "Renamed source"
    p["nodes"].append({"id": "n-new1", "label": "My new step", "kind": "step", "x": 300, "y": 1200})
    p["edges"] = [e for e in p["edges"] if (e["from"], e["to"]) != ("patents", "data_business")]
    p["edges"].append({"from": "n-new1", "to": "inbox", "label": "my data"})
    p["nodes"] = [n for n in p["nodes"] if n["id"] != "telegram"]
    p["notes"] = [{"id": "t-1", "text": "Merge the two YAML stores?", "x": 10, "y": 10}]
    r = owner.post("/manage/data-flow/save", json=p)
    assert r.status_code == 200 and r.json()["ok"]
    texts = [c["text"] for c in r.json()["changes"]]
    first = f["nodes"][0]["label"]
    assert f"moved '{first}' to Stores" in texts
    assert f"renamed '{f['nodes'][1]['label']}' to 'Renamed source'" in texts
    assert "new node 'My new step' in Processing (processing)" in texts
    assert "new edge My new step→var/inbox (daily pull) 'my data'" in texts
    assert "deleted edge Patents & filings→data/business YAML (research) 'evidence'" in texts
    assert "deleted node 'Inbox summary / Telegram'" in texts
    assert not any(t.startswith("deleted edge Daily") for t in texts)  # an edge of a deleted node goes with it
    assert "free note near Sources: Merge the two YAML stores?" in texts
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
    mine = {"id": "n-mine", "label": "Mine", "kind": "step", "note": "", "x": 1, "y": 1, "lane": "sources"}
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
    assert "- free note near Stores: Combine both inboxes" in sec
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
