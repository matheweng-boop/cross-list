"""Interactive visuals in tabs (owner, 2 Nov 2026): RF & wireless · Power & isolation · Basics, one closed drop-down
line per sub-group, a search box, deep links kept. The mapping is the #vz-tabs block of the template; this checks that
every visual has its line (none falls to "More") and that "Isolation and power" is split by visual id."""

import json
import re

from app.config import PROJECT_ROOT
from app.services import library

STATIC = PROJECT_ROOT / "app" / "web" / "static"
STRUCTURE = {
    "RF & wireless": ["RF links", "Receivers", "Matching and filters", "Broadcast radio", "GNSS", "UWB", "Timing"],
    "Power & isolation": ["Isolation", "Power switching", "Circuits in motion"],
    "Basics": ["Digital basics"],
}


def registry() -> dict[str, str]:
    """Visual id -> its definition group, from visuals.js and the static/vz files (as test_growth reads them)."""
    js = "".join(p.read_text() for p in [STATIC / "visuals.js", *sorted((STATIC / "vz").glob("*.js"))])
    return dict(re.findall(r'id: "([a-z0-9]+)", group: "([^"]+)"', js))


def block(html: str, block_id: str):
    return json.loads(html.split(f'<script id="{block_id}" type="application/json">')[1].split("</script>")[0])


def placed(tabs: list[dict], reg: dict[str, str]) -> dict[str, tuple[str, str]]:
    """The same placement as the page code in visuals.js: listed ids first, then definition groups."""
    subs = [(t["label"], s) for t in tabs for s in t["subs"]]
    out: dict[str, tuple[str, str]] = {}
    for tab, s in subs:
        for i in s.get("ids", []):
            if i in reg and i not in out:
                out[i] = (tab, s["label"])
    for i, group in reg.items():
        hit = next(((tab, s["label"]) for tab, s in subs if group in s.get("groups", [])), None)
        if i not in out and hit:
            out[i] = hit
    return out


def test_tabs_and_lines_as_the_owner_asked(client):
    html = client.get("/visuals").text
    tabs = block(html, "vz-tabs")
    assert {t["label"]: [s["label"] for s in t["subs"]] for t in tabs} == STRUCTURE
    reg = registry()
    assert len(reg) >= 35
    where = placed(tabs, reg)
    assert set(where) == set(reg), set(reg) - set(where)  # every visual has a line: nothing falls to "More"
    line = lambda name: {i for i, (_, s) in where.items() if s == name}  # noqa: E731
    assert line("Isolation") == {"cmti", "creep", "emc"}
    assert line("Power switching") >= {"gate", "thermal", "swloss", "turnon"}
    assert len(line("Circuits in motion")) == 6
    assert {"fmim", "mod", "flow", "rds", "dab"} <= line("Broadcast radio")
    assert {"dbm", "link", "wave"} <= line("RF links") and {"nf", "ip3"} <= line("Receivers")
    assert where["hex"] == ("Basics", "Digital basics") and where["jitter"] == ("RF & wireless", "Timing")
    assert where["uwb"] == ("RF & wireless", "UWB") and len(line("GNSS")) == 4


def test_page_has_tabs_search_and_keywords(client):
    html = client.get("/visuals").text
    assert 'id="vz-tabbar"' in html and 'role="tablist"' in html and 'id="vz-q"' in html and 'id="vz-hits"' in html
    assert 'class="vz-hint"' in html  # no visual until one is picked or linked
    words = block(html, "vz-words")
    assert "VSWR" in words["vswr"] and "jitter" in words["jitter"]
    # every visual the other pages link to (library.VISUALS) is on the page under a line
    reg = registry()
    assert {k for k in library.VISUALS if k != "rf-bands"} <= set(reg)
    js = (STATIC / "visuals.js").read_text()
    assert 'JSON.parse($("#vz-tabs").textContent)' in js and "reveal(id)" in js and "hashchange" in js
