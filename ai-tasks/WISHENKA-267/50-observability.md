# WISHENKA-267: Observability Implementation

## Logging Implementation

### Added Logs

A signed-in page still obtains the CSRF token with the existing
`GET /api/auth/csrf`. Publishing that string on `window.csrfToken` in
`prepareCsrf` (`wishenka/web/static/app.js`) is a browser assignment of a
value the page already fetched. It is not a new server event. This step
adds no log and does not log the token value. Product code was not edited.

The request is already logged, and those records stay as they are:

- `RequestLoggingMiddleware` in `wishenka/web/app.py` (logger `wishenka.web`)
  writes `HTTP request completed: %s %s status=%d duration=%.2fms` for
  `GET /api/auth/csrf`. Extras are `method`, `path`, `status_code`, and
  `duration_ms`. The path is the URL path only (`sanitize_log_path`). The
  response body, including `csrf_token`, stays out of the record. The same
  middleware writes `HTTP request started: GET` at DEBUG before the handler
  runs.
- `get_csrf` in `wishenka/web/routes/auth.py` (logger `wishenka.auth`) writes
  INFO `CSRF token issued for user %s` with event `csrf_token_issued` when a
  cookie session is issued a token. The only extra is `telegram_id`. The
  token string is not a field and is not in the message. A request that is
  not a cookie session stays the existing WARNING `CSRF token request
  rejected: cookie session required` (`csrf_cookie_missing`), also with
  `telegram_id` only.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none
- **WARNING**: none added. A CSRF request without a cookie session still
  uses the existing WARNING above.
- **NOTICE**: none
- **INFO**: none added. The completed-request line and `CSRF token issued`
  are the existing `GET /api/auth/csrf` logs. Neither record contains the
  token value.
- **DEBUG**: none added. Request start stays on `RequestLoggingMiddleware`.

### Log Structure

Log format used:

- Structured logs: yes, unchanged (`RequestLoggingMiddleware` extras on
  logger `wishenka.web`; issuance extras on `wishenka.auth`)
- Includes context: yes, unchanged (method, path, HTTP status, duration in
  milliseconds; on the issuance record, `telegram_id`). The token value
  stays out of both records.
- Log levels: `INFO`, `DEBUG`, and `WARNING` (existing). This step adds
  none.

## Metrics Implementation (if applicable)

This step adds none. `GET /api/auth/csrf` stays visible on the existing
request log named above.

### Performance Metrics

This step adds none. Request duration stays on `duration_ms` in
`RequestLoggingMiddleware`.

### Business Metrics

This step adds none. A cookie session that is issued a token stays the
existing INFO `CSRF token issued`.

### System Health Metrics

This step adds none.

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

No integration is added. Existing `GET /api/auth/csrf` logs are unchanged.

## Validation Results

Validation results:

- [x] Logs are correctly formatted — no new statement. Completed-request
  extras stay `method`, `path`, `status_code`, and `duration_ms`. The
  issuance record stays `event` and `telegram_id`.
- [x] Metrics are collected correctly — this step adds none
- [x] Logging works in error scenarios — a CSRF request without a cookie
  session still goes through `get_csrf`, which writes the existing WARNING
  `csrf_cookie_missing`. The middleware still writes the completed-request
  INFO line for that response.
- [x] Large data structures are not logged — the token value is not added
  to any record
- [x] Metrics are available for monitoring — this step adds none; the
  existing request extras are unchanged

No production code changed in this step, so the suite was not re-run.

## Notes

Assigning `window.csrfToken` (and clearing it after an `Invalid CSRF token`
response) happens in the browser. Neither assignment emits a server event.
An operator still sees the existing `GET /api/auth/csrf` request log, and
this step adds no log and does not log the token value.
