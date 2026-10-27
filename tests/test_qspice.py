"""QSPICE library (owner, 27 Oct 2026): forum design threads summarised in our own words, "Seen in practice" notes for
the block diagrams, how-tos, common fixes, models for our parts and the Ask box; plus Data management › AI services
(later). The forum is the owner's narrow exception to "never any qorvo.com host": its QSPICE category and topics only.
"""

import re
from datetime import date

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import yamlio
from app.config import PROJECT_ROOT
from app.db import get_engine
from app.models import ExternalSubmission, QspiceQuestion
from app.services import ai_services, blocks, digest, qspice

RAW = (PROJECT_ROOT / "data" / "library" / "qspice_forum.yaml").read_text()
D = yamlio.load(RAW)
NAME_FIELDS = {"user", "username", "author", "name", "poster", "handle", "avatar", "avatar_template", "signature",
               "email", "display_username", "posters", "user_id", "by"}  # fmt: skip


def _walk(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            yield path + "/" + str(k), k, v
            yield from _walk(v, f"{path}/{k}")
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _walk(v, f"{path}/{i}")


def _texts(x):
    if isinstance(x, str):
        yield x
    elif isinstance(x, dict):
        for v in x.values():
            yield from _texts(v)
    elif isinstance(x, list):
        for v in x:
            yield from _texts(v)


# ---- the data file -------------------------------------------------------------------------------------------------
@pytest.mark.smoke
def test_data_file_is_valid():
    fns = blocks.catalogue()["functions"]
    topics = D["topics"]
    assert 30 <= len(topics) <= 60
    assert len({t["id"] for t in topics}) == len(topics)
    for t in topics:
        assert {"id", "title", "url", "date", "fns", "circuit", "problem", "fix", "gist"} <= set(t), t["id"]
        assert t["fns"] and all(f in fns for f in t["fns"]), t["id"]
        assert date.fromisoformat(str(t["date"])) <= date(2026, 10, 27)
        for k in ("circuit", "problem", "fix"):
            assert isinstance(t[k], str) and t[k].strip(), (t["id"], k)
        # our own words, short: at most three sentences and no long passages
        assert len(re.findall(r"[.!?](?:\s|$)", t["fix"])) <= 3 and len(t["fix"]) <= 400, t["id"]
        assert digest.words(t["gist"]) <= digest.MAX_WORDS, t["id"]
    for n in D["practice"]:
        assert n["fn"] in fns and n["text"] and digest.words(n["gist"]) <= digest.MAX_WORDS, n["id"]
    assert all(m["model"] for m in D["models"]) and any(m["model"] == "Not in our data" for m in D["models"])


def test_no_user_names_handles_or_emails():
    for path, key, _ in _walk(D):
        assert str(key).lower() not in NAME_FIELDS, path
    for text in _texts(D):
        assert not re.search(r"(?<![\w.])@[A-Za-z_]\w*", text), text  # no @handles
        assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text), text  # no e-mails
    # names of the forum's regular helpers and posters seen while reading must not slip into the summaries
    body = RAW.split("\ntopics:", 1)[1].lower()
    for name in ("kelvin", "kskelvin", "physicboy", "macsky", "bordodynov", "engelhardt", "wiedmann", "basso",
                 "mohamed", "jari", "kiwanuka", "ankit", "thorsten", "jonas", "suded"):  # fmt: skip
        assert name not in body, name


def test_every_link_is_the_allowed_host_and_path():
    for t in D["topics"]:
        m = qspice.TOPIC_URL.match(t["url"])
        assert m and int(m.group(1)) == t["id"], t["url"]
    for h in D["help"]:
        assert h["links"] and all(qspice.TOPIC_URL.match(u) for u in h["links"]), h["id"]
    # any qorvo.com link anywhere in the file is the forum's QSPICE category or one of its topics
    for u in re.findall(r"https?://[^\s\"'),\]]+", RAW.split("\ntopics:", 1)[1]):
        if "qorvo.com" in u:
            assert qspice.TOPIC_URL.match(u) or u.startswith(qspice.CATEGORY_URL), u
    assert D["source"]["section"] == qspice.CATEGORY_URL


def test_notes_and_fixes_have_two_or_more_sources():
    ids = {t["id"] for t in D["topics"]}
    for n in [*D["practice"], *D["fixes"]]:
        assert len(set(n["topics"])) >= 2 and set(n["topics"]) <= ids, n["id"]
    for n in qspice.practice():
        assert len(n["threads"]) == len(n["topics"]) >= 2


def test_the_exception_is_recorded_with_its_limits():
    src = next(s for s in yamlio.load((PROJECT_ROOT / "data" / "library" / "sources.yaml").read_text())["sources"]
               if s["id"] == "qspice_forum")  # fmt: skip
    assert src["url"] == qspice.CATEGORY_URL and "27 Oct 2026" in src["access"]
    assert "Remove user names" in src["access"] and "Nothing else on any qorvo.com host" in src["access"]
    daily = (PROJECT_ROOT / "docs" / "daily_update.md").read_text()
    assert "QSPICE" in daily and "about 20 requests" in daily and "unanswered questions" in daily.lower()
    assert "data/manage/ai_services.yaml" in daily


# ---- the page, the block editor and To confirm ---------------------------------------------------------------------
@pytest.mark.smoke
def test_page_renders_with_filter_notes_help_and_models(client):
    html = client.get("/qspice").text
    assert "<h1>QSPICE library</h1>" in html and 'id="threads"' in html and 'id="practice"' in html
    assert 'id="fixes"' in html and 'id="help"' in html and 'id="models"' in html and "Not AI" in html
    assert html.count('class="qs-topic"') == len(D["topics"])
    assert "Not in our data" in html and "SMP1320" in html
    one = client.get("/qspice?fn=optocoupler").text
    n = len(qspice.topics("optocoupler"))
    assert one.count('class="qs-topic"') == n >= 2 and 'aria-current="true" class="qs-on">Optocoupler' in one
    assert "Seen in practice" in one and "3 threads" in one
    assert client.get("/qspice?fn=nope").text.count('class="qs-topic"') == len(D["topics"])  # unknown filter: all


def test_block_editor_and_evidence_show_practice_notes(client):
    html = client.get("/blocks/new").text
    assert 'id="bk-practice"' in html and "gate_driver" in html.split('id="bk-practice"')[1].split("</script>")[0]
    js = (PROJECT_ROOT / "app" / "web" / "static" / "blocks.js").read_text()
    assert "Seen in practice (QSPICE forum)" in js and "practiceLine(b.fn)" in js
    ev = client.get("/business/evidence/optocoupler")
    if ev.status_code == 200:  # the function page exists when the function is in an application
        assert "Seen in practice (QSPICE forum)" in ev.text


def test_to_confirm_items_for_threads_and_notes():
    rows = {r["key"]: r for r in digest.items()}
    for t in D["topics"]:
        r = rows[f"forum:{t['id']}"]
        assert r["gist"] == t["gist"] and not r["auto"] and r["href"] == f"/qspice#t-{t['id']}"
    for n in D["practice"]:
        r = rows[f"forum-note:{n['id']}"]
        assert r["gist"] == n["gist"] and r["type_label"] == "Seen in practice"


def test_guests_read_the_list_but_not_to_confirm(make_guest):
    guest, _ = make_guest("Gwen Guest")
    page = guest.get("/qspice")
    assert page.status_code == 200 and page.text.count('class="qs-topic"') == len(D["topics"])
    assert "Unanswered questions" not in page.text
    assert guest.get("/manage/to-confirm").status_code == 403


def test_owner_sees_items_in_to_confirm(client):
    html = client.get("/manage/to-confirm?type=forum").text
    assert "QSPICE forum:" in html


# ---- Ask ----------------------------------------------------------------------------------------------------------
def test_ask_finds_the_right_thread():
    hits = qspice.ask("crystal oscillator does not start")
    assert qspice.answered(hits) and hits[0].cover >= qspice.GOOD
    assert any("crystal" in h.title.lower() for h in hits[:3])
    hits = qspice.ask("timestep too small in my inverter")
    assert qspice.answered(hits)
    assert qspice.ask("") == [] and qspice.ask("how do I") == []


def test_ask_page_match_does_not_store(client):
    html = client.get("/qspice", params={"q": "LLC ringing at ZVS"}).text
    assert 'class="qs-hits"' in html and "No good match" not in html
    with Session(get_engine()) as s:
        assert s.scalars(select(QspiceQuestion)).all() == []


def test_owner_unanswered_question_is_stored_screened(owner):
    q = "Does Kowalski's frobnicator model from bob@example.com and @drsmith work with zyxwvut?"
    html = owner.get("/qspice", params={"q": q}).text
    assert "Kept for the daily run" in html
    with Session(get_engine()) as s:
        rows = s.scalars(select(QspiceQuestion)).all()
    assert len(rows) == 1
    text = rows[0].text
    assert "frobnicator" in text and "zyxwvut" in text
    assert "Kowalski" not in text and "@" not in text and "example.com" not in text and "drsmith" not in text
    assert text in owner.get("/qspice").text  # listed for the owner
    owner.get("/qspice", params={"q": q})  # the same question the same day is kept once
    with Session(get_engine()) as s:
        assert len(s.scalars(select(QspiceQuestion)).all()) == 1


def test_guest_question_is_not_stored(make_guest):
    guest, _ = make_guest("Gus Guest")
    html = guest.get("/qspice", params={"q": "frobnicator zyxwvut quux"}).text
    assert "Your questions are not stored" in html and "Kept for the daily run" not in html
    with Session(get_engine()) as s:
        assert s.scalars(select(QspiceQuestion)).all() == []
        assert s.scalars(select(ExternalSubmission)).all() == []


def test_questions_are_kept_twelve_months_and_reach_the_inbox(session):
    session.add_all([QspiceQuestion(text="old frobnicator", day=date(2025, 1, 1)),
                     QspiceQuestion(text="new frobnicator", day=date(2026, 10, 27))])  # fmt: skip
    session.commit()
    assert qspice.purge(session, date(2026, 10, 27)) == 1
    lines = qspice.inbox_lines(session, date(2026, 10, 1))
    assert lines[0].strip() == "## QSPICE: unanswered questions" and any("new frobnicator" in x for x in lines)
    assert not any("old frobnicator" in x for x in lines)


def test_screen_keeps_technical_words_and_part_numbers():
    s = qspice.screen("Why does my UCC27282 half bridge oscillate with a crystal? Ask Jane Smith.")
    assert "UCC27282" in s and "oscillate" in s and "crystal?" in s and "Jane" not in s and "Smith" not in s


# ---- AI services (later) -------------------------------------------------------------------------------------------
def test_ai_services_file_is_valid():
    rows = ai_services.data()
    assert len(rows) >= 6 and len({r["id"] for r in rows}) == len(rows)
    for r in rows:
        assert set(ai_services.FIELDS) <= set(r), r.get("id")
        assert r["status"] in ai_services.STATUS and "API key" in r["needs"] and "approval" in r["needs"]
    assert next(r for r in rows if r["id"] == "research_agent")["status"] == "parked"


def test_ai_services_page_is_owner_only(owner, make_guest):
    html = owner.get("/manage/ai-services").text
    assert "<h1>AI services (later)</h1>" in html and "Research agent page" in html and "Parked" in html
    guest, _ = make_guest("Gil Guest")
    assert guest.get("/manage/ai-services").status_code == 403
