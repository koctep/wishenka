"""Web-layer helpers for client Idempotency-Key validation, hashing, and replay."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, Request, Response, status
from pydantic import BaseModel

logger = logging.getLogger(__name__)

IDEMPOTENCY_KEY_HEADER = "Idempotency-Key"
_IDEMPOTENCY_KEY_RE = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
JSON_MEDIA_TYPE = "application/json"
HTML_MEDIA_TYPE = "text/html; charset=utf-8"


def parse_idempotency_key(request: Request) -> str | None:
    """Validate and return the optional Idempotency-Key header, or raise 400 if malformed."""
    raw = request.headers.get(IDEMPOTENCY_KEY_HEADER)
    if raw is None:
        return None
    if not _IDEMPOTENCY_KEY_RE.fullmatch(raw):
        route = request.scope.get("route")
        route_path = getattr(route, "path", None)
        logger.warning(
            "Invalid Idempotency-Key header rejected",
            extra={
                "event": "idempotency_key_invalid",
                "method": request.method,
                "route_path": route_path,
                "key_length": len(raw),
            },
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key must be 1..128 characters matching [A-Za-z0-9._:-]",
        )
    return raw


def compute_request_hash(
    operation: str,
    target: Mapping[str, Any],
    payload: Mapping[str, Any] | None = None,
) -> str:
    """Compute a deterministic SHA-256 fingerprint for an idempotent mutation request."""
    canonical = json.dumps(
        {
            "operation": operation,
            "target": dict(target),
            "payload": dict(payload) if payload is not None else {},
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def serialize_dto_response(dto: BaseModel, status_code: int) -> tuple[int, str, str]:
    """Serialize a Pydantic response DTO into (status_code, content_type, body)."""
    return status_code, JSON_MEDIA_TYPE, dto.model_dump_json()


def build_replay_response(status_code: int, content_type: str, body: str) -> Response:
    """Reconstruct a FastAPI Response from a persisted idempotency record."""
    media_type = content_type.split(";", 1)[0].strip() or JSON_MEDIA_TYPE
    return Response(content=body, status_code=status_code, media_type=media_type)


def retention_hours_from_request(request: Request) -> int:
    """Read configured idempotency retention hours from app state, defaulting to 24."""
    settings = getattr(request.app.state, "settings", None)
    return int(getattr(settings, "idempotency_retention_hours", 24))
