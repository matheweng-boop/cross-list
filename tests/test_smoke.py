"""The quick check (owner, 26 Oct 2026): `uv run pytest -m smoke` runs while working, together with the tests for
what changed; the full suite runs once per release with `-n auto`. The smoke set is these tests plus a few marked
@pytest.mark.smoke in the feature files: Cross a list on known parts (tests/test_cross_list.py), the data files'
consistency (tests/test_data_consistency.py) and one shareable PDF (tests/test_share_versions.py)."""

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Part
from app.web import nav

pytestmark = pytest.mark.smoke


def main_pages() -> list[str]:
    """Every page the menus and tabs link to."""
    hrefs = [h for _, _, items in (*nav.NAV, nav.UTILITY) for _, h, *_ in items]
    hrefs += list(nav.HOMES.values()) + [h for group in nav.TABS for _, h in group]
    return sorted(set(hrefs))


def test_every_main_page_opens_for_the_owner(owner):
    pages = main_pages()
    assert len(pages) > 20
    bad = {url: r.status_code for url in pages if (r := owner.get(url)).status_code != 200}
    assert bad == {}


def test_every_real_data_file_loads_and_validates(tmp_path, monkeypatch):
    """All of data/real (with the unofficial overlays), as the server loads it on a fresh disk; the loader refuses
    unknown parameters, wrong pin counts and other invalid entries."""
    from app import main
    from app.config import get_settings
    from app.db import init_engine

    monkeypatch.setattr(get_settings(), "data_dir", tmp_path / "var")
    engine = init_engine(f"sqlite:///{tmp_path / 'all.db'}")
    main.bootstrap(engine, False)
    with Session(engine) as s:
        assert main.load_real_if_changed(s) is True
        s.commit()
        assert s.scalar(select(func.count(Part.id))) > 1000
    engine.dispose()
