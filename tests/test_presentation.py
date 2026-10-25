"""Shareable > Presentation builder (owner, 25 Oct 2026): topics from the data, the selection in the address, the
preview slides, continuation slides, share-safety of every slide, saved decks (owner only), the 16:9 PDF and the
browser flow."""

import re

import pytest

from app.services import presentation as pr
from app.services import site_guard
from tests.test_browser import overflow, page  # noqa: F401  (the browser fixture)

UWB = ("title,agenda,auto_uwb.overview,auto_uwb.diagram,auto_uwb.parts,auto_uwb.together,note.uwb_signal_path,"
       "auto_uwb.facts,closing")  # fmt: skip


def test_topics_come_from_the_data_with_uwb_and_its_knowledge():
    from app.services import library, systems
    from app.services import tech_overview as to

    ids = set(pr.topic_index())
    assert {t["key"] for t in library.topics()} - {"semiconductor_cost"} <= ids  # every public deep dive
    assert {f"tech-{p['key']}" for p in to.build()["platforms"]} <= ids
    subs = {x["key"] for s in systems.systems() for x in s["subsystems"] if not x["topics"]}
    assert subs <= ids  # sub-systems without a deep dive
    uwb = pr.topic_index()["auto_uwb"]
    assert uwb["group"] == "Automotive"
    assert set(uwb["sections"]) == {"overview", "diagram", "parts", "together", "facts"}
    assert "uwb_signal_path" in uwb["notes"] and len(uwb["notes"]) >= 4
    assert "IEEE 802.15.4z" in uwb["sections"]["facts"][0]["standards"]
    assert any("UWB channel 9" in b for b in uwb["sections"]["facts"][0]["bands"])


def test_selection_and_order_round_trip_in_the_address():
    ids = pr.parse("closing, note.uwb_signal_path,title,bogus,auto_uwb.overview,title,auto_uwb.nothing")
    assert ids == ["closing", "note.uwb_signal_path", "title", "auto_uwb.overview"]
    assert pr.parse(pr.query(ids)) == ids


def test_preview_renders_every_slide_with_the_counter(client):
    r = client.get("/shareable/presentation/preview?s=" + UWB)
    assert r.status_code == 200
    n = len(pr.build(pr.parse(UWB)))
    assert n >= 9 and r.text.count('aria-roledescription="slide"') == n
    assert f"1 / {n}" in r.text and f"{n} / {n}" in r.text
    assert "Public information" in r.text and "Back to edit" in r.text
    assert "AEC-Q" in r.text  # automotive parts carry the mark


def test_long_sections_continue_on_the_next_slide():
    slides = pr.split_bullets("Lead " * 30, [f"Point {i} " + "word " * 25 for i in range(9)])
    assert len(slides) > 1 and slides[0]["lead"] and not slides[1]["lead"]
    assert sum(len(s["points"]) for s in slides) == 9
    built = pr.build(["note.uwb_signal_path"])
    assert len(built) >= 2 and built[0]["title"].endswith(f"(1/{len(built)})")


def test_every_slide_of_every_topic_is_share_safe_and_names_no_site():
    for sid in pr.all_section_ids():
        for s in pr.build([sid]):
            text = s["title"] + " " + pr._slide_text(s["body"])
            assert not pr.problems(text), (sid, pr.problems(text))
            assert not site_guard.hits(text), sid
            assert not re.search(r"\best\b", text), sid


def test_counts_are_rounded_and_the_unsafe_topic_is_left_out():
    assert any("price" in x for x in pr.left_out())
    for t in pr.topic_index().values():
        for pg in t["sections"].get("parts", []):
            for row in pg["rows"]:
                for v in row["counts"].values():
                    assert re.fullmatch(r"\d{1,2}|\d[\d,]*\+", v), v


def test_guest_builds_and_previews_but_only_the_owner_saves(make_guest, locked):
    from tests.conftest import sign_in_owner

    guest, _ = make_guest()
    assert guest.get("/shareable/presentation?s=" + UWB).status_code == 200
    assert guest.get("/shareable/presentation/preview?s=" + UWB).status_code == 200
    form = {"name": "UWB for a car maker", "s": UWB, "title": "UWB in the car", "closing": "Thank you.",
            "t.auto_uwb.overview": "UWB in the car"}  # fmt: skip
    assert guest.post("/shareable/presentation/save", data=form, follow_redirects=False).status_code == 403
    assert sign_in_owner(locked).status_code == 303
    r = locked.post("/shareable/presentation/save", data=form, follow_redirects=False)
    assert r.status_code == 303 and "deck=uwb-for-a-car-maker" in r.headers["location"]
    page_ = locked.get("/shareable/presentation")
    assert "UWB for a car maker" in page_.text
    pv = locked.get("/shareable/presentation/preview?deck=uwb-for-a-car-maker")
    assert "UWB in the car" in pv.text and "Thank you." in pv.text
    bad = locked.post("/shareable/presentation/save", data={**form, "closing": "Our roadmap and the gap"})
    assert bad.status_code == 400 and "roadmap" in bad.text
    assert "UWB for a car maker" not in guest.get("/shareable/presentation").text  # the list is the owner's
    d = locked.post("/shareable/presentation/delete", data={"deck": "uwb-for-a-car-maker"}, follow_redirects=False)
    assert d.status_code == 303
    assert "uwb-for-a-car-maker" not in locked.get("/shareable/presentation").text


def test_shareable_lists_the_builder(client):
    r = client.get("/shareable")
    assert "/shareable/presentation" in r.text and "Presentation builder" in r.text


# ---- in the browser -------------------------------------------------------------------------------------------------
@pytest.mark.browser
def test_builder_flow_preview_keys_and_reorder(page):  # noqa: F811
    expect = pytest.importorskip("playwright.sync_api").expect
    page.goto("/shareable/presentation", timeout=90_000)  # the first call builds the topic list
    page.locator(".pb-tcheck[value=auto_uwb]").check()
    items = page.locator("#pb-i-auto_uwb")
    expect(items).to_be_visible()
    items.locator("input[value='auto_uwb.overview']").check()
    items.locator("input[value='note.uwb_signal_path']").check()
    expect(page.locator("#pb-list li")).to_have_count(2)
    assert "s=auto_uwb.overview,note.uwb_signal_path" in page.url
    page.locator("#pb-list li").nth(1).locator("button[data-move='-1']").click()
    assert "s=note.uwb_signal_path,auto_uwb.overview" in page.url
    page.locator("#pb-list li").nth(1).locator("button[data-move='-1']").click()
    page.locator("#pb-preview").click()
    page.wait_for_url("**/preview?**")
    total = page.locator(".pv-deck > .pv-slide").count()
    assert total >= 3
    expect(page.locator("#pv-counter")).to_have_text(f"1 / {total}")
    page.keyboard.press("ArrowRight")
    expect(page.locator("#pv-counter")).to_have_text(f"2 / {total}")
    page.keyboard.press("ArrowLeft")
    expect(page.locator("#pv-counter")).to_have_text(f"1 / {total}")
    expect(page.locator(".pv-thumb")).to_have_count(total)
    page.locator("#pv-full").click()
    expect(page.locator("#pv-stage.pv-full")).to_have_count(1)
    page.keyboard.press("Escape")
    page.get_by_text("Back to edit").click()
    page.wait_for_url("**/shareable/presentation?**")
    expect(page.locator("#pb-list li")).to_have_count(2)
    page.locator("#pb-list li").first.locator("[data-remove]").click()
    expect(page.locator("#pb-list li")).to_have_count(1)
    assert "s=note.uwb_signal_path" in page.url


@pytest.mark.browser
def test_no_slide_overflows_and_the_pdf_has_one_slide_per_page(chromium, live_server, tmp_path):
    ctx = chromium.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.goto(live_server + "/shareable/presentation/preview?s=" + UWB, timeout=90_000)
    n = pg.locator(".pv-deck > .pv-slide").count()
    for i in range(n):
        h = pg.evaluate(
            f"(() => {{ const b = document.querySelectorAll('.pv-deck > .pv-slide')[{i}]"
            ".querySelector('.pv-body'); return b ? b.scrollHeight - b.clientHeight : 0; })()"
        )
        assert h <= 1, f"slide {i + 1} overflows by {h} px"
        pg.keyboard.press("ArrowRight")
    pdf = pg.pdf(width="13.333in", height="7.5in", print_background=True)
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) == n
    phone = chromium.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    m = phone.new_page()
    for url in ("/shareable/presentation?s=" + UWB, "/shareable/presentation/preview?s=" + UWB):
        m.goto(live_server + url)
        assert overflow(m) <= 1, url
    m.locator("#pv-next").click()
    assert m.locator("#pv-counter").inner_text() == f"2 / {n}"
    ctx.close()
    phone.close()
