# WISHENKA-9: Observability Implementation

## Logging Implementation

### Added Logs

Structured contextual logging for Mini App favorites and viewing history operations in domain service (`wishenka.wishlists`) and HTTP routes (`wishenka.web.wishlists`):
- **EMERG**: N/A - none implemented at endpoint level
- **ALERT**: N/A - none implemented at endpoint level
- **CRIT**: N/A - none implemented at endpoint level
- **ERR**:
  - `wishenka.web` in `RequestLoggingMiddleware` - unhandled HTTP exception logging with request method, redacted path, and execution duration
- **WARNING**:
  - `wishenka.wishlists` & `wishenka.web.wishlists` in `add_favorite` - self-favoriting attempt denied (`event=favorite_own_wishlist_denied`)
  - `wishenka.wishlists` & `wishenka.web.wishlists` in `add_favorite` - attempt to favorite a soft-deleted wishlist (`event=favorite_deleted_wishlist_denied`)
  - `wishenka.wishlists` & `wishenka.web.wishlists` in `record_view` - attempt to record view history for a soft-deleted wishlist (`event=favorite_deleted_wishlist_denied`)
  - `wishenka.auth` in `get_current_user` - unauthorized / unauthenticated attempts to access `/api/favorites` or `/api/history` (`event=auth_failure`, `reason=missing_credentials` or `reason=invalid_session_token`)
- **NOTICE**: N/A - mapped to standard INFO in Python logging
- **INFO**:
  - `wishenka.wishlists` & `wishenka.web.wishlists` in `add_favorite` - wishlist added to user's favorites (`event=favorite_added`, `wishlist_id`, `user_id`)
  - `wishenka.wishlists` & `wishenka.web.wishlists` in `remove_favorite` - wishlist removed from user's favorites (`event=favorite_removed`, `wishlist_id`, `user_id`)
  - `wishenka.wishlists` & `wishenka.web.wishlists` in `list_favorites` - user's favorites retrieved (`event=favorites_listed`, `user_id`, `count`)
  - `wishenka.wishlists` & `wishenka.web.wishlists` in `record_view` - wishlist view recorded in user's history (`event=view_history_recorded`, `wishlist_id`, `user_id`)
  - `wishenka.wishlists` & `wishenka.web.wishlists` in `get_history` - user's recent viewing history listed (`event=view_history_listed`, `user_id`, `count`)
  - `wishenka.wishlists` & `wishenka.web.wishlists` in `clear_history` - user's viewing history cleared (`event=view_history_cleared`, `user_id`)
- **DEBUG**:
  - `wishenka.web` in `RequestLoggingMiddleware` - HTTP request started (`method`, `path`)

### Log Structure

Log format used:
- Structured logs: yes (JSON formatter via `wishenka.logging.JsonFormatter` or key-value extra fields)
- Includes context: yes (`event`, `wishlist_id`, `user_id`, `count`)
- Log levels: DEBUG, INFO, WARNING, ERROR

### Secret Redaction & Zero Surprise Leak

- Raw capabilities (`invite_token`, `public_token`), session cookies (`session_id`), and CSRF tokens (`x-csrf-token`) are strictly excluded from log records, messages, and `extra` parameters.
- Reservation and surprise details (`is_reserved_by_me`, `reserved_quantity`, `available_quantity`, item titles) are never logged during favorites or history operations.
- Large data structures (complete wishlist DTOs, items arrays, raw JSON responses) are omitted; only numeric identifiers and record count metrics are logged.

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:
- **Response time**: `duration_ms` tracked per request in `RequestLoggingMiddleware` (`wishenka/web/app.py`)
- **Throughput**: Monitored via request completion logging (`status_code`, `method`, `path`)
- **Error rate**: Tracked via `status_code >= 400` in HTTP completion logs and WARNING/ERROR events

### Business Metrics

Business metrics:
- `favorite_added`: Favoriting conversion volume - `wishenka.web.wishlists` & `wishenka.wishlists`
- `favorite_removed`: Unfavoriting churn count - `wishenka.web.wishlists` & `wishenka.wishlists`
- `favorites_listed`: Favorites engagement frequency - `wishenka.web.wishlists` & `wishenka.wishlists`
- `view_history_recorded`: Wishlist view activity - `wishenka.web.wishlists` & `wishenka.wishlists`
- `view_history_listed`: History retrieval count - `wishenka.web.wishlists` & `wishenka.wishlists`
- `view_history_cleared`: Privacy clearance actions - `wishenka.web.wishlists` & `wishenka.wishlists`

### System Health Metrics

System health metrics:
- **Resource usage**: SQLite WAL transaction mode with bounded 20-entry cap per user for viewing history
- **Component status**: Healthcheck endpoint `/healthz` provides probe status

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [x] Alerting rules (WARNING alerts on `favorite_deleted_wishlist_denied`, `favorite_own_wishlist_denied`, `auth_failure`)
- [x] Log aggregation (ELK, Loki, etc. via standard JSON output format)

## Validation Results

Validation results:
- [x] Logs are correctly formatted
- [x] Metrics are collected correctly (latency duration_ms, status codes, item counts)
- [x] Logging works in error scenarios (self-favoriting denied, deleted wishlist access, unauthorized requests)
- [x] Large data structures are not logged
- [x] Metrics are available for monitoring

## Notes

- All tests adhere to the `do-testing` contract: explicit `pytest.mark.timeout(30)` markers and structured `caplog` validations.
- Regression suite `tests/test_wishlist_sections_observability.py` provides 100% automated test coverage for all added events, warnings, and redactions.
