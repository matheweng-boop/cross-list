"""Future growth > Automotive focus (owner, 3 Nov 2026): six goals, short to long term, every "why" number taken live
from the page it links to (Automotive map, Cross-sell, reference designs, research cases, TAM, Systems library)."""

from app.services import auto_focus as af
from app.services import automotive as au
from app.services import blocks, refmatch, reports, tam
from app.services import systems as sy
from app.web import nav


def _goals(session) -> dict[str, dict]:
    return {g["id"]: g for g in af.build(session)["goals"]}


def test_six_goals_cover_the_horizons_and_the_three_angles(session):
    gs = af.build(session)["goals"]
    assert [g["id"] for g in gs] == ["sell_now", "anchors", "qualify", "variant", "draw", "gaps"]
    assert [g["n"] for g in gs] == [1, 2, 3, 4, 5, 6]
    assert {g["horizon"] for g in gs} == {"short", "mid", "long"}
    assert [g["horizon"] for g in gs] == sorted((g["horizon"] for g in gs), key=["short", "mid", "long"].index)
    assert {g["angle"] for g in gs} == {"a", "b", "c"}  # place parts, new components, other markets
    for g in gs:
        assert g["goal"] and g["title"] and "est" in g["effort"], g["id"]
        assert len(g["steps"]) <= 3 and (g["why"] or g.get("missing")), g["id"]
        assert all(x["href"] and x["src"] for x in g["why"]), g["id"]


def test_why_numbers_match_their_sources(session):
    m, g = au.build(session), _goals(session)
    live = [c for c in m["cells"].values() if c["status"] != "rejected"]
    a = g["sell_now"]["why"]
    assert a[0]["n"] == m["counts"]["A"] == sum(c["level"] == "A" for c in live)
    if len(a) > 1 and a[1]["src"] == "Automotive map":
        by = {}
        for c in live:
            if c["level"] == "A":
                by[c["fn"]] = by.get(c["fn"], 0) + 1
        assert a[1]["n"] == max(by.values())
    q = g["qualify"]
    b = [x for x in m["moves"] if x["level"] == "B"]
    if b:
        assert q["why"][0]["n"] == (b[0]["opp"] or {}).get("score") and q["why"][1]["n"] == m["counts"]["B"]
    gp = g["gaps"]["why"][0]
    assert gp["n"] == m["counts"]["gap"] == sum(c["level"] == "gap" for c in live)
    lib, idx = blocks.templates(), af.car_diagrams()
    an = refmatch.anchors_for([lib[i] for i in idx], blocks.counts(session))
    if an:
        assert g["anchors"]["why"][0]["n"] == len(an) and g["anchors"]["why"][1]["n"] == an[0]["n"]
    else:
        assert g["anchors"]["missing"]
    v = g["variant"]
    if not v.get("missing"):
        r = reports.report(v["links"][0]["href"].rsplit("/", 1)[1])
        assert v["why"][1]["n"] == r["feasibility"] and len(v["steps"]) == len((r.get("next_steps") or [])[:3])
    tams = tam.by_function(session)
    for x in (x for g_ in g.values() for x in g_["why"] if x["tam"]):
        assert x["n"] in {t["usd"] for t in tams.values()}


def test_draw_table_counts_the_other_systems(session):
    f = af.build(session)
    named = set(_goals(session)["qualify"].get("fns", ())) | set(_goals(session)["variant"].get("fns", ()))
    for r in f["draw"]:
        assert r["fn"] not in named and r["level"] in ("B", "C") and "est" in r["take"]
        want = [s for s in sy.systems_of_function(r["fn"]) if s["key"] != "automotive"][:2]
        assert [(s["title"], s["n"]) for s in r["source"]] == [(s["title"], s["n"]) for s in want]


def test_page_renders_the_cards_the_table_and_the_fold(client):
    html = client.get("/business/automotive-focus").text
    assert "<h1>Automotive focus</h1>" in html
    assert "<title>Automotive focus – Future growth – BizDev</title>" in html
    assert html.count('class="af-card') == 6
    for h in af.HORIZON.values():
        assert h in html
    assert '<details class="af-how small" id="af-how"><summary>How these were picked</summary>' in html
    assert 'id="ae-draw"' in html and "Which markets to draw new car parts from" in html
    assert 'aria-current="page" class="on">Automotive focus<' in html


def test_menu_lists_future_growth_exactly():
    growth = next(items for key, _, items in nav.NAV if key == "growth")
    assert [(label, href) for label, href, _ in growth] == [
        ("Research & ideas", "/business/reports"), ("Automotive focus", "/business/automotive-focus"),
        ("Markets & customers", "/business/markets"), ("Shortlist & cases", "/business/shortlist"),
        ("TAM estimates", "/business/tam")]  # fmt: skip


def test_a_rejected_call_leaves_the_goals(client, session):
    c = next(c for c in au.build(session)["cells"].values() if c["level"] == "gap" and c["status"] == "proposed")
    before = _goals(session)["gaps"]["why"][0]["n"]
    client.post("/business/automotive/review", data={"cell": c["key"], "verdict": "reject"})
    from sqlalchemy.orm import Session

    from app.db import get_engine

    with Session(get_engine()) as s:
        assert _goals(s)["gaps"]["why"][0]["n"] == before - 1
    client.post("/business/automotive/review", data={"cell": c["key"], "verdict": "reset"})


def test_guest_sees_the_goals_without_tam(make_guest, owner):
    g, _ = make_guest()
    html = g.get("/business/automotive-focus").text
    assert html.count('class="af-card') == 6 and 'href="/business/tam"' not in html
