"""Configuration settings for Wishenka application."""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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
    notice_global_per_second: int = Field(default=20, ge=1, le=30)
    notice_chat_interval_seconds: int = Field(default=1, ge=1)
    notice_reminder_lead_days: tuple[int, ...] = (7,)
    support_chat_id: int | None = None
    support_admin_ids: tuple[int, ...] = ()
    support_session_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    support_max_message_length: int = Field(default=2000, ge=100, le=3500)
    support_rate_limit_window_seconds: int = Field(default=3600, ge=60)
    support_rate_limit_max_tickets: int = Field(default=3, ge=1, le=50)

    model_config = SettingsConfigDict(
        env_prefix="WISHENKA_",
        env_file=".env",
        extra="ignore",
    )

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
