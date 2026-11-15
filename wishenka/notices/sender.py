"""Delivery of a gift notice to Telegram: outcome classes, the sender protocol and its bot."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from aiogram import Bot
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramEntityTooLarge,
    TelegramForbiddenError,
    TelegramMigrateToChat,
    TelegramNotFound,
    TelegramRetryAfter,
    TelegramUnauthorizedError,
)
from aiogram.utils.token import TokenValidationError, validate_token

from wishenka.config import Settings

PLACEHOLDER_TOKEN = "dummy_bot_token"  # noqa: S105 - the documented "not configured" value

# Subclasses are tested before the bases that would swallow them: TelegramEntityTooLarge is a
# TelegramNetworkError (ambiguous) but the request itself is wrong (design 7).
_REJECTED = (
    TelegramForbiddenError,
    TelegramBadRequest,
    TelegramNotFound,
    TelegramEntityTooLarge,
    TelegramMigrateToChat,
)
_NOT_PROCESSED = (TelegramRetryAfter, TelegramUnauthorizedError)


class SendOutcome(StrEnum):
    """How one send attempt ended."""

    DELIVERED = "delivered"
    REJECTED = "rejected"  # definitely not delivered, never retried
    RETRYABLE = "retryable"  # definitely not delivered, retry later
    AMBIGUOUS = "ambiguous"  # may have been delivered


@dataclass(frozen=True)
class SendResult:
    """Outcome of one send; ``error_class`` is a class name, never a message."""

    outcome: SendOutcome
    retry_after: float | None = None
    error_class: str | None = None


class NoticeSender(Protocol):
    """Anything that can send a plain text message to a Telegram chat."""

    async def send(self, chat_id: int, text: str) -> SendResult:
        """Send ``text`` to ``chat_id`` and classify the outcome."""
        ...

    async def close(self) -> None:
        """Release network resources."""
        ...


def classify_error(error: Exception) -> SendResult:
    """Map a send failure to an outcome with the ordered ``isinstance`` chain of design 7."""
    name = type(error).__name__
    if isinstance(error, _REJECTED):
        return SendResult(SendOutcome.REJECTED, error_class=name)
    if isinstance(error, TelegramRetryAfter):
        return SendResult(SendOutcome.RETRYABLE, float(error.retry_after), name)
    if isinstance(error, _NOT_PROCESSED):
        return SendResult(SendOutcome.RETRYABLE, error_class=name)
    # 5xx, network errors, other API errors and anything unexpected may follow a delivery.
    return SendResult(SendOutcome.AMBIGUOUS, error_class=name)


class AiogramNoticeSender:
    """Production sender: one ``aiogram.Bot`` with an explicit request timeout."""

    def __init__(self, token: str, request_timeout: float) -> None:
        """Build the bot; ``AiohttpSession`` replaces the 60 second default timeout."""
        self._bot = Bot(token, session=AiohttpSession(timeout=request_timeout))

    async def send(self, chat_id: int, text: str) -> SendResult:
        """Send a plain text message (no ``parse_mode``) and classify the outcome."""
        try:
            await self._bot.send_message(chat_id, text)
        except Exception as error:  # every unknown failure is ambiguous (classify_error)
            return classify_error(error)
        return SendResult(SendOutcome.DELIVERED)

    async def close(self) -> None:
        """Close the bot session."""
        await self._bot.session.close()


def build_sender(settings: Settings) -> AiogramNoticeSender | None:
    """Return a sender, or ``None`` for an empty, placeholder or invalid token (never logged)."""
    token = settings.bot_token
    if not token or token == PLACEHOLDER_TOKEN:
        return None
    try:
        validate_token(token)
    except TokenValidationError:
        return None
    return AiogramNoticeSender(token, settings.receipt_notice_request_timeout_seconds)


__all__ = [
    "AiogramNoticeSender",
    "NoticeSender",
    "SendOutcome",
    "SendResult",
    "build_sender",
    "classify_error",
]
