"""FastAPI security dependencies for resolving authentication context."""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from wishenka.auth.models import (
    AuthenticatedUser,
    AuthValidationError,
    SessionClaims,
)
from wishenka.auth.session import SessionTokenService, compute_revocation_subject_hash
from wishenka.config import Settings
from wishenka.users.store import UserStore
from wishenka.wishlists.store import WishlistStore

logger = logging.getLogger("wishenka.auth")


def get_settings(request: Request) -> Settings:
    """Extract settings from application state or create default instance."""
    app_settings = getattr(request.app.state, "settings", None)
    if isinstance(app_settings, Settings):
        return app_settings
    return Settings()


def get_user_store(request: Request) -> UserStore:
    """Retrieve UserStore from application state or create default instance."""
    store = getattr(request.app.state, "user_store", None)
    if isinstance(store, UserStore):
        return store
    settings = getattr(request.app.state, "settings", None) or Settings()
    return UserStore(settings.database_url)


async def _is_session_active(
    request: Request,
    settings: Settings,
    claims: SessionClaims,
) -> bool:
    """Verify that the user still exists and the token has not been revoked."""
    wishlist_store = getattr(request.app.state, "wishlist_store", None)
    engine = getattr(wishlist_store, "engine", None)
    if not isinstance(engine, AsyncEngine):
        return True

    if isinstance(wishlist_store, WishlistStore):
        async with wishlist_store.read_transaction() as conn:
            return await _session_row_active(conn, settings, claims)

    async with engine.connect() as raw_conn:
        conn = await raw_conn.execution_options(read_only=True)
        await conn.begin()
        try:
            return await _session_row_active(conn, settings, claims)
        finally:
            if conn.in_transaction():
                await conn.rollback()


async def _session_row_active(
    conn: AsyncConnection,
    settings: Settings,
    claims: SessionClaims,
) -> bool:
    """Read the user or revocation row. The caller owns the transaction."""
    if claims.user_id is not None:
        has_users = await conn.scalar(
            text("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'users'")
        )
        if has_users is not None:
            active = await conn.scalar(
                text("SELECT 1 FROM users WHERE id = :uid AND telegram_id = :tg_id LIMIT 1"),
                {"uid": claims.user_id, "tg_id": claims.telegram_id},
            )
            return active is not None
        return True

    has_revocations = await conn.scalar(
        text(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'deleted_session_revocations'"
        )
    )
    if has_revocations is None:
        return True

    subject_hash = compute_revocation_subject_hash(claims.telegram_id, settings.secret_key)
    revoked_before = await conn.scalar(
        text(
            "SELECT revoked_before FROM deleted_session_revocations "
            "WHERE subject_hash = :subject_hash"
        ),
        {"subject_hash": subject_hash},
    )
    return not (revoked_before is not None and claims.iat <= int(revoked_before))


async def get_optional_current_user(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthenticatedUser | None:
    """Extract and verify user context from Authorization header or session cookie.

    Returns:
        AuthenticatedUser if valid credentials present, None if no credentials provided.

    Raises:
        HTTPException(401): If provided credentials are malformed, invalid, or expired.
    """
    token: str | None = None
    auth_method = "cookie"

    # 1. Prioritize Authorization: Bearer header
    auth_header = request.headers.get("Authorization")
    if auth_header:
        if not auth_header.startswith("Bearer ") or not auth_header[7:].strip():
            raise HTTPException(status_code=401, detail="Invalid authorization header")
        token = auth_header[7:].strip()
        auth_method = "bearer"

    # 2. Fall back to session cookie
    if not token:
        token = request.cookies.get(settings.session_cookie_name)
        if not token:
            token = request.cookies.get("session_id") or request.cookies.get("wishenka_session")
        if token:
            auth_method = "cookie"

    # 3. If no credentials provided, return None (anonymous guest access)
    if not token:
        return None

    # 4. Verify token
    service = SessionTokenService(
        secret_key=settings.secret_key,
        default_ttl_seconds=settings.session_ttl_seconds,
    )
    try:
        claims = service.verify_token(token)
    except AuthValidationError as err:
        logger.warning(
            "Session token verification failed: %s",
            err,
            extra={
                "event": "auth_failure",
                "reason": "invalid_session_token",
                "auth_method": auth_method,
                "error_type": type(err).__name__,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid session token: {err}",
            headers={"WWW-Authenticate": "Bearer"},
        ) from err

    if not await _is_session_active(request, settings, claims):
        subject_hash = compute_revocation_subject_hash(claims.telegram_id, settings.secret_key)
        logger.warning(
            "Session token rejected: account deleted or session revoked",
            extra={
                "event": "session_rejected_revoked_or_deleted",
                "subject_hash_prefix": subject_hash[:12],
                "auth_method": auth_method,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session revoked or account deleted",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.debug(
        "Resolved session user %s via %s",
        claims.telegram_id,
        auth_method,
        extra={
            "telegram_id": claims.telegram_id,
            "username": claims.username,
            "auth_method": auth_method,
            "event": "auth_session_resolved",
        },
    )

    return AuthenticatedUser(
        telegram_id=claims.telegram_id,
        first_name=claims.first_name,
        username=claims.username,
        auth_method=auth_method,
        user_id=claims.user_id,
    )


async def get_current_user(
    user: Annotated[AuthenticatedUser | None, Depends(get_optional_current_user)],
) -> AuthenticatedUser:
    """Enforce authenticated user context for protected endpoints.

    Raises:
        HTTPException(401): If user is unauthenticated.
    """
    if user is None:
        logger.warning(
            "Unauthenticated access attempt to protected endpoint",
            extra={"event": "auth_failure", "reason": "missing_credentials"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
