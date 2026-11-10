"""Telegram WebApp initData cryptographic validator."""

import hashlib
import hmac
import json
import logging
import time
import urllib.parse

from wishenka.auth.models import (
    ExpiredInitDataError,
    InvalidSignatureError,
    MalformedInitDataError,
    TelegramInitData,
    TelegramUser,
)

logger = logging.getLogger("wishenka.auth")


def validate_telegram_init_data(
    init_data_raw: str,
    bot_token: str,
    max_age_seconds: int = 86400,
    clock_drift_seconds: int = 60,
) -> TelegramUser:
    """Validate Telegram WebApp initData HMAC-SHA256 signature and return verified user.

    Args:
        init_data_raw: Raw query string from Telegram.WebApp.initData
        bot_token: Telegram bot token used as HMAC key material
        max_age_seconds: Maximum allowed age for auth_date timestamp (default 24h)
        clock_drift_seconds: Maximum allowed future timestamp drift (default 60s)

    Returns:
        Verified TelegramUser instance.

    Raises:
        InvalidSignatureError: HMAC signature verification failed
        ExpiredInitDataError: auth_date is expired or too far in future
        MalformedInitDataError: initData string format or JSON is invalid
    """
    if not init_data_raw or not isinstance(init_data_raw, str):
        logger.warning(
            "Telegram initData validation failed: raw string is empty or invalid type",
            extra={"event": "auth_failure", "reason": "malformed_init_data"},
        )
        raise MalformedInitDataError("Empty or invalid initData string")

    parsed_pairs = urllib.parse.parse_qsl(init_data_raw, keep_blank_values=True)
    if not parsed_pairs:
        logger.warning(
            "Telegram initData validation failed: unparseable query string",
            extra={"event": "auth_failure", "reason": "malformed_init_data"},
        )
        raise MalformedInitDataError("Failed to parse initData query parameters")

    params: dict[str, str] = dict(parsed_pairs)

    if "hash" not in params:
        logger.warning(
            "Telegram initData validation failed: missing hash parameter",
            extra={"event": "auth_failure", "reason": "malformed_init_data"},
        )
        raise MalformedInitDataError("Missing required 'hash' parameter in initData")

    received_hash = params.pop("hash")

    if "auth_date" not in params:
        logger.warning(
            "Telegram initData validation failed: missing auth_date parameter",
            extra={"event": "auth_failure", "reason": "malformed_init_data"},
        )
        raise MalformedInitDataError("Missing required 'auth_date' parameter in initData")

    try:
        auth_date = int(params["auth_date"])
    except (ValueError, TypeError) as err:
        logger.warning(
            "Telegram initData validation failed: non-integer auth_date",
            extra={"event": "auth_failure", "reason": "malformed_init_data"},
        )
        raise MalformedInitDataError("Invalid non-integer 'auth_date' parameter") from err

    # 1. Constant-time HMAC-SHA256 verification
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, received_hash):
        logger.warning(
            "Telegram initData signature verification failed",
            extra={"event": "auth_failure", "reason": "invalid_signature"},
        )
        raise InvalidSignatureError("Telegram initData signature verification failed")

    # 2. Freshness and clock drift checks
    now = int(time.time())
    if auth_date > now + clock_drift_seconds:
        logger.warning(
            "Telegram initData auth_date is in the future: auth_date=%s, now=%s",
            auth_date,
            now,
            extra={
                "event": "auth_failure",
                "reason": "expired_init_data",
                "auth_date": auth_date,
            },
        )
        raise ExpiredInitDataError(
            f"initData auth_date is in the future: {auth_date} > {now + clock_drift_seconds}"
        )
    if now - auth_date > max_age_seconds:
        age_seconds = now - auth_date
        logger.warning(
            "Telegram initData auth_date has expired: age=%ss > max_age=%ss",
            age_seconds,
            max_age_seconds,
            extra={
                "event": "auth_failure",
                "reason": "expired_init_data",
                "auth_date": auth_date,
                "age_seconds": age_seconds,
            },
        )
        raise ExpiredInitDataError(
            f"initData auth_date has expired: age={age_seconds}s > {max_age_seconds}s"
        )

    # 3. User payload deserialization and validation
    if "user" not in params:
        logger.warning(
            "Telegram initData validation failed: missing user parameter",
            extra={"event": "auth_failure", "reason": "malformed_init_data"},
        )
        raise MalformedInitDataError("Missing required 'user' parameter in initData")

    try:
        user_dict = json.loads(params["user"])
        user = TelegramUser.model_validate(user_dict)
    except Exception as err:
        logger.warning(
            "Telegram initData validation failed: malformed user JSON payload",
            extra={"event": "auth_failure", "reason": "malformed_init_data"},
        )
        raise MalformedInitDataError(f"Failed to parse user profile from initData: {err}") from err

    logger.debug(
        "Telegram initData successfully validated for user %s",
        user.id,
        extra={
            "telegram_id": user.id,
            "username": user.username,
            "event": "init_data_validated",
        },
    )
    return user


def parse_telegram_init_data(init_data_raw: str) -> TelegramInitData:
    """Parse raw query string from Telegram.WebApp.initData into TelegramInitData model.

    Note:
        This function extracts parameters without validating the cryptographic signature.
        To verify HMAC-SHA256 signature and freshness, use `validate_telegram_init_data`
        or `TelegramInitDataValidator`.

    Args:
        init_data_raw: Raw query string from Telegram.WebApp.initData

    Returns:
        TelegramInitData instance containing parsed fields and raw params.

    Raises:
        MalformedInitDataError: If query parameters, hash, auth_date, or user JSON are malformed.
    """
    if not init_data_raw or not isinstance(init_data_raw, str):
        raise MalformedInitDataError("Empty or invalid initData string")

    parsed_pairs = urllib.parse.parse_qsl(init_data_raw, keep_blank_values=True)
    if not parsed_pairs:
        raise MalformedInitDataError("Failed to parse initData query parameters")

    params: dict[str, str] = dict(parsed_pairs)

    if "hash" not in params:
        raise MalformedInitDataError("Missing required 'hash' parameter in initData")

    received_hash = params["hash"]

    if "auth_date" not in params:
        raise MalformedInitDataError("Missing required 'auth_date' parameter in initData")

    try:
        auth_date = int(params["auth_date"])
    except (ValueError, TypeError) as err:
        raise MalformedInitDataError("Invalid non-integer 'auth_date' parameter") from err

    if "user" not in params:
        raise MalformedInitDataError("Missing required 'user' parameter in initData")

    try:
        user_dict = json.loads(params["user"])
        user = TelegramUser.model_validate(user_dict)
    except Exception as err:
        raise MalformedInitDataError(f"Failed to parse user profile from initData: {err}") from err

    query_id = params.get("query_id")

    return TelegramInitData(
        auth_date=auth_date,
        hash=received_hash,
        query_id=query_id,
        user=user,
        raw_params=params,
    )


class TelegramInitDataValidator:
    """Cryptographic validator and parser for Telegram WebApp initData."""

    def __init__(
        self,
        bot_token: str,
        max_age_seconds: int = 86400,
        clock_drift_seconds: int = 60,
    ) -> None:
        self.bot_token = bot_token
        self.max_age_seconds = max_age_seconds
        self.clock_drift_seconds = clock_drift_seconds

    def parse(self, init_data_raw: str) -> TelegramInitData:
        """Parse raw initData without signature verification."""
        return parse_telegram_init_data(init_data_raw)

    def validate(self, init_data_raw: str) -> TelegramUser:
        """Validate HMAC-SHA256 signature and timestamp freshness, returning TelegramUser."""
        return validate_telegram_init_data(
            init_data_raw=init_data_raw,
            bot_token=self.bot_token,
            max_age_seconds=self.max_age_seconds,
            clock_drift_seconds=self.clock_drift_seconds,
        )
