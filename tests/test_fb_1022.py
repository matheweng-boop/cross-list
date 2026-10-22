"""Owner comments of 22 Oct 2026 (daily update): precision fixes, layout changes and new sections."""

from pathlib import Path

from tests.test_pipeline import ids, real  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[1]


def test_sso8_creepage_is_at_least_not_measured():
    files = [
        ROOT / "data/business/cases/hv-extra-wide-isolation.yaml",
        ROOT / "app/web/templates/business/reports/iso7821dww-isolation.html",
        ROOT / "app/web/templates/business/reports/hv-extra-wide-isolation.background.html",
        ROOT / "data/business/reports.yaml",
    ]
    for f in files:
        text = f.read_text()
        assert "measured 8.5" not in text and "measures 8.5" not in text and "8.5 mm measured" not in text, f
    bg = files[2].read_text()
    assert "7. Summary and Future Outlook" in bg
    assert "Skyworks is currently developing a new ultra-wide-body (UWB) SOIC package" in bg


def test_walk_market_size_points_to_tam_and_is_not_logged(client, session, real):  # noqa: F811
    from sqlalchemy import select

    from app.models import SiteFeedback
    from app.services import walk

    comp = ids(client, "ISO7741DBQR")
    html = client.get(f"/parts/{comp}/walk?upto=5").text
    assert "ASP and application volumes" not in html
    assert "no public market-size estimate yet" in html or "public estimate" in html
    texts = session.scalars(select(SiteFeedback.text).where(SiteFeedback.author == walk.AUTHOR)).all()
    assert not any("market size" in t or "market-size" in t for t in texts)


def test_no_feedback_sections_at_the_bottom(client):
    caps = client.get("/business/capabilities").text
    assert 'action="/business/capabilities/feedback"' not in caps and 'id="feedback"' not in caps
    rep = client.get("/business/reports/filters-1-11ghz").text
    assert "/ask" not in rep and 'class="fb-open"' in rep  # only the floating button
    # old form targets still answer
    r = client.post("/business/capabilities/feedback", data={"kind": "idea", "text": "x"}, follow_redirects=False)
    assert r.status_code == 303


def test_walk_cards_short_heading_full_text_and_next_on_top(client, real):  # noqa: F811
    from app.services import walk

    assert walk.short_name("True-wireless (TWS) earbuds with charging case") == "True-wireless earbuds with charging case"
    assert walk.short_name("AC solid-state circuit breaker (SSCB) with air-gap relay, AC/DC current sensing") == (
        "AC solid-state circuit breaker"
    )
    comp = ids(client, "ISO7741DBQR")
    html = client.get(f"/parts/{comp}/walk").text
    assert html.index("Next: 3 Best of ours around it") < html.index('id="step-1"')  # with the step buttons on top
    assert html.count("Next: 3") == 1
    assert 'class="link-btn walk-name"' in html and 'id="walk-full"' in html
    assert "more</li>" not in html  # nothing cut off
    css = (ROOT / "app/web/static/app.css").read_text()
    assert "text-overflow: ellipsis; white-space: nowrap; }\n.walk-also" not in css
