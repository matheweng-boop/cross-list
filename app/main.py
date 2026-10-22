"""FastAPI application factory."""

import hashlib
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import PROJECT_ROOT, get_settings
from app.db import Base, init_engine
from app.models import BusinessInput, Package, Part
from app.services.seed import UNOFFICIAL, UNOFFICIAL_DIR, ensure_local_user, load_file

SYNTHETIC_FILE = PROJECT_ROOT / "data" / "synthetic" / "demo.yaml"


def load_real_if_changed(session: Session) -> bool:
    """Load data/real/*.yaml when the files differ from the last load (server deploys).

    Parts are updated in place, so engineer feedback and cached prices are kept. The unofficial overlays
    (data/real/unofficial/) and the use_unofficial_data setting count as part of the data: switching the setting off or
    deleting the folder reloads every file without them, which removes their values from the database.
    """
    real = PROJECT_ROOT / "data" / "real"
    files = sorted(real.glob("*.yaml"))
    use_unofficial = get_settings().use_unofficial_data
    overlays = sorted((real / UNOFFICIAL_DIR).glob("*.yaml")) if use_unofficial else []
    digest = hashlib.sha256(
        b"".join(f.read_bytes() for f in files)
        + b"".join(f.name.encode() + f.read_bytes() for f in overlays)
        + f"unofficial={use_unofficial}".encode()
    ).hexdigest()
    marker = get_settings().data_dir / "real_data.sha256"
    if marker.exists() and marker.read_text().strip() == digest:
        return False
    for path in files:
        load_file(session, path, unofficial=use_unofficial)
    session.flush()
    # packages defined only by an overlay that no part uses any more (overlay switched off or removed)
    for pkg in session.scalars(select(Package).where(Package.name.startswith(UNOFFICIAL))):
        if not session.scalar(select(func.count(Part.id)).where(Part.package_id == pkg.id)):
            session.delete(pkg)
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
        # the owner deleted the retired commercial inputs (ASPs and volumes), 22 Oct 2026: nothing proprietary is kept
        session.execute(delete(BusinessInput))
        empty = session.scalar(select(func.count(Part.id))) == 0
        if get_settings().load_real_on_start:
            load_real_if_changed(session)
        elif empty and seed_synthetic:
            load_file(session, SYNTHETIC_FILE, synthetic=True)
        session.commit()


def _warm_caches() -> None:
    """Parse the catalogues and data files and compute per-function candidates once, after start-up."""
    try:
        from app.db import get_session
        from app.services import automotive, blocks, broadcast, opportunity, products, refdesigns, rf_bands, rf_coverage

        blocks.catalog_rows()
        blocks.catalog_parts()
        products._catalogue_index()
        blocks.templates()
        blocks.background_templates()
        refdesigns.designs()
        broadcast.documents()
        rf_coverage.parts()
        rf_coverage.competitor_parts()
        rf_bands.rf_parts()
        rf_bands.band_counts()
        opportunity.customers()
        session = next(get_session())
        try:
            blocks.counts(session)
            blocks.requirements(session)
            products.index(session)
            from app.services import validation

            validation._part_checks(session)
            automotive.build(session)
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
    from app.web.automotive import router as automotive_router
    from app.web.blocks import router as blocks_router
    from app.web.broadcast import router as broadcast_router
    from app.web.business import router as business_router
    from app.web.competitors import router as competitors_router
    from app.web.feedback import router as feedback_router
    from app.web.pipeline import router as pipeline_router
    from app.web.portfolio import router as portfolio_router
    from app.web.requests import router as requests_router
    from app.web.reviews import router as reviews_router
    from app.web.routes import router as web_router
    from app.web.uploads import router as uploads_router
    from app.web.verify import router as verify_router

    app.add_middleware(PasswordGate)
    app.add_middleware(GZipMiddleware, minimum_size=1000)  # the larger pages are 0.3-0.6 MB of HTML
    app.include_router(auth_router)

    @app.exception_handler(Exception)
    async def server_error(request: Request, exc: Exception):
        """A failed page keeps its URL (search and filters) and says so; API calls get JSON. Nothing is retried."""
        logging.getLogger(__name__).exception("request failed: %s", request.url.path)
        if request.url.path.startswith("/api/"):
            return JSONResponse({"error": "The calculation failed. Nothing was saved; try again."}, status_code=500)
        from app.web.routes import templates

        return templates.TemplateResponse(request, "error.html", {"url": str(request.url)}, status_code=500)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        """Pages get a readable page (not found, bad input); API calls and HTMX fragments keep the JSON / text."""
        if request.url.path.startswith("/api/") or request.headers.get("HX-Request") or exc.status_code < 400:
            return await http_exception_handler(request, exc)
        from app.web.routes import templates

        title = {404: "Not found", 400: "Nothing was changed", 405: "Not available"}.get(
            exc.status_code, "Not possible"
        )
        detail = (
            exc.detail if isinstance(exc.detail, str) and exc.detail not in ("Not Found", "Method Not Allowed") else ""
        )
        message = detail or (
            "This address does not exist on the site." if exc.status_code == 404 else "The request was refused."
        )
        ctx = {"title": title, "message": message}
        return templates.TemplateResponse(request, "error_status.html", ctx, status_code=exc.status_code,
                                          headers=getattr(exc, "headers", None))  # fmt: skip

    @app.exception_handler(RequestValidationError)
    async def bad_input(request: Request, exc: RequestValidationError):
        if request.url.path.startswith("/api/"):
            return await request_validation_exception_handler(request, exc)
        from app.web.routes import templates

        ctx = {
            "title": "Not found",
            "message": "The address has a value the page cannot use (for example a number that is text).",
        }
        return templates.TemplateResponse(request, "error_status.html", ctx, status_code=422)

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        return RedirectResponse("/static/favicon.svg", status_code=301)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"ok": True}

    app.include_router(api_router, prefix="/api")
    app.include_router(web_router)
    app.include_router(portfolio_router)
    app.include_router(broadcast_router)
    app.include_router(requests_router)
    app.include_router(blocks_router)
    app.include_router(business_router)
    app.include_router(competitors_router)
    app.include_router(automotive_router)
    app.include_router(pipeline_router)
    app.include_router(feedback_router)
    app.include_router(uploads_router)
    app.include_router(reviews_router)
    app.include_router(verify_router)
    return app
