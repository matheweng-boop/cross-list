"""Owner, 24 Oct 2026: one storyline through every research report (decision, answer, needed now, what to say
externally, next steps), shown as the Bottom line under the title, as next steps at the end and as a thread line at the
end of every main section."""

import html
import re
from pathlib import Path

import pytest

from app.services import prelim
from app.services import reports as rp

ROOT = Path(__file__).resolve().parents[1]
BODIES = ROOT / "app/web/templates/business/reports"
THREAD = '<p class="rpt-thread"><b>For the decision:</b>'


def test_every_report_has_a_complete_storyline():
    rows = rp.reports()
    assert len(rows) >= 14
    for r in rows:
        assert rp.story_problems(r) == [], r["slug"]
        assert r["story_issues"] == []
        assert r["decision"].endswith("?") and r["answer"]["conf"] in rp.CONFIDENCE
        assert all(len(s["why"]) > 20 for s in r["next_steps"]), r["slug"]


def test_story_check_catches_gaps_and_blocked_words():
    bad = {"decision": "Should we?", "answer": {"text": "Yes", "conf": "sure"}, "needed_now": [],
           "say_externally": "Our roadmap has it, made in our own fab; the margin is fine (est).",
           "next_steps": [{"what": "x", "who": "BU"}]}  # fmt: skip
    probs = " ".join(rp.story_problems(bad))
    assert "conf" in probs and "needed_now" in probs and "three steps" in probs
    assert set(rp.blocked_words(bad["say_externally"])) == {"roadmap", "fab", "margin", "est"}
    assert rp.blocked_words("We are interested in the latest test results and fabric.") == []
    assert rp.story_problems({}) and "no decision" in rp.story_problems({})


def test_say_externally_is_safe_to_say():
    for r in rp.reports():
        text = r["say_externally"]
        assert rp.blocked_words(text) == [], (r["slug"], rp.blocked_words(text))
        assert 2 <= text.count(". ") + 1 <= 4, r["slug"]  # two or three sentences
        assert "$" not in text and "Not enough data" not in text, r["slug"]


def test_report_and_case_pairs_share_or_hand_over_the_decision():
    for r in rp.reports():
        cases = [s for s in r.get("see_also") or [] if (rp.report(s) or {}).get("kind") == "idea"]
        if r["kind"] != "report" or not cases:
            continue
        handed = {s.get("case") for s in r["next_steps"]}
        shared = any(rp.report(c)["decision"] == r["decision"] for c in cases)
        assert shared or handed & set(cases), r["slug"]
        assert all(rp.report(c) for c in handed - {None})


def test_every_body_section_ends_with_a_thread_line():
    for r in rp.reports():
        if r["kind"] == "idea":
            c = prelim.raw(r["slug"])
            th = c.get("thread") or {}
            need = {"position", "market", "outlook", "features", "asp", "risks"}
            need |= {"benefit"} if c.get("customer_benefit") else set()
            need |= {"product"} if c.get("product") else set()
            need |= {"questions"} if c.get("questions") else set()
            assert need <= set(th), (r["slug"], need - set(th))
            assert set(th) <= set(rp.CASE_THREADS), r["slug"]
            assert all(10 < len(v) < 200 for v in th.values()), r["slug"]
            continue
        body = (BODIES / f"{r['slug']}.html").read_text()
        sections = re.split(r"<h2>", body)[1:]
        assert sections, r["slug"]
        for sec in sections:
            if sec.startswith("Sources"):
                assert THREAD not in sec
                continue
            assert THREAD in sec, (r["slug"], sec[:40])


def test_bottom_line_renders_on_every_report_and_the_list(client):
    for r in rp.reports():
        page = html.unescape(client.get(f"/business/reports/{r['slug']}").text)
        assert 'class="rpt-bl"' in page and "Bottom line" in page, r["slug"]
        assert r["decision"] in page and r["answer"]["text"] in page and r["say_externally"] in page
        assert all(s["what"] in page and s["who"] in page for s in r["next_steps"])
        # under the title, above the summary box; the checklist comes after the body and before the sources
        assert page.index("<h1>") < page.index('class="rpt-bl"') < page.index('class="brief"'), r["slug"]
        assert page.index('class="brief"') < page.index('class="rpt-end"'), r["slug"]
        if "<h2>Sources</h2>" in page:
            assert page.index('class="rpt-end"') < page.index("<h2>Sources</h2>")
        assert page.count('class="rpt-thread"') >= 4, r["slug"]
    listing = html.unescape(client.get("/business/reports").text)
    for r in rp.reports():
        assert f"<b>Decision:</b> {r['decision']}" in listing


def test_hot_swap_storyline_is_the_owners_example(client):
    r = rp.report("auto-hv-hot-swap")
    assert "reinforced successor to Si875x" in r["decision"]
    assert any(s.get("case") == "iso-current-sense-charging" for s in r["next_steps"])
    page = client.get("/business/reports/auto-hv-hot-swap").text
    assert 'href="/business/reports/iso-current-sense-charging">→ the case' in page


CHROMIUM = Path("/opt/pw-browsers/chromium")


def _chromium() -> str | None:
    return str(CHROMIUM) if CHROMIUM.exists() else None  # never "playwright install"


@pytest.mark.skipif(_chromium() is None, reason="no Chromium in /opt/pw-browsers")
def test_report_pages_fit_390px(client, chromium):
    """Uses the session's one Chromium (tests/conftest.py): a second sync Playwright in the same run fails."""

    def serve(route):
        url = route.request.url.replace("http://bizdev.test", "")
        res = client.get(url)
        route.fulfill(status=res.status_code, body=res.content,
                      headers={"content-type": res.headers.get("content-type", "text/html")})  # fmt: skip

    ctx = chromium.new_context(viewport={"width": 390, "height": 900})
    page = ctx.new_page()
    page.route("http://bizdev.test/**", serve)
    for r in rp.reports():
        page.goto(f"http://bizdev.test/business/reports/{r['slug']}")
        box = page.locator(".rpt-bl").bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= 390, r["slug"]
        end = page.locator(".rpt-end").bounding_box()
        assert end and end["x"] + end["width"] <= 390, r["slug"]
        wide = page.evaluate("document.documentElement.scrollWidth")
        assert wide <= 390, (r["slug"], wide)
    ctx.close()
