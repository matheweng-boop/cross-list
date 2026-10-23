"""Technology reviews: the data format, the list and detail pages for every review file, requests, agree / disagree, and
the links from part, catalogue, walk-through and application pages."""

import copy
import json
import urllib.parse

import pytest
from sqlalchemy import select

from app import yamlio
from app.config import get_settings
from app.models import DataReview, Part, TechReviewRequest
from app.services import inbox
from app.services import reviews as rv
from app.web import nav

FILES = sorted(p for p in rv.FOLDER.glob("*.yaml") if not p.name.startswith("_"))
GOOD = {
    "slug": "test-part", "title": "Test part", "maker": "Qorvo", "family": "motor_controller", "parts": ["PAC5527QM"],
    "app_area": "Motor control",
    "in_brief": [{"text": "One chip", "conf": "high", "src": "s1"}],
    "problem": {"summary": "Motors need electronics", "points": [{"text": "Space", "conf": "med", "src": "s1"}]},
    "concept": {"summary": "Four blocks",
                "blocks": [{"name": "Power manager", "what": "w", "why": "y", "conf": "high"}]},
    "key_features": [{"feature": "Supply", "value": "6-40 V", "meaning": "m", "why_it_matters": "w", "conf": "high",
                      "src": ["s1"]}],
    "applications": [{"diagram": "Light EV BLDC drive, 48 V (TI)", "role": "MCU", "conf": "med"},
                     {"diagram": "No such diagram", "role": "x", "conf": "low"}],
    "learn": {"5": "a", "25": "b"},
    "sources": [{"id": "s1", "title": "Datasheet", "note": "unofficial copy"}],
}  # fmt: skip


def test_every_review_file_follows_the_format():
    assert FILES, "data/reviews holds at least one review"
    _, errors, warnings = rv.load_dir(rv.FOLDER)
    assert errors == [], errors
    assert warnings == [], warnings  # every diagram named in a review exists
    for p in FILES:
        data = yamlio.load(p.read_text())
        assert data["slug"] == p.stem


def test_a_good_file_passes_and_unknown_diagrams_are_left_out_with_a_warning():
    r, warnings = rv.validate(copy.deepcopy(GOOD), "test-part")
    assert [a["kind"] for a in r["applications"]] == ["library"]
    assert len(warnings) == 1 and "No such diagram" in warnings[0]
    assert r["status"] == "draft" and "key_features.0" in rv.item_keys(r)


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda d: d.update(slug="other"), "slug must equal the file name"),
        (lambda d: d.update(family="not_a_function"), "family 'not_a_function'"),
        (lambda d: d.pop("title"), "title is missing"),
        (lambda d: d["key_features"][0].pop("why_it_matters"), "key_features[0] misses why_it_matters"),
        (lambda d: d["in_brief"][0].update(src="s9"), "src not in sources: s9"),
        (lambda d: d["in_brief"][0].update(conf="sure"), "conf must be high, med or low"),
        (lambda d: d.update(sources=[{"title": "no id"}]), "sources[0] has no id"),
    ],
)
def test_a_broken_file_fails_clearly(change, message):
    data = copy.deepcopy(GOOD)
    change(data)
    with pytest.raises(rv.ReviewError, match="test-part") as e:
        rv.validate(data, "test-part")
    assert message in str(e.value)


def test_a_broken_file_is_left_out_not_fatal(tmp_path):
    (tmp_path / "test-part.yaml").write_text(json.dumps(GOOD))
    bad = {**GOOD, "slug": "broken"}
    bad.pop("sources")
    (tmp_path / "broken.yaml").write_text(json.dumps(bad))
    (tmp_path / "_format.yaml").write_text("not: a review")
    ok, errors, _ = rv.load_dir(tmp_path)
    assert list(ok) == ["test-part"] and len(errors) == 1 and errors[0].startswith("broken:")


def test_list_and_detail_pages_render_for_every_review(client):
    page = client.get("/reviews")
    assert page.status_code == 200 and "Request a part review" in page.text
    for p in FILES:
        r = rv.get(p.stem)
        assert f'href="/reviews/{p.stem}"' in page.text
        d = client.get(f"/reviews/{p.stem}")
        assert d.status_code == 200, p.stem
        for heading in ("In brief", "The problem", "The concept", "Key features", "Where it sits",
                        "Competitors and crosses", "Sources", "Learn about this"):  # fmt: skip
            assert heading in d.text, (p.stem, heading)
        for a in r["applications"]:
            if a["kind"] == "library":
                href = f"/blocks/new?diagram={urllib.parse.quote(a['diagram'], safe='/')}"
                assert href in d.text.replace("&amp;", "&")
        if any("unofficial" in str(s.get("note")) for s in r["sources"]):
            assert "unofficial copy" in d.text
    assert client.get("/reviews/no-such-review").status_code == 404


def test_search_by_part_number_and_words(client):
    r = client.get("/reviews?q=PAC5527")
    assert "/reviews/qorvo-pac5527-motor-driver" in r.text
    assert "/reviews/qorvo-pac5527-motor-driver" in client.get("/reviews?q=brushless+motor").text
    assert "/reviews/qorvo-pac5527-motor-driver" not in client.get("/reviews?q=zzzz-nothing").text


def test_library_diagram_links_open_the_diagram(client):
    r = rv.get("qorvo-pac5527-motor-driver")
    a = next(a for a in r["applications"] if a["kind"] == "library")
    page = client.get(f"/blocks/new?diagram={urllib.parse.quote(a['diagram'], safe='/')}")
    assert page.status_code == 200 and a["name"] in page.text


def test_request_is_stored_listed_and_in_the_inbox(client, session, monkeypatch):
    r = client.post("/reviews/request", data={"mpn": "ACT72350", "question": "What does the buck do?",
                                              "application": "E-bike"}, follow_redirects=False)  # fmt: skip
    assert r.status_code == 303 and "#requested" in r.headers["location"]
    row = session.scalars(select(TechReviewRequest)).one()
    assert (row.mpn, row.application, row.status) == ("ACT72350", "E-bike", "new")
    page = client.get("/reviews")
    assert "ACT72350" in page.text and "What does the buck do?" in page.text
    text = inbox.collect(session, row.created_at.date())
    assert "## Technology review requests" in text
    assert "[new] ACT72350: What does the buck do? · application: E-bike" in text
    monkeypatch.setattr(get_settings(), "inbox_token", "k" * 40)
    api = client.get("/api/inbox", headers={"Authorization": "Bearer " + "k" * 40})
    assert "ACT72350" in api.text
    assert client.post("/reviews/request", data={"mpn": "", "question": "x"}).status_code == 400
    # a request for a part that has a review is answered by it
    client.post("/reviews/request", data={"mpn": "PAC5527QM", "question": "Which features matter in a drill?"})
    e = next(e for e in rv.requests(session) if e["row"].mpn == "PAC5527QM")
    assert e["status"] == "done" and e["review"]["slug"] == "qorvo-pac5527-motor-driver"
    # the owner drops or links a request
    assert client.post(f"/reviews/requests/{row.id}", data={"status": "dropped"}).status_code in (200, 303)
    session.refresh(row)
    assert row.status == "dropped"
    assert client.post(f"/reviews/requests/{row.id}", data={"status": "nope"}).status_code == 400


def test_suggestions_for_the_part_number_box(client):
    r = client.get("/reviews/suggest?mpn=PAC552")
    assert '<option value="PAC5527QM">' in r.text
    assert client.get("/reviews/suggest?mpn=P").text == ""


def test_agree_and_disagree_save_a_data_review(client, session):
    slug = "qorvo-pac5527-motor-driver"
    form = {"key": "key_features.0", "verdict": "disagree", "comment": "Check the 40 V limit"}
    r = client.post(f"/reviews/{slug}/react", data=form, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("#i-key_features-0")
    d = session.scalars(select(DataReview).where(DataReview.dataset == f"review:{slug}")).one()
    assert (d.key, d.verdict, d.comment) == ("key_features.0", "wrong", "Check the 40 V limit")
    page = client.get(f"/reviews/{slug}")
    assert "disputed" in page.text and "Check the 40 V limit" in page.text and "high ↓" not in page.text
    assert client.post(f"/reviews/{slug}/react", data={"key": "nope.1", "verdict": "agree"}).status_code == 400
    assert client.post(f"/reviews/{slug}/react", data={"key": "in_brief.0", "verdict": "maybe"}).status_code == 400
    client.post(f"/reviews/{slug}/react", data={"key": "in_brief.0", "verdict": "agree"})
    assert "agreed" in client.get(f"/reviews/{slug}").text


def test_disputed_item_confidence_drops_one_step(session):
    r = rv.get("qorvo-pac5527-motor-driver")
    session.add(DataReview(dataset=rv.dataset(r["slug"]), key="in_brief.0", verdict="wrong"))
    session.commit()
    x = rv.with_feedback(session, r)["rows"]["in_brief"][0]
    assert (x["conf_was"], x["conf"]) == ("high", "med")


def test_part_pages_show_the_request_button_or_the_review(client, session):
    any_part = session.scalars(select(Part).limit(1)).first()  # any part from the demo data will do
    page = client.get(f"/parts/{any_part.id}")
    assert "Request a part review" in page.text
    assert f"/reviews?part={urllib.parse.quote(any_part.mpn, safe='/')}#request" in page.text.replace("&amp;", "&")
    # catalogue-only parts (most Qorvo parts) get the review link on the search results
    found = client.get("/find?q=PAC5527")
    assert "/reviews/qorvo-pac5527-motor-driver" in found.text
    assert rv.for_part("PAC5527QM") and rv.for_part("pac5527qm") and not rv.for_part("ISO7741")


def test_application_page_lists_reviews_for_its_diagram(client):
    r = rv.get("qorvo-pac5527-motor-driver")
    a = next(a for a in r["applications"] if a["kind"] == "library")
    page = client.get(f"/business/applications/{a['index']}")
    assert page.status_code == 200 and "Technology reviews for parts in this diagram" in page.text
    assert "/reviews/qorvo-pac5527-motor-driver" in page.text


def test_nav_places_reviews_under_products(client):
    products = next(s for s in nav.NAV if s[0] == "products")  # owner, 23 Oct 2026: Part reviews sit with the parts
    assert ("Part reviews", "/reviews") in [(i[0], i[1]) for i in products[2]]
    assert nav.place("/reviews") == ("products", "/reviews")
    assert nav.place("/reviews/qorvo-pac5527-motor-driver") == ("products", "/reviews")
    assert nav.place("/manage/reviews") == ("manage", "/manage/verify")  # a tab of Site data, 23 Oct 2026
    assert 'href="/reviews"' in client.get("/parts").text
