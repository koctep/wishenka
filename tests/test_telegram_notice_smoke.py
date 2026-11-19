"""Opt-in real Telegram smoke tests and offline sender/formatting guard checks."""

from __future__ import annotations

import os

import pytest

from wishenka.config import Settings
from wishenka.notices.sender import (
    PLACEHOLDER_TOKEN,
    SendOutcome,
    SendResult,
    build_sender,
)
from wishenka.notices.worker import TITLE_LIMIT, notice_text

pytestmark = pytest.mark.timeout(60)

_ENV_TOKEN = "WISHENKA_TELEGRAM_SMOKE_TOKEN"
_ENV_CHAT_ID = "WISHENKA_TELEGRAM_SMOKE_CHAT_ID"
_ENV_INVALID_CHAT_ID = "WISHENKA_TELEGRAM_SMOKE_INVALID_CHAT_ID"
_TELEGRAM_MESSAGE_LIMIT = 4096


def _parse_int_env(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def _smoke_credentials() -> tuple[str, int] | None:
    token = os.environ.get(_ENV_TOKEN, "").strip()
    chat_id = _parse_int_env(_ENV_CHAT_ID)
    if not token or token == PLACEHOLDER_TOKEN or chat_id is None:
        return None
    return token, chat_id


def _invalid_chat_id() -> int:
    parsed = _parse_int_env(_ENV_INVALID_CHAT_ID)
    return 0 if parsed is None else parsed


_SKIP_REASON = (
    f"Opt-in live Telegram smoke test skipped: set {_ENV_TOKEN} and {_ENV_CHAT_ID} to run"
)


@pytest.mark.telegram_smoke
@pytest.mark.skipif(_smoke_credentials() is None, reason=_SKIP_REASON)
async def test_telegram_smoke_delivers_plain_text_with_special_chars_and_truncation() -> None:
    """Deliver a real plain-text gift notice with special chars and >100-char titles."""
    creds = _smoke_credentials()
    assert creds is not None
    token, chat_id = creds

    settings = Settings(bot_token=token, receipt_notice_request_timeout_seconds=15.0)
    sender = build_sender(settings)
    assert sender is not None, "WISHENKA_TELEGRAM_SMOKE_TOKEN must be a valid Telegram bot token"

    wish_title = "Smoke <script> & \"quotes\" 'apos' > " + ("W" * 120)
    list_title = "Smoke <Wishlist> & " + ("L" * 120)
    text = notice_text(wish_title, list_title, locale="ru")
    assert len(text) <= _TELEGRAM_MESSAGE_LIMIT

    try:
        result = await sender.send(chat_id, text)
    finally:
        await sender.close()

    assert result == SendResult(outcome=SendOutcome.DELIVERED)


@pytest.mark.telegram_smoke
@pytest.mark.skipif(_smoke_credentials() is None, reason=_SKIP_REASON)
async def test_telegram_smoke_rejects_invalid_chat() -> None:
    """Verify real Telegram API rejection is classified as SendOutcome.REJECTED."""
    creds = _smoke_credentials()
    assert creds is not None
    token, _ = creds

    settings = Settings(bot_token=token, receipt_notice_request_timeout_seconds=15.0)
    sender = build_sender(settings)
    assert sender is not None

    try:
        result = await sender.send(_invalid_chat_id(), "Wishenka smoke negative check")
    finally:
        await sender.close()

    assert result.outcome == SendOutcome.REJECTED
    assert result.error_class


def test_build_sender_rejects_placeholder_and_invalid_tokens() -> None:
    """Offline guard: empty, placeholder, and malformed tokens never build a live sender."""
    assert build_sender(Settings(bot_token="")) is None
    assert build_sender(Settings(bot_token=PLACEHOLDER_TOKEN)) is None
    assert build_sender(Settings(bot_token="not-a-valid-token")) is None


def test_notice_text_truncates_titles_and_preserves_plain_text() -> None:
    """Offline guard: titles are capped at TITLE_LIMIT and special chars stay unescaped."""
    wish_prefix = "<script>&\"'>"
    list_prefix = "<List & 'Title'>"
    long_wish = wish_prefix + ("W" * (TITLE_LIMIT + 50))
    long_list = list_prefix + ("L" * (TITLE_LIMIT + 50))

    text = notice_text(long_wish, long_list, locale="ru")

    assert wish_prefix in text
    assert list_prefix in text
    assert long_wish[:TITLE_LIMIT] in text
    assert long_list[:TITLE_LIMIT] in text
    assert long_wish[: TITLE_LIMIT + 1] not in text
    assert long_list[: TITLE_LIMIT + 1] not in text
    assert len(text) < _TELEGRAM_MESSAGE_LIMIT
