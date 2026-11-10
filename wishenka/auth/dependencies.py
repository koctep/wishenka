"""FastAPI security dependencies for resolving authentication context."""

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status

from wishenka.auth.models import (
    AuthenticatedUser,
    AuthValidationError,
)
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings

logger = logging.getLogger("wishenka.auth")


def get_settings(request: Request) -> Settings:
    """Extract settings from application state or create default instance."""
    app_settings = getattr(request.app.state, "settings", None)
    if isinstance(app_settings, Settings):
        return app_settings
    return Settings()


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
    if auth_header and auth_header.startswith("Bearer "):
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
