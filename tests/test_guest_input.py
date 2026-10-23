"""Guests: every POST that stores input is held for the owner's review and changes nothing until approved; approval
replays it through the owner's own route with the guest's name; rejection changes nothing. One case per route."""

import hashlib
import re
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import Base, get_engine
from app.main import create_app
from app.models import (
    BlockDiagram,
    BroadcastConfig,
    CrossFeedback,
    ExternalSubmission,
    ReportQuestion,
    ScheduledReview,
    ShortlistItem,
    SiteFeedback,
    TechReviewRequest,
)
from app.services import automotive as au
from app.services import inbox

AUTH_TABLES = {"accounts", "passkey_credentials", "invites", "webauthn_challenges", "pow_spent",
               "external_submissions", "users", "organizations"}  # fmt: skip
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def fingerprint() -> str:
    """A hash of every table guests could change (all but the sign-in tables and the review queue)."""
    h = hashlib.sha256()
    with get_engine().connect() as c:
        for t in Base.metadata.sorted_tables:
            if t.name in AUTH_TABLES:
                continue
            for row in c.execute(text(f"SELECT * FROM {t.name} ORDER BY 1")):
                h.update(repr(tuple(row)).encode())
    return h.hexdigest()


def _id_after(owner, session, model, url, **kw):
    owner.post(url, follow_redirects=False, **kw)
    session.expire_all()
    return session.scalar(select(model.id).order_by(model.id.desc()).limit(1))


def _part_ids(owner, *mpns):
    out = []
    for m in mpns:
        r = owner.get(f"/find?q={m}", follow_redirects=False)
        out.append(int(re.search(r"/parts/(\d+)", r.headers["location"]).group(1)))
    return out


# name -> setup(owner, session) returning (method, path, request kwargs)
def c_site_feedback(o, s):
    return "post", "/site-feedback", {"json": {"text": "Bigger legend please", "path": "/portfolio", "author": "Boss",
                                              "client": "g1"}}  # fmt: skip


def c_cross_feedback(o, s):
    ref, cand = _part_ids(o, "SR8641", "SC141")
    return "post", "/feedback", {"data": {"reference_id": ref, "candidate_id": cand, "verdict": "reject",
                                          "note": "too slow"}}  # fmt: skip


def c_requests(o, s):
    return "post", "/requests", {"data": {"mpns": "SR8641", "note": "please"}}


def c_review_request(o, s):
    return "post", "/reviews/request", {"data": {"mpn": "PAC5527QM", "question": "Which features matter in a drill?"}}


def c_review_request_status(o, s):
    rid = _id_after(o, s, TechReviewRequest, "/reviews/request", data={"mpn": "PAC5527QM", "question": "Why?"})
    return "post", f"/reviews/requests/{rid}", {"data": {"status": "dropped"}}


def c_review_react(o, s):
    return "post", "/reviews/qorvo-pac5527-motor-driver/react", {"data": {"key": "key_features.0",
                                                                          "verdict": "disagree", "author": "Boss"}}


def c_library_react(o, s):
    from app.services import library

    rule = next(r for r in library.topic("traction_asil_d")["design_rules"] if r.get("conf") in ("high", "med"))
    return "post", "/library/traction_asil_d/react", {"data": {"item": rule["id"], "verdict": "disagree",
                                                               "comment": "check", "author": ""}}  # fmt: skip


def c_report_react(o, s):
    return "post", "/business/reports/radio-tuner-next/react", {"data": {"key": "f-node", "verdict": "further",
                                                                         "comment": "Two dies", "author": ""}}


def c_report_ask(o, s):
    return "post", "/business/reports/filters-1-11ghz/ask", {"data": {"text": "Which ceramic filters?", "author": ""}}


def c_report_question(o, s):
    qid = _id_after(o, s, ReportQuestion, "/business/reports/filters-1-11ghz/ask", data={"text": "S band filters?"})
    return "post", f"/business/reports/questions/{qid}", {"data": {"status": "good", "answer": "Yes"}}


def c_area_request(o, s):
    return "post", "/blocks/area-request", {"data": {"area": "Robotics", "why": "Humanoids", "author": "x"}}


def c_block_feedback(o, s):
    return "post", "/api/blocks/feedback", {"json": {"message": "Add a boost stage", "diagram_name": "T"}}


def c_design_create(o, s):
    return "post", "/api/blocks/designs", {"json": {"name": "Guest design", "data": {"groups": [], "links": []}}}


def c_design_update(o, s):
    did = o.post("/api/blocks/designs", json={"name": "T", "data": {"groups": [], "links": []}}).json()["id"]
    return "put", f"/api/blocks/designs/{did}", {"json": {"name": "Renamed", "data": {"groups": [], "links": []}}}


def c_design_delete(o, s):
    did = o.post("/api/blocks/designs", json={"name": "T", "data": {"groups": [], "links": []}}).json()["id"]
    return "post", f"/blocks/{did}/delete", {}


def c_blocks_verify(o, s):
    return "post", "/blocks/verify", {"data": {"i": 0, "on": "1", "author": "", "note": "checked"}}


def c_config_create(o, s):
    return "post", "/api/broadcast/configs", {"json": {"name": "Guest radio", "data": {"tuners": 2}}}


def c_config_update(o, s):
    cid = o.post("/api/broadcast/configs", json={"name": "Mine", "data": {"tuners": 1}}).json()["id"]
    return "put", f"/api/broadcast/configs/{cid}", {"json": {"name": "Renamed", "data": {}}}


def c_config_delete(o, s):
    cid = o.post("/api/broadcast/configs", json={"name": "Mine", "data": {"tuners": 1}}).json()["id"]
    return "post", f"/broadcast/configurations/{cid}/delete", {}


def c_shortlist(o, s):
    return "post", "/business/shortlist", {"data": {"origin": "idea", "key": "Wireless audio for e-bikes"}}


def c_shortlist_update(o, s):
    sid = _id_after(o, s, ShortlistItem, "/business/shortlist", data={"origin": "idea", "key": "Owner idea"})
    return "post", f"/business/shortlist/{sid}", {"data": {"note": "guest note"}}


def c_schedule(o, s):
    return "post", "/business/schedule", {"data": {"title": "ISO7821DWW in on-board chargers", "next": "/parts"}}


def c_schedule_update(o, s):
    sid = _id_after(o, s, ScheduledReview, "/business/schedule", data={"title": "Owner topic"})
    return "post", f"/business/schedule/{sid}", {"data": {"act": "remove"}}


def c_case(o, s):
    return "post", "/business/cases", {"data": {"title": "Guest case"}}


def c_case_update(o, s):
    r = o.post("/business/cases", data={"title": "Owner case"}, follow_redirects=False)
    cid = int(r.headers["location"].rsplit("/", 1)[1])
    return "post", f"/business/cases/{cid}", {"data": {"act": "note", "kind": "upside", "text": "Reuses IP"}}


def c_decision(o, s):
    from app.services import blocks

    fn = next(iter(blocks.catalogue()["functions"]))
    return "post", "/business/decision", {"data": {"fn": fn, "status": "set_aside", "note": "later"}}


def c_tech_feedback(o, s):
    return "post", "/business/capabilities/feedback", {"data": {"kind": "missing", "topic": "BAW", "text": "Add XBAW",
                                                                "author": ""}}  # fmt: skip


def c_data_review(o, s):
    return "post", "/api/business/review", {"json": {"dataset": "technology", "key": "pol_ldo", "verdict": "wrong",
                                                     "comment": "x", "author": "Boss"}}  # fmt: skip


def c_mapping(o, s):
    return "post", "/business/evidence/pol_ldo/mapping", {"data": {"mpn": "TESTX1", "manufacturer": "Qorvo",
                                                                   "verdict": "yes", "author": ""}}  # fmt: skip


def c_automotive(o, s):
    key = next(c["key"] for c in au.build(s)["cells"].values() if c["status"] == "proposed")
    return "post", "/business/automotive/review", {"data": {"cell": key, "verdict": "reject"}}


def c_price_call(o, s):
    (pid,) = _part_ids(o, "SR8641")
    return "post", f"/pricing/{pid}/call", {"data": {"verdict": "low", "comment": "0.5 at 100k", "author": ""}}


def c_pipeline_new(o, s):
    (pid,) = _part_ids(o, "SC141")
    return "post", "/pipeline/new", {"data": {"part": pid}}


def c_pipeline_step(o, s):
    pid, our = _part_ids(o, "SC141", "SR8641")
    draft = o.post("/pipeline/new", data={"part": pid}, follow_redirects=False).headers["location"].split("?")[0]
    return "post", draft, {"data": {"act": "ours", "our": str(our)}}


CASES = {k[2:]: v for k, v in globals().items() if k.startswith("c_")}


@pytest.mark.parametrize("name", sorted(CASES))
def test_guest_post_changes_nothing_until_approved(name, owner, make_guest, session):
    method, path, kw = CASES[name](owner, session)
    guest, gid = make_guest("Anna Guest")
    before = fingerprint()
    r = getattr(guest, method)(path, follow_redirects=False, **kw)
    assert r.status_code in (200, 303), r.text
    assert fingerprint() == before, "a guest submission changed the site"
    sub = session.scalars(select(ExternalSubmission).order_by(ExternalSubmission.id.desc())).first()
    assert sub.status == "pending" and sub.account_id == gid and sub.target == path and sub.author == "Anna Guest"
    if r.status_code == 200 and r.headers["content-type"].startswith("application/json"):
        assert r.json()["review"] is True
    # the owner approves: the item is applied through the same route, as the owner's own would be
    a = owner.post(f"/manage/guest-input/{sub.id}", data={"act": "approve", "note": "ok"}, follow_redirects=False)
    assert a.status_code == 303
    session.expire_all()
    sub = session.get(ExternalSubmission, sub.id)
    assert sub.status == "approved", (sub.result, a.headers["location"])
    assert fingerprint() != before


def test_every_post_route_is_covered(client):
    """Each POST/PUT route is either covered above, compute-only, owner-only for guests, or part of signing in."""
    from app.auth import access
    from app.services import guest_input

    signing_in = {"/login", "/passkey/login/options", "/passkey/login/verify", "/invite/{token}/options",
                  "/invite/{token}/verify"}  # fmt: skip
    covered = {"/site-feedback", "/feedback", "/requests", "/reviews/request", "/reviews/requests/{rid}",
               "/reviews/{slug}/react", "/library/{key}/react", "/business/reports/{slug}/react",
               "/business/reports/{slug}/ask", "/business/reports/questions/{qid}", "/blocks/area-request",
               "/api/blocks/feedback", "/api/blocks/designs", "/api/blocks/designs/{design_id}",
               "/blocks/{design_id}/delete", "/blocks/verify", "/api/broadcast/configs",
               "/api/broadcast/configs/{config_id}", "/broadcast/configurations/{config_id}/delete",
               "/business/shortlist", "/business/shortlist/{item_id}", "/business/schedule",
               "/business/schedule/{item_id}", "/business/cases", "/business/cases/{case_id}", "/business/decision",
               "/business/capabilities/feedback", "/api/business/review", "/business/evidence/{fn}/mapping",
               "/business/automotive/review", "/pricing/{part_id}/call", "/pipeline/new", "/pipeline/{draft_id}",
               "/site-feedback/{item_id}/file"}  # fmt: skip
    missing = []
    for route in client.app.routes:
        methods = getattr(route, "methods", set()) or set()
        if not methods & {"POST", "PUT", "PATCH", "DELETE"}:
            continue
        p = route.path.replace(":int", "")
        sample = re.sub(r"\{[^}]+\}", "1", p)
        if p in signing_in or p in covered or guest_input.is_compute_only(p) or access.owner_only(sample, "POST"):
            continue
        missing.append(p)
    assert not missing, f"POST routes without a guest test: {missing}"


def test_compute_only_posts_work_for_guests(make_guest, session):
    guest, _ = make_guest()
    before = fingerprint()
    r = guest.post("/api/blocks/counts", json={"req": {"am_fm_tuner": {"dab": True, "pd": True}}})
    assert r.status_code == 200 and "review" not in r.json()
    assert guest.post("/pricing/builder", data={"mpn": "Si46922"}).status_code == 200
    assert fingerprint() == before
    assert session.scalar(select(ExternalSubmission.id)) is None


OWNER_ONLY = [("get", "/manage/overview"), ("get", "/manage/schedule"), ("get", "/manage/verify"),
              ("get", "/manage/reviews"), ("get", "/manage/feedback"), ("get", "/manage/uploads"),
              ("get", "/business/tam"), ("get", "/business/quality"), ("get", "/business/validation"),
              ("get", "/requests"), ("get", "/blocks/feedback"), ("get", "/blocks/area-requests"),
              ("get", "/manage/people"), ("get", "/manage/guest-input"), ("get", "/owner/passkeys"),
              ("get", "/api/blocks/feedback"), ("post", "/manage/uploads"), ("post", "/manage/feedback/respond"),
              ("post", "/business/tam"), ("post", "/business/tam/review"), ("post", "/business/quality/answer"),
              ("post", "/requests/1"), ("post", "/blocks/feedback/1"), ("post", "/blocks/area-requests/1"),
              ("post", "/manage/verify/1"), ("post", "/manage/people/invite"), ("post", "/manage/guest-input/1"),
              ("post", "/owner/passkeys/options")]  # fmt: skip


@pytest.mark.parametrize("method,path", OWNER_ONLY)
def test_data_management_is_403_for_guests(method, path, make_guest, session):
    guest, _ = make_guest()
    before = fingerprint()
    r = getattr(guest, method)(path, data={"x": "1"}) if method == "post" else guest.get(path)
    assert r.status_code == 403
    assert fingerprint() == before and session.scalar(select(ExternalSubmission.id)) is None


def test_guest_reads_pages_without_data_management(make_guest):
    guest, _ = make_guest("Anna Guest")
    page = guest.get("/parts").text
    assert "You are signed in as Anna Guest (guest). Your input is reviewed before it is used." in page
    assert 'href="/manage/overview"' not in page and "Data management" not in page
    assert guest.get("/business/method").status_code == 200 and guest.get("/rules").status_code == 200
    assert guest.get("/").status_code == 200


def test_form_post_redirects_back_with_a_thank_you(make_guest):
    guest, _ = make_guest()
    r = guest.post("/requests", data={"mpns": "SR8641"}, headers={"referer": "http://testserver/parts?q=SR"},
                   follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and r.headers["location"] == "/parts?q=SR"
    assert "Thanks, sent for review" in guest.get("/parts?q=SR").text
    assert "Thanks, sent for review" not in guest.get("/parts?q=SR").text  # shown once


def test_reject_changes_nothing_and_owner_sees_full_text(owner, make_guest, session):
    guest, _ = make_guest("Anna Guest")
    guest.post("/site-feedback", json={"text": "A long comment " * 10, "path": "/parts", "client": "c9"})
    sub = session.scalar(select(ExternalSubmission))
    page = owner.get("/manage/guest-input").text
    assert "Anna Guest" in page and "Feedback button" in page and ("A long comment " * 10).strip() in page
    assert "1</b> guest input to review" in owner.get("/manage/overview").text
    before = fingerprint()
    r = owner.post(f"/manage/guest-input/{sub.id}", data={"act": "reject", "note": "off topic"})
    assert r.status_code == 200 and "Rejected" in r.text
    assert fingerprint() == before
    session.expire_all()
    assert session.get(ExternalSubmission, sub.id).status == "rejected"
    # a reviewed item cannot be approved afterwards
    owner.post(f"/manage/guest-input/{sub.id}", data={"act": "approve"})
    assert fingerprint() == before


def test_approved_items_carry_the_guests_name(owner, make_guest, session):
    guest, _ = make_guest("Anna Guest")
    guest.post("/site-feedback", json={"text": "From Anna", "path": "/parts", "author": "The Owner", "client": "c1"})
    ref, cand = _part_ids(owner, "SR8641", "SC141")
    guest.post("/feedback", data={"reference_id": ref, "candidate_id": cand, "verdict": "reject", "note": "slow"})
    for sub in session.scalars(select(ExternalSubmission)).all():
        owner.post(f"/manage/guest-input/{sub.id}", data={"act": "approve"})
    session.expire_all()
    fb = session.scalar(select(SiteFeedback).where(SiteFeedback.text == "From Anna"))
    assert fb.author == "Anna Guest"  # a guest cannot sign as someone else
    cf = session.scalar(select(CrossFeedback).where(CrossFeedback.note == "slow"))
    assert cf.user.display_name == "Anna Guest"


def test_feedback_file_follows_its_approved_item(owner, make_guest, session, tmp_path, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path / "var")
    guest, _ = make_guest()
    sid = guest.post("/site-feedback", json={"text": "See picture", "path": "/", "client": "c5"}).json()["id"]
    r = guest.post(f"/site-feedback/{sid}/file", data={"client": "c5"}, files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 200 and r.json()["review"]
    subs = session.scalars(select(ExternalSubmission).order_by(ExternalSubmission.id)).all()
    parent, file_sub = subs
    r = owner.post(f"/manage/guest-input/{file_sub.id}", data={"act": "approve"})
    assert "Approve the feedback this file belongs to first" in r.text
    owner.post(f"/manage/guest-input/{parent.id}", data={"act": "approve"})
    owner.post(f"/manage/guest-input/{file_sub.id}", data={"act": "approve"})
    session.expire_all()
    assert session.get(ExternalSubmission, file_sub.id).status == "approved"


def test_inbox_lists_only_approved_guest_input(owner, make_guest, session):
    guest, _ = make_guest("Anna Guest")
    guest.post("/site-feedback", json={"text": "Approved idea", "path": "/", "client": "c1"})
    guest.post("/site-feedback", json={"text": "Pending idea", "path": "/", "client": "c1"})
    first = session.scalars(select(ExternalSubmission).order_by(ExternalSubmission.id)).first()
    owner.post(f"/manage/guest-input/{first.id}", data={"act": "approve"})
    session.expire_all()
    out = inbox.collect(session, (datetime.now(UTC) - timedelta(days=1)).date())
    section = out.split("## Guest input (approved, with names)")[1]
    assert "Approved idea" in section and "Anna Guest" in section
    assert "Pending idea" not in out
    assert "Waiting for the owner's review: 1 guest item(s)" in section


def test_replay_scope_cannot_be_set_from_outside(tmp_path):
    """The approval marker lives in the ASGI scope; no header or form field can set it."""
    app = create_app(f"sqlite:///{tmp_path / 'x.db'}", seed_synthetic=False)
    from fastapi.testclient import TestClient

    from app.config import get_settings

    s = get_settings()
    old = s.site_password
    s.site_password = "pw"
    try:
        with TestClient(app) as c:
            r = c.get("/parts", headers={"crosslist.replay": "1"}, follow_redirects=False)
            assert r.status_code == 303
    finally:
        s.site_password = old
    with Session(get_engine()) as db:
        assert db.scalar(select(BlockDiagram.id)) is None and db.scalar(select(BroadcastConfig.id)) is None
