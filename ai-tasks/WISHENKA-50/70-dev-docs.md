# WISHENKA-50: Developer Documentation Updates

## Overview

This document summarizes the developer documentation updates made for Jira task WISHENKA-50:
"[Техдолг] Конфигурируемый TTL токенов и фоновая очистка истекших приглашений".

Primary documentation file updated:
- [`doc/dev/wishlists.md`](file:///home/src/doc/dev/wishlists.md)

## Summary of Documentation Updates

### 1. Configurable Token TTL & Retention Settings
Documented new configuration fields in `wishenka.config.Settings` and environment variables:
- `invite_token_ttl_seconds: int = 604800` (7 days):
  Configures collaborator onboarding invite token TTL.
  Environment variable: `WISHENKA_INVITE_TOKEN_TTL_SECONDS`.
- `wishlist_retention_days: int = 30` (30 days):
  Retention window before permanently purging soft-deleted wishlists.
  Environment variable: `WISHENKA_WISHLIST_RETENTION_DAYS`.
- `background_cleanup_interval_seconds: int = 3600` (1 hour):
  Sleep interval between background cleanup runs.
  Environment variable: `WISHENKA_BACKGROUND_CLEANUP_INTERVAL_SECONDS`.
- `background_cleanup_enabled: bool = True`:
  Master toggle for background cleanup worker in application lifespan.
  Environment variable: `WISHENKA_BACKGROUND_CLEANUP_ENABLED`.

### 2. Repository Maintenance & Cleanup Methods
Documented data access methods in `wishenka.wishlists.repository.WishlistRepository`:
- `cleanup_expired_tokens(now: datetime | None = None) -> int`:
  Revokes expired collaborator invite tokens (`invite_token_expires_at <= now`),
  removes capability tokens from `wl_invite_tokens`, prepends `'revoked:'` in `wl_lists`,
  and nullifies `invite_token_expires_at`.
- `purge_archived_wishlists(threshold: datetime) -> int`:
  Permanently deletes soft-deleted wishlists (`status = 'deleted'`) where `updated_at <= threshold`.
  Deletes associated tokens from `wl_tokens` and `wl_invite_tokens`, then executes row-level
  `DELETE FROM wl_lists` with `PRAGMA foreign_keys = ON`, cascading atomically to members, items,
  reservations, favorites, and history entries.
- `purge_deleted_wishlists(threshold: datetime) -> int`:
  Semantic alias forwarding directly to `purge_archived_wishlists`.
- `WishlistStore` convenience methods:
  Added matching asynchronous proxies on `WishlistStore` executing within serialized write
  transactions (`BEGIN IMMEDIATE`).

### 3. Background Cleanup Architecture (`wishenka.wishlists.cleanup`)
Documented background maintenance components:
- `CleanupStats` dataclass:
  Records `expired_tokens_cleaned`, `wishlists_purged`, `duration_ms`, `started_at`,
  and `finished_at`.
- `run_cleanup_cycle(store, settings, now=None) -> CleanupStats`:
  Runs one complete cleanup cycle, catches operational exceptions gracefully, and emits
  structured audit logs (`background_cleanup_completed` or `background_cleanup_failed`).
- `background_cleanup_worker(store, settings, stop_event=None) -> None`:
  Long-running worker loop executing periodic cleanup cycles at configured intervals.
  Emits `background_worker_started` and `background_worker_stopped`.

### 4. Application Lifespan & Test Configuration
Documented integration with FastAPI lifespan in `wishenka.web.app.create_app`:
- Worker lifecycle: spawned on app startup when `settings.background_cleanup_enabled` is True,
  cancelled and awaited on shutdown.
- Disabling worker in test environments:
  Pass `background_cleanup_enabled=False` to `Settings(...)` or set environment variable
  `WISHENKA_BACKGROUND_CLEANUP_ENABLED=false` to prevent background tasks during tests.
  Allows tests to invoke `run_cleanup_cycle` deterministically with synthetic timestamps.

### 5. Observability & Audit Logging
Documented new structured logging events under `wishenka.wishlists` logger namespace:
- `background_worker_started` (`INFO`): logged at worker startup with interval.
- `background_worker_stopped` (`INFO`): logged on graceful worker shutdown.
- `background_cleanup_completed` (`INFO`): cycle metrics (cleaned, purged, duration_ms).
- `background_cleanup_failed` (`ERROR`): operational errors with exc_info.
- `wishlist_repo_mutation` (`INFO`): repository mutation counts for cleanup operations.

## Verification Checklist

- [x] Configurable token TTL documented (`invite_token_ttl_seconds`).
- [x] Soft-deleted retention window documented (`wishlist_retention_days`).
- [x] Background cleanup runner and worker documented (`wishenka.wishlists.cleanup`).
- [x] Repository cleanup methods documented (`WishlistRepository`, `WishlistStore`).
- [x] Disabling worker in tests documented (`background_cleanup_enabled = False`).
- [x] All lines strictly <= 100 characters.
