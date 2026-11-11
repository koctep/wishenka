"""Authentication module for Wishenka application."""

from wishenka.auth.dependencies import (
    get_current_user,
    get_optional_current_user,
    get_settings,
    get_user_store,
)
from wishenka.auth.init_data import (
    TelegramInitDataValidator,
    parse_telegram_init_data,
    validate_telegram_init_data,
)
from wishenka.auth.models import (
    AuthenticatedUser,
    AuthResponse,
    AuthValidationError,
    ExpiredInitDataError,
    InvalidSignatureError,
    MalformedInitDataError,
    SessionClaims,
    TelegramAuthRequest,
    TelegramInitData,
    TelegramUser,
)
from wishenka.auth.session import (
    SessionTokenService,
    delete_session_cookie,
    set_session_cookie,
)

__all__ = [
    "AuthResponse",
    "AuthValidationError",
    "AuthenticatedUser",
    "ExpiredInitDataError",
    "InvalidSignatureError",
    "MalformedInitDataError",
    "SessionClaims",
    "SessionTokenService",
    "TelegramAuthRequest",
    "TelegramInitData",
    "TelegramInitDataValidator",
    "TelegramUser",
    "delete_session_cookie",
    "get_current_user",
    "get_optional_current_user",
    "get_settings",
    "get_user_store",
    "parse_telegram_init_data",
    "set_session_cookie",
    "validate_telegram_init_data",
]
