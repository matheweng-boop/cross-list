"""Questions to ask per segment (owner, 9 Nov 2026; app/services/segment_questions.py): every system and sub-system of
the Systems library has questions to the customer, to the customer's developers and to our business unit, each with the
answer box of the report questions (internal / can-be-shared switch, the reminder, history, guest rules). Answers are
stored under the slug seg:<system>[/<sub-system>] and appear in Data management › Answers with a segment filter."""

import html
import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app import yamlio
from app.models import Answer, ExternalSubmission
from app.services import answers, systems
from app.services import reports as rp
from app.services import segment_questions as sq

SYS, SUB = "automotive", "charging"
KEY = f"{SYS}/{SUB}"
SLUG = sq.slug_of(KEY)
WARN = "Don't record confidential figures or plans; summarise instead"
BANNED = re.compile(r"\b(exact|precise) (volumes?|prices?|figures?)\b|\byour (prices?|margins?|revenue|forecast)\b"
                    r"|\bconfidential\b|\bcustomer names?\b", re.I)  # fmt: skip


def _q(key=KEY, group="customer"):
    return next(q for q in sq.questions(key) if q["group"] == group)


def _add(client, key, qid, text, who="", sharing="internal"):
    system, _, sub = key.partition("/")
    data = {"key": qid, "text": text, "who": who, "sharing": sharing, "sub": sub}
    r = client.post(f"/library/questions/{system}/answers", data=data, follow_redirects=False)
    assert r.status_code == 303, r.text
    return int(re.search(r"saved=(\d+)", r.headers["location"]).group(1))


def _page(client, key=KEY):
    return html.unescape(client.get(sq.href(sq.slug_of(key))).text)


# ---- the questions ---------------------------------------------------------------------------------------------------
def test_every_system_and_sub_system_has_questions_in_all_three_groups():
    raw = yamlio.load(sq.FILE.read_text())["segments"]
    keys = {s["key"] for s in sq.segments()}
    assert set(raw) == keys, "one set per system and sub-system of systems.yaml, nothing else"
    assert len(keys) == len(systems.systems()) + sum(len(s["subsystems"]) for s in systems.systems())
    for s in sq.segments():
        qs = sq.questions(s["key"])
        ids, texts = [q["id"] for q in qs], [q["text"].strip().lower() for q in qs]
        assert len(ids) == len(set(ids)), f"duplicate id in {s['key']}"
        assert len(texts) == len(set(texts)), f"duplicate question in {s['key']}"
        for g, _ in sq.GROUPS:
            n = sum(q["group"] == g for q in qs)
            assert n >= (4 if s["sub"] else 3) and n <= 6, (s["key"], g, n)
        for q in qs:
            assert q["text"].endswith("?") and q["why"], (s["key"], q["id"])
            assert not BANNED.search(q["text"]), (s["key"], q["text"])  # neutral: never asks for confidential data
            assert "data centre" not in q["text"].lower()
        for slug in raw[s["key"]].get("reports") or []:
            assert rp.report(slug) is not None, (s["key"], slug)


def test_report_questions_are_linked_not_repeated():
    for s in sq.segments():
        mine = {q["text"].strip().lower() for q in sq.questions(s["key"])}
        for r in sq.reports(s["key"]):
            theirs = {q["text"].strip().lower() for q in answers.questions(r["slug"])}
            assert not mine & theirs, (s["key"], r["slug"])
    assert [r["slug"] for r in sq.reports(KEY)][:2] == ["auto-charging-power", "iso-current-sense-charging"]


# ---- pages and the answer box ----------------------------------------------------------------------------------------
def test_sub_system_page_shows_three_tabs_with_answer_boxes(client):
    page = _page(client)
    sec = page.split('id="questions-to-ask"', 1)[1]
    assert "<details" in page.split('id="questions-to-ask"', 1)[0][-200:]
    for key, label in sq.TABS.items():
        assert f'data-sq="{key}"' in sec and f">{label} <small>" in sec
    q = _q(group="developers")
    box = sec.split(f'id="i-{q["id"]}"', 1)[1][:3000]
    assert WARN in box and "<textarea" in box and 'name="who"' in box and f'value="{SUB}"' in box
    assert "🔒 Internal only" in box and "✅ Can be used for research (inbox)" in box
    assert 'action="/library/questions/automotive/answers"' in box
    assert "Why we ask:" in sec and "/business/reports/auto-charging-power#questions-to-ask" in page
    system = _page(client, SYS)
    assert "/library/questions/automotive/charging" in system and 'id="questions-to-ask"' in system
    lib = client.get("/library").text
    assert "/library/questions/automotive/charging" in lib and "/library/questions/automotive" in lib
    assert client.get("/library/questions/automotive/nope").status_code == 404
    assert client.get("/library/questions/nope").status_code == 404


def test_deep_dive_shows_its_sub_system_questions_folded_at_the_bottom(client):
    """Owner, 9 Nov 2026: "Put the questions at the bottom of each sub-system": after the references, the last thing;
    "Question should be foldable": folded until opened."""
    page = html.unescape(client.get("/library/dc_timing").text)
    before, sec = page.split('id="questions-to-ask"', 1)
    assert "<details" in before[-60:] and sec.startswith(">")
    assert before.index('id="refs"') < len(before) and 'href="#questions-to-ask"' in before
    assert _q("datacenter/networking")["text"] in sec  # dc_timing sits first in networking
    assert "/library/questions/datacenter/networking" in sec
    assert "<h2" not in sec.split("</details>")[-1]  # nothing after it but the "all questions" link


def test_block_diagram_library_shows_the_picked_sub_systems_questions_at_the_bottom(client):
    page = html.unescape(client.get(f"/blocks?system={SYS}&sub={SUB}").text)
    assert page.count('id="questions-to-ask"') == 1
    before, sec = page.split('id="questions-to-ask"', 1)
    assert before.rindex('id="sub-charging"') < before.rindex("Cross-sell in")  # after its diagrams and cross-sell
    assert sec.startswith(">")  # folded (owner, 9 Nov 2026)
    assert "Questions to ask: " in sec[:400] and _q()["text"] in sec and _q(group="bu")["text"] in sec
    assert f'name="back" value="/blocks?system={SYS}&sub={SUB}"' in sec
    # only the picked sub-system's: no other segment's questions, and none without a pick
    other = _q(next(f"{SYS}/{x['key']}" for x in systems.get(SYS)["subsystems"] if x["key"] != SUB))["text"]
    assert other not in page
    for url in ("/blocks", f"/blocks?system={SYS}", "/library"):
        assert 'id="questions-to-ask"' not in client.get(url).text, url
    assert "/library/questions/automotive/charging" in client.get("/library").text  # the button stays there
    # every sub-system gets its own
    for s in systems.systems():
        for x in s["subsystems"][:1]:
            p = html.unescape(client.get(f"/blocks?system={s['key']}&sub={x['key']}").text)
            assert sq.questions(f"{s['key']}/{x['key']}")[0]["text"] in p, (s["key"], x["key"])


def test_an_answer_saved_at_the_bottom_comes_back_to_that_page(client, session):
    back = f"/blocks?system={SYS}&sub={SUB}&saved=1"
    r = client.post("/library/questions/automotive/answers", follow_redirects=False,
                    data={"key": _q()["id"], "sub": SUB, "text": "Back to blocks", "back": back})  # fmt: skip
    loc = r.headers["location"]
    assert r.status_code == 303 and loc.startswith(f"/blocks?system={SYS}&sub={SUB}&saved=") and "saved=1&" not in loc
    assert loc.endswith(f"#i-{_q()['id']}") and "Back to blocks" in client.get(loc.split("#")[0]).text
    r = client.post("/library/questions/automotive/answers", follow_redirects=False,
                    data={"key": _q()["id"], "sub": SUB, "text": "No back", "back": "//evil.example"})  # fmt: skip
    assert r.headers["location"].startswith("/library/questions/automotive/charging?saved=")


def test_cross_sell_has_no_questions(client):
    """Owner, 9 Nov 2026: "do not include question on the cross sell"."""
    for url in (f"/blocks/cross-sell?system={SYS}&sub={SUB}", f"/blocks/cross-sell?system={SYS}"):
        page = html.unescape(client.get(url).text)
        assert 'id="questions-to-ask"' not in page and _q()["text"] not in page, url


def test_an_answer_to_a_segment_question_works_like_a_report_answer(client, session):
    q = _q()
    aid = _add(client, KEY, q["id"], "SEG-1101 they use shunts with isolated amplifiers", who="Charger maker")
    a = session.get(Answer, aid)
    assert (a.slug, a.question, a.sharing, a.question_text) == (SLUG, q["id"], "internal", q["text"])
    page = _page(client)
    card = page.split(f'id="ans-{aid}"', 1)[1][:4000]
    assert "SEG-1101" in card and "Charger maker" in card and f"/manage/answers/{aid}/sharing" in card
    # switch and edit keep the history and return to the segment page
    r = client.post(f"/manage/answers/{aid}/sharing", data={"sharing": "shared"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/library/questions/automotive/charging")
    client.post(f"/manage/answers/{aid}/edit", data={"text": "SEG-1101 edited", "who": "", "sharing": "shared"})
    assert "Earlier versions (2)" in _page(client)
    # the system's own questions take no sub-system
    sys_q = _q(SYS, "bu")
    aid2 = _add(client, SYS, sys_q["id"], "SEG-1102 system level")
    assert session.get(Answer, aid2).slug == "seg:automotive"
    # unknown question or segment
    assert client.post("/library/questions/automotive/answers", data={"key": "nope", "text": "x", "sub": SUB}
                       ).status_code == 404  # fmt: skip
    assert client.post("/library/questions/automotive/answers", data={"key": q["id"], "text": "x", "sub": "nope"}
                       ).status_code == 404  # fmt: skip
    assert client.post("/library/questions/automotive/answers", data={"key": q["id"], "text": " ", "sub": SUB}
                       ).status_code == 400  # fmt: skip


# ---- internal vs shareable -------------------------------------------------------------------------------------------
def test_guests_never_see_internal_or_held_segment_answers(owner, make_guest, session):
    q, q2 = _q(), _q(group="bu")
    internal = _add(owner, KEY, q["id"], "SEG-INT-7731 stays with the owner", who="Secret Person")
    _add(owner, KEY, q["id"], "SEG-SHR-4410 may be shared", who="Named Person", sharing="shared")
    held = _add(owner, KEY, q2["id"], "SEG-HELD-5521 confidential numbers", sharing="shared")
    assert answers.is_held(session.get(Answer, held))
    assert all(t in _page(owner) for t in ("SEG-INT-7731", "SEG-SHR-4410", "SEG-HELD-5521", "Secret Person"))
    guest, _ = make_guest("Anna Guest")
    page = _page(guest)
    assert "SEG-SHR-4410" in page
    for hidden in ("SEG-INT-7731", "SEG-HELD-5521", "Secret Person", "Named Person", "Earlier versions",
                   "/manage/answers"):  # fmt: skip
        assert hidden not in page, hidden
    assert "🔒 Internal only" not in page and WARN in page  # the reminder stays, the switch is the owner's
    assert guest.post(f"/manage/answers/{internal}/sharing", data={"sharing": "shared"}).status_code == 403


def test_a_guest_segment_answer_waits_for_review_and_lands_internal(owner, make_guest, session):
    from app.services import guest_input

    guest, _ = make_guest("Anna Guest")
    q = _q(group="developers")
    r = guest.post("/library/questions/automotive/answers", data={"key": q["id"], "text": "SEG-GUEST-8812 SiC next",
                                                                    "who": "Dev", "sharing": "shared", "sub": SUB},
                   follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and session.scalar(select(Answer.id)) is None
    sub = session.scalars(select(ExternalSubmission)).one()
    assert sub.kind == "Answer to a segment question"
    assert owner.post(f"/manage/guest-input/{sub.id}", data={"act": "approve"}, follow_redirects=False
                      ).status_code == 303  # fmt: skip
    session.expire_all()
    a = session.scalars(select(Answer)).one()
    assert (a.slug, a.sharing, a.author) == (SLUG, "internal", "Anna Guest")
    lines = "\n".join(guest_input.inbox_lines(session, datetime.now(UTC) - timedelta(days=1)))
    assert "SEG-GUEST-8812" not in lines and "kept internal" in lines


def test_inbox_names_the_segment_and_counts_internal_answers(client, session, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "inbox_token", "k" * 40)
    q, q2 = _q(), _q(group="developers")
    _add(client, KEY, q["id"], "SEG-INT-1203 do not use")
    _add(client, KEY, q2["id"], "SEG-SHR-3307 they plan 1000 V systems", who="Dev team", sharing="shared")
    text = client.get("/api/inbox", headers={"Authorization": "Bearer " + "k" * 40}).text
    section = text.split("## Questions to ask: answers", 1)[1].split("\n## ", 1)[0]
    assert "SEG-INT-1203" not in text
    assert "Internal answers (owner only, the text stays on the site): 1 new, 0 changed" in section
    assert f"{SLUG} (segment Automotive › Charging) / {q2['id']} (new)" in section
    assert "SEG-SHR-3307 they plan 1000 V systems" in section and "deep dive or block diagram" in section


def test_internal_segment_answers_are_in_no_shareable(client, session):
    _add(client, KEY, _q()["id"], "SEG-INT-6060 owner only", who="WHO-6060")
    for url in ("/shareable", "/shareable/automotive", "/shareable/pack", "/business/reports/questions.txt"):
        r = client.get(url)
        if r.status_code == 200:
            assert "SEG-INT-6060" not in r.text and "WHO-6060" not in r.text, url


# ---- the overview ----------------------------------------------------------------------------------------------------
def test_answers_overview_filters_by_segment(client, session):
    a1 = _add(client, KEY, _q()["id"], "SEG-OV charging one")
    _add(client, "datacenter/networking", _q("datacenter/networking")["id"], "SEG-OV timing one", sharing="shared")
    _add(client, KEY, _q(group="bu")["id"], "SEG-OV charging bu")
    all_ = html.unescape(client.get("/manage/answers").text)
    assert "SEG-OV charging one" in all_ and "SEG-OV timing one" in all_
    assert 'name="segment"' in all_ and "Segment questions (Systems library): 3 of" in all_
    assert f'href="/library/questions/automotive/charging#i-{_q()["id"]}"' in all_
    one = html.unescape(client.get("/manage/answers?segment=automotive/charging").text)
    assert "SEG-OV charging one" in one and "SEG-OV timing one" not in one
    opened = one.split('id="all-answers"', 1)[0]
    assert f"/library/questions/automotive/charging#i-{_q(group='developers')['id']}" in opened  # open, linked
    assert "/business/reports/" not in opened  # the open report questions are not mixed in
    system = html.unescape(client.get("/manage/answers?segment=automotive").text)
    assert "SEG-OV charging one" in system and "SEG-OV timing one" not in system  # a system includes its subs
    shared = html.unescape(client.get("/manage/answers?segment=datacenter&sharing=shared").text)
    assert "SEG-OV timing one" in shared and "SEG-OV charging" not in shared
    assert client.get("/manage/answers?segment=bogus").status_code == 200
    assert a1 in {a.id for a in answers.overview(session, segment=KEY)["answers"]}


def test_report_answers_keep_their_keys_and_pages(client, session):
    """The report and case questions are unchanged: same slugs, ids, form action and redirect."""
    r = client.post("/business/reports/filters-1-11ghz/answers", data={"key": "q-bu-passband", "text": "Still works"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"].startswith("/business/reports/filters-1-11ghz?saved=")
    a = session.scalars(select(Answer)).one()
    assert (a.slug, a.question) == ("filters-1-11ghz", "q-bu-passband")
    page = html.unescape(client.get("/business/reports/filters-1-11ghz").text)
    assert 'action="/business/reports/filters-1-11ghz/answers"' in page and 'name="sub"' not in page


# ---- owner, 9 Nov 2026: Data center regrouped; answers stored under a retired segment key follow their question ----
def test_answers_under_a_retired_segment_key_show_where_their_question_went(client, session):
    assert sq.moved()["datacenter/timing"][0] == "datacenter/networking"
    for old, new in sq.moved().items():
        assert sq.segment(old) is None and all(sq.segment(k) for k in new)
    assert {q["id"] for q in sq.questions("datacenter/server-board")} >= {"c-platform", "d-pcie7", "b-gen7"}
    assert {q["id"] for q in sq.questions("home/enterprise-wifi")} >= {"c-ap", "d-wifi7", "b-fem"}
    for key in ("datacenter/scale-up", "datacenter/nic-dpu"):  # new sets in the same three groups
        assert {q["group"] for q in sq.questions(key)} == {"customer", "developers", "bu"}
    assert not any("Taiwan" in q["text"] for q in sq.questions("datacenter"))  # owner: "do not talk about it"
    session.add_all([Answer(slug="seg:datacenter/timing", question="d-224g", text="SEG-MOVED-224G"),
                     Answer(slug="seg:datacenter/timing", question="d-pcie7", text="SEG-MOVED-GEN7"),
                     Answer(slug="seg:datacenter/network", question="c-ap", text="SEG-MOVED-AP")])  # fmt: skip
    session.commit()
    assert sq.home_of("datacenter/timing", "d-224g") == "datacenter/networking"
    assert sq.home_of("datacenter/timing", "d-pcie7") == "datacenter/server-board"
    net = client.get("/library/questions/datacenter/networking").text
    assert "SEG-MOVED-224G" in net and "SEG-MOVED-GEN7" not in net
    assert "SEG-MOVED-GEN7" in client.get("/library/questions/datacenter/server-board").text
    assert "SEG-MOVED-AP" in client.get("/library/questions/home/enterprise-wifi").text
    assert sq.title("seg:datacenter/timing") == "Data center › Front-end / back-end networking"
