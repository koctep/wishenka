"""Tests for WISHENKA-88: public-link rate limiting."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from wishenka.auth.models import AuthenticatedUser, TelegramUser
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.web.rate_limit import SlidingWindowRateLimiter
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
