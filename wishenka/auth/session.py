"""Stateless signed session tokens and cookie management."""

import base64
import hashlib
import hmac
import json
import time

from fastapi import Response

from wishenka.auth.models import (
    AuthValidationError,
    ExpiredInitDataError,
    InvalidSignatureError,
    SessionClaims,
)
from wishenka.config import Settings


class SessionTokenService:
    """Issues and verifies HMAC-SHA256 signed stateless session tokens."""

    def __init__(self, secret_key: str, default_ttl_seconds: int = 2592000) -> None:
        self.secret_key = secret_key.encode("utf-8")
        self.default_ttl_seconds = default_ttl_seconds

    def create_token(
        self,
        telegram_id: int,
        first_name: str,
        username: str | None = None,
        ttl_seconds: int | None = None,
        user_id: int | None = None,
    ) -> str:
        """Issue a signed session token.

        Args:
            telegram_id: User's Telegram numeric ID
            first_name: User's first name
            username: User's Telegram username without @
            ttl_seconds: Optional TTL override in seconds
            user_id: Optional internal database user ID

        Returns:
            URL-safe token string in format '<payload_b64>.<sig_b64>'
        """
        now = int(time.time())
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl_seconds
        claims = SessionClaims(
            telegram_id=telegram_id,
            first_name=first_name,
            username=username,
            user_id=user_id,
            iat=now,
            exp=now + ttl,
        )
        payload_bytes = claims.model_dump_json().encode("utf-8")
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode("ascii").rstrip("=")

        signature_bytes = hmac.new(
            self.secret_key, payload_b64.encode("ascii"), hashlib.sha256
        ).digest()
        sig_b64 = base64.urlsafe_b64encode(signature_bytes).decode("ascii").rstrip("=")

        return f"{payload_b64}.{sig_b64}"

    def verify_token(self, token: str) -> SessionClaims:
        """Verify token signature and expiration, returning SessionClaims.

        Args:
            token: Signed session token string

        Returns:
            Validated SessionClaims

        Raises:
            AuthValidationError: If token format is invalid
            InvalidSignatureError: If HMAC signature is invalid
            ExpiredInitDataError: If token has expired
        """
        if not token or "." not in token:
            raise AuthValidationError("Invalid session token format")

        parts = token.split(".")
        if len(parts) != 2:
            raise AuthValidationError("Malformed session token parts")

        payload_b64, sig_b64 = parts[0], parts[1]

        # Pad base64 strings if necessary
        rem_sig = len(sig_b64) % 4
        padded_sig = sig_b64 + ("=" * (4 - rem_sig) if rem_sig else "")

        try:
            expected_sig = hmac.new(
                self.secret_key, payload_b64.encode("ascii"), hashlib.sha256
            ).digest()
            received_sig = base64.urlsafe_b64decode(padded_sig.encode("ascii"))
        except Exception as err:
            raise InvalidSignatureError("Failed to decode token signature") from err

        if not hmac.compare_digest(expected_sig, received_sig):
            raise InvalidSignatureError("Session token signature verification failed")

        rem_payload = len(payload_b64) % 4
        padded_payload = payload_b64 + ("=" * (4 - rem_payload) if rem_payload else "")

        try:
            payload_json = base64.urlsafe_b64decode(padded_payload.encode("ascii")).decode("utf-8")
            data = json.loads(payload_json)
            claims = SessionClaims.model_validate(data)
        except Exception as err:
            raise AuthValidationError("Failed to deserialize session claims") from err

        now = int(time.time())
        if claims.exp < now:
            raise ExpiredInitDataError(f"Session token expired at {claims.exp} (now: {now})")

        return claims


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    """Set secure session cookie on outgoing response."""
    # Convert samesite value to valid Literal['lax', 'strict', 'none']
    samesite_val = settings.session_cookie_samesite.lower()
    valid_samesite = (
        "none" if samesite_val == "none" else ("strict" if samesite_val == "strict" else "lax")
    )

    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=valid_samesite,  # type: ignore[arg-type]
        domain=settings.session_cookie_domain,
        path="/",
    )


def delete_session_cookie(response: Response, settings: Settings) -> None:
    """Clear session cookie from client."""
    samesite_val = settings.session_cookie_samesite.lower()
    valid_samesite = (
        "none" if samesite_val == "none" else ("strict" if samesite_val == "strict" else "lax")
    )

    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        domain=settings.session_cookie_domain,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=valid_samesite,  # type: ignore[arg-type]
    )


def compute_revocation_subject_hash(telegram_id: int, secret_key: str) -> str:
    """Compute a non-reversible HMAC-SHA256 subject hash for session revocation."""
    return hmac.new(
        secret_key.encode("utf-8"),
        f"deleted:{telegram_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
