import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.main import create_app
from app.models import Part


@pytest.fixture
def client(tmp_path):
    app = create_app(f"sqlite:///{tmp_path / 'test.db'}", seed_synthetic=True)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def session(client):
    with Session(get_engine()) as s:
        yield s


@pytest.fixture
def part(session):
    def get(mpn: str) -> Part:
        return session.scalars(select(Part).where(Part.mpn == mpn)).unique().one()

    return get
