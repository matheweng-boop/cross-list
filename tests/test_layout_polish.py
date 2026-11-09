"""Layout polish (owner, 22 Oct 2026): long tokens wrap, card grids fit a phone screen, inline forms line up."""

import re
from pathlib import Path

CSS = (Path(__file__).resolve().parents[1] / "app/web/static/app.css").read_text()


def test_long_words_wrap_inside_text_blocks():
    assert ".content :is(p, li, dd, dt, td, th, summary, figcaption, blockquote, legend, h1, h2, h3, h4) " \
           "{ overflow-wrap: break-word; }" in CSS
    assert ".learn-links a { white-space: nowrap; }" not in CSS


def test_auto_grids_never_force_a_column_wider_than_the_screen():
    # repeat(auto-fit|auto-fill, minmax(22rem, 1fr)) overflows a 390 px phone; the minimum is capped at 100%
    assert not re.search(r"repeat\(auto-fi(t|ll), minmax\([0-9.]+rem,", CSS)


def test_inline_form_controls_share_a_height():
    assert ".rv-search, .vf-form, .tam-review, .qa-form { align-items: stretch; }" in CSS
    assert ".review-actions input { flex: 1 1 12rem; margin: 0; height: auto;" in CSS
    assert ".feat-groups { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .6rem; " \
           "align-items: stretch; }" in CSS


def test_scripts_and_styles_are_revalidated_so_a_release_reaches_the_ipad(client):
    """Owner, 9 Nov 2026: the block diagram fix did not show on the iPad (old script kept). Scripts and styles carry
    no-cache (checked on each load; 304 while unchanged), pictures keep normal caching."""
    for path in ("/static/blocks.js", "/static/app.css"):
        r = client.get(path)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache", path
        assert client.get(path, headers={"If-None-Match": r.headers["etag"]}).status_code == 304
