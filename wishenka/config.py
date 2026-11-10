"""Configuration settings for Wishenka application."""

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

    model_config = SettingsConfigDict(
        env_prefix="WISHENKA_",
        env_file=".env",
        extra="ignore",
    )
