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

logger = logging.getLogger("wishenka.web")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for structured request and response logging with execution time."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()
        logger.debug(
            "HTTP request started: %s %s",
            request.method,
            request.url.path,
            extra={"method": request.method, "path": request.url.path},
        )
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.info(
                "HTTP request completed: %s %s status=%d duration=%.2fms",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                extra={
                    "method": request.method,
                    "path": request.url.path,
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
                request.url.path,
                duration_ms,
                extra={
                    "method": request.method,
                    "path": request.url.path,
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

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
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
        logger.info("Wishenka web application shutting down")

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/healthz")
    async def healthcheck() -> dict[str, Any]:
        """Health check endpoint for liveness and readiness probes."""
        logger.debug("Healthcheck endpoint probed")
        return {"status": "ok"}

    return app
