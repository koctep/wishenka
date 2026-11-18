# WISHENKA-89: Observability Implementation

## Logging Implementation

### Added Logs

No new runtime log statements were required for `WISHENKA-89` because the existing structured logging infrastructure (`wishenka/logging.py`, `wishenka/i18n/catalog.py`, and the SSR route loggers) already covers all in-scope SSR routes, error/refusal paths, and translation fallback paths without exposing PII or secret tokens:

- **EMERG**: None required (in-process localization formatting and template rendering have no system-level failure modes).
- **ALERT**: None required.
- **CRIT**: None required.
- **ERR**: None required (invalid inputs and missing entities are handled as `4xx` HTTP responses or localized validation notices).
- **WARNING**:
  - `wishenka/i18n/catalog.py` (`t()`): Logs `event="i18n_missing_translation_key"` with `i18n_key`, `locale`, and `fallback_locale` (`"en"` or `"key"`) whenever a catalog key is missing in the target locale or in both locales.
  - `wishenka/web/routes/sharing.py`: Logs `event="wishlist_shared_view_failed"` on public share lookup failure and `event="invite_join_failed"` on invalid/expired/deleted/archived invite join attempts (with `user_id` only, no tokens or PII).
  - `wishenka/web/routes/items_ui.py`: Logs validation/authorization warnings on item UI actions.
  - `wishenka/web/routes/receipts_ui.py`: Logs `event="receipt_inventory_busy"` and refusal events via `_log(logging.WARNING, ...)` with entity IDs only.
- **NOTICE**: None (Python `logging` uses standard levels; `INFO` / `WARNING` cover operational events).
- **INFO**:
  - `wishenka/web/routes/sharing.py`: Logs `wishlist_shared_view`, `invite_joined`, and sharing/member management actions with `wishlist_id`, `role`, and `is_collaborative` (no tokens or PII).
  - `wishenka/web/routes/items_ui.py`: Logs item UI views (including `duration_ms`) and mutations.
  - `wishenka/web/routes/receipts_ui.py`: Logs `ui_receipt_form_opened` and `receipt_recorded_http` with entity IDs.
- **DEBUG**:
  - `wishenka/users/store.py`, `wishenka/bot/i18n.py`, `wishenka/notices/reminders.py`: Existing `locale_auto_resolved`, `locale_explicit_updated`, `bot_commands_locale_synced`, and `notice_locale_resolved` events remain active for upstream locale lifecycle diagnostics.

### Log Structure

Log format used:
- Structured logs: **Yes** (`wishenka/logging.py` `JsonFormatter` serializes `timestamp`, `level`, `logger`, `message`, optional `exception`, and `extra` fields as JSON lines when `json_logs=True`).
- Includes context: **Yes** (`event`, `i18n_key`, `locale`, `fallback_locale`, `wishlist_id`, `user_id`, `duration_ms` — no PII, usernames, or invite/public tokens).
- Log levels: `WARNING`, `INFO`, `DEBUG` (mapped to syslog-compatible levels).

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:
- **Response time**: `duration_ms` logged on wishlist SSR view in `wishenka/web/routes/items_ui.py` (no new Prometheus metrics introduced).
- **Throughput**: N/A (not applicable for static template/catalog localization).
- **Error rate**: Tracked via structured `WARNING` events (`i18n_missing_translation_key`, `wishlist_shared_view_failed`, `invite_join_failed`, receipt refusals).

### Business Metrics

Business metrics:
- N/A — `WISHENKA-89` localizes existing SSR views and routes without adding new business workflows.

### System Health Metrics

System health metrics:
- **Resource usage**: N/A (`format_date` in `wishenka/i18n/formatters.py` is pure, stateless, and free of OS `locale.setlocale` calls).
- **Component status**: N/A.

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (N/A for this task)
- [ ] Grafana dashboards (N/A for this task)
- [ ] Alerting rules (existing log-based alerts on `i18n_missing_translation_key` remain applicable)
- [x] Log aggregation (`JsonFormatter` in `wishenka/logging.py` outputs JSON lines to `stdout`)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (`JsonFormatter` in `wishenka/logging.py`; verified `i18n_missing_translation_key` structured `extra` fields in `tests/test_i18n_unit.py`)
- [x] Metrics are collected correctly (N/A — no new metrics added)
- [x] Logging works in error scenarios (`tests/test_i18n_unit.py` verifies `i18n_missing_translation_key` fallback warnings via `caplog`, and no PII leakage in locale/profile logs)
- [x] Large data structures are not logged (only scalar IDs, `i18n_key`, `locale`, `event`, and `duration_ms` are logged; no full DTOs, templates, or tokens)
- [x] Metrics are available for monitoring (N/A)

## Notes

- `wishenka/i18n/dependencies.py` (`get_request_locale`) is reused unchanged per `20-architecture.md`. Unauthenticated requests on `/share/{public_token}` and `/invite/{invite_token}` naturally fall back to `?lang=` / `Accept-Language` / `"en"` without emitting warning noise.
- `wishenka/i18n/formatters.py` (`format_date`) uses a static `_EN_MONTHS` tuple and deterministic `DD.MM.YYYY` / `MMM D, YYYY` formatting, avoiding process-global `locale.setlocale` state.
- `wishenka/web/routes/reservations_ui.py` exposes read-only SSR views (`GET /web/reservations`, `/web/reservations/card`, `/web/reservations/list`) with no new error/mutating paths requiring additional logging.
