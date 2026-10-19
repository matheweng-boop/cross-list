"""FastAPI application factory."""

import hashlib
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


def load_real_if_changed(session: Session) -> bool:
    """Load data/real/*.yaml when the files differ from the last load (server deploys).

    Parts are updated in place, so engineer feedback and cached prices are kept.
    """
    files = sorted((PROJECT_ROOT / "data" / "real").glob("*.yaml"))
    digest = hashlib.sha256(b"".join(f.read_bytes() for f in files)).hexdigest()
    marker = get_settings().data_dir / "real_data.sha256"
    if marker.exists() and marker.read_text().strip() == digest:
        return False
    for path in files:
        load_file(session, path)
    session.flush()
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(digest)
    return True


def bootstrap(engine, seed_synthetic: bool) -> None:
    # Schema is created directly for now; Alembic migrations are introduced
    # before the first real-data / multi-user deployment.
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        ensure_local_user(session)
        empty = session.scalar(select(func.count(Part.id))) == 0
        if get_settings().load_real_on_start:
            load_real_if_changed(session)
        elif empty and seed_synthetic:
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
    from app.auth.gate import PasswordGate
    from app.auth.gate import router as auth_router
    from app.web.broadcast import router as broadcast_router
    from app.web.routes import router as web_router

    app.add_middleware(PasswordGate)
    app.include_router(auth_router)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"ok": True}

    app.include_router(api_router, prefix="/api")
    app.include_router(web_router)
    app.include_router(broadcast_router)
    return app
