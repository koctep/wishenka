# WISHENKA-30: Observability Implementation

## Logging Implementation

### Added Logs

The Telegram bot polling process uses the existing `LOG_LEVEL` and `LOG_JSON` configuration
(`wishenka.logging.configure_logging`). Structured operational events added in
`wishenka/bot/support.py` on logger `wishenka.bot.support`:

| Level | Event | Extra Fields | Location | Meaning |
| --- | --- | --- | --- | --- |
| **INFO** | `bot_support_prompted` | `event` | `support.py:support_command`, `support_open_callback` | Interactive support input session opened via `/support` or `support:open`. |
| **INFO** | `bot_support_cancelled` | `event` | `support.py:support_cancel_callback`, `cancel_command` | Active support session cancelled by the user via `support:cancel` or `/cancel`. |
| **INFO** | `bot_support_rejected` | `event`, `reason` | `support.py:_submit_support_message`, `non_text_message` | Support input rejected (`reason`: `empty`, `too_long`, `non_text`, or `rate_limited`). |
| **INFO** | `bot_support_submitted` | `event`, `outcome` | `support.py:_submit_support_message` | Support ticket delivered to at least one destination (`outcome`: `delivered` or `partial`). |
| **WARNING** | `bot_support_unavailable` | `event`, `reason` | `support.py:_submit_support_message` | Support destination unconfigured (`reason`: `unconfigured`) or a subset of configured destinations failed (`reason`: `partial_send_failed`). |
| **ERROR** | `bot_support_unavailable` | `event`, `reason` | `support.py:_submit_support_message` | Delivery to all configured support destinations failed (`reason`: `send_failed`). |

Existing bot error boundaries that also cover the support flow:

- **ERROR**: `wishenka/bot/entry.py:entry_error` on logger `wishenka.bot.entry` emits
  `bot_start_failed` with the exception class name (`type(_event.exception).__name__`) when an
  unhandled exception escapes any mounted sub-router (`support`, `birthdays`, or `capture`),
  preventing aiogram from logging raw exception messages or tracebacks.
- **ERROR**: `wishenka/bot/__main__.py:cleanup_loop` on logger `wishenka.bot.cleanup` emits
  `bot_draft_cleanup_failed` without exception text when periodic cleanup of expired
  `bot_drafts`, `birthday_input`, `support_input`, and aged `support_tickets` rows fails.
- **EMERG / ALERT / CRIT / NOTICE / DEBUG**: None added.

Operations intentionally not logged:

- Viewing `/help` or pressing `How it works` (`entry:help`).
- Implicitly clearing a pending `support_input` row when the user switches to `/start`, `/help`,
  `/birthdays`, or `/reservation_confirmations` (`clear_support_session`), or when an expired
  `support_input` row is lazily deleted on the next message.
- Routine hourly deletions of expired `support_input` and aged `support_tickets` rows in
  `cleanup_drafts`.

### Log Structure

- **Structured logs**: Yes (`extra={"event": ...}` with bounded `reason` or `outcome` strings).
- **Includes context**: Bounded operational status only (`reason` in `{"empty", "too_long",
  "non_text", "rate_limited", "unconfigured", "partial_send_failed", "send_failed"}`, `outcome` in
  `{"delivered", "partial"}`).
- **Log levels**: `INFO`, `WARNING`, `ERROR`.
- **Formatter behavior**: When `WISHENKA_LOG_JSON=true`, `JsonFormatter` serializes `timestamp`,
  `level`, `logger`, `message`, and the `extra` dictionary (under Python 3.12+, `extra` also
  includes `taskName` from `asyncio`). When `WISHENKA_LOG_JSON=false`, the default stream formatter
  outputs `%(asctime)s [%(levelname)s] %(name)s: %(message)s` (fixed message strings without the
  `extra` keys).
- **Privacy and surprise protection**: Support log records never include support message text, URLs,
  capability tokens (`p_*`, `i_*`, `/share/*`, `/invite/*`), ticket references (`SUP-...`),
  internal user IDs, Telegram user or chat IDs, usernames, display names, wishlist titles,
  reservation or receipt details, or exception messages. User upserts in `principal()`, `/start`,
  and `/help` wrap `UserStore.upsert_user` with the `_private_bot_user` `ContextVar` filter on
  `wishenka.users` so PII-bearing `user_created` / `user_updated` logs are suppressed during
  private bot interactions.

## Metrics Implementation

The repository has no in-process metrics collector or Prometheus exporter for the bot process.
Operational indicators are derived from structured JSON log events in an external log collector:

### Performance Metrics

- **Response time**: Not measured for support operations (no latency timer was added to
  `wishenka.bot.support`).
- **Throughput**: Derivable from the rate of `bot_support_prompted` and `bot_support_submitted`
  events on `wishenka.bot.support`.
- **Error rate**: Derivable from `bot_support_unavailable` (`reason="send_failed"` at `ERROR`,
  `reason="partial_send_failed"` and `reason="unconfigured"` at `WARNING`) and `bot_start_failed`
  on `wishenka.bot.entry`.

### Business Metrics

- **Support funnel (`bot_support_prompted` vs `bot_support_submitted` / `bot_support_cancelled`)**:
  Measures how often opened support sessions result in delivered tickets versus user cancellations
  (inline `/support <text>` submissions emit `bot_support_submitted` without
  `bot_support_prompted`).
- **Validation and flood rejections (`bot_support_rejected` by `reason`)**: Tracks user input
  friction (`empty`, `too_long`, `non_text`) and per-user rate-limit enforcement (`rate_limited`).

### System Health Metrics

- **Resource usage**: Not collected in-process; delegated to host or container runtime monitoring.
- **Component status**: Support channel configuration and Telegram destination reachability are
  reflected by `bot_support_unavailable` (`unconfigured`, `partial_send_failed`, `send_failed`);
  SQLite cleanup loop health is reflected by `bot_draft_cleanup_failed`.

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics (not configured in repository)
- [ ] Grafana dashboards (not configured in repository)
- [ ] Alerting rules (not configured in repository)
- [x] Log aggregation compatible via structured JSON output (`JsonFormatter` when
  `WISHENKA_LOG_JSON=true`)

## Validation Results

Validation results:

- [x] Logs are correctly formatted (`test_support_observability_events_json_format_and_error_redaction`
  validates every `wishenka.bot.support` event through `JsonFormatter`)
- [x] Metrics/event indicators are emitted with bounded `reason` and `outcome` values across
  prompt, cancel, validation rejection, rate limit, partial delivery, full delivery, unconfigured
  destination, and send failure scenarios
- [x] Logging works in error scenarios without leaking sensitive exception details
  (`test_unconfigured_or_failing_destination_reports_honestly_without_false_confirmation` and
  `test_support_observability_events_json_format_and_error_redaction` assert `caplog` error records
  and verify exception strings are omitted)
- [x] Large data structures, message bodies, capability tokens, wish titles, surprise data, and user
  identifiers are not logged (`test_privacy_surprise_protection_and_capability_redaction`)
- [ ] External monitoring dashboards/exporters (not applicable; no metrics backend in project)

Executed verification commands:

- `.venv/bin/pytest tests/test_bot_support_repro.py tests/test_bot_support.py` — `13 passed in 2.08s`
- `make analyze` — Ruff linter, Ruff format check, and Mypy (`172 source files`) passed with 0 issues.

## Notes

- When `WISHENKA_LOG_JSON=false`, the default plain-text formatter prints only the static message
  string (for example, `Support message rejected` or `Support ticket submitted`) without rendering
  the `extra` dictionary (`event`, `reason`, `outcome`). Deployments that aggregate or alert on
  event reasons should enable `WISHENKA_LOG_JSON=true`.
- External Telegram infrastructure and reverse proxies must independently protect their own access
  logs and bot token configurations.
