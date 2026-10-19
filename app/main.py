"""FastAPI application factory."""

import hashlib
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
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


def _warm_caches() -> None:
    """Parse the catalogues and compute per-function candidates once, after start-up."""
    try:
        from app.db import get_session
        from app.services import blocks, products

        blocks.catalog_rows()
        blocks.catalog_parts()
        products._catalogue_index()
        session = next(get_session())
        try:
            blocks.counts(session)
            blocks.requirements(session)
        finally:
            session.close()
    except Exception:  # a failed warm-up only means the first request does the work
        logging.getLogger(__name__).exception("cache warm-up failed")


def create_app(database_url: str | None = None, seed_synthetic: bool | None = None) -> FastAPI:
    settings = get_settings()
    engine = init_engine(database_url)
    seed = settings.seed_synthetic if seed_synthetic is None else seed_synthetic

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # warm the large caches in the background so the first visitors do not wait (or time out) on them
        threading.Thread(target=_warm_caches, daemon=True).start()
        yield

    bootstrap(engine, seed)
    app = FastAPI(title="BizDev", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "web" / "static"), name="static")

    from app.api.routes import router as api_router
    from app.auth.gate import PasswordGate
    from app.auth.gate import router as auth_router
    from app.web.blocks import router as blocks_router
    from app.web.broadcast import router as broadcast_router
    from app.web.business import router as business_router
    from app.web.requests import router as requests_router
    from app.web.routes import router as web_router

    app.add_middleware(PasswordGate)
    app.include_router(auth_router)

    @app.exception_handler(Exception)
    async def server_error(request: Request, exc: Exception):
        """A failed page keeps its URL (search and filters) and says so; API calls get JSON. Nothing is retried."""
        logging.getLogger(__name__).exception("request failed: %s", request.url.path)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": "The calculation failed. Nothing was saved; try again."}, status_code=500)
        from app.web.routes import templates

        return templates.TemplateResponse(request, "error.html", {"url": str(request.url)}, status_code=500)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"ok": True}

    app.include_router(api_router, prefix="/api")
    app.include_router(web_router)
    app.include_router(broadcast_router)
    app.include_router(requests_router)
    app.include_router(blocks_router)
    app.include_router(business_router)
    return app
