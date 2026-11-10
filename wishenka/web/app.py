"""FastAPI application factory."""

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from wishenka.config import Settings
from wishenka.logging import configure_logging
from wishenka.web.routes.auth import router as auth_router
from wishenka.web.routes.wishlists import router as wishlist_router
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

logger = logging.getLogger("wishenka.web")


class ShareTokenAccessFilter(logging.Filter):
    """Remove public capability tokens from Uvicorn access records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) == 5:
            client, method, path, version, status = record.args
            if isinstance(path, str) and path.startswith("/api/public/wishlists/"):
                record.args = (client, method, "/api/public/wishlists/{token}", version, status)
        return True


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for structured request and response logging with execution time."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()
        path = request.url.path
        if path.startswith("/api/public/wishlists/"):
            path = "/api/public/wishlists/{token}"
        logger.debug(
            "HTTP request started: %s %s",
            request.method,
            path,
            extra={"method": request.method, "path": path},
        )
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "HTTP request completed: %s %s status=%d duration=%.2fms",
                request.method,
                path,
                response.status_code,
                duration_ms,
                extra={
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            return response
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "HTTP request unhandled exception: %s %s duration=%.2fms",
                request.method,
                path,
                duration_ms,
                extra={
                    "method": request.method,
                    "path": path,
                    "duration_ms": round(duration_ms, 2),
                },
            )
            raise


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure the FastAPI application instance.

    Args:
        settings: Application settings override. Defaults to Settings().

    Returns:
        Configured FastAPI application instance.
    """
    if settings is None:
        settings = Settings()

    configure_logging(log_level=settings.log_level, json_logs=settings.log_json)
    access_logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, ShareTokenAccessFilter) for item in access_logger.filters):
        access_logger.addFilter(ShareTokenAccessFilter())

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await app.state.wishlist_store.initialize()
        logger.info(
            "Wishenka web application starting up",
            extra={
                "app_name": settings.app_name,
                "environment": settings.environment,
                "debug": settings.debug,
                "log_level": settings.log_level,
            },
        )
        yield
        await app.state.wishlist_store.engine.dispose()
        logger.info("Wishenka web application shutting down")

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.wishlist_store = WishlistStore(settings.database_url)
    app.state.domain_service = WishlistService(store=app.state.wishlist_store)

    app.add_middleware(RequestLoggingMiddleware)
    app.include_router(auth_router)
    app.include_router(wishlist_router)

    @app.get("/healthz")
    async def healthcheck() -> dict[str, Any]:
        """Health check endpoint for liveness and readiness probes."""
        logger.debug("Healthcheck endpoint probed")
        return {"status": "ok"}

    return app
