"""Turn a research file (data/blocks/research/*.yaml: applications with groups, fn_hint, links, features) into
block-diagram templates appended to data/blocks/templates.yaml.

  uv run python tools/research_to_templates.py data/blocks/research/ti_block_diagrams.yaml "TI" category-map.yaml

Groups whose fn_hint is empty become an 'external_block' carrying the group label. Features become design
questions that are recorded only (no requirement is set; nothing is assumed). Templates already present (same
name) are skipped, so the script can be re-run.
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
FN = yaml.safe_load((ROOT / "data/blocks/functions.yaml").read_text())["functions"]
TEMPLATES = ROOT / "data/blocks/templates.yaml"


def convert(app: dict, docs: dict, vendor: str, category: str) -> dict:
    groups, ids = [], set()
    for g in app["groups"]:
        sock = g.get("socket_fn") or []
        hints = [*(g.get("fn_hint") or []), *(sock if isinstance(sock, list) else [sock])]
        fns = [str(h).split(" (")[0] for h in hints]
        fns = list(dict.fromkeys(f for f in fns if f in FN))
        blocks = fns or [{"fn": "external_block", "label": g["label"]}]
        groups.append({"id": g["id"], "label": g["label"], "blocks": blocks})
        ids.add(g["id"])
    per_row = 4 if len(groups) > 8 else 3
    for i, g in enumerate(groups):
        g["col"], g["row"] = i % per_row, i // per_row
    links = [[a, b, str(lab or "")] for a, b, *rest in app.get("links") or [] for lab in [rest[0] if rest else ""]
             if a in ids and b in ids]  # fmt: skip
    questions = []
    for f in app.get("features") or []:
        choices = [("yes" if c is True else "no" if c is False else str(c)) for c in f.get("choices") or []]
        if choices:
            questions.append({"id": f["id"], "question": str(f["question"]).rstrip("?"), "choices": choices,
                              "source": str(f.get("source", ""))[:160]})  # fmt: skip
    srcs = []
    for s in app.get("sources") or []:
        d = docs.get(s.get("doc"), {})
        srcs.append(
            {"doc": s.get("doc"), "title": d.get("title", s.get("doc")), "url": s.get("url") or d.get("url", "")}
        )
    name = re.sub(r"\s+", " ", app["name"])
    return {"name": f"{name} ({vendor})", "category": category, "note": f"From {vendor} public material: "
            + ", ".join(s["doc"] for s in srcs if s.get("doc"))[:200], "sources": srcs, "groups": groups,
            "links": links, "questions": questions}  # fmt: skip


def main(path: str, vendor: str, cats: dict) -> None:
    research = yaml.safe_load(Path(path).read_text())
    existing = {t["name"] for t in yaml.safe_load(TEMPLATES.read_text())}
    out = []
    for app in research["applications"]:
        t = convert(app, research.get("docs") or {}, app.get("vendor") or vendor, cats.get(app["id"], "Other"))
        if t["name"] not in existing:
            out.append(t)
    if out:
        text = yaml.safe_dump(out, sort_keys=False, allow_unicode=True, width=200, default_flow_style=None)
        with TEMPLATES.open("a") as fh:
            src = Path(path).resolve().relative_to(ROOT)
            fh.write(f"\n# ---- converted from {src} by tools/research_to_templates.py\n{text}")
    print(f"{len(out)} templates added")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], yaml.safe_load(Path(sys.argv[3]).read_text()) if len(sys.argv) > 3 else {})
