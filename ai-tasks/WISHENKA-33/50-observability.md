# WISHENKA-33: Observability Implementation

## Logging Implementation

### Added Logs

Structured logging for the bilingual (`RU`/`EN`) localization lifecycle uses `wishenka/logging.py` (`JsonFormatter` when `json_logs=True`, plain structured formatter otherwise) without PII (`first_name`, `last_name`, `username`, `display_name`) or secrets (`initData`, bot tokens, session/CSRF tokens):

- **EMERG**: None — localization failures degrade safely to `"en"` fallback and do not halt the process.
- **ALERT**: None — no immediate human intervention required for locale resolution or best-effort bot command sync.
- **CRIT**: None — non-fatal subsystem; DB schema migration runs at startup under Alembic.
- **ERR**: None — invalid user input is rejected with HTTP `422` (`WARNING`), and best-effort Telegram `setMyCommands` errors are logged at `WARNING` without failing the request.
- **WARNING**:
  - `wishenka/web/routes/profile.py` (`wishenka.web.profile`) — `locale_invalid_request`: emitted when `PATCH /api/profile/locale` receives an unsupported or malformed locale payload (`extra`: `event`, `user_id`, `status_code`).
  - `wishenka/bot/i18n.py` and `wishenka/web/routes/profile.py` (`wishenka.bot.i18n`) — `bot_commands_locale_sync_failed`: emitted when timeout-bounded per-chat `setMyCommands` fails or times out (`extra`: `event`, `user_id`, `target_locale`, `error_type`).
  - `wishenka/i18n/catalog.py` (`wishenka.i18n`) — `i18n_missing_translation_key`: emitted when a translation key is absent in the target locale or catalog (`extra`: `event`, `i18n_key`, `locale`, `fallback_locale`).
- **NOTICE**: Mapped to `INFO` in Python `logging` (see `INFO` below).
- **INFO**:
  - `wishenka/users/store.py` (`wishenka.users`) — `locale_explicit_updated`: emitted when `UserStore.set_locale()` persists an explicit `RU`/`EN` choice (`extra`: `event`, `user_id`, `previous_locale`, `new_locale`, `previous_source`, `locale_source`).
- **DEBUG**:
  - `wishenka/users/store.py` (`wishenka.users`) — `locale_auto_resolved`: emitted on `UserStore.upsert_user()` / `upsert_from_bot()` (`extra`: `event`, `channel`, `resolved_locale`, `locale_source`, `changed`, `fallback_used`). Note: `_PrivateUserLogFilter` in `wishenka/bot/i18n.py` suppresses `wishenka.users` records during private bot interactions to prevent identifier leakage.
  - `wishenka/bot/i18n.py` (`wishenka.bot.i18n`) — `bot_commands_locale_synced`: emitted when per-chat `setMyCommands` succeeds (`extra`: `event`, `user_id`, `target_locale`).
  - `wishenka/notices/store.py` (`wishenka.notices.store`) — `notice_locale_resolved`: emitted when `NoticeStore` resolves recipient locale for gift notices (`extra`: `event`, `channel`, `locale`, `fallback_used`).
  - `wishenka/notices/reminders.py` (`wishenka.notices.reminders`) — `notice_locale_resolved`: emitted when `_normalize_row_locale()` resolves recipient locale for occasion/event reminders (`extra`: `event`, `channel`, `locale`, `fallback_used`).

### Log Structure

Log format used:
- Structured logs: yes (`wishenka.logging.JsonFormatter` outputs JSON lines with `timestamp`, `level`, `logger`, `message`, and `extra` dictionary; `extra` keys avoid reserved `LogRecord` attributes).
- Includes context: yes (`event`, `channel`, `user_id`, `locale`/`resolved_locale`/`target_locale`, `locale_source`, `fallback_used`, `error_type`, `status_code`).
- Log levels: `WARNING`, `INFO`, `DEBUG` (mapped to Python `logging` levels; `NOTICE` is represented by `INFO`).

## Metrics Implementation (if applicable)

Not applicable: the repository does not include a Prometheus/OpenTelemetry metrics exporter (`wishenka` uses structured JSON logging via `wishenka/logging.py` for production observability).

### Performance Metrics

- **Response time**: N/A (per-chat `setMyCommands` is offloaded to FastAPI `BackgroundTasks` and bounded by `asyncio.wait_for(..., timeout=2.0)`).
- **Throughput**: N/A
- **Error rate**: Tracked via structured `WARNING` events (`locale_invalid_request`, `bot_commands_locale_sync_failed`, `i18n_missing_translation_key`).

### Business Metrics

- Tracked via structured `INFO` / `DEBUG` log events (`locale_explicit_updated`, `locale_auto_resolved`, `notice_locale_resolved`).

### System Health Metrics

- **Resource usage**: N/A (handled at container/runtime level).
- **Component status**: N/A (SQLite schema health checked at startup via Alembic `upgrade_to_head_sync`).

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (not applicable — no metrics endpoint in repository)
- [ ] Grafana dashboards (not applicable)
- [ ] Alerting rules (log-based alerts can match `event="bot_commands_locale_sync_failed"` or `event="i18n_missing_translation_key"`)
- [x] Log aggregation (ELK, Loki, etc.) — structured JSON lines emitted via `wishenka.logging.JsonFormatter` to `stdout`.

## Validation Results

Validation results:
- [x] Logs are correctly formatted — verified `JsonFormatter().format(...)` produces valid JSON with expected `extra` fields in `tests/test_i18n_unit.py`.
- [ ] Metrics are collected correctly (not applicable — no metrics library in project)
- [x] Logging works in error scenarios — verified `locale_invalid_request` (`422`), `bot_commands_locale_sync_failed` (`RuntimeError`), `i18n_missing_translation_key`, and `notice_locale_resolved` (`fallback_used=True`) in `tests/test_i18n_unit.py`.
- [x] Large data structures are not logged — verified only scalar identifiers/enum values are logged and PII (`first_name`, `last_name`, `username`) is absent from `caplog.text`.
- [ ] Metrics are available for monitoring (not applicable)
- [x] Full quality gate passed after final edits: `make analyze` (Ruff lint/format + Mypy strict on 188 files) and `make test` (`1070 passed`).

## Notes

- Added `bot_commands_locale_synced` (`DEBUG` in `wishenka/bot/i18n.py`) and `test_i18n_observability_structured_logs_and_no_pii` in `tests/test_i18n_unit.py` during Step 6 to cover both success and failure paths of `sync_user_bot_commands`, `UserStore` auto/explicit locale events, and `reminders` locale resolution.
