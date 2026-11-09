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
    bot_token: str = ""

    model_config = SettingsConfigDict(
        env_prefix="WISHENKA_",
        env_file=".env",
        extra="ignore",
    )
