"""VCR-compatible YAML web cassette recording, sanitization, and offline replay engine."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
import yaml  # type: ignore[import-untyped]

from wishenka.items.encoding import decode_html
from wishenka.items.exceptions import CassetteError, CassetteMissError
from wishenka.items.fetcher import PreviewTransportConfig, offline_replay_route
from wishenka.items.marketplaces import clean_url
from wishenka.items.ssrf import SSRFSafeTransport

logger = logging.getLogger("wishenka.items")

DEFAULT_CASSETTES_DIR: Path = (
    Path(__file__).resolve().parents[2] / "tests" / "cassettes" / "marketplaces"
)


SENSITIVE_HEADER_NAMES: frozenset[str] = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "set-cookie2",
        "x-api-key",
        "x-auth-token",
        "x-csrf-token",
        "x-xsrf-token",
        "cf-connecting-ip",
        "x-forwarded-for",
        "x-real-ip",
        "x-client-ip",
        "x-device-id",
        "x-session-id",
    }
)

SENSITIVE_HEADER_SUBSTRINGS: tuple[str, ...] = (
    "cookie",
    "token",
    "secret",
    "auth",
    "session",
    "api-key",
    "apikey",
)

SENSITIVE_QUERY_KEYS: frozenset[str] = frozenset(
    {
        "token",
        "access_token",
        "refresh_token",
        "id_token",
        "api_key",
        "apikey",
        "session",
        "session_id",
        "sessionid",
        "auth",
        "auth_token",
        "key",
        "secret",
        "password",
        "passwd",
        "signature",
        "sig",
    }
)


class CassetteMode(StrEnum):
    """Execution mode for the marketplace cassette testbench."""

    REPLAY = "replay"
    RECORD = "record"
    REFRESH = "refresh"


def resolve_cassette_mode(mode: CassetteMode | str | None = None) -> CassetteMode:
    """Resolve cassette execution mode from explicit argument or WISHENKA_CASSETTE_MODE env."""
    if isinstance(mode, CassetteMode):
        return mode
    raw = mode if mode is not None else os.environ.get("WISHENKA_CASSETTE_MODE", "replay")
    normalized = str(raw).strip().lower()
    try:
        return CassetteMode(normalized)
    except ValueError as exc:
        raise CassetteError(f"Unsupported cassette mode: {raw!r}") from exc


def _is_sensitive_header(name: str) -> bool:
    """Check if a header name matches sensitive authentication, cookie, or client IP patterns."""
    lowered = name.strip().lower()
    if lowered in SENSITIVE_HEADER_NAMES:
        return True
    return any(sub in lowered for sub in SENSITIVE_HEADER_SUBSTRINGS)


def sanitize_headers(headers: Mapping[str, Any] | httpx.Headers | None) -> dict[str, list[str]]:
    """Strip sensitive authentication, cookie, token, and IP headers (case-insensitive)."""
    if not headers:
        return {}

    sanitized: dict[str, list[str]] = {}
    if isinstance(headers, httpx.Headers):
        for raw_key in headers:
            if _is_sensitive_header(raw_key):
                continue
            key_lower = raw_key.strip().lower()
            values = [str(v) for v in headers.get_list(raw_key)]
            if values:
                sanitized[key_lower] = values
        return sanitized

    for raw_key, raw_val in headers.items():
        if _is_sensitive_header(str(raw_key)):
            continue
        key_lower = str(raw_key).strip().lower()
        values = [str(v) for v in raw_val] if isinstance(raw_val, (list, tuple)) else [str(raw_val)]
        if values:
            sanitized[key_lower] = values
    return sanitized


def sanitize_uri(uri: str) -> str:
    """Strip URL userinfo credentials, tracking parameters, and sensitive query tokens."""
    cleaned = clean_url(uri)
    if not cleaned:
        return ""
    try:
        parts = urlsplit(cleaned)
    except Exception:
        return cleaned

    if not parts.scheme or not parts.netloc:
        return cleaned

    # Strip user:pass@ credentials if present in netloc
    netloc = parts.netloc
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[-1]

    query_tuples = parse_qsl(parts.query, keep_blank_values=True)
    filtered_query: list[tuple[str, str]] = []
    for key, val in query_tuples:
        key_lower = key.strip().lower()
        if key_lower in SENSITIVE_QUERY_KEYS or any(
            sub in key_lower for sub in ("token", "secret", "password", "api_key", "apikey", "auth")
        ):
            continue
        filtered_query.append((key, val))

    new_query = urlencode(filtered_query)
    return urlunsplit((parts.scheme, netloc, parts.path, new_query, ""))


@dataclass(frozen=True, slots=True)
class CassetteRequest:
    """Recorded and sanitized HTTP request inside a cassette interaction."""

    method: str
    uri: str
    headers: dict[str, list[str]] = field(default_factory=dict)
    body: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CassetteRequest:
        """Deserialize CassetteRequest from a VCR-compatible dictionary."""
        method = str(data.get("method", "GET")).upper()
        uri = sanitize_uri(str(data.get("uri", "")))
        headers = sanitize_headers(data.get("headers") or {})
        body_raw = data.get("body")
        body = body_raw.get("string") if isinstance(body_raw, Mapping) else body_raw
        return cls(
            method=method,
            uri=uri,
            headers=headers,
            body=str(body) if body is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize CassetteRequest to a VCR-compatible dictionary."""
        return {
            "method": self.method.upper(),
            "uri": sanitize_uri(self.uri),
            "headers": sanitize_headers(self.headers),
            "body": self.body,
        }


@dataclass(frozen=True, slots=True)
class CassetteResponse:
    """Recorded and sanitized HTTP response inside a cassette interaction."""

    status_code: int
    reason_phrase: str
    headers: dict[str, list[str]] = field(default_factory=dict)
    body: str = ""
    http_version: str = "HTTP/1.1"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> CassetteResponse:
        """Deserialize CassetteResponse from a VCR-compatible dictionary."""
        status_raw = data.get("status")
        if isinstance(status_raw, Mapping):
            status_code = int(status_raw.get("code", 200))
            reason_phrase = str(status_raw.get("message") or _default_reason_phrase(status_code))
        else:
            status_code = int(data.get("status_code", 200))
            reason_phrase = str(data.get("reason_phrase") or _default_reason_phrase(status_code))

        body_raw = data.get("body")
        if isinstance(body_raw, Mapping):
            body_str = str(body_raw.get("string", "") or "")
        elif body_raw is None:
            body_str = ""
        else:
            body_str = str(body_raw)

        return cls(
            status_code=status_code,
            reason_phrase=reason_phrase,
            headers=sanitize_headers(data.get("headers") or {}),
            body=body_str,
            http_version=str(data.get("http_version", "HTTP/1.1")),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize CassetteResponse to a VCR-compatible dictionary."""
        return {
            "status": {
                "code": self.status_code,
                "message": self.reason_phrase or _default_reason_phrase(self.status_code),
            },
            "http_version": self.http_version,
            "headers": sanitize_headers(self.headers),
            "body": {
                "string": self.body,
            },
        }


@dataclass(frozen=True, slots=True)
class CassetteInteraction:
    """Single HTTP request/response pair stored inside a cassette."""

    request: CassetteRequest
    response: CassetteResponse
    marketplace: str | None = None
    scenario: str | None = None
    recorded_at: str | None = None

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, Any],
        *,
        default_marketplace: str | None = None,
        default_scenario: str | None = None,
    ) -> CassetteInteraction:
        """Deserialize CassetteInteraction from dictionary."""
        req = CassetteRequest.from_dict(data.get("request") or {})
        resp = CassetteResponse.from_dict(data.get("response") or {})
        return cls(
            request=req,
            response=resp,
            marketplace=data.get("marketplace") or default_marketplace,
            scenario=data.get("scenario") or default_scenario,
            recorded_at=data.get("recorded_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize CassetteInteraction to dictionary with sanitization applied."""
        sanitized = sanitize_interaction(self)
        payload: dict[str, Any] = {}
        if sanitized.recorded_at:
            payload["recorded_at"] = sanitized.recorded_at
        payload["request"] = sanitized.request.to_dict()
        payload["response"] = sanitized.response.to_dict()
        return payload


def sanitize_interaction(interaction: CassetteInteraction) -> CassetteInteraction:
    """Return a sanitized copy of a CassetteInteraction."""
    clean_req = CassetteRequest(
        method=interaction.request.method.upper(),
        uri=sanitize_uri(interaction.request.uri),
        headers=sanitize_headers(interaction.request.headers),
        body=interaction.request.body,
    )
    clean_resp = CassetteResponse(
        status_code=interaction.response.status_code,
        reason_phrase=interaction.response.reason_phrase,
        headers=sanitize_headers(interaction.response.headers),
        body=interaction.response.body,
        http_version=interaction.response.http_version,
    )
    return CassetteInteraction(
        request=clean_req,
        response=clean_resp,
        marketplace=interaction.marketplace,
        scenario=interaction.scenario,
        recorded_at=interaction.recorded_at,
    )


def _default_reason_phrase(status_code: int) -> str:
    """Resolve standard HTTP reason phrase for status code."""
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "OK" if status_code < 400 else "Error"


class Cassette:
    """In-memory representation of a VCR-compatible YAML web cassette."""

    def __init__(
        self,
        *,
        version: int = 1,
        marketplace: str | None = None,
        scenario: str | None = None,
        interactions: list[CassetteInteraction] | None = None,
    ) -> None:
        self.version = version
        self.marketplace = marketplace
        self.scenario = scenario
        self.interactions: list[CassetteInteraction] = [
            sanitize_interaction(item) for item in (interactions or [])
        ]

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Cassette:
        """Construct a Cassette from a parsed YAML dictionary."""
        if not isinstance(data, Mapping):
            raise CassetteError("Invalid cassette structure: root must be a mapping")
        version = int(data.get("version", 1))
        marketplace = data.get("marketplace")
        scenario = data.get("scenario")
        raw_interactions = data.get("interactions") or []
        if not isinstance(raw_interactions, list):
            raise CassetteError("Invalid cassette structure: 'interactions' must be a list")

        interactions = [
            CassetteInteraction.from_dict(
                item,
                default_marketplace=marketplace,
                default_scenario=scenario,
            )
            for item in raw_interactions
            if isinstance(item, Mapping)
        ]
        return cls(
            version=version,
            marketplace=str(marketplace) if marketplace is not None else None,
            scenario=str(scenario) if scenario is not None else None,
            interactions=interactions,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize Cassette into a YAML-ready dictionary."""
        payload: dict[str, Any] = {"version": self.version}
        if self.marketplace is not None:
            payload["marketplace"] = self.marketplace
        if self.scenario is not None:
            payload["scenario"] = self.scenario
        payload["interactions"] = [
            sanitize_interaction(interaction).to_dict() for interaction in self.interactions
        ]
        return payload

    @classmethod
    def load(cls, path: Path | str) -> Cassette:
        """Load a YAML cassette file from disk."""
        cassette_path = Path(path)
        if not cassette_path.is_file():
            raise CassetteError(f"Cassette file not found: {cassette_path}")
        try:
            raw_text = cassette_path.read_text(encoding="utf-8")
            parsed = yaml.safe_load(raw_text) or {}
        except Exception as exc:
            raise CassetteError(f"Failed to parse cassette {cassette_path}: {exc}") from exc
        cassette = cls.from_dict(parsed)
        logger.debug(
            "Loaded cassette %s (marketplace=%s, scenario=%s, interactions=%d)",
            cassette_path,
            cassette.marketplace,
            cassette.scenario,
            len(cassette.interactions),
            extra={
                "event": "cassette_loaded",
                "cassette_path": str(cassette_path),
                "marketplace": cassette.marketplace,
                "scenario": cassette.scenario,
                "interactions_count": len(cassette.interactions),
            },
        )
        return cassette

    def save(self, path: Path | str) -> None:
        """Persist sanitized cassette interactions to a YAML file on disk."""
        cassette_path = Path(path)
        cassette_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = yaml.safe_dump(
            self.to_dict(),
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
            width=120,
        )
        cassette_path.write_text(serialized, encoding="utf-8")
        logger.debug(
            "Saved sanitized cassette %s (marketplace=%s, scenario=%s, interactions=%d)",
            cassette_path,
            self.marketplace,
            self.scenario,
            len(self.interactions),
            extra={
                "event": "cassette_saved",
                "cassette_path": str(cassette_path),
                "marketplace": self.marketplace,
                "scenario": self.scenario,
                "interactions_count": len(self.interactions),
            },
        )

    def find_interaction(self, method: str, uri: str) -> CassetteInteraction | None:
        """Look up a recorded interaction matching HTTP method and normalized URI."""
        normalized_method = method.upper()
        normalized_target = sanitize_uri(uri)
        raw_cleaned_target = clean_url(uri)

        for interaction in self.interactions:
            if interaction.request.method.upper() != normalized_method:
                continue
            recorded_uri = interaction.request.uri
            if (
                sanitize_uri(recorded_uri) == normalized_target
                or clean_url(recorded_uri) == raw_cleaned_target
                or recorded_uri == uri
            ):
                return interaction
        return None

    def add_interaction(
        self,
        interaction: CassetteInteraction,
        *,
        replace: bool = False,
    ) -> CassetteInteraction:
        """Add a sanitized interaction to the cassette, optionally replacing existing matches."""
        sanitized = sanitize_interaction(interaction)
        if replace:
            target_method = sanitized.request.method.upper()
            target_uri = sanitized.request.uri
            self.interactions = [
                existing
                for existing in self.interactions
                if not (
                    existing.request.method.upper() == target_method
                    and sanitize_uri(existing.request.uri) == target_uri
                )
            ]
        self.interactions.append(sanitized)
        return sanitized


def load_marketplace_cassette(
    marketplace: str,
    scenario: str,
    *,
    cassettes_dir: Path | None = None,
) -> Cassette:
    """Load a reference marketplace cassette (`<marketplace>_<scenario>.yaml`)."""
    base_dir = cassettes_dir or DEFAULT_CASSETTES_DIR
    cassette_path = base_dir / f"{marketplace}_{scenario}.yaml"
    return Cassette.load(cassette_path)


class CassetteTransport(httpx.AsyncBaseTransport):
    """httpx AsyncBaseTransport for offline cassette replay and sanitized recording."""

    def __init__(
        self,
        cassette: Cassette,
        *,
        mode: CassetteMode | str = CassetteMode.REPLAY,
        cassette_path: Path | str | None = None,
        inner_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.cassette = cassette
        self.mode = resolve_cassette_mode(mode)
        self.cassette_path = Path(cassette_path) if cassette_path is not None else None
        self.inner_transport = inner_transport
        self._owns_inner_transport = False

    def _get_or_create_inner_transport(self) -> httpx.AsyncBaseTransport:
        """Obtain the origin transport for RECORD or REFRESH mode."""
        if self.inner_transport is not None:
            return self.inner_transport
        self.inner_transport = SSRFSafeTransport()
        self._owns_inner_transport = True
        return self.inner_transport

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Serve HTTP response from cassette or record/refresh from origin transport."""
        method = request.method.upper()
        uri = str(request.url)

        if self.mode in (CassetteMode.REPLAY, CassetteMode.RECORD):
            matched = self.cassette.find_interaction(method, uri)
            if matched is not None:
                logger.debug(
                    "Cassette replay hit for %s %s (status=%d)",
                    method,
                    matched.request.uri,
                    matched.response.status_code,
                    extra={
                        "event": "cassette_replay_hit",
                        "method": method,
                        "uri": matched.request.uri,
                        "status_code": matched.response.status_code,
                        "mode": self.mode.value,
                        "marketplace": self.cassette.marketplace,
                        "scenario": self.cassette.scenario,
                    },
                )
                return self._build_httpx_response(request, matched.response)

        if self.mode == CassetteMode.REPLAY:
            cassette_label = str(self.cassette_path) if self.cassette_path else "<in-memory>"
            sanitized_target_uri = sanitize_uri(uri)
            logger.warning(
                "Cassette miss in offline REPLAY mode for %s %s (cassette=%s)",
                method,
                sanitized_target_uri,
                cassette_label,
                extra={
                    "event": "cassette_miss",
                    "method": method,
                    "uri": sanitized_target_uri,
                    "cassette_path": cassette_label,
                    "marketplace": self.cassette.marketplace,
                    "scenario": self.cassette.scenario,
                },
            )
            raise CassetteMissError(
                f"No recorded interaction for {method} {sanitized_target_uri} "
                f"in cassette {cassette_label}",
                method=method,
                uri=sanitized_target_uri,
                cassette_path=cassette_label,
            )

        # RECORD (on miss) or REFRESH mode
        origin = self._get_or_create_inner_transport()
        live_response = await origin.handle_async_request(request)
        raw_bytes = await live_response.aread()
        content_type = live_response.headers.get("content-type", "")
        body_text = decode_html(raw_bytes, content_type)

        req_body: str | None = None
        if request.content:
            req_body = request.content.decode("utf-8", errors="replace")

        recorded_interaction = CassetteInteraction(
            request=CassetteRequest(
                method=method,
                uri=sanitize_uri(uri),
                headers=sanitize_headers(request.headers),
                body=req_body,
            ),
            response=CassetteResponse(
                status_code=live_response.status_code,
                reason_phrase=(
                    live_response.reason_phrase or _default_reason_phrase(live_response.status_code)
                ),
                headers=sanitize_headers(live_response.headers),
                body=body_text,
                http_version=live_response.extensions.get("http_version", b"HTTP/1.1").decode(
                    "ascii", errors="ignore"
                )
                if isinstance(live_response.extensions.get("http_version"), bytes)
                else str(live_response.extensions.get("http_version") or "HTTP/1.1"),
            ),
            marketplace=self.cassette.marketplace,
            scenario=self.cassette.scenario,
            recorded_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        self.cassette.add_interaction(
            recorded_interaction,
            replace=(self.mode == CassetteMode.REFRESH),
        )
        if self.cassette_path is not None:
            self.cassette.save(self.cassette_path)

        event_name = (
            "cassette_refreshed" if self.mode == CassetteMode.REFRESH else "cassette_recorded"
        )
        logger.info(
            "%s sanitized cassette interaction for %s %s (status=%d, mode=%s)",
            "Refreshed" if self.mode == CassetteMode.REFRESH else "Recorded",
            method,
            recorded_interaction.request.uri,
            live_response.status_code,
            self.mode.value,
            extra={
                "event": event_name,
                "method": method,
                "uri": recorded_interaction.request.uri,
                "status_code": live_response.status_code,
                "mode": self.mode.value,
                "marketplace": self.cassette.marketplace,
                "scenario": self.cassette.scenario,
                "cassette_path": str(self.cassette_path) if self.cassette_path else None,
            },
        )
        return self._build_httpx_response(request, recorded_interaction.response)

    @staticmethod
    def _build_httpx_response(
        request: httpx.Request,
        recorded: CassetteResponse,
    ) -> httpx.Response:
        """Construct a streaming-compatible httpx.Response from a CassetteResponse."""
        header_pairs: list[tuple[str, str]] = []
        for key, values in recorded.headers.items():
            if key.lower() in ("content-length", "transfer-encoding", "content-encoding"):
                continue
            for value in values:
                header_pairs.append((key, value))

        body_bytes = recorded.body.encode("utf-8")
        header_pairs.append(("content-length", str(len(body_bytes))))

        return httpx.Response(
            status_code=recorded.status_code,
            headers=header_pairs,
            content=body_bytes,
            request=request,
            extensions={
                "reason_phrase": recorded.reason_phrase.encode("ascii", errors="replace"),
                "http_version": recorded.http_version.encode("ascii", errors="replace"),
            },
        )

    async def aclose(self) -> None:
        """Close owned origin transport if created."""
        if self._owns_inner_transport and self.inner_transport is not None:
            await self.inner_transport.aclose()


@asynccontextmanager
async def cassette_client(
    cassette_path: Path | str,
    *,
    mode: CassetteMode | str | None = None,
    inner_transport: httpx.AsyncBaseTransport | None = None,
    marketplace: str | None = None,
    scenario: str | None = None,
) -> AsyncIterator[httpx.AsyncClient]:
    """Create an httpx.AsyncClient backed by CassetteTransport for the given cassette file."""
    resolved_mode = resolve_cassette_mode(mode)
    path = Path(cassette_path)

    if path.is_file():
        cassette = Cassette.load(path)
    elif resolved_mode in (CassetteMode.RECORD, CassetteMode.REFRESH):
        cassette = Cassette(marketplace=marketplace, scenario=scenario)
    else:
        raise CassetteError(f"Cassette file does not exist for REPLAY mode: {path}")

    transport = CassetteTransport(
        cassette,
        mode=resolved_mode,
        cassette_path=path,
        inner_transport=inner_transport,
    )
    async with httpx.AsyncClient(
        transport=transport,
        follow_redirects=True,
        trust_env=False,
    ) as client:
        yield client


def cassette_replay_routes(cassette: Cassette) -> PreviewTransportConfig:
    """Copy a cassette to a fixture-only preview route with no recording delegate."""
    responses: dict[str, tuple[int, dict[str, str], bytes]] = {}
    for interaction in cassette.interactions:
        if interaction.request.method.upper() != "GET":
            continue
        response = interaction.response
        headers = {
            key: ", ".join(values)
            for key, values in response.headers.items()
            if key.lower() not in {"content-length", "transfer-encoding", "content-encoding"}
        }
        responses[interaction.request.uri] = (
            response.status_code,
            headers,
            response.body.encode("utf-8"),
        )
    route = offline_replay_route(
        responses, marketplace=cassette.marketplace, scenario=cassette.scenario
    )
    return PreviewTransportConfig(default=route, mounts={})


async def _verify_all_reference_cassettes(cassettes_dir: Path) -> int:
    """Verify fixtures through the non-network replay transport without consulting DNS."""
    from http.cookiejar import CookieJar

    from wishenka.items.fetcher import RejectCookies, UrlMetadataService
    from wishenka.items.service import ItemPreviewService

    class OfflineMetadataService(UrlMetadataService):
        """Use only a freshly created, fixture-backed transport for offline verification."""

        async def _fetch_html(
            self,
            url: str,
            client: httpx.AsyncClient | None = None,
            routes: PreviewTransportConfig | None = None,
        ) -> tuple[str, str]:
            if client is not None or routes is None or routes.mounts:
                raise CassetteError("Offline verification requires its fixture-only route")
            async with httpx.AsyncClient(
                transport=routes.default.transport,
                cookies=CookieJar(policy=RejectCookies()),
                trust_env=False,
            ) as replay_client:
                return await self._stream_and_read(replay_client, url)

    yaml_files = sorted(cassettes_dir.glob("*.yaml"))
    if not yaml_files:
        raise CassetteError(f"No cassette files found in {cassettes_dir}")

    for yaml_path in yaml_files:
        cassette = Cassette.load(yaml_path)
        if not cassette.interactions:
            raise CassetteError(f"Cassette {yaml_path} has no interactions")
        target_uri = cassette.interactions[0].request.uri
        routes = cassette_replay_routes(cassette)
        preview = await ItemPreviewService(
            url_metadata_service=OfflineMetadataService(), routes=routes
        ).fetch_preview(target_uri)
        if cassette.scenario == "antibot" and not preview.is_fallback:
            raise CassetteError(f"Antibot cassette {yaml_path.name} did not trigger fallback")
        if cassette.scenario == "product" and (preview.is_fallback or not preview.title):
            raise CassetteError(
                f"Product cassette {yaml_path.name} unexpectedly degraded to fallback"
            )
    return len(yaml_files)


async def _record_or_refresh_cassette(
    *,
    mode: CassetteMode,
    url: str,
    output_path: Path,
    marketplace: str | None = None,
    scenario: str | None = None,
    inner_transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Record or refresh a single marketplace cassette via ItemPreviewService."""
    from http.cookiejar import CookieJar

    from wishenka.items.fetcher import DEFAULT_TIMEOUT, RejectCookies, UrlMetadataService
    from wishenka.items.fetcher import _validate_request as validate_request

    if inner_transport is not None:
        raise CassetteError(
            "Custom recording transports are not supported by safe preview recording"
        )
    cassette = (
        Cassette.load(output_path)
        if output_path.is_file()
        else Cassette(marketplace=marketplace, scenario=scenario)
    )
    transport = CassetteTransport(cassette, mode=mode, cassette_path=output_path)
    async with httpx.AsyncClient(
        transport=transport,
        timeout=DEFAULT_TIMEOUT,
        cookies=CookieJar(policy=RejectCookies()),
        event_hooks={"request": [validate_request]},
        trust_env=False,
    ) as client:
        # The response is already recorded; preview treats HTTP errors as fallback.
        with suppress(httpx.HTTPStatusError):
            await UrlMetadataService()._stream_and_read(client, clean_url(url))


async def _refresh_all_cassettes(
    cassettes_dir: Path,
    *,
    mode: CassetteMode,
    inner_transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """Record or refresh all existing YAML cassettes in a directory."""
    yaml_files = sorted(cassettes_dir.glob("*.yaml"))
    if not yaml_files:
        raise CassetteError(f"No cassette files found in {cassettes_dir}")

    for yaml_path in yaml_files:
        cassette = Cassette.load(yaml_path)
        if not cassette.interactions:
            raise CassetteError(f"Cassette {yaml_path} has no interactions")
        target_uri = cassette.interactions[0].request.uri
        await _record_or_refresh_cassette(
            mode=mode,
            url=target_uri,
            output_path=yaml_path,
            marketplace=cassette.marketplace,
            scenario=cassette.scenario,
            inner_transport=inner_transport,
        )
    return len(yaml_files)


def main(
    argv: list[str] | None = None,
    *,
    inner_transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """CLI entrypoint for offline verification or controlled recording of marketplace cassettes."""
    parser = argparse.ArgumentParser(
        prog="python -m wishenka.items.cassettes",
        description="Verify or record sanitized marketplace web cassettes.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify all reference cassettes in offline REPLAY mode.",
    )
    parser.add_argument(
        "--mode",
        choices=[m.value for m in CassetteMode],
        default=None,
        help="Cassette operation mode: replay, record, or refresh.",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="Target marketplace URL to record or refresh.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output YAML path for a recorded or refreshed cassette.",
    )
    parser.add_argument(
        "--marketplace",
        type=str,
        default=None,
        help="Optional marketplace slug metadata (e.g. ozon, wildberries).",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default=None,
        help="Optional scenario metadata (e.g. product, antibot).",
    )
    parser.add_argument(
        "--cassettes-dir",
        type=Path,
        default=DEFAULT_CASSETTES_DIR,
        help="Directory containing marketplace YAML cassettes.",
    )
    args = parser.parse_args(argv)

    if args.verify or args.mode == CassetteMode.REPLAY.value:
        count = asyncio.run(_verify_all_reference_cassettes(args.cassettes_dir))
        print(f"Verified {count} marketplace cassettes offline.")
        return 0

    if args.mode in (CassetteMode.RECORD.value, CassetteMode.REFRESH.value):
        resolved_mode = CassetteMode(args.mode)
        if (args.url is None) != (args.output is None):
            parser.error("Both --url and --output must be provided together.")
        if args.url is not None and args.output is not None:
            asyncio.run(
                _record_or_refresh_cassette(
                    mode=resolved_mode,
                    url=args.url,
                    output_path=args.output,
                    marketplace=args.marketplace,
                    scenario=args.scenario,
                    inner_transport=inner_transport,
                )
            )
            print(f"{resolved_mode.value.capitalize()}ed cassette at {args.output}.")
            return 0

        count = asyncio.run(
            _refresh_all_cassettes(
                args.cassettes_dir,
                mode=resolved_mode,
                inner_transport=inner_transport,
            )
        )
        print(f"{resolved_mode.value.capitalize()}ed {count} marketplace cassettes.")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "Cassette",
    "CassetteError",
    "CassetteInteraction",
    "CassetteMissError",
    "CassetteMode",
    "CassetteRequest",
    "CassetteResponse",
    "CassetteTransport",
    "DEFAULT_CASSETTES_DIR",
    "SENSITIVE_HEADER_NAMES",
    "cassette_client",
    "load_marketplace_cassette",
    "resolve_cassette_mode",
    "sanitize_headers",
    "sanitize_interaction",
    "sanitize_uri",
]
