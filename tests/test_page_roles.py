"""Clearer page roles (owner, 2 Nov 2026): a "where am I" strip on the Systems library, a deep dive, the Block diagram
library (and a diagram opened from it) and the workspace; breadcrumbs with a link to the other view of the same
sub-system on deep dives and diagrams; "Application library" renamed "Block diagram library" (the URL stays /blocks)."""

import re

from app.services import library
from app.services import systems as sy
from app.web import nav

STEPS = ("Systems library", "Deep dive", "Block diagrams", "Your workspace")
WHAT = {
    "Systems library": "The map of systems and the sub-systems they are made of.",
    "Deep dive": "A written explainer for one sub-system: how it works, our block diagram, design rules, trends, where "
    "our and Qorvo&#39;s parts sit, competitors, market and references.",
    "Block diagrams": "Real block diagrams from public sources, with their blocks, candidate parts and coverage.",
    "Your workspace": "Your own diagrams, to build, edit and save.",
}


def strip(html: str) -> str:
    assert html.count('<nav class="where"') == 1
    return html.split('<nav class="where"')[1].split("</nav>")[0]


def current(html: str) -> str:
    """The highlighted step's label."""
    s = strip(html)
    assert s.count('aria-current="page"') == 1
    return re.search(r'aria-current="page"><b>\d</b> ([^<]+)</span>', s).group(1)


def crumbs(html: str) -> list[str]:
    return [c.split("</nav>")[0] for c in html.split('<nav class="crumbs small" aria-label="Breadcrumb">')[1:]]


def first(n: int) -> tuple[int, dict, dict]:
    """A library diagram in a sub-system with n deep dives (n = 0, 1 or several), with its system and sub-system."""
    for s in sy.systems():
        for x in s["subsystems"]:
            if (len(x["topics"]) > 1 if n > 1 else len(x["topics"]) == n) and x["idx"]:
                i = next(i for i in x["idx"] if len(sy.place_of(i)) == 1)
                return i, s, x
    raise AssertionError(n)


def test_the_strip_names_the_step_and_what_the_page_shows(client):
    i, _, _ = first(1)
    pages = {"/library": "Systems library", "/library/auto_uwb": "Deep dive", "/blocks": "Block diagrams",
             f"/blocks/new?template={i}": "Block diagrams", "/blocks/new": "Your workspace"}  # fmt: skip
    for path, step in pages.items():
        html = client.get(path).text
        s = strip(html)
        assert current(html) == step, path
        assert [re.sub(r"<[^>]+>|\d", "", x).strip() for x in re.findall(r"<li[^>]*>(.*?)</li>", s)] == list(STEPS)
        assert f'<p class="where-what">{WHAT[step]}</p>' in s, path
        assert html.index('<nav class="where"') < html.index("<h1"), path  # at the top
    lib = strip(client.get("/blocks").text)
    assert '<a href="/library"><b>1</b> Systems library</a>' in lib and '<a href="/blocks/new"><b>4</b>' in lib
    assert '<span class="where-off"><b>2</b> Deep dive</span>' in lib  # no single deep dive to point at here


def test_the_strip_is_one_include_on_the_four_pages():
    from app.config import PROJECT_ROOT

    root = PROJECT_ROOT / "app" / "web" / "templates"
    users = sorted(p.relative_to(root).as_posix() for p in root.rglob("*.html") if "where_strip(" in p.read_text())
    assert users == ["_where.html", "blocks/editor.html", "blocks/index.html", "library/index.html",
                     "library/topic.html"]  # fmt: skip


def test_bare_editor_has_no_strip_and_saved_diagram_is_the_workspace(client):
    i, _, _ = first(1)
    assert '<nav class="where"' not in client.get(f"/blocks/new?template={i}&bare=1").text
    r = client.post("/api/blocks/designs", json={"name": "Strip test", "data": {"groups": [], "links": []}})
    assert r.status_code == 200, r.text
    html = client.get(f"/blocks/{r.json()['id']}").text
    assert current(html) == "Your workspace" and not crumbs(html)


def test_deep_dive_breadcrumbs_and_its_block_diagrams(client):
    for t in library.topics():
        html = client.get(f"/library/{t['key']}").text
        place = sy.topic_place(t["key"])
        (c,) = crumbs(html)
        if not place:
            assert 'href="/library#sys-other"' in c
            continue
        s, x = sy.get(place[0]), sy.sub(*place)
        assert f'<a href="/library#sys-{s["key"]}">{s["title"]}</a>' in c.replace("&amp;", "&")
        assert f'href="/library#card-{s["key"]}-{x["key"]}"' in c and x["title"] in c.replace("&amp;", "&")
        link = f'/blocks?system={s["key"]}&amp;sub={x["key"]}#sub-{x["key"]}'
        assert f'href="{link}">▦ See its block diagrams ({len(x["idx"])})</a>' in c
        # the strip points its other steps at the same sub-system
        assert f'<a href="/library#sys-{s["key"]}"><b>1</b>' in strip(html) and f'href="{link}"><b>3</b>' in strip(html)
    other = [t["key"] for t in library.topics() if not sy.topic_place(t["key"])]
    if other:
        assert "Other deep dives" in crumbs(client.get(f"/library/{other[0]}").text)[0]


def test_diagram_breadcrumbs_and_its_deep_dives(client):
    titles = {t["key"]: t["title"] for t in library.topics()}
    for n in (0, 1, 2):
        i, s, x = first(n)
        html = client.get(f"/blocks/new?template={i}").text
        (c,) = crumbs(html)
        assert f'href="/blocks?system={s["key"]}#area-{s["key"]}">' in c
        assert f'href="/blocks?system={s["key"]}&amp;sub={x["key"]}#sub-{x["key"]}">' in c
        deep = [k for k in x["topics"] if k in titles]
        assert c.count('class="sys-btn sys-btn-deep"') == len(deep), (n, x["key"])
        assert ("📖 Read the deep dive<" in c) == (len(deep) == 1)
        for k in deep:
            assert f'href="/library/{k}"' in c
        if deep:  # the strip's Deep dive step opens the sub-system's (first) deep dive
            assert f'<a href="/library/{deep[0]}"><b>2</b> Deep dive</a>' in strip(html)
    many = [i for i in range(len(sy.blocks.templates())) if len(sy.place_of(i)) > 1]
    if many:
        assert len(crumbs(client.get(f"/blocks/new?template={many[0]}").text)) == len(sy.place_of(many[0]))
    assert not crumbs(client.get("/blocks/new").text)


def test_application_library_is_now_the_block_diagram_library(client):
    labels = [label for _, _, items in nav.NAV for label, _, _ in items]
    assert "Block diagram library" in labels and "Application library" not in labels
    assert "Application workspace" in labels  # the workspace keeps its name and URL
    html = client.get("/blocks").text
    assert "<h1>Block diagram library</h1>" in html and "<title>Block diagram library – " in html
    assert 'href="/blocks" title="Diagrams grouped by system and sub-system, with their coverage" aria-current="page"' \
        in html  # same URL
    for path in ("/blocks", "/library", "/library/auto_uwb", "/broadcast", "/blocks/new"):
        assert "Application library" not in client.get(path).text, path
