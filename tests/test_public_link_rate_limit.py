"""Tests for WISHENKA-88: public-link rate limiting."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, Request, Response
from pydantic import ValidationError

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.web.rate_limit import (
    PublicLinkRateLimitMiddleware,
    SlidingWindowRateLimiter,
    resolve_client_ip,
)
from wishenka.wishlists.service import WishlistService

pytestmark = pytest.mark.timeout(30)


@asynccontextmanager
async def _build_app(
    tmp_path: Path,
    *,
    db_name: str = "rate_limit.db",
    enabled: bool = True,
    max_requests: int = 3,
    window_seconds: int = 60,
    trust_proxy_headers: bool = False,
) -> AsyncIterator[tuple[FastAPI, str, str]]:
    """Create a test FastAPI app with public-link rate limiting configured and seed one wishlist."""
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / db_name}",
        secret_key="rate-limit-test-secret",
        public_rate_limit_enabled=enabled,
        public_rate_limit_max_requests=max_requests,
        public_rate_limit_window_seconds=window_seconds,
        public_rate_limit_trust_proxy_headers=trust_proxy_headers,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        await app.state.user_store.upsert_user(TelegramUser(id=101, first_name="Alice"))
        service: WishlistService = app.state.domain_service
        owner = AuthenticatedUser(
            telegram_id=101,
            first_name="Alice",
            username=None,
            auth_method="session_token",
        )
        wishlist = await service.create_wishlist(owner=owner, title="Secret Birthday List")
        yield app, str(wishlist.public_token), str(wishlist.invite_token)


def _http_scope_request(
    *,
    method: str = "GET",
    path: str = "/share/example-token",
    client: tuple[str, int] | None = ("127.0.0.1", 80),
    headers: dict[str, str] | None = None,
    app: FastAPI | None = None,
) -> Request:
    """Build a Request from an ASGI scope, including a missing socket peer."""
    raw_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    scope: dict[str, Any] = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "query_string": b"",
        "headers": raw_headers,
        "client": client,
        "server": ("testserver", 80),
    }
    if app is not None:
        scope["app"] = app
    return Request(scope)


async def _passthrough(_request: Request) -> Response:
    """Stand-in route used when the limiter itself is the subject."""
    return Response(status_code=204)


def _assert_retry_after(response: httpx.Response, *, window_seconds: int) -> None:
    """Refusal matches the existing public-link Retry-After contract."""
    assert response.status_code == 429
    assert "Retry-After" in response.headers
    retry_after = int(response.headers["Retry-After"])
    assert 1 <= retry_after <= window_seconds


@pytest.mark.asyncio
async def test_public_links_within_limit_are_allowed(tmp_path: Path) -> None:
    """Requests within the configured limit to /share, /invite, and /invite/join are not blocked."""
    async with _build_app(tmp_path, max_requests=3, window_seconds=60) as (
        app,
        public_token,
        invite_token,
    ):
        transport = httpx.ASGITransport(app=app, client=("10.0.0.1", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            r1 = await client.get(f"/share/{public_token}")
            r2 = await client.get(f"/invite/{invite_token}")
            r3 = await client.post(
                f"/invite/{invite_token}/join",
                headers={"Origin": "http://testserver"},
            )

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code != 429


@pytest.mark.asyncio
async def test_public_links_exceeding_limit_return_429_and_retry_after(tmp_path: Path) -> None:
    """Exceeding the limit (including nonexistent tokens) returns 429 and Retry-After."""
    async with _build_app(tmp_path, max_requests=3, window_seconds=60) as (
        app,
        public_token,
        invite_token,
    ):
        transport = httpx.ASGITransport(app=app, client=("10.0.0.10", 12345))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for idx in range(3):
                resp = await client.get(f"/share/nonexistent-token-{idx}")
                assert resp.status_code == 404

            # 4th request to any public link from the same client must be rate-limited
            blocked_html = await client.get(
                f"/share/{public_token}",
                headers={"Accept-Language": "en"},
            )
            assert blocked_html.status_code == 429
            assert "Retry-After" in blocked_html.headers
            retry_after = int(blocked_html.headers["Retry-After"])
            assert 1 <= retry_after <= 60
            assert public_token not in blocked_html.text
            assert "Secret Birthday List" not in blocked_html.text
            assert blocked_html.headers.get("X-Content-Type-Options") == "nosniff"
            assert blocked_html.headers.get("Referrer-Policy") == "no-referrer"

            # Subsequent /invite/{token} and /invite/{token}/join are also rate-limited
            blocked_invite = await client.get(
                f"/invite/{invite_token}",
                headers={"Accept": "application/json", "Accept-Language": "ru"},
            )
            assert blocked_invite.status_code == 429
            assert "Retry-After" in blocked_invite.headers
            assert invite_token not in blocked_invite.text

            blocked_join = await client.post(
                f"/invite/{invite_token}/join",
                headers={"Origin": "http://testserver"},
            )
            assert blocked_join.status_code == 429
            assert "Retry-After" in blocked_join.headers


@pytest.mark.asyncio
async def test_rate_limit_isolates_clients_and_ignores_spoofed_xff_by_default(
    tmp_path: Path,
) -> None:
    """Rate limits are isolated per client IP and ignore X-Forwarded-For unless trusted."""
    async with _build_app(
        tmp_path,
        db_name="isolation.db",
        max_requests=2,
        window_seconds=60,
        trust_proxy_headers=False,
    ) as (app, public_token, _invite_token):
        t1 = httpx.ASGITransport(app=app, client=("10.0.0.1", 1111))
        t2 = httpx.ASGITransport(app=app, client=("10.0.0.2", 2222))

        async with httpx.AsyncClient(transport=t1, base_url="http://testserver") as c1:
            assert (
                await c1.get(f"/share/{public_token}", headers={"X-Forwarded-For": "1.1.1.1"})
            ).status_code == 200
            assert (
                await c1.get(f"/share/{public_token}", headers={"X-Forwarded-For": "2.2.2.2"})
            ).status_code == 200
            # Spoofed X-Forwarded-For must NOT bypass the limit when trust_proxy_headers=False
            blocked = await c1.get(
                f"/share/{public_token}",
                headers={"X-Forwarded-For": "3.3.3.3"},
            )
            assert blocked.status_code == 429

        # Different client IP must not be affected
        async with httpx.AsyncClient(transport=t2, base_url="http://testserver") as c2:
            ok = await c2.get(f"/share/{public_token}")
            assert ok.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_respects_proxy_headers_when_trusted(tmp_path: Path) -> None:
    """When trust_proxy_headers=True, X-Forwarded-For isolates distinct downstream clients."""
    async with _build_app(
        tmp_path,
        db_name="proxy.db",
        max_requests=2,
        window_seconds=60,
        trust_proxy_headers=True,
    ) as (app, public_token, _invite_token):
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 8080))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            assert (
                await client.get(
                    f"/share/{public_token}",
                    headers={"X-Forwarded-For": "203.0.113.10"},
                )
            ).status_code == 200
            assert (
                await client.get(
                    f"/share/{public_token}",
                    headers={"X-Forwarded-For": "203.0.113.10"},
                )
            ).status_code == 200
            blocked = await client.get(
                f"/share/{public_token}",
                headers={"X-Forwarded-For": "203.0.113.10"},
            )
            assert blocked.status_code == 429

            other_client = await client.get(
                f"/share/{public_token}",
                headers={"X-Forwarded-For": "203.0.113.11"},
            )
            assert other_client.status_code == 200


@pytest.mark.asyncio
async def test_rate_limit_recovers_after_window_expires(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Client regains access once the sliding window has elapsed."""
    now = [1000.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])

    async with _build_app(
        tmp_path,
        db_name="recovery.db",
        max_requests=2,
        window_seconds=60,
    ) as (app, public_token, _invite_token):
        transport = httpx.ASGITransport(app=app, client=("10.0.0.5", 5555))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            assert (await client.get(f"/share/{public_token}")).status_code == 200
            now[0] = 1010.0
            assert (await client.get(f"/share/{public_token}")).status_code == 200
            now[0] = 1020.0
            assert (await client.get(f"/share/{public_token}")).status_code == 429

            # Advance past the 60s window from the earliest recorded request (1000.0 + 60.0)
            now[0] = 1061.0
            assert (await client.get(f"/share/{public_token}")).status_code == 200


@pytest.mark.asyncio
async def test_non_public_routes_are_not_rate_limited(tmp_path: Path) -> None:
    """Non-public routes like /healthz are unaffected even after public link limit is hit."""
    async with _build_app(
        tmp_path,
        db_name="healthz.db",
        max_requests=1,
        window_seconds=60,
    ) as (app, public_token, _invite_token):
        transport = httpx.ASGITransport(app=app, client=("10.0.0.9", 9999))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            assert (await client.get(f"/share/{public_token}")).status_code == 200
            assert (await client.get(f"/share/{public_token}")).status_code == 429

            health = await client.get("/healthz")
            assert health.status_code == 200
            assert health.json() == {"status": "ok"}


def test_sliding_window_limiter_evicts_oldest_when_max_clients_reached() -> None:
    """Bounded max_clients prunes expired buckets first and evicts LRU client if still full."""
    now = [100.0]
    limiter = SlidingWindowRateLimiter(
        max_requests=2,
        window_seconds=60,
        max_clients=2,
        clock=lambda: now[0],
    )

    assert limiter.check_and_record("client-1").allowed is True
    now[0] = 101.0
    assert limiter.check_and_record("client-2").allowed is True
    assert limiter.tracked_clients == 2

    # Active capacity reached: adding client-3 evicts least-recently-used client-1
    now[0] = 102.0
    assert limiter.check_and_record("client-3").allowed is True
    assert limiter.tracked_clients == 2

    # Advance past window so client-2 and client-3 expire; client-4 prunes them
    now[0] = 200.0
    assert limiter.check_and_record("client-4").allowed is True
    assert limiter.tracked_clients == 1


@pytest.mark.asyncio
async def test_rate_limit_localized_429_responses(tmp_path: Path) -> None:
    """429 responses honor ?lang= and Accept-Language in both HTML and JSON formats."""
    async with _build_app(
        tmp_path,
        db_name="i18n.db",
        max_requests=1,
        window_seconds=60,
    ) as (app, public_token, _invite_token):
        transport = httpx.ASGITransport(app=app, client=("10.0.0.20", 1234))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            assert (await client.get(f"/share/{public_token}")).status_code == 200

            ru_html = await client.get(
                f"/share/{public_token}",
                headers={"Accept-Language": "ru"},
            )
            assert ru_html.status_code == 429
            assert "Слишком много запросов" in ru_html.text

            en_html = await client.get(
                f"/share/{public_token}?lang=en",
                headers={"Accept-Language": "ru"},
            )
            assert en_html.status_code == 429
            assert "Too many requests" in en_html.text

            ru_json = await client.get(
                f"/share/{public_token}",
                headers={"Accept": "application/json", "Accept-Language": "ru"},
            )
            assert ru_json.status_code == 429
            payload = ru_json.json()
            assert "Слишком много запросов" in payload["detail"]
            assert isinstance(payload["retry_after"], int)
            assert payload["retry_after"] >= 1


@pytest.mark.asyncio
async def test_rate_limit_disabled_allows_requests(tmp_path: Path) -> None:
    """When public_rate_limit_enabled=False, requests are not throttled."""
    async with _build_app(
        tmp_path,
        db_name="disabled.db",
        enabled=False,
        max_requests=1,
        window_seconds=60,
    ) as (app, public_token, _invite_token):
        transport = httpx.ASGITransport(app=app, client=("10.0.0.30", 1234))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for _ in range(3):
                resp = await client.get(f"/share/{public_token}")
                assert resp.status_code == 200


def test_rate_limit_settings_validation() -> None:
    """Settings rejects out-of-range public rate-limit parameters."""
    with pytest.raises(ValidationError):
        Settings(public_rate_limit_max_requests=0)
    with pytest.raises(ValidationError):
        Settings(public_rate_limit_window_seconds=0)
    with pytest.raises(ValidationError):
        Settings(public_rate_limit_max_clients=50)


@pytest.mark.asyncio
async def test_rate_limit_logs_structured_event_without_token_leakage(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Rate-limited requests log structured fields and never leak raw capability tokens."""
    async with _build_app(
        tmp_path,
        db_name="observability.db",
        max_requests=1,
        window_seconds=60,
    ) as (app, public_token, invite_token):
        transport = httpx.ASGITransport(app=app, client=("10.0.0.40", 4321))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            caplog.clear()
            with caplog.at_level(logging.DEBUG, logger="wishenka"):
                ok_resp = await client.get(f"/share/{public_token}")
                assert ok_resp.status_code == 200
                assert not [
                    r
                    for r in caplog.records
                    if getattr(r, "event", None) == "public_link_rate_limited"
                ]

                blocked_share = await client.get(f"/share/{public_token}")
                assert blocked_share.status_code == 429

                blocked_join = await client.post(
                    f"/invite/{invite_token}/join",
                    headers={"Origin": "http://testserver"},
                )
                assert blocked_join.status_code == 429

        rate_limit_records = [
            r
            for r in caplog.records
            if r.name == "wishenka.web.rate_limit"
            and getattr(r, "event", None) == "public_link_rate_limited"
        ]
        assert len(rate_limit_records) == 2

        share_record, join_record = rate_limit_records
        assert share_record.levelno == logging.WARNING
        assert getattr(share_record, "route", None) == "/share/{token}"
        assert getattr(share_record, "method", None) == "GET"
        assert getattr(share_record, "client_ip", None) == "10.0.0.40"
        assert isinstance(getattr(share_record, "retry_after", None), int)
        assert getattr(share_record, "retry_after", 0) >= 1

        assert join_record.levelno == logging.WARNING
        assert getattr(join_record, "route", None) == "/invite/{token}/join"
        assert getattr(join_record, "method", None) == "POST"
        assert getattr(join_record, "client_ip", None) == "10.0.0.40"
        assert isinstance(getattr(join_record, "retry_after", None), int)
        assert getattr(join_record, "retry_after", 0) >= 1

        wishenka_records = [r for r in caplog.records if r.name.startswith("wishenka")]
        assert wishenka_records
        for record in wishenka_records:
            assert public_token not in record.getMessage()
            assert invite_token not in record.getMessage()
            for value in record.__dict__.values():
                if isinstance(value, str):
                    assert public_token not in value
                    assert invite_token not in value


@pytest.mark.asyncio
async def test_head_share_shares_allowance_with_get(tmp_path: Path) -> None:
    """HEAD /share/{token} spends the same allowance, so the third call is refused."""
    async with _build_app(
        tmp_path,
        db_name="head_share.db",
        max_requests=2,
        window_seconds=60,
    ) as (app, public_token, _invite_token):
        transport = httpx.ASGITransport(app=app, client=("10.0.0.50", 1500))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            head = await client.head(f"/share/{public_token}")
            first_get = await client.get(f"/share/{public_token}")
            second_get = await client.get(f"/share/{public_token}")

        assert head.status_code != 429
        assert first_get.status_code == 200
        assert second_get.status_code == 429


@pytest.mark.asyncio
async def test_head_invite_shares_allowance_with_get(tmp_path: Path) -> None:
    """Two HEAD /invite/{token} probes spend the allowance, so the following GET is 429."""
    async with _build_app(
        tmp_path,
        db_name="head_invite.db",
        max_requests=2,
        window_seconds=60,
    ) as (app, _public_token, invite_token):
        transport = httpx.ASGITransport(app=app, client=("10.0.0.51", 1501))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first_head = await client.head(f"/invite/{invite_token}")
            second_head = await client.head(f"/invite/{invite_token}")
            opened = await client.get(f"/invite/{invite_token}")

        assert first_head.status_code != 429
        assert second_head.status_code != 429
        assert opened.status_code == 429


@pytest.mark.asyncio
async def test_head_unknown_share_token_is_rate_limited_without_leaking(tmp_path: Path) -> None:
    """Unknown-secret HEAD probes share one allowance and the refusal names no secret."""
    async with _build_app(
        tmp_path,
        db_name="head_unknown.db",
        max_requests=1,
        window_seconds=60,
    ) as (app, _public_token, _invite_token):
        transport = httpx.ASGITransport(app=app, client=("10.0.0.52", 1502))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first = await client.head("/share/missing-one")
            second = await client.head("/share/missing-two")

        assert first.status_code != 429
        _assert_retry_after(second, window_seconds=60)
        assert "missing-one" not in second.text
        assert "missing-two" not in second.text
        assert "Secret Birthday List" not in second.text


@pytest.mark.asyncio
async def test_head_past_allowance_matches_page_open_refusal(tmp_path: Path) -> None:
    """Once GET has filled the budget, HEAD on share and invite is the same 429."""
    async with _build_app(
        tmp_path,
        db_name="head_refused.db",
        max_requests=1,
        window_seconds=60,
    ) as (app, public_token, invite_token):
        transport = httpx.ASGITransport(app=app, client=("10.0.0.53", 1503))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            opened = await client.get(f"/share/{public_token}")
            blocked_share = await client.head(f"/share/{public_token}")
            blocked_invite = await client.head(f"/invite/{invite_token}")

        assert opened.status_code == 200
        _assert_retry_after(blocked_share, window_seconds=60)
        _assert_retry_after(blocked_invite, window_seconds=60)
        assert public_token not in blocked_share.text
        assert invite_token not in blocked_invite.text
        assert "Secret Birthday List" not in blocked_share.text
        assert "Secret Birthday List" not in blocked_invite.text


@pytest.mark.asyncio
async def test_in_budget_public_links_stay_available_when_head_is_counted(
    tmp_path: Path,
) -> None:
    """Inside the allowance, HEAD, share open, invite open, and join stay available."""
    async with _build_app(
        tmp_path,
        db_name="head_in_budget.db",
        max_requests=4,
        window_seconds=60,
    ) as (app, public_token, invite_token):
        transport = httpx.ASGITransport(app=app, client=("10.0.0.54", 1504))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            head = await client.head(f"/share/{public_token}")
            share = await client.get(f"/share/{public_token}")
            invite = await client.get(f"/invite/{invite_token}")
            joined = await client.post(
                f"/invite/{invite_token}/join",
                headers={"Origin": "http://testserver"},
            )

        assert head.status_code != 429
        assert share.status_code == 200
        assert invite.status_code == 200
        assert joined.status_code != 429


def test_resolve_client_ip_uses_x_real_ip_when_proxy_trusted() -> None:
    """Trusted X-Real-IP is the visitor; whitespace is stripped; X-Forwarded-For wins."""
    peer = ("192.0.2.10", 4000)
    named = _http_scope_request(
        client=peer,
        headers={"X-Real-IP": "  203.0.113.8  "},
    )
    assert resolve_client_ip(named, trust_proxy_headers=True) == "203.0.113.8"

    forwarded = _http_scope_request(
        client=peer,
        headers={
            "X-Forwarded-For": "198.51.100.20",
            "X-Real-IP": "203.0.113.8",
        },
    )
    assert resolve_client_ip(forwarded, trust_proxy_headers=True) == "198.51.100.20"


def test_resolve_client_ip_ignores_x_real_ip_when_proxy_untrusted() -> None:
    """With proxy trust off, X-Real-IP is ignored and the socket peer is the visitor."""
    request = _http_scope_request(
        client=("10.0.0.7", 70),
        headers={"X-Real-IP": "203.0.113.8"},
    )
    assert resolve_client_ip(request, trust_proxy_headers=False) == "10.0.0.7"


def test_resolve_client_ip_unknown_when_client_missing() -> None:
    """No socket peer and no trusted address is the single key ``unknown``."""
    request = _http_scope_request(client=None)
    assert resolve_client_ip(request, trust_proxy_headers=False) == "unknown"
    assert resolve_client_ip(request, trust_proxy_headers=True) == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("trust_proxy_headers", [False, True])
async def test_unidentified_requests_share_one_public_link_allowance(
    tmp_path: Path,
    trust_proxy_headers: bool,
) -> None:
    """Two peer-less public-link requests with no trusted address share one allowance."""
    async with _build_app(
        tmp_path,
        db_name="unknown_peer.db",
        max_requests=1,
        window_seconds=60,
        trust_proxy_headers=trust_proxy_headers,
    ) as (app, public_token, _invite_token):
        middleware = PublicLinkRateLimitMiddleware(app)
        path = f"/share/{public_token}"
        first = await middleware.dispatch(
            _http_scope_request(path=path, client=None, app=app),
            _passthrough,
        )
        second = await middleware.dispatch(
            _http_scope_request(path=path, client=None, app=app),
            _passthrough,
        )

        assert first.status_code != 429
        assert second.status_code == 429


@pytest.mark.asyncio
async def test_distinct_trusted_x_real_ip_visitors_have_separate_allowances(
    tmp_path: Path,
) -> None:
    """Trusted X-Real-IP values are separate visitors even when the socket peer matches."""
    async with _build_app(
        tmp_path,
        db_name="x_real_ip.db",
        max_requests=1,
        window_seconds=60,
        trust_proxy_headers=True,
    ) as (app, public_token, _invite_token):
        transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 8080))
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            first = await client.get(
                f"/share/{public_token}",
                headers={"X-Real-IP": "203.0.113.8"},
            )
            other = await client.get(
                f"/share/{public_token}",
                headers={"X-Real-IP": "203.0.113.9"},
            )
            repeat = await client.get(
                f"/share/{public_token}",
                headers={"X-Real-IP": "203.0.113.8"},
            )

        assert first.status_code != 429
        assert other.status_code != 429
        assert repeat.status_code == 429
