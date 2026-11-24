"""Authentication routes for Telegram WebApp login and session management."""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from wishenka.auth.dependencies import (
    get_current_user,
    get_settings,
    get_user_store,
)
from wishenka.auth.init_data import validate_telegram_init_data
from wishenka.auth.models import (
    AuthenticatedUser,
    AuthResponse,
    AuthValidationError,
    TelegramAuthRequest,
)
from wishenka.auth.session import (
    SessionTokenService,
    delete_session_cookie,
    set_session_cookie,
)
from wishenka.config import Settings
from wishenka.i18n.dependencies import LocaleDep
from wishenka.users.store import UserStore, UserStoreBusyError
from wishenka.web.security import csrf_value

logger = logging.getLogger("wishenka.auth")

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/telegram", response_model=AuthResponse)
async def auth_telegram(
    payload: TelegramAuthRequest,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> AuthResponse:
    """Exchange Telegram WebApp initData for signed session token and cookie."""
    try:
        user = validate_telegram_init_data(
            init_data_raw=payload.init_data,
            bot_token=settings.bot_token,
            max_age_seconds=settings.telegram_auth_max_age_seconds,
        )
    except AuthValidationError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid initData: {err}",
        ) from err

    try:
        user_record = await user_store.upsert_user(user)
    except UserStoreBusyError as err:
        logger.warning(
            "Telegram auth busy while persisting user",
            extra={
                "event": "auth_user_store_busy",
                "status_code": status.HTTP_503_SERVICE_UNAVAILABLE,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(err),
        ) from err

    service = SessionTokenService(
        secret_key=settings.secret_key,
        default_ttl_seconds=settings.session_ttl_seconds,
    )
    token = service.create_token(
        telegram_id=user.id,
        first_name=user.first_name,
        username=user.username,
        user_id=user_record.id,
    )

    set_session_cookie(response=response, token=token, settings=settings)
    logger.info(
        "User %s authenticated successfully via Telegram WebApp",
        user.id,
        extra={
            "telegram_id": user.id,
            "username": user.username,
            "user_id": user_record.id,
            "event": "auth_success",
        },
    )
    return AuthResponse(
        token=token,
        user=user,
        user_id=user_record.id,
        locale=user_record.locale,
    )


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, Any]:
    """Clear session cookie and log out caller."""
    delete_session_cookie(response=response, settings=settings)

    telegram_id: int | None = None
    username: str | None = None
    token = request.cookies.get(settings.session_cookie_name)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    if token:
        service = SessionTokenService(
            secret_key=settings.secret_key,
            default_ttl_seconds=settings.session_ttl_seconds,
        )
        try:
            claims = service.verify_token(token)
            telegram_id = claims.telegram_id
            username = claims.username
        except Exception:
            pass

    if telegram_id is not None:
        logger.info(
            "User %s logged out",
            telegram_id,
            extra={
                "telegram_id": telegram_id,
                "username": username,
                "event": "logout",
            },
        )
    else:
        logger.info(
            "Session logged out",
            extra={
                "event": "logout",
            },
        )
    return {"status": "ok"}


@router.get("/me")
async def get_me(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    locale: LocaleDep,
) -> dict[str, Any]:
    """Retrieve current authenticated user context."""
    return {
        "telegram_id": current_user.telegram_id,
        "first_name": current_user.first_name,
        "username": current_user.username,
        "auth_method": current_user.auth_method,
        "user_id": current_user.user_id,
        "locale": locale,
    }


@router.get("/csrf")
async def get_csrf(
    request: Request,
    response: Response,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> dict[str, str]:
    """Issue a CSRF value bound to the verified session cookie."""
    cookie = request.cookies.get(settings.session_cookie_name)
    if not cookie or current_user.auth_method != "cookie":
        logger.warning(
            "CSRF token request rejected: cookie session required for user %s",
            current_user.telegram_id,
            extra={
                "event": "csrf_cookie_missing",
                "telegram_id": current_user.telegram_id,
            },
        )
        raise HTTPException(status_code=401, detail="Cookie session required")
    response.headers["Cache-Control"] = "no-store"
    logger.info(
        "CSRF token issued for user %s",
        current_user.telegram_id,
        extra={
            "event": "csrf_token_issued",
            "telegram_id": current_user.telegram_id,
        },
    )
    return {"csrf_token": csrf_value(settings.csrf_secret_key, cookie)}
