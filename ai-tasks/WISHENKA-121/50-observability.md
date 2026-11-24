# WISHENKA-121: Observability Implementation

## Logging Implementation

### Audited Scope

- `wishenka/sqlite.py`: Low-level SQLAlchemy `connect`/`begin` event hooks (`configure_immediate_transactions`) and exception predicate (`is_sqlite_busy`). No per-transaction logging is emitted here to avoid high-volume log noise; busy and error events are logged at the store and route layers.
- `wishenka/users/store.py`: `UserStore` write transaction wrapper (`_immediate`), WAL initialization (`initialize`), and read-only wrapper (`_read`).
- `wishenka/web/routes/auth.py`: `POST /api/auth/telegram` (`UserStoreBusyError` -> HTTP 503).
- `wishenka/web/routes/profile.py`: `PATCH /api/profile/locale` and `PATCH /api/profile/birthdate` (`UserStoreBusyError` -> HTTP 503, `UserNotFoundError` -> HTTP 404).

### Added & Verified Logs

- **ERR**:
  - `wishenka/users/store.py` (`UserStore._immediate`) — `event="user_store_error"`, `operation=<method>` when a non-busy `SQLAlchemyError` occurs during a `BEGIN IMMEDIATE` write transaction. Does not log PII or raw SQL/driver exception text.
  - `wishenka/users/store.py` (`UserStore.initialize`, added in Step 6) — `event="user_store_error"`, `operation="initialize"` when a non-busy `SQLAlchemyError` occurs during autocommit WAL/pragma setup.
- **WARNING**:
  - `wishenka/users/store.py` (`UserStore._immediate` & `UserStore.initialize`) — `event="user_store_busy"`, `operation=<method>` when `is_sqlite_busy(exc)` triggers `UserStoreBusyError`. No PII or raw driver text.
  - `wishenka/web/routes/auth.py` (`auth_telegram`, `status_code=503` added in Step 6) — `event="auth_user_store_busy"`, `status_code=503` on HTTP 503 `UserStoreBusyError`. No `init_data`, `bot_token`, session token, or user PII.
  - `wishenka/web/routes/profile.py` (`update_profile_locale`) — `event="locale_user_store_busy"`, `user_id`, `status_code=503` on HTTP 503 `UserStoreBusyError`.
  - `wishenka/web/routes/profile.py` (`update_profile_locale`, added in Step 6) — `event="locale_user_not_found"`, `user_id`, `status_code=404` on `UserNotFoundError` (aligned with `update_profile_birthdate`).
  - `wishenka/web/routes/profile.py` (`update_profile_birthdate`) — `event="birthdate_user_store_busy"`, `user_id`, `status_code=503` on HTTP 503 `UserStoreBusyError`.

### Log Structure

- Structured logs: yes (`wishenka.logging.JsonFormatter` serializes `extra` fields into JSON when `LOG_JSON=true`).
- Includes context: yes (`event`, `operation`, `status_code`, and internal `user_id` where authenticated; no PII, tokens, or raw SQLite error strings).
- Log levels: `WARNING` (retryable busy / 404 / 503), `ERROR` (unexpected database errors).

## Metrics Implementation (if applicable)

No dedicated Prometheus/metrics backend is configured in the repository; observability relies on structured JSON logging via `wishenka.logging.configure_logging`.

## Monitoring Integration

- [ ] Prometheus metrics (N/A — not used in project)
- [ ] Grafana dashboards (N/A — not used in project)
- [ ] Alerting rules (log-based alerts can match `event="user_store_busy"`, `event="user_store_error"`, and `status_code=503`)
- [x] Log aggregation (`JsonFormatter` in `wishenka/logging.py`)

## Validation Results

- [x] Logs are correctly formatted (structured `extra` dict compatible with `JsonFormatter`)
- [x] Logging works in error scenarios (verified via `caplog` in `tests/test_user_store_concurrency_repro.py`)
- [x] Large data structures, PII, and tokens are not logged in `user_store_busy`, `user_store_error`, or HTTP 503 handlers

## Notes

- `UserStore._read` mirrors `WishlistStore.execute_read` and does not swallow or remap `SQLAlchemyError` on read-only queries.
- `wishenka/bot/i18n.py` continues to apply `_PrivateUserLogFilter` to `wishenka.users` during private bot interactions.
