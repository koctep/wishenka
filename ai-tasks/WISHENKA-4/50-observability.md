# WISHENKA-4: Observability Implementation

## Logging Implementation

### Added Logs

- **EMERG**: N/A for authentication subsystem.
- **ALERT**: N/A for authentication subsystem.
- **CRIT**: N/A for authentication subsystem.
- **ERR**: N/A (standard authentication failures are client-side validation errors logged as WARNING).
- **WARNING**:
  - `wishenka/auth/init_data.py:validate_telegram_init_data` — Authentication signature verification failure (`event: auth_failure`, `reason: invalid_signature`).
  - `wishenka/auth/init_data.py:validate_telegram_init_data` — Expired or future `auth_date` timestamp (`event: auth_failure`, `reason: expired_init_data`, `auth_date`, `age_seconds`).
  - `wishenka/auth/init_data.py:validate_telegram_init_data` — Malformed query string or missing/invalid fields (`event: auth_failure`, `reason: malformed_init_data`).
  - `wishenka/auth/dependencies.py:get_optional_current_user` — Session token verification failure (`event: auth_failure`, `reason: invalid_session_token`, `auth_method`, `error_type`).
  - `wishenka/auth/dependencies.py:get_current_user` — Unauthenticated access attempt to protected endpoint (`event: auth_failure`, `reason: missing_credentials`).
- **NOTICE**: N/A.
- **INFO**:
  - `wishenka/web/routes/auth.py:auth_telegram` — Successful authentication via Telegram WebApp initData (`event: auth_success`, `telegram_id`, `username`).
  - `wishenka/web/routes/auth.py:logout` — Caller session logout / cookie invalidation (`event: logout`, `telegram_id`, `username`).
- **DEBUG**:
  - `wishenka/auth/init_data.py:validate_telegram_init_data` — initData successfully validated (`event: init_data_validated`, `telegram_id`, `username`).
  - `wishenka/auth/dependencies.py:get_optional_current_user` — Resolved session user identity (`event: auth_session_resolved`, `telegram_id`, `username`, `auth_method`).

### Log Structure

Log format used:
- Structured logs: Yes (formatted via `JsonFormatter` in JSON production mode or formatted console output).
- Includes context: Yes (timestamp, level, logger `wishenka.auth`, event classification `event`, `telegram_id`, `username`, failure reasons). Sensitive tokens, raw bot credentials, and HMAC keys are strictly excluded from log records.
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL.

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:
- **Response time**: Measured per-request in `RequestLoggingMiddleware` as `duration_ms` on `/api/auth/telegram`, `/api/auth/logout`, and `/api/auth/me`.
- **Throughput**: Tracked via HTTP access logs on `/api/auth/*`.
- **Error rate**: Tracked via HTTP 401 Unauthorized responses and WARNING log records on `wishenka.auth`.

### Business Metrics

Business metrics:
- **Successful Logins**: Tracked by counting INFO log records with `event="auth_success"` and distinct `telegram_id` fields.
- **Failed Authentication Attempts**: Tracked by counting WARNING log records with `event="auth_failure"` grouped by `reason` (`invalid_signature`, `expired_init_data`, `malformed_init_data`, `invalid_session_token`).
- **User Logouts**: Tracked by counting INFO log records with `event="logout"`.

### System Health Metrics

System health metrics:
- **Resource usage**: Standard container CPU and memory metrics.
- **Component status**: Healthy runtime via `/healthz`.

## Monitoring Integration

Integration with monitoring systems:
- [x] Docker stdout/stderr structured stream ready for log collectors (Vector, Fluentbit, Loki, ELK)
- [x] JSON log serialization supported via `Settings.log_json` (`WISHENKA_LOG_JSON=true`)
- [x] Structured `extra` fields automatically preserved in JSON payloads
- [ ] Prometheus metrics (deferred to future telemetry epic)
- [ ] Grafana dashboards (deferred to future telemetry epic)
- [ ] Security alert rules for brute-force/signature tampering spikes (to be configured in SIEM / alertmanager)

## Validation Results

Validation results:
- [x] Logs are correctly formatted
- [x] Metrics / events are collected correctly with structured `extra` dicts
- [x] Logging works in error scenarios (invalid signature, expired initData, malformed query, invalid session token)
- [x] Large data structures and sensitive secrets (bot token, raw HMAC keys, tokens) are not logged
- [x] Verified by automated tests in `tests/test_auth.py` (`test_auth_logging_success`, `test_auth_logging_invalid_signature_warning`, `test_auth_logging_logout`, `test_auth_logging_expired_warning`, `test_auth_logging_malformed_warning`, `test_auth_logging_invalid_session_token_warning`)
- [x] Full quality gate verified: `make check` passed (18 tests passing, 0 linter errors, 0 type issues)

## Notes

- All auth loggers share the dedicated hierarchy `wishenka.auth`.
- Privacy & security: raw initData strings and HMAC tokens are never dumped to log lines to prevent credential leakage.
