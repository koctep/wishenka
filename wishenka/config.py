"""Configuration settings for Wishenka application."""

import ipaddress
import json
from collections.abc import Iterable, Mapping
from typing import Annotated, Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

DEFAULT_SSRF_MAX_RESPONSE_BYTES: int = 2 * 1024 * 1024  # 2 MiB (2,097,152 bytes)
DEFAULT_SSRF_ALLOWED_SCHEMES: tuple[str, ...] = ("http", "https")
SUPPORTED_SSRF_SCHEMES: frozenset[str] = frozenset({"http", "https"})
DEFAULT_SSRF_FORBIDDEN_CIDRS: tuple[str, ...] = (
    "0.0.0.0/8",
    "10.0.0.0/8",
    "100.64.0.0/10",
    "127.0.0.0/8",
    "169.254.0.0/16",
    "172.16.0.0/12",
    "192.0.0.0/24",
    "192.0.2.0/24",
    "192.168.0.0/16",
    "198.18.0.0/15",
    "198.51.100.0/24",
    "203.0.113.0/24",
    "224.0.0.0/4",
    "240.0.0.0/4",
    "255.255.255.255/32",
    "::/128",
    "::1/128",
    "fc00::/7",
    "fe80::/10",
    "ff00::/8",
)


def _parse_env_string_tuple(value: Any, *, field_name: str) -> tuple[str, ...]:
    """Parse a JSON array, comma-separated string, or iterable of strings."""
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            raise ValueError(f"{field_name} must not be blank")
        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"{field_name} must be a valid JSON array or comma-separated list"
                ) from exc
            if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
                raise ValueError(f"{field_name} JSON value must be an array of strings")
            return tuple(parsed)
        parts = [segment.strip() for segment in raw.split(",")]
        if any(not part for part in parts):
            raise ValueError(f"{field_name} must not contain empty comma-separated entries")
        return tuple(parts)

    if isinstance(value, (bytes, bytearray, Mapping)) or not isinstance(value, Iterable):
        raise ValueError(f"{field_name} must be a sequence of strings")

    items = list(value)
    if not all(isinstance(item, str) for item in items):
        raise ValueError(f"{field_name} entries must all be strings")
    return tuple(items)


class Settings(BaseSettings):
    """Application runtime settings loaded from environment or defaults."""

    app_name: str = "wishenka"
    environment: str = "development"
    debug: bool = False
    log_level: str = "INFO"
    log_json: bool = False
    sqlite_db_path: str = "data/wishenka.db"
    database_url: str = "sqlite+aiosqlite:///data/wishenka.db"
    bot_token: str = "dummy_bot_token"
    secret_key: str = "wishenka_default_secret_key_change_in_prod"
    session_secret_key: str = "wishenka_default_secret_key_change_in_prod"
    session_cookie_name: str = "session_id"
    session_ttl_seconds: int = 2592000
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "none"
    session_cookie_domain: str | None = None
    telegram_auth_max_age_seconds: int = 86400
    application_origin: str = "http://testserver"
    csrf_secret_key: str = "wishenka_csrf_default_change_in_prod"
    mini_app_url: str = ""
    telegram_bot_username: str = ""
    telegram_app_short_name: str = ""
    invite_token_ttl_seconds: int = 7 * 86400
    wishlist_retention_days: int = 30
    idempotency_retention_hours: int = Field(default=24, ge=1)
    background_cleanup_interval_seconds: int = 3600
    background_cleanup_enabled: bool = True
    receipt_notice_worker_enabled: bool = True
    receipt_notice_poll_interval_seconds: float = Field(default=5.0, gt=0)
    receipt_notice_max_attempts: int = Field(default=5, ge=1, le=20)
    receipt_notice_backoff_base_seconds: int = Field(default=30, ge=1)
    receipt_notice_backoff_max_seconds: int = 3600
    receipt_notice_request_timeout_seconds: float = Field(default=30.0, gt=0)
    receipt_notice_claim_lease_seconds: int = 300
    receipt_notice_summary_window_seconds: int = Field(default=300, ge=60)
    receipt_notice_retention_days: int = Field(default=30, ge=1)
    birthday_retention_days: int = Field(default=30, ge=1)
    bot_destination_retention_days: int = Field(default=30, ge=1)
    reminder_retention_days: int = Field(default=30, ge=1)
    receipt_dedup_retention_days: int = Field(default=30, ge=1)
    bot_capture_order_retention_days: int = Field(default=30, ge=2)
    notice_global_per_second: int = Field(default=20, ge=1, le=30)
    notice_chat_interval_seconds: int = Field(default=1, ge=1)
    notice_reminder_lead_days: tuple[int, ...] = (7,)
    support_chat_id: int | None = None
    support_admin_ids: tuple[int, ...] = ()
    support_session_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    support_max_message_length: int = Field(default=2000, ge=100, le=3500)
    support_rate_limit_window_seconds: int = Field(default=3600, ge=60)
    support_rate_limit_max_tickets: int = Field(default=3, ge=1, le=50)
    public_rate_limit_enabled: bool = True
    public_rate_limit_max_requests: int = Field(default=30, ge=1, le=10000)
    public_rate_limit_window_seconds: int = Field(default=60, ge=1, le=86400)
    public_rate_limit_trust_proxy_headers: bool = False
    public_rate_limit_max_clients: int = Field(default=10000, ge=100)
    ssrf_max_response_bytes: int = Field(default=DEFAULT_SSRF_MAX_RESPONSE_BYTES, ge=1)
    ssrf_allowed_schemes: Annotated[tuple[str, ...], NoDecode] = DEFAULT_SSRF_ALLOWED_SCHEMES
    ssrf_forbidden_cidrs: Annotated[tuple[str, ...], NoDecode] = DEFAULT_SSRF_FORBIDDEN_CIDRS

    model_config = SettingsConfigDict(
        env_prefix="WISHENKA_",
        env_file=".env",
        extra="ignore",
    )

    @field_validator("ssrf_max_response_bytes", mode="before")
    @classmethod
    def _validate_ssrf_max_response_bytes(cls, value: Any) -> Any:
        """Reject non-integer types such as bool and float before int coercion."""
        if isinstance(value, (bool, float)):
            raise ValueError("ssrf_max_response_bytes must be a positive integer")
        return value

    @field_validator("ssrf_allowed_schemes", mode="before")
    @classmethod
    def _validate_ssrf_allowed_schemes(cls, value: Any) -> tuple[str, ...]:
        """Parse and validate non-empty supported URL schemes in lowercase."""
        items = _parse_env_string_tuple(value, field_name="ssrf_allowed_schemes")
        normalized: list[str] = []
        seen: set[str] = set()
        for item in items:
            if not item or any(ch.isspace() for ch in item) or "/" in item or ":" in item:
                raise ValueError(f"Invalid URL scheme entry: {item!r}")
            scheme = item.lower()
            if scheme not in SUPPORTED_SSRF_SCHEMES:
                raise ValueError(
                    f"Unsupported URL scheme {item!r}; allowed: {sorted(SUPPORTED_SSRF_SCHEMES)}"
                )
            if scheme not in seen:
                seen.add(scheme)
                normalized.append(scheme)
        if not normalized:
            raise ValueError("ssrf_allowed_schemes must contain at least one supported scheme")
        return tuple(normalized)

    @field_validator("ssrf_forbidden_cidrs", mode="before")
    @classmethod
    def _validate_ssrf_forbidden_cidrs(cls, value: Any) -> tuple[str, ...]:
        """Parse and canonicalize IPv4/IPv6 CIDR network overrides."""
        items = _parse_env_string_tuple(value, field_name="ssrf_forbidden_cidrs")
        canonical: list[str] = []
        seen: set[str] = set()
        for item in items:
            if not item or any(ch.isspace() for ch in item):
                raise ValueError(f"Invalid CIDR entry: {item!r}")
            try:
                network = ipaddress.ip_network(item, strict=False)
            except ValueError as exc:
                raise ValueError(f"Invalid CIDR network {item!r}: {exc}") from exc
            cidr = str(network)
            if cidr not in seen:
                seen.add(cidr)
                canonical.append(cidr)
        return tuple(canonical)

    @model_validator(mode="after")
    def _check_receipt_notice_limits(self) -> "Settings":
        """Reject notice limits that contradict each other."""
        if self.receipt_notice_backoff_max_seconds < self.receipt_notice_backoff_base_seconds:
            raise ValueError("receipt_notice_backoff_max_seconds must be >= the backoff base")
        if (
            self.receipt_notice_claim_lease_seconds
            < self.receipt_notice_request_timeout_seconds + 30
        ):
            raise ValueError(
                "receipt_notice_claim_lease_seconds must be >= the request timeout plus 30"
            )
        if self.receipt_notice_poll_interval_seconds > self.receipt_notice_summary_window_seconds:
            raise ValueError(
                "receipt_notice_poll_interval_seconds must not exceed the summary window"
            )
        if not self.notice_reminder_lead_days or any(
            day <= 0 for day in self.notice_reminder_lead_days
        ):
            raise ValueError("notice_reminder_lead_days must contain positive day values")
        return self
