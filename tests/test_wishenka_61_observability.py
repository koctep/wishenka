"""Observability tests for WISHENKA-61 (Step 6): idempotency logging and privacy invariants."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.test_booking_idempotency import (
    _GIFTER_ID,
    _OWNER_ID,
    _SQLITE_PREFIX,
    _auth_header,
    _seed_wishlist_and_item,
)
from wishenka.auth.session import SessionTokenService
from wishenka.config import Settings
from wishenka.web.app import create_app
from wishenka.wishlists.cleanup import run_cleanup_cycle
from wishenka.wishlists.store import WishlistStore

pytestmark = pytest.mark.timeout(20)

_FORBIDDEN_FIELDS = {
    "idempotency_key",
    "request_hash",
    "response_body",
    "body",
    "token",
}


def _events(
    caplog: pytest.LogCaptureFixture, logger_name: str, event_name: str
) -> list[logging.LogRecord]:
    return [
        r for r in caplog.records if r.name == logger_name and getattr(r, "event", "") == event_name
    ]


def _assert_no_secret_leak(
    records: list[logging.LogRecord],
    forbidden_values: tuple[str, ...],
) -> None:
    for record in records:
        assert not (_FORBIDDEN_FIELDS & set(record.__dict__.keys()))
        rendered = f"{record.getMessage()} {record.__dict__}"
        for secret in forbidden_values:
            assert secret not in rendered


@pytest.fixture
def obs_app(tmp_path: Path) -> Iterator[tuple[TestClient, SessionTokenService, FastAPI]]:
    """Create an isolated FastAPI TestClient backed by a temporary SQLite database."""
    settings = Settings(
        database_url=f"{_SQLITE_PREFIX}{tmp_path / 'idempotency_obs.db'}",
        secret_key="idempotency-obs-test-secret",
    )
    app = create_app(settings)
    sessions = SessionTokenService(settings.secret_key)
    with TestClient(app) as client:
        yield client, sessions, app


def test_idempotency_replay_hit_logs_without_leaking_key_or_surprise(
    obs_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Replay hit logs idempotency_replay_hit once and suppresses duplicate commit log."""
    client, sessions, app = obs_app
    wishlist_id, item_id, public_token = _seed_wishlist_and_item(app, quantity=3)
    raw_key = "obs-replay-secret-key-001"
    headers = _auth_header(sessions, _GIFTER_ID, "Gifter", idempotency_key=raw_key)

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="wishenka.wishlists.store"):
        r1 = client.post(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations",
            json={"quantity": 1},
            headers=headers,
        )
        r2 = client.post(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations",
            json={"quantity": 1},
            headers=headers,
        )
    assert r1.status_code == 201
    assert r2.status_code == 201

    commits = _events(caplog, "wishenka.wishlists.store", "wishlist_inventory_committed")
    replays = _events(caplog, "wishenka.wishlists.store", "idempotency_replay_hit")
    assert len(commits) == 1
    assert len(replays) == 1
    assert replays[0].__dict__["item_id"] == item_id
    assert replays[0].__dict__["operation"] == "create_reservation"
    assert replays[0].__dict__["response_status"] == 201
    _assert_no_secret_leak(
        replays,
        (raw_key, public_token, "Board Game", "Birthday"),
    )
    assert "actor_id" not in replays[0].__dict__


def test_idempotency_conflict_logs_for_reservation_and_receipt(
    obs_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Payload mismatch 409 emits structured conflict warnings without raw key."""
    client, sessions, app = obs_app
    wishlist_id, item_id, public_token = _seed_wishlist_and_item(app, quantity=3)

    res_key = "obs-conflict-res-key"
    res_headers = _auth_header(sessions, _GIFTER_ID, "Gifter", idempotency_key=res_key)
    assert (
        client.post(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations",
            json={"quantity": 1},
            headers=res_headers,
        ).status_code
        == 201
    )

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        conflict_res = client.post(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations",
            json={"quantity": 2},
            headers=res_headers,
        )
    assert conflict_res.status_code == 409
    res_conflicts = _events(caplog, "wishenka.web.reservations", "reservation_idempotency_conflict")
    rollbacks = _events(caplog, "wishenka.wishlists.store", "wishlist_inventory_rolled_back")
    assert len(res_conflicts) == 1
    assert res_conflicts[0].__dict__["reason"] == "idempotency_conflict"
    assert res_conflicts[0].__dict__["item_id"] == item_id
    assert len(rollbacks) == 1
    assert rollbacks[0].__dict__["error_type"] == "IdempotencyConflictError"
    _assert_no_secret_leak(res_conflicts + rollbacks, (res_key, public_token, "Board Game"))

    # Receipt endpoint conflict
    rcpt_key = "obs-conflict-rcpt-key"
    rcpt_headers = _auth_header(sessions, _OWNER_ID, "Owner", idempotency_key=rcpt_key)
    assert (
        client.post(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts",
            json={"quantity": 1},
            headers=rcpt_headers,
        ).status_code
        == 201
    )

    caplog.clear()
    with caplog.at_level(logging.WARNING):
        conflict_rcpt = client.post(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/receipts",
            json={"quantity": 2},
            headers=rcpt_headers,
        )
    assert conflict_rcpt.status_code == 409
    rcpt_conflicts = _events(caplog, "wishenka.web.receipts", "receipt_idempotency_conflict")
    assert len(rcpt_conflicts) == 1
    _assert_no_secret_leak(rcpt_conflicts, (rcpt_key, public_token, "Board Game"))


def test_invalid_idempotency_key_logs_warning_without_raw_value_or_token(
    obs_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Malformed Idempotency-Key header logs key_length and route template, not raw key or token."""
    client, sessions, app = obs_app
    _, item_id, public_token = _seed_wishlist_and_item(app, quantity=2)
    bad_key = "bad key with spaces!@#"
    headers = _auth_header(sessions, _GIFTER_ID, "Gifter", idempotency_key=bad_key)

    caplog.clear()
    with caplog.at_level(logging.WARNING, logger="wishenka.web.idempotency"):
        resp = client.post(
            f"/api/public/wishlists/{public_token}/items/{item_id}/reservations",
            json={"quantity": 1},
            headers=headers,
        )
    assert resp.status_code == 400

    invalid_logs = _events(caplog, "wishenka.web.idempotency", "idempotency_key_invalid")
    assert len(invalid_logs) == 1
    assert invalid_logs[0].__dict__["method"] == "POST"
    assert invalid_logs[0].__dict__["key_length"] == len(bad_key)
    assert invalid_logs[0].__dict__["route_path"] == (
        "/api/public/wishlists/{token}/items/{item_id}/reservations"
    )
    _assert_no_secret_leak(invalid_logs, (bad_key, public_token))


def test_expired_idempotency_cleanup_logs_counts(
    obs_app: tuple[TestClient, SessionTokenService, FastAPI],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Cleanup logs idempotency_records_purged only when >0 and records count in cycle summary."""
    client, sessions, app = obs_app
    wishlist_id, item_id, _ = _seed_wishlist_and_item(app, quantity=2)
    headers = _auth_header(sessions, _GIFTER_ID, "Gifter", idempotency_key="obs-cleanup-key-1")
    assert (
        client.post(
            f"/api/wishlists/{wishlist_id}/items/{item_id}/reservations",
            json={"quantity": 1},
            headers=headers,
        ).status_code
        == 201
    )

    store: WishlistStore = app.state.wishlist_store
    settings: Settings = app.state.settings

    # Not yet expired -> 0 cleaned, no idempotency_records_purged log
    caplog.clear()
    with caplog.at_level(logging.INFO):
        stats_none = asyncio.run(run_cleanup_cycle(store, settings, now=datetime.now(UTC)))
    assert stats_none.idempotency_records_cleaned == 0
    assert _events(caplog, "wishenka.wishlists.store", "idempotency_records_purged") == []
    cycle_none = _events(caplog, "wishenka.wishlists.cleanup", "background_cleanup_completed")
    assert len(cycle_none) == 1
    assert cycle_none[0].__dict__["idempotency_records_cleaned"] == 0

    # Past retention -> 1 cleaned, both purged and cycle summary logs emitted
    caplog.clear()
    with caplog.at_level(logging.INFO):
        stats_one = asyncio.run(
            run_cleanup_cycle(store, settings, now=datetime.now(UTC) + timedelta(hours=25))
        )
    assert stats_one.idempotency_records_cleaned == 1
    purged_logs = _events(caplog, "wishenka.wishlists.store", "idempotency_records_purged")
    assert len(purged_logs) == 1
    assert purged_logs[0].__dict__["purged_count"] == 1
    cycle_one = _events(caplog, "wishenka.wishlists.cleanup", "background_cleanup_completed")
    assert len(cycle_one) == 1
    assert cycle_one[0].__dict__["idempotency_records_cleaned"] == 1
