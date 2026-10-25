"""Reference-design matching, a bit stricter and then based on feedback (owner, 25 Oct 2026: "Should be based on
feedback. So a bit stricter at first"): stricter constants, the owner's Fits / Doesn't fit on a diagram's list,
dismissed suggestions, the inbox section."""

from datetime import UTC, datetime

from app.models import DataReview
from app.services import blocks, inbox, refmatch

TRACTION = "ev-traction-inverter"


def _tpl_index(key: str) -> int:
    return next(i for i, t in enumerate(blocks.templates()) if refmatch.diagram_key(t) == key)


def _answer(c, diagram, item, verdict, comment=""):
    return c.post("/reference-designs/feedback", data={"diagram": diagram, "item": item, "verdict": verdict,
                                                       "comment": comment, "back": "/blocks"},
                  follow_redirects=False)  # fmt: skip


def test_stricter_constants_are_in_effect():
    assert refmatch.TITLE_SHARE == 0.70 and (refmatch.MIN_SHARED, refmatch.MIN_SHARED_FULL) == (3, 2)
    assert (refmatch.SUGGEST_SHARE, refmatch.MIN_DESIGNS_FOR_SUGGESTIONS) == (0.40, 4)
    assert (refmatch.ADD_SHARE, refmatch.ADD_MIN) == (0.60, 8)
    # a loose match from before: TI's dual 15 V isolated bias supply (PMP22992) counted for the EV traction inverter
    # with only two shared functions (isolated DC/DC, wide-Vin buck); now it needs three
    e = refmatch.data()["by_key"][TRACTION]
    assert "TI:PMP22992.1" not in e["designs"]
    t = blocks.templates()[_tpl_index(TRACTION)]
    d = refmatch.index()["by_key"]["TI:PMP22992.1"]
    assert len(set(blocks.template_functions(t)) & set(d["functions"])) == 2
    assert refmatch.match([t], [d], blocks.template_functions) == [[]]
    # the suggestions in the file follow the new thresholds
    for x in refmatch.data()["diagrams"]:
        for s in x["suggested"]:
            assert x["n"] >= 4 and s["n"] / x["n"] >= 0.40


def test_owner_marks_doesnt_fit_and_the_design_leaves_the_diagram(client, session):
    raw = refmatch.data()["by_key"][TRACTION]
    a = raw["anchors"][0]
    k = a["designs"][0]
    assert _answer(client, TRACTION, k, "nofit", "power-only board").status_code == 303
    e = refmatch.entry(TRACTION)
    assert e["n"] == raw["n"] - 1 and k not in e["designs"] and e["removed"] == [k]
    for f in refmatch.index()["by_key"][k]["functions"]:  # function shares recomputed without it
        assert e["functions"].get(f, 0) == raw["functions"][f] - 1
    for x in e["anchors"]:
        assert k not in x["designs"] and x["n"] == len(x["designs"]) > 0
    na = next((x["n"] for x in e["anchors"] if x["part"] == a["part"]), 0)
    assert na == a["n"] - 1
    for s in e["suggested"]:
        assert s["n"] == e["functions"][s["fn"]] and s["n"] / e["n"] >= refmatch.SUGGEST_SHARE
    # the list: count and cards without it, listed under "Removed"
    lst = client.get(f"/reference-designs?diagram={TRACTION}").text
    assert f"<b>{raw['n'] - 1}</b> public reference designs" in lst
    assert lst.count('class="rd-card"') == raw["n"] - 1 and "0 confirmed by you, 1 removed" in lst
    assert 'id="rd-removed"' in lst
    anc = client.get(f"/reference-designs?diagram={TRACTION}&anchor={a['part']}").text
    assert anc.count('class="rd-card"') == a["n"] - 1
    # the diagram
    page = client.get(f"/blocks/new?template={_tpl_index(TRACTION)}").text
    assert f"{raw['n'] - 1} public reference designs</a>" in page and "0 confirmed by you, 1 removed" in page
    # Fits on another design: confirmed, with the review history under it
    k2 = e["designs"][0]
    assert _answer(client, TRACTION, k2, "fits", "right application").status_code == 303
    lst = client.get(f"/reference-designs?diagram={TRACTION}").text
    assert "✓ Fits · confirmed by you" in lst and "1 confirmed by you, 1 removed" in lst
    assert "right application" in lst
    assert refmatch.entry(TRACTION)["fits"] == [k2]
    # put back: the latest answer wins
    assert _answer(client, TRACTION, k, "reset").status_code == 303
    assert refmatch.entry(TRACTION)["n"] == raw["n"]
    assert session.query(DataReview).filter_by(dataset="refmatch").count() == 3  # append-only


def test_suggestion_can_be_dismissed(client):
    raw = refmatch.data()["by_key"][TRACTION]
    fn = raw["suggested"][0]["fn"]
    i = _tpl_index(TRACTION)
    assert "Not a block for this diagram" in client.get(f"/blocks/new?template={i}").text
    assert _answer(client, TRACTION, f"fn:{fn}", "nofit").status_code == 303
    e = refmatch.entry(TRACTION)
    assert fn not in [s["fn"] for s in e["suggested"]] and e["n"] == raw["n"]
    assert "Not suggested any more" in client.get(f"/blocks/new?template={i}").text
    kb = refmatch.kb_view(blocks.templates()[i], {})
    assert fn not in [s[0] for s in kb["suggested"]] and kb["fn_out"][0][0] == fn
    assert _answer(client, TRACTION, f"fn:{fn}", "reset").status_code == 303
    assert fn in [s["fn"] for s in refmatch.entry(TRACTION)["suggested"]]


def test_unknown_items_are_refused(client):
    assert _answer(client, "no-such-diagram", "TI:X", "nofit").status_code == 404
    assert _answer(client, TRACTION, "TI:NOT-MATCHED", "nofit").status_code == 404
    assert _answer(client, TRACTION, "fn:not_a_function", "nofit").status_code == 404


def test_guest_cannot_answer_owner_can(owner, make_guest):
    k = refmatch.data()["by_key"][TRACTION]["designs"][0]
    g, _ = make_guest()
    assert _answer(g, TRACTION, k, "nofit").status_code == 403
    assert "Doesn't fit</button>" not in g.get(f"/reference-designs?diagram={TRACTION}").text  # no buttons
    assert refmatch.entry(TRACTION)["n"] == refmatch.data()["by_key"][TRACTION]["n"]
    assert "Doesn't fit</button>" in owner.get(f"/reference-designs?diagram={TRACTION}").text
    assert _answer(owner, TRACTION, k, "nofit").status_code == 303
    assert k in refmatch.entry(TRACTION)["removed"]


def test_inbox_has_a_reference_design_feedback_section(client, session):
    k = refmatch.data()["by_key"][TRACTION]["designs"][0]
    assert _answer(client, TRACTION, k, "nofit", "only the bias supply").status_code == 303
    text = inbox.collect(session, datetime.now(UTC).date())
    sec = text.split("## Reference design feedback")[1].split("\n## ")[0]
    assert f"Doesn't fit: EV traction inverter / {k}" in sec and "only the bias supply" in sec
    assert "refmatch /" not in text  # not repeated under the general review answers
