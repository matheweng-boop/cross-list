"""Data management, owner feedback 21 Oct: TAM estimates instead of Commercial inputs, a file in the Feedback window,
the Verify next pop-up, yes / no review questions, the compact Overview and the public-sources statement."""

from sqlalchemy import select

from app.models import DataReview, FeedbackAttachment, TamEstimate, Upload, VerifyTask
from app.services import quality, tam
from app.web import nav

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


# ---- 1. TAM estimates ------------------------------------------------------------------------------------------
def test_tam_examples_come_with_sources_and_are_labelled():
    rows = tam.researched()
    assert len(rows) >= 5 and len({e["key"] for e in rows}) == len(rows)
    for e in rows:
        assert e["value"] and e["year"] and e["source"]["publisher"] and e["quality"] and e["example"]
        assert not e["source"]["url"] or e["source"]["url"].startswith("https://")


def test_tam_page_review_and_add(client, session):
    labels = [i[0] for i in dict((k, v) for k, _, v in nav.NAV)["growth"]]  # owner, 23 Oct 2026: Future growth
    assert "TAM estimates" in labels and "Commercial inputs" not in labels
    r = client.get("/business/data", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"] == "/business/tam"
    html = client.get("/business/tam").text
    assert "TAM estimates" in html and "Market Research Future" in html and "example from research notes" in html
    assert "Source quality" in html and 'aria-current="page"' in html
    # a single estimate (members of a combined topic are no longer separate review items; owner, 25 Oct 2026)
    key = next(e["key"] for e in tam.researched() if e["fn"] != "am_fm_tuner"
               and e["key"] not in tam.applied())  # applied ones are locked
    r = client.post("/business/tam/review", data={"key": key, "answer": "disagree", "comment": "counts modules"},
                    follow_redirects=False)  # fmt: skip
    assert r.status_code == 303
    row = session.scalar(select(DataReview).where(DataReview.dataset == "tam", DataReview.key == key))
    assert row.verdict == "wrong" and row.comment == "counts modules"
    assert "you disagree" in client.get("/business/tam").text
    assert client.post("/business/tam/review", data={"key": "nope", "answer": "agree"}).status_code == 400
    # add one: nothing is estimated, the dollar value is only read from the text
    assert "error=" in client.post("/business/tam", data={"product": "X"}, follow_redirects=False).headers["location"]
    client.post("/business/tam", data={"product": "Automotive UWB front ends", "value": "$420 M", "year": "2025",
                                       "region": "Global", "source_publisher": "Example Research",
                                       "source_url": "javascript:alert(1)", "quality": "press release"})  # fmt: skip
    t = session.scalar(select(TamEstimate))
    assert t.usd == 420e6 and t.year == 2025 and t.source_url is None
    assert "Automotive UWB front ends" in client.get("/business/tam").text
    assert tam.parse_usd("$1.4 B") == 1.4e9 and tam.parse_usd("$400–500 M") == 400e6 and tam.parse_usd("n/a") is None


# ---- 2. a file in the Feedback window ---------------------------------------------------------------------------
def test_feedback_with_a_file(client, session, tmp_uploads):
    assert 'name="file"' in client.get("/").text  # the Feedback window has the file field on every page
    sent = {"text": "This diagram is wrong", "path": "/blocks", "client": "abc"}
    fid = client.post("/site-feedback", json=sent).json()["id"]
    files = {"file": ("shot.png", PNG, "image/png")}
    assert client.post(f"/site-feedback/{fid}/file", data={"client": "other"}, files=files).status_code == 404
    bad = client.post(f"/site-feedback/{fid}/file", data={"client": "abc"}, files={"file": ("x.svg", b"<svg>", "x")})
    assert bad.status_code == 400 and "PNG" in bad.json()["detail"]
    r = client.post(f"/site-feedback/{fid}/file", data={"client": "abc"}, files=files)
    assert r.status_code == 200 and r.json()["ok"]
    link = session.scalar(select(FeedbackAttachment).where(FeedbackAttachment.feedback_id == fid))
    u = session.get(Upload, link.upload_id)
    assert u.content_type == "image/png" and u.original_name == "shot.png" and (tmp_uploads / u.file_name).exists()
    digest = client.get("/manage/feedback").text
    assert "Attached:" in digest and f"/manage/uploads/{u.id}/file" in digest
    assert client.get(f"/manage/uploads/{u.id}/file").content == PNG
    assert "Feedback: This diagram is wrong" in client.get("/manage/uploads").text  # the Uploads page still lists it


# ---- 3. Verify next: comparison and answer in one pop-up --------------------------------------------------------
def test_verify_cross_popup(client, session, real):
    html = client.get("/manage/verify").text
    crosses = session.scalars(select(VerifyTask).where(VerifyTask.kind == "cross", VerifyTask.status == "open")).all()
    assert crosses
    t = crosses[0]
    assert f'<dialog class="vd" id="vd-{t.id}"' in html and f'data-dialog="vd-{t.id}"' in html
    dialog = html.split(f'id="vd-{t.id}"', 1)[1].split("</dialog>", 1)[0]
    assert "vd-spec" in dialog and "vd-side" in dialog and "compare-table" in dialog
    assert f'action="/manage/verify/{t.id}"' in dialog and 'name="note"' in dialog


# ---- 4. review queue as yes / no questions ----------------------------------------------------------------------
def test_questions_are_specific_yes_no(client, session):
    html = client.get("/business/quality").text
    assert 'id="questions"' in html and "Questions for you" in html
    queue = html.split('id="questions"', 1)[1].split('id="research"', 1)[0]
    assert "confidence" not in queue.lower() and ">Yes<" in queue and ">No<" in queue and 'name="comment"' in queue
    assert "Review status per dataset" not in html
    from app.services import opportunity as op

    apps = op.with_status(op.applications(), op.makers(session), op.company("combined")[2])
    qs = quality.questions(session, apps)
    assert qs and all(q["question"].endswith("?") and q["check"] for q in qs)
    assert any(q["dataset"] == "tam" and "Does " in q["question"] for q in qs)
    comp = quality.ask("competition", "pol_ldo", "PoL LDO", {"vendors": ["TI", "ADI"]})
    assert comp["question"] == "Do these companies sell a PoL LDO today: TI, ADI?"
    entry = {"outlook": "growing", "note": "EVs", "check": {"evidence": ["https://x.org/a - page"]}}
    trend = quality.ask("trends", "gate_driver", "Gate driver", entry)
    assert "gate driver" in trend["question"] and trend["links"] == [("x.org", "https://x.org/a")]
    assert "Open the source" in trend["check"]
    # answering: Yes / No with a comment becomes a review of the item
    q = next(q for q in qs if q["dataset"] != "tam")
    answer = {"dataset": q["dataset"], "key": q["key"], "answer": "no", "comment": "one more supplier"}
    r = client.post("/business/quality/answer", data=answer, follow_redirects=False)
    assert r.status_code == 303 and "#questions" in r.headers["location"]
    row = session.scalar(select(DataReview).where(DataReview.dataset == q["dataset"], DataReview.key == q["key"]))
    assert row.verdict == "wrong" and row.comment == "one more supplier"
    unknown = {"dataset": "x", "key": "y", "answer": "yes"}
    assert client.post("/business/quality/answer", data=unknown).status_code == 400


# ---- 5. compact overview at the front of Data management --------------------------------------------------------
def test_overview_first_in_data_management(client):
    assert nav.UTILITY[2][0][1] == "/manage/overview"
    html = client.get("/manage/overview").text
    assert 'class="ov-table"' in html and "TAM estimates" in html and "Technology rating" in html
    assert "open in Verify next" in html and 'aria-current="page"' in html
    assert '<a href="/manage/overview"' in client.get("/").text  # the Data management link opens it


# ---- 6. methodology: public sources and polite collection -------------------------------------------------------
def test_method_states_public_sources(client):
    html = client.get("/business/method").text
    head = html.split('id="public"', 1)[1][:1500]
    assert "public sources" in head and "No confidential company data" in head
    assert "robots.txt" in head and "one request at a time" in head and "never logs in" in head
