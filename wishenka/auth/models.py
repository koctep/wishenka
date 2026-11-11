"""Authentication domain models and exception hierarchies."""

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuthValidationError(Exception):
    """Base exception for authentication validation failures."""


class InvalidSignatureError(AuthValidationError):
    """Raised when Telegram initData hash does not match expected HMAC-SHA256 signature."""


class ExpiredInitDataError(AuthValidationError):
    """Raised when Telegram initData auth_date timestamp has expired or is invalid."""


class MalformedInitDataError(AuthValidationError):
    """Raised when Telegram initData string is missing required fields or has invalid format."""


class TelegramUser(BaseModel):
    """Telegram user profile extracted and verified from WebApp initData."""

    model_config = ConfigDict(frozen=True)

    id: int = Field(description="Telegram numeric user ID")
    first_name: str = Field(description="User first name")
    last_name: str | None = Field(default=None, description="User last name if provided")
    username: str | None = Field(default=None, description="Telegram username without @")
    language_code: str | None = Field(
        default=None, description="User language code (e.g. 'ru', 'en')"
    )
    is_premium: bool = Field(default=False, description="Whether user has Telegram Premium")


class TelegramInitData(BaseModel):
    """Parsed representation of Telegram WebApp initData payload."""

    model_config = ConfigDict(frozen=True)

    auth_date: int = Field(description="Unix timestamp of authentication")
    hash: str = Field(description="HMAC-SHA256 signature provided by Telegram")
    query_id: str | None = Field(default=None, description="Unique WebApp query ID")
    user: TelegramUser = Field(description="Validated user profile")
    raw_params: dict[str, Any] = Field(
        default_factory=dict, description="All parsed query parameters"
    )


class SessionClaims(BaseModel):
    """Payload stored inside signed session token."""

    model_config = ConfigDict(frozen=True)

    telegram_id: int = Field(description="Telegram numeric user ID")
    first_name: str = Field(description="User first name")
    username: str | None = Field(default=None, description="Telegram username")
    user_id: int | None = Field(default=None, description="Internal database user ID")
    iat: int = Field(description="Issued at timestamp")
    exp: int = Field(description="Expiration timestamp")


@dataclass(frozen=True)
class AuthenticatedUser:
    """Security context resolved for request caller."""

    telegram_id: int
    first_name: str
    username: str | None = None
    auth_method: str = "cookie"
    user_id: int | None = None


class TelegramAuthRequest(BaseModel):
    """Request payload for /api/auth/telegram."""

    init_data: str = Field(description="Raw Telegram.WebApp.initData query string")


class AuthResponse(BaseModel):
    """Response payload for successful authentication exchange."""

    token: str = Field(description="Signed session token")
    user: TelegramUser = Field(description="Verified Telegram user profile")
    user_id: int | None = Field(default=None, description="Internal database user ID")
