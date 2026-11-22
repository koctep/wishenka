"""FastAPI application factory."""

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from datetime import timedelta
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from wishenka.config import Settings
from wishenka.items.fetcher import PreviewTransportConfig, safe_direct_route
from wishenka.items.preview_cache import PreviewCache
from wishenka.items.service import ItemPreviewService
from wishenka.logging import configure_logging
from wishenka.notices.sender import NoticeSender, build_sender
from wishenka.notices.store import NoticeStore
from wishenka.notices.worker import NoticeWorker
from wishenka.users.store import UserStore
from wishenka.web.rate_limit import (
    PublicLinkRateLimitMiddleware,
    SlidingWindowRateLimiter,
)
from wishenka.web.routes.auth import router as auth_router
from wishenka.web.routes.items import router as items_router
from wishenka.web.routes.items_ui import router as items_ui_router
from wishenka.web.routes.miniapp import router as miniapp_router
from wishenka.web.routes.profile import router as profile_router
from wishenka.web.routes.receipts import router as receipts_router
from wishenka.web.routes.receipts_ui import router as receipts_ui_router
from wishenka.web.routes.reservations import router as reservations_router
from wishenka.web.routes.reservations_ui import router as reservations_ui_router
from wishenka.web.routes.sharing import router as sharing_router
from wishenka.web.routes.wishlists import router as wishlist_router
from wishenka.web.security import BrowserSecurityMiddleware
from wishenka.wishlists.cleanup import background_cleanup_worker
from wishenka.wishlists.service import WishlistService
from wishenka.wishlists.store import WishlistStore

logger = logging.getLogger("wishenka.web")
notice_logger = logging.getLogger("wishenka.wishlists.notices")


class ShareTokenAccessFilter(logging.Filter):
    """Remove public capability tokens from Uvicorn access records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) == 5:
            client, method, path, version, status = record.args
            if isinstance(path, str) and path.startswith("/api/public/wishlists/"):
                record.args = (client, method, "/api/public/wishlists/{token}", version, status)
            elif isinstance(path, str) and path.startswith("/share/"):
                record.args = (client, method, "/share/{token}", version, status)
            elif isinstance(path, str) and path.startswith("/invite/"):
                raw_path = path.split("?", 1)[0]
                sanitized = (
                    "/invite/{token}/join" if raw_path.endswith("/join") else "/invite/{token}"
                )
                record.args = (client, method, sanitized, version, status)
            elif isinstance(path, str) and "?" in path:
                record.args = (client, method, path.split("?", 1)[0], version, status)
        return True


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for structured request and response logging with execution time."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()
        path = request.url.path
        if path.startswith("/api/public/wishlists/"):
            path = "/api/public/wishlists/{token}"
        elif path.startswith("/share/"):
            path = "/share/{token}"
        elif path.startswith("/invite/"):
            path = "/invite/{token}/join" if path.endswith("/join") else "/invite/{token}"
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


def _start_notice_worker(app: FastAPI, settings: Settings, injected: NoticeSender | None) -> None:
    """Start the notice worker task, or log why there is none (rows then stay ``pending``)."""
    sender: NoticeSender | None = None
    reason = "disabled_by_setting"
    if settings.receipt_notice_worker_enabled:
        sender = injected or build_sender(settings)
        reason = "no_bot_token"
    if sender is None:
        notice_logger.info(
            "Notice worker is not started",
            extra={"event": "receipt_notice_worker_disabled", "reason": reason},
        )
        return
    worker = NoticeWorker(app.state.notice_store, sender, settings)
    app.state.notice_sender = sender
    app.state.notice_task = asyncio.create_task(
        worker.run(asyncio.Event()), name="receipt_notice_worker"
    )
    notice_logger.info("Notice worker started", extra={"event": "receipt_notice_worker_started"})


async def _stop_notice_worker(app: FastAPI) -> None:
    """Cancel the notice worker task, close its sender and log the stop."""
    task: asyncio.Task[None] | None = app.state.notice_task
    sender: NoticeSender | None = app.state.notice_sender
    if task is None:
        return
    task.cancel()
    try:
        with suppress(asyncio.CancelledError):
            await task
    finally:
        if sender is not None:
            await sender.close()
        notice_logger.info(
            "Notice worker stopped", extra={"event": "receipt_notice_worker_stopped"}
        )


def create_app(
    settings: Settings | None = None, notice_sender: NoticeSender | None = None
) -> FastAPI:
    """Create and configure the FastAPI application instance.

    Args:
        settings: Application settings override. Defaults to Settings().
        notice_sender: Sender of gift notices; tests pass a fake. Defaults to a Telegram bot
            built from the settings, or no worker at all when no usable token is configured.

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
        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10, keepalive_expiry=5)
        route = safe_direct_route(limits=limits, settings=settings)
        cache: PreviewCache | None = None
        try:
            cache = PreviewCache()
            app.state.item_preview_service = ItemPreviewService(
                routes=PreviewTransportConfig(default=route, mounts={}),
                cache=cache,
                settings=settings,
            )
            await app.state.wishlist_store.initialize()
            await app.state.user_store.initialize()

            if settings.background_cleanup_enabled:
                cleanup_task = asyncio.create_task(
                    background_cleanup_worker(
                        app.state.wishlist_store, settings, notice_store=app.state.notice_store
                    ),
                    name="background_cleanup_worker",
                )
                app.state.background_cleanup_task = cleanup_task
                app.state.cleanup_task = cleanup_task

            _start_notice_worker(app, settings, notice_sender)

            logger.info(
                "Wishenka web application starting up",
                extra={
                    "app_name": settings.app_name,
                    "environment": settings.environment,
                    "debug": settings.debug,
                    "log_level": settings.log_level,
                    "ssrf_max_response_bytes": settings.ssrf_max_response_bytes,
                    "ssrf_allowed_schemes": list(settings.ssrf_allowed_schemes),
                    "ssrf_forbidden_cidr_count": len(settings.ssrf_forbidden_cidrs),
                },
            )
            yield
        finally:
            running_task: asyncio.Task[None] | None = getattr(
                app.state, "background_cleanup_task", None
            ) or getattr(app.state, "cleanup_task", None)
            try:
                try:
                    if running_task is not None:
                        running_task.cancel()
                        with suppress(asyncio.CancelledError):
                            await running_task
                finally:
                    await _stop_notice_worker(app)
            finally:
                if cache is not None:
                    cache.clear()
                app.state.item_preview_service = None
                await route.transport.aclose()
                await app.state.wishlist_store.dispose()
                await app.state.user_store.dispose()
                logger.info("Wishenka web application shutting down")

    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.wishlist_store = WishlistStore(settings.database_url)
    app.state.user_store = UserStore(settings.database_url)
    default_invite_ttl = timedelta(seconds=settings.invite_token_ttl_seconds)
    app.state.domain_service = WishlistService(
        store=app.state.wishlist_store,
        default_invite_ttl=default_invite_ttl,
    )
    app.state.background_cleanup_task = None
    app.state.cleanup_task = None
    app.state.notice_store = NoticeStore(app.state.wishlist_store, settings)
    app.state.notice_task = None
    app.state.notice_sender = None
    app.state.public_link_rate_limiter = SlidingWindowRateLimiter(
        max_requests=settings.public_rate_limit_max_requests,
        window_seconds=settings.public_rate_limit_window_seconds,
        max_clients=settings.public_rate_limit_max_clients,
    )

    app.add_middleware(PublicLinkRateLimitMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(BrowserSecurityMiddleware)
    app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
    app.include_router(miniapp_router)
    app.include_router(auth_router)
    app.include_router(profile_router)
    app.include_router(items_router)
    app.include_router(reservations_router)
    app.include_router(receipts_router)
    app.include_router(reservations_ui_router)
    app.include_router(items_ui_router)
    app.include_router(receipts_ui_router)
    app.include_router(wishlist_router)
    app.include_router(sharing_router)

    @app.get("/healthz")
    async def healthcheck() -> dict[str, Any]:
        """Health check endpoint for liveness and readiness probes."""
        logger.debug("Healthcheck endpoint probed")
        return {"status": "ok"}

    return app
