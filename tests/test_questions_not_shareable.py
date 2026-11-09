"""No question and no answer in any Shareable output (owner, 9 Nov 2026: "Do not include shareable with questions").

Every Questions to ask (the Systems library segments' and the research reports' and cases', including each report's
first business-unit question) and every answer, internal or "can be shared" (on a segment: "can be used for
research"), stays out of the Shareable pages, the combined PDF, the PowerPoint, each animated deck, the Technology
overview and the presentation builder's slides."""

import html
import re

from app.services import answers
from app.services import presentation as pr
from app.services import presentation_pptx as pp
from app.services import segment_questions as sq
from app.services import share_animated as sa
from app.services import share_pdf as spdf
from app.services import share_reports as sr

SEG_KEY = "automotive/charging"
REPORT = "auto-uwb-15-4ab"
MARKS = {"internal": "QZXSEGINT", "shared": "QZXSEGSHR", "r-internal": "QZXREPINT", "r-shared": "QZXREPSHR"}


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"-\s+", "-", text or "")).lower()


def _seed(client) -> None:
    """Two answers to a segment question and two to a report question, one internal and one shareable each."""
    q = sq.questions(SEG_KEY)[0]["id"]
    for sharing in ("internal", "shared"):
        r = client.post("/library/questions/automotive/answers", follow_redirects=False,
                        data={"key": q, "sub": "charging", "sharing": sharing, "text": f"{MARKS[sharing]} words",
                              "who": f"{MARKS[sharing]}who"})  # fmt: skip
        assert r.status_code == 303
    rq = answers.questions(REPORT)[0]["id"]
    for sharing in ("internal", "shared"):
        m = MARKS["r-" + sharing]
        r = client.post(f"/business/reports/{REPORT}/answers", follow_redirects=False,
                        data={"key": rq, "sharing": sharing, "text": f"{m} words", "who": f"{m}who"})  # fmt: skip
        assert r.status_code == 303


def _questions() -> list[str]:
    """A long stretch of every question's wording: enough to be its own, short enough to survive a line break."""
    out = {_norm(q["text"])[:70] for q in [*answers.segment_questions(), *answers.all_questions()]}
    return sorted(t for t in out if len(t) >= 40)


def _leaks(name: str, text: str, questions: list[str]) -> list[str]:
    t = _norm(html.unescape(text))
    assert len(t) > 200, (name, "no text: the check would prove nothing")
    found = [m for m in MARKS.values() if m.lower() in t] + [q for q in questions if q in t]
    return [f"{name}: {x}" for x in found]


def test_no_question_or_answer_in_any_shareable_output(client):
    _seed(client)
    qs = _questions()
    assert len(qs) > 600  # segment and report questions both
    # the check works: the same answers are on their own pages
    seg = client.get(sq.href(sq.slug_of(SEG_KEY))).text
    assert MARKS["internal"] in seg and MARKS["shared"] in seg
    assert len(_leaks("control", seg, qs)) >= 10  # its questions are found by the same check
    assert MARKS["r-shared"] in client.get(f"/business/reports/{REPORT}").text
    leaks: list[str] = []
    # the Shareable pages: the list and every report, the Technology overview among them
    keys = [e.key for e in sr.REGISTRY]
    assert "overview" in keys
    for url in ["/shareable", *(e.url for e in sr.REGISTRY), "/shareable/presentation"]:
        r = client.get(url)
        assert r.status_code == 200, url
        leaks += _leaks(url, r.text, qs)
    # the combined PDF and the PowerPoint of every report
    pdf = client.get("/shareable/pdf?r=" + ",".join(keys))
    assert pdf.status_code == 200 and pdf.content[:4] == b"%PDF"
    leaks += _leaks("PDF", "\n".join(spdf.texts(pdf.content)), qs)
    deck = client.get("/shareable/pptx?r=" + ",".join(keys))
    assert deck.status_code == 200
    leaks += _leaks("PowerPoint", "\n".join(t for slide in pp.texts(deck.content) for t in slide), qs)
    # each animated deck
    for k in keys:
        r = client.get(f"/shareable/animated/{k}")
        assert r.status_code == 200, k
        leaks += _leaks(f"animated {k}", "\n".join(sa.texts(r.content)), qs)
    # the presentation builder: every section it offers
    built = pp.build(pr.build(pr.all_section_ids()), pr.DEFAULT_TITLE)
    leaks += _leaks("presentation", "\n".join(t for slide in pp.texts(built) for t in slide), qs)
    assert not leaks, "\n".join(leaks[:20])


def test_the_segment_switch_says_research_and_keeps_its_stored_value(client, session):
    """On a segment question the switch reads "Can be used for research (inbox)"; reports keep "Can be shared"; both
    store "shared", so the inbox (full text vs count) and guests work as before."""
    from app.models import Answer

    _seed(client)
    box = client.get(sq.href(sq.slug_of(SEG_KEY))).text
    assert "✅ Can be used for research (inbox)" in box and "✅ Can be shared" not in box
    assert "✅ Can be shared" in client.get(f"/business/reports/{REPORT}").text
    rows = session.query(Answer).filter(Answer.text.like("QZX%")).all()
    assert sorted(a.sharing for a in rows) == ["internal", "internal", "shared", "shared"]
    ov = client.get("/manage/answers").text
    assert "✅ Can be used for research (inbox)" in ov and "✅ Can be shared" in ov
