"""Tests for Telegram WebApp initData validation and session context authentication."""

import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from typing import Annotated, Any

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from wishenka.auth import (
    AuthenticatedUser,
    AuthValidationError,
    ExpiredInitDataError,
    InvalidSignatureError,
    TelegramInitData,
    TelegramInitDataValidator,
    TelegramUser,
    get_current_user,
    get_optional_current_user,
    parse_telegram_init_data,
    validate_telegram_init_data,
)
from wishenka.config import Settings
from wishenka.web.app import create_app

pytestmark = pytest.mark.timeout(10)

TEST_BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz1234567"


def create_test_init_data(
    user_data: dict[str, Any],
    bot_token: str = TEST_BOT_TOKEN,
    auth_date: int | None = None,
    tampered: bool = False,
    extra_params: dict[str, str] | None = None,
) -> str:
    """Generate a Telegram WebApp initData query string with HMAC-SHA256 signature."""
    if auth_date is None:
        auth_date = int(time.time())

    params: dict[str, str] = {
        "auth_date": str(auth_date),
        "user": json.dumps(user_data, separators=(",", ":")),
    }
    if extra_params:
        params.update(extra_params)

    # Telegram data-check-string: sorted alphabetically by key, separated by newline
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))

    # Secret key: HMAC-SHA256(key="WebAppData", msg=bot_token)
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()

    # Hash: HMAC-SHA256(key=secret_key, msg=data_check_string).hex()
    computed_hash = hmac.new(
        secret_key, data_check_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    if tampered:
        # Invert or alter last character of hash to simulate signature tampering
        altered_char = "0" if computed_hash[-1] != "0" else "1"
        computed_hash = computed_hash[:-1] + altered_char

    params["hash"] = computed_hash
    return urllib.parse.urlencode(params)


def test_validate_init_data_success() -> None:
    """Valid Telegram initData must return verified TelegramUser with matching fields."""
    user_payload = {
        "id": 279058397,
        "first_name": "Vladislav",
        "last_name": "K",
        "username": "vlad",
        "language_code": "ru",
        "is_premium": True,
    }
    init_data = create_test_init_data(user_payload, bot_token=TEST_BOT_TOKEN)

    user = validate_telegram_init_data(init_data, bot_token=TEST_BOT_TOKEN)

    assert isinstance(user, TelegramUser)
    assert user.id == 279058397
    assert user.first_name == "Vladislav"
    assert user.last_name == "K"
    assert user.username == "vlad"
    assert user.language_code == "ru"
    assert user.is_premium is True


def test_telegram_init_data_validator_class() -> None:
    """TelegramInitDataValidator parses and validates properly."""
    user_payload = {
        "id": 999999,
        "first_name": "ValidatorUser",
        "username": "validator",
    }
    init_data = create_test_init_data(user_payload, bot_token=TEST_BOT_TOKEN)

    validator = TelegramInitDataValidator(bot_token=TEST_BOT_TOKEN)

    parsed = validator.parse(init_data)
    assert isinstance(parsed, TelegramInitData)
    assert parsed.user.id == 999999
    assert parsed.user.first_name == "ValidatorUser"

    user = validator.validate(init_data)
    assert isinstance(user, TelegramUser)
    assert user.id == 999999
    assert user.username == "validator"

    standalone_parsed = parse_telegram_init_data(init_data)
    assert standalone_parsed.user.id == 999999


def test_validate_init_data_tampered_hash() -> None:
    """Tampered initData or invalid signature must raise InvalidSignatureError."""
    user_payload = {"id": 10001, "first_name": "Alice", "username": "alice"}
    init_data = create_test_init_data(user_payload, bot_token=TEST_BOT_TOKEN, tampered=True)

    with pytest.raises((InvalidSignatureError, AuthValidationError)):
        validate_telegram_init_data(init_data, bot_token=TEST_BOT_TOKEN)


def test_validate_init_data_expired() -> None:
    """InitData with auth_date older than max_age_seconds must raise ExpiredInitDataError."""
    user_payload = {"id": 10002, "first_name": "Bob", "username": "bob"}
    two_days_ago = int(time.time()) - 172800
    init_data = create_test_init_data(
        user_payload,
        bot_token=TEST_BOT_TOKEN,
        auth_date=two_days_ago,
    )

    with pytest.raises((ExpiredInitDataError, AuthValidationError)):
        validate_telegram_init_data(init_data, bot_token=TEST_BOT_TOKEN, max_age_seconds=86400)


def test_auth_endpoint_exchange() -> None:
    """POST /api/auth/telegram exchanges valid initData for session cookie and JSON token."""
    settings = Settings(bot_token=TEST_BOT_TOKEN)
    app = create_app(settings)
    client = TestClient(app)

    user_payload = {"id": 424242, "first_name": "Carol", "username": "carol"}
    init_data = create_test_init_data(user_payload, bot_token=TEST_BOT_TOKEN)

    response = client.post(
        "/api/auth/telegram", json={"init_data": init_data}, headers={"Origin": "http://testserver"}
    )

    assert response.status_code == 200
    body = response.json()
    assert "token" in body
    assert body["token"]
    assert body["user"]["id"] == 424242
    assert body["user"]["first_name"] == "Carol"
    assert body["user"]["username"] == "carol"

    # Verify session cookie was set with proper attributes
    assert "session_id" in response.cookies
    assert response.cookies["session_id"] == body["token"]


def test_protected_endpoint_requires_auth() -> None:
    """Protected endpoint requires authentication; accepts both cookie and Bearer header."""
    settings = Settings(bot_token=TEST_BOT_TOKEN)
    app = create_app(settings)

    @app.get("/api/test-protected-route")
    async def custom_protected(
        current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> dict[str, Any]:
        return {"telegram_id": current_user.telegram_id, "username": current_user.username}

    client = TestClient(app)

    user_payload = {"id": 999001, "first_name": "Dave", "username": "dave"}
    init_data = create_test_init_data(user_payload, bot_token=TEST_BOT_TOKEN)

    # 1. Unauthenticated request to protected route -> 401 Unauthorized
    unauth_resp = client.get("/api/test-protected-route")
    assert unauth_resp.status_code == 401

    # 2. Authenticate to obtain token and session cookie
    auth_resp = client.post(
        "/api/auth/telegram", json={"init_data": init_data}, headers={"Origin": "http://testserver"}
    )
    assert auth_resp.status_code == 200
    token = auth_resp.json()["token"]

    # 3. Authenticated request using session cookie -> 200 OK
    cookie_client = TestClient(app, cookies={"session_id": token})
    cookie_resp = cookie_client.get("/api/test-protected-route")
    assert cookie_resp.status_code == 200
    assert cookie_resp.json()["telegram_id"] == 999001

    # 4. Authenticated request using Authorization: Bearer header -> 200 OK
    header_resp = client.get(
        "/api/test-protected-route",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert header_resp.status_code == 200
    assert header_resp.json()["telegram_id"] == 999001


def test_optional_auth_resolution() -> None:
    """Optional auth dependency resolves AuthenticatedUser when token present, None when absent."""
    settings = Settings(bot_token=TEST_BOT_TOKEN)
    app = create_app(settings)

    @app.get("/api/test-optional-auth")
    async def optional_auth_route(
        current_user: Annotated[
            AuthenticatedUser | None, Depends(get_optional_current_user)
        ] = None,
    ) -> dict[str, Any]:
        if current_user is None:
            return {"authenticated": False, "user_id": None}
        return {"authenticated": True, "user_id": current_user.telegram_id}

    client = TestClient(app)

    # 1. Anonymous caller receives authenticated=False
    guest_resp = client.get("/api/test-optional-auth")
    assert guest_resp.status_code == 200
    assert guest_resp.json() == {"authenticated": False, "user_id": None}

    # 2. Authenticate and call with cookie
    user_payload = {"id": 888111, "first_name": "Eve", "username": "eve"}
    init_data = create_test_init_data(user_payload, bot_token=TEST_BOT_TOKEN)
    auth_resp = client.post(
        "/api/auth/telegram", json={"init_data": init_data}, headers={"Origin": "http://testserver"}
    )
    token = auth_resp.json()["token"]

    auth_client = TestClient(app, cookies={"session_id": token})
    user_resp = auth_client.get("/api/test-optional-auth")
    assert user_resp.status_code == 200
    assert user_resp.json() == {"authenticated": True, "user_id": 888111}


def test_auth_logging_success(caplog: pytest.LogCaptureFixture) -> None:
    """Successful authentication must emit INFO log with user details and event metadata."""
    settings = Settings(bot_token=TEST_BOT_TOKEN)
    app = create_app(settings)
    client = TestClient(app)

    user_payload = {"id": 1234567, "first_name": "Alice", "username": "alice"}
    init_data = create_test_init_data(user_payload, bot_token=TEST_BOT_TOKEN)

    with caplog.at_level(logging.INFO, logger="wishenka.auth"):
        response = client.post(
            "/api/auth/telegram",
            json={"init_data": init_data},
            headers={"Origin": "http://testserver"},
        )

    assert response.status_code == 200
    matching_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.auth"
        and r.levelname == "INFO"
        and getattr(r, "event", None) == "auth_success"
    ]
    assert len(matching_records) == 1
    record = matching_records[0]
    assert getattr(record, "telegram_id", None) == 1234567
    assert getattr(record, "username", None) == "alice"


def test_auth_logging_invalid_signature_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Tampered signature must emit WARNING log with auth_failure event and reason."""
    settings = Settings(bot_token=TEST_BOT_TOKEN)
    app = create_app(settings)
    client = TestClient(app)

    user_payload = {"id": 1234568, "first_name": "Mallory", "username": "mallory"}
    tampered_data = create_test_init_data(user_payload, bot_token=TEST_BOT_TOKEN, tampered=True)

    with caplog.at_level(logging.WARNING, logger="wishenka.auth"):
        response = client.post(
            "/api/auth/telegram",
            json={"init_data": tampered_data},
            headers={"Origin": "http://testserver"},
        )

    assert response.status_code == 401
    matching_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.auth"
        and r.levelname == "WARNING"
        and getattr(r, "event", None) == "auth_failure"
    ]
    assert len(matching_records) == 1
    record = matching_records[0]
    assert getattr(record, "reason", None) == "invalid_signature"


def test_auth_logging_logout(caplog: pytest.LogCaptureFixture) -> None:
    """User logout must emit INFO log with logout event and user identification."""
    settings = Settings(bot_token=TEST_BOT_TOKEN)
    app = create_app(settings)
    client = TestClient(app)

    user_payload = {"id": 1234569, "first_name": "Bob", "username": "bob"}
    init_data = create_test_init_data(user_payload, bot_token=TEST_BOT_TOKEN)

    auth_resp = client.post(
        "/api/auth/telegram", json={"init_data": init_data}, headers={"Origin": "http://testserver"}
    )
    token = auth_resp.json()["token"]

    auth_client = TestClient(app, cookies={"session_id": token})
    with caplog.at_level(logging.INFO, logger="wishenka.auth"):
        csrf = auth_client.get("/api/auth/csrf").json()["csrf_token"]
        logout_resp = auth_client.post(
            "/api/auth/logout", headers={"Origin": "http://testserver", "X-CSRF-Token": csrf}
        )

    assert logout_resp.status_code == 200
    matching_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.auth"
        and r.levelname == "INFO"
        and getattr(r, "event", None) == "logout"
    ]
    assert len(matching_records) == 1
    record = matching_records[0]
    assert getattr(record, "telegram_id", None) == 1234569


def test_auth_logging_expired_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Expired initData must emit WARNING log with auth_failure event and expired reason."""
    settings = Settings(bot_token=TEST_BOT_TOKEN)
    app = create_app(settings)
    client = TestClient(app)

    user_payload = {"id": 1234570, "first_name": "Eve", "username": "eve"}
    expired_data = create_test_init_data(
        user_payload,
        bot_token=TEST_BOT_TOKEN,
        auth_date=int(time.time()) - 200000,
    )

    with caplog.at_level(logging.WARNING, logger="wishenka.auth"):
        response = client.post(
            "/api/auth/telegram",
            json={"init_data": expired_data},
            headers={"Origin": "http://testserver"},
        )

    assert response.status_code == 401
    matching_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.auth"
        and r.levelname == "WARNING"
        and getattr(r, "event", None) == "auth_failure"
    ]
    assert len(matching_records) == 1
    record = matching_records[0]
    assert getattr(record, "reason", None) == "expired_init_data"


def test_auth_logging_malformed_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Malformed initData query must emit WARNING log with auth_failure event."""
    settings = Settings(bot_token=TEST_BOT_TOKEN)
    app = create_app(settings)
    client = TestClient(app)

    with caplog.at_level(logging.WARNING, logger="wishenka.auth"):
        response = client.post(
            "/api/auth/telegram",
            json={"init_data": "invalid=query_string"},
            headers={"Origin": "http://testserver"},
        )

    assert response.status_code == 401
    matching_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.auth"
        and r.levelname == "WARNING"
        and getattr(r, "event", None) == "auth_failure"
    ]
    assert len(matching_records) == 1
    record = matching_records[0]
    assert getattr(record, "reason", None) == "malformed_init_data"


def test_auth_logging_invalid_session_token_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Accessing protected endpoint with invalid token must emit WARNING log."""
    settings = Settings(bot_token=TEST_BOT_TOKEN)
    app = create_app(settings)
    client = TestClient(app)

    with caplog.at_level(logging.WARNING, logger="wishenka.auth"):
        response = client.get(
            "/api/auth/me",
            headers={"Authorization": "Bearer not-a-valid-token"},
        )

    assert response.status_code == 401
    matching_records = [
        r
        for r in caplog.records
        if r.name == "wishenka.auth"
        and r.levelname == "WARNING"
        and getattr(r, "event", None) == "auth_failure"
    ]
    assert len(matching_records) == 1
    record = matching_records[0]
    assert getattr(record, "reason", None) == "invalid_session_token"
