# WISHENKA-182: Observability Implementation

## Logging Implementation

### Added Logs

No new production log statements were added in `WISHENKA-182`. Existing structured logging and privacy controls already cover all modified/created components:

- **INFO / WARNING / ERROR (`wishenka/bot/support.py`)**: All support flow outcomes remain logged via structured `extra={"event": ...}` events without PII, message bodies, or capability tokens:
  - `bot_support_prompted` (INFO)
  - `bot_support_cancelled` (INFO)
  - `bot_support_rejected` (`reason`: `empty`, `too_long`, `rate_limited`) (INFO)
  - `bot_support_unavailable` (`reason`: `unconfigured`, `partial_send_failed` at WARNING; `send_failed` at ERROR)
  - `bot_support_submitted` (`outcome`: `delivered`, `partial`) (INFO)
- **Privacy Suppression (`wishenka/bot/principal.py`, `wishenka/bot/i18n.py`)**: `ensure_private_bot_user` preserves the `_private_bot_user` `ContextVar` guard around `users.upsert_from_bot(user)` so `_PrivateUserLogFilter` suppresses `wishenka.users` identifier logs during private bot interactions (verified by `tests/test_wishenka_182_repro.py`).
- **Capability Redaction (`wishenka/bot/support.py`)**: `redact_capabilities` masks regex-matched capability tokens (`p_*`, `i_*`, `/share/*`, `/invite/*`, `/api/public/wishlists/*`, `startapp=*`) and user-scoped tokens from `collect_diagnostic_context` before support ticket formatting/delivery.
- **Database Parameter Suppression (`wishenka/wishlists/store.py`)**: `WishlistStore.execute_read` inherits the engine's `hide_parameters=True` setting and `aiosqlite` `WARNING` log level, preventing SQL bound parameters (including capability tokens) from leaking into logs. Per-transaction logs are intentionally omitted on `execute_read` (consistent with `WishlistStore.transaction` / `_immediate`) to avoid high-volume log noise.
- **Router Error & Capture Filters (`wishenka/bot/entry.py`, `wishenka/bot/capture.py`)**: `entry_error` logs sanitized exception types (`bot_start_failed`) without tracebacks/tokens, and `_PrivatePreviewFilter` remains active in `capture.py`.

### Log Structure

Log format used:
- Structured logs: yes (`wishenka.logging.JsonFormatter` with `extra={"event": ...}` metadata)
- Includes context: yes (event name, outcome/reason, sanitized error type; PII and capability tokens excluded or suppressed)
- Log levels: `INFO`, `WARNING`, `ERROR` (plus `DEBUG` for non-sensitive diagnostics where already configured)

## Metrics Implementation (if applicable)

Not applicable — the repository does not use Prometheus or a dedicated metrics backend. Diagnostic counters in `collect_diagnostic_context` (`active_wishlist_count`, `archived_wishlist_count`, `collaborative_membership_count`, `bot_destination_active`, `active_draft_present`) continue to be included in support ticket headers.

### Performance Metrics

- N/A (no metrics collector configured in `wishenka`)

### Business Metrics

- N/A

### System Health Metrics

- N/A

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (N/A — not used in repository)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A)
- [x] Log aggregation (structured JSON output via `wishenka.logging.JsonFormatter`)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (structured `extra={"event": ...}` verified in `wishenka/bot/support.py` and `wishenka/bot/entry.py`)
- [x] Metrics are collected correctly (N/A — diagnostic context fields verified in `tests/test_wishenka_182_repro.py` and `tests/test_bot_support.py`)
- [x] Logging works in error scenarios (`entry_error`, `bot_support_unavailable`)
- [x] Large data structures are not logged
- [x] Privacy controls verified (`_private_bot_user` suppression of `wishenka.users` logs and `redact_capabilities` verified by `tests/test_wishenka_182_repro.py`)

## Notes

- Adding per-call `INFO` or `DEBUG` logs inside `WishlistStore.execute_read` or `ensure_private_bot_user` was evaluated and intentionally avoided: `execute_read` is a high-frequency transaction primitive matching `transaction()`, and logging user/chat IDs in `ensure_private_bot_user` would contradict the private-bot identifier suppression policy.
