"""Domain models for user persistence."""

from dataclasses import dataclass
from datetime import datetime

from wishenka.i18n.locale import LocaleSource, SupportedLocale


@dataclass(frozen=True)
class UserRecord:
    """Represents a persisted user profile in the database."""

    id: int
    telegram_id: int
    first_name: str
    last_name: str | None
    username: str | None
    language_code: str | None
    is_premium: bool
    created_at: datetime
    updated_at: datetime
    locale: SupportedLocale = "en"
    locale_source: LocaleSource = "auto"

    @property
    def display_name(self) -> str:
        """Return formatted user display name combining first and optional last name."""
        full = f"{self.first_name} {self.last_name or ''}".strip()
        return full or self.first_name
