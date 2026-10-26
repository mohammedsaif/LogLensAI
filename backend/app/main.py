"""FastAPI application factory. Run with: uvicorn app.main:create_app --factory"""

import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import __version__
from app.ai.providers.base import AIProvider
from app.ai.providers.factory import get_provider
from app.api.v1 import analyses, misc
from app.core.config import Settings, get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, request_id_var
from app.db.models import Base
from app.db.session import Database
from app.services.incident_service import IncidentService

log = logging.getLogger("loglens.http")


def create_app(
    settings: Settings | None = None,
    provider_factory: Callable[[Settings], AIProvider | None] = get_provider,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)
    db = Database(settings.database_url)
    incidents = IncidentService(db, settings, provider_factory)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if settings.database_url.startswith("sqlite"):
            # SQLite is for tests / quick local runs. PostgreSQL schemas are managed by Alembic migrations.
            Base.metadata.create_all(db.engine)
        interrupted = incidents.mark_interrupted()
        purged = incidents.purge_expired()
        log.info(
            "startup",
            extra={
                "ai_provider": settings.ai_provider,
                "interrupted": interrupted,
                "purged": purged,
                "version": __version__,
            },
        )
        yield
        db.engine.dispose()

    app = FastAPI(
        title="LogLens AI API",
        version=__version__,
        description="Turns application logs into a five-line, evidence-referenced incident summary. "
        "Deterministic extraction first; Claude interprets a redacted evidence pack.",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.db = db
    app.state.incidents = incidents

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["*"],
        expose_headers=["Content-Disposition", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(rid[:64])
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid[:64]
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path not in ("/health/live", "/health/ready"):
            log.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - start) * 1000, 1),
                    "request_id": rid,
                },
            )
        return response

    register_exception_handlers(app)

    health = APIRouter(prefix="/health", tags=["health"])

    @health.get("/live")
    def live() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @health.get("/ready")
    def ready() -> JSONResponse:
        try:
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001
            log.exception("readiness_failed")
            return JSONResponse(status_code=503, content={"status": "unavailable", "database": "down"})
        return JSONResponse({"status": "ok", "database": "up", "ai_provider": settings.ai_provider})

    app.include_router(health)
    api_v1 = APIRouter(prefix="/api/v1")
    api_v1.include_router(analyses.router)
    api_v1.include_router(misc.router)
    app.include_router(api_v1)
    return app
