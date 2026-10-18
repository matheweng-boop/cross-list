"""FastAPI application factory."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT, get_settings
from app.db import Base, init_engine
from app.models import Part
from app.services.seed import ensure_local_user, load_file

SYNTHETIC_FILE = PROJECT_ROOT / "data" / "synthetic" / "demo.yaml"


def bootstrap(engine, seed_synthetic: bool) -> None:
    # Schema is created directly for now; Alembic migrations are introduced
    # before the first real-data / multi-user deployment.
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_local_user(session)
        if seed_synthetic and session.scalar(select(func.count(Part.id))) == 0:
            load_file(session, SYNTHETIC_FILE, synthetic=True)
        session.commit()


def create_app(database_url: str | None = None, seed_synthetic: bool | None = None) -> FastAPI:
    settings = get_settings()
    engine = init_engine(database_url)
    seed = settings.seed_synthetic if seed_synthetic is None else seed_synthetic

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield

    bootstrap(engine, seed)
    app = FastAPI(title="Cross List", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "web" / "static"), name="static")

    from app.api.routes import router as api_router
    from app.web.routes import router as web_router

    app.include_router(api_router, prefix="/api")
    app.include_router(web_router)
    return app
