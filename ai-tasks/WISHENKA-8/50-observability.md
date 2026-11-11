# WISHENKA-8: Observability Implementation

## Logging Implementation

### Added Logs

Structured contextual logging for Mini App wishlist management, collaboration, and security:
- **EMERG**: N/A - none implemented at endpoint level
- **ALERT**: N/A - none implemented at endpoint level
- **CRIT**: N/A - none implemented at endpoint level
- **ERR**:
  - `wishenka.web` in `RequestLoggingMiddleware` - unhandled HTTP exception logging with request method, redacted path, and execution duration
- **WARNING**:
  - `wishenka.web.security` in `BrowserSecurityMiddleware` - origin header mismatches (`event=origin_mismatch`, `event=csrf_origin_mismatch`)
  - `wishenka.web.security` in `BrowserSecurityMiddleware` - invalid CSRF token attempts on browser mutations (`event=csrf_token_invalid`)
  - `wishenka.auth` in `/api/auth/csrf` - unauthenticated or non-cookie CSRF token requests (`event=csrf_cookie_missing`)
  - `wishenka.web.wishlists` in `require_member` - unauthorized access attempts to non-member wishlists or manager operations (`event=wishlist_access_denied`)
  - `wishenka.web.wishlists` in `update_wishlist`, `change_status`, `reset_share`, `set_role`, `delete_member`, `reset_invite` - blocked mutations on archived wishlists (`event=wishlist_archived_mutation_blocked`)
  - `wishenka.web.wishlists` in `change_status` - invalid status transition attempts (`event=wishlist_state_transition_invalid`)
  - `wishenka.web.wishlists` in `reset_share` - failure to generate unique public token after retries (`event=share_token_generation_failed`)
  - `wishenka.web.wishlists` in `public_wishlist` - non-existent or deleted public wishlist lookup (`event=public_wishlist_not_found`)
  - `wishenka.web.wishlists` in `set_role` - unauthorized role change attempts by non-owners or on owner (`event=role_change_denied`, `event=member_not_found`)
  - `wishenka.web.wishlists` in `delete_member` - invalid member removal attempts (`event=member_removal_denied`)
  - `wishenka.web.wishlists` in `find_invitation` - malformed, expired, or non-existent invite token lookups (`event=invitation_token_malformed`, `event=invitation_token_invalid_or_expired`)
  - `wishenka.web.wishlists` in `accept_invite` - failed invite acceptance (`event=invitation_join_failed`)
  - `wishenka.web.wishlists` in `execute` - permission denial or storage rejection (`event=permission_denied`)
- **NOTICE**: N/A - mapped to standard INFO in Python logging
- **INFO**:
  - `wishenka.web.miniapp` in `miniapp` - Mini App shell requested (`event=miniapp_shell_requested`)
  - `wishenka.auth` in `/api/auth/csrf` - CSRF token successfully issued for verified session (`event=csrf_token_issued`)
  - `wishenka.web.wishlists` in `create_wishlist` - wishlist created (`event=wishlist_created`)
  - `wishenka.web.wishlists` in `update_wishlist` - wishlist details updated (`event=wishlist_updated`)
  - `wishenka.web.wishlists` in `change_status` - wishlist archived or restored (`event=wishlist_status_changed`)
  - `wishenka.web.wishlists` in `reset_share` - public share token regenerated (`event=wishlist_share_token_reset`)
  - `wishenka.web.wishlists` in `public_wishlist` - public wishlist viewed (`event=public_wishlist_viewed`)
  - `wishenka.web.wishlists` in `set_role` - member role changed (`event=member_role_updated`)
  - `wishenka.web.wishlists` in `delete_member` - member removed (`event=member_removed`)
  - `wishenka.web.wishlists` in `reset_invite` - invitation token reset (`event=invite_token_reset`)
  - `wishenka.web.wishlists` in `preview_invite` - invitation preview accessed (`event=invitation_previewed`)
  - `wishenka.web.wishlists` in `accept_invite` - member joined or already joined (`event=invitation_accepted`, `event=invitation_already_member`)
  - `wishenka.web.wishlists` in `execute` - successful transactional wishlist mutation (`event=wishlist_mutation_committed`)
  - `wishenka.web` in `RequestLoggingMiddleware` - HTTP request completion with latency and status code (`method`, `path`, `status_code`, `duration_ms`)
- **DEBUG**:
  - `wishenka.web` in `RequestLoggingMiddleware` - HTTP request started (`method`, `path`)

### Log Structure

Log format used:
- Structured logs: yes (JSON formatter via `wishenka.logging.JsonFormatter` or key-value extra fields)
- Includes context: yes (`event`, `wishlist_id`, `user_id`, `actor_id`, `target_user_id`, `operation`, `status`)
- Log levels: DEBUG, INFO, WARNING, ERROR

### Secret Redaction & Zero Surprise Leak

- Raw capabilities (`invite_token`, `public_token`, `x-invite-token`), session cookies (`session_id`), and CSRF tokens (`x-csrf-token`) are strictly excluded from log records, messages, and `extra` parameters.
- `ShareTokenAccessFilter` strips public sharing tokens from Uvicorn access log lines (`/api/public/wishlists/{token}`).
- Reservation and surprise data are excluded from public and non-admin logging.
- Large data structures (full items list, binary contents, DOM fragments) are omitted; only identifiers and operational state keys are recorded.

## Metrics Implementation (if applicable)

### Performance Metrics

Added performance metrics:
- **Response time**: `duration_ms` tracked per request in `RequestLoggingMiddleware` (`wishenka/web/app.py`)
- **Throughput**: Monitored via request completion logging (`status_code`, `method`, `path`)
- **Error rate**: Tracked via `status_code >= 400` in HTTP completion logs and WARNING/ERROR events

### Business Metrics

Business metrics:
- `wishlist_created`: Wishlist creation volume - `wishenka.web.wishlists`
- `wishlist_status_changed`: Archive / restore transition counts - `wishenka.web.wishlists`
- `invitation_accepted`: Collaborative conversion count - `wishenka.web.wishlists`
- `public_wishlist_viewed`: Viral sharing viewership - `wishenka.web.wishlists`
- `share_token_reset` / `invite_token_reset`: Token rotation activity - `wishenka.web.wishlists`

### System Health Metrics

System health metrics:
- **Resource usage**: Managed by SQLite WAL journal mode and connection timeout handling
- **Component status**: Healthcheck endpoint `/healthz` provides probe status

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [x] Alerting rules (WARNING alerts on `csrf_token_invalid`, `origin_mismatch`, `wishlist_access_denied`)
- [x] Log aggregation (ELK, Loki, etc. via standard JSON output format)

## Validation Results

Validation results:
- [x] Logs are correctly formatted
- [x] Metrics are collected correctly (latency duration_ms, status codes)
- [x] Logging works in error scenarios (access violations, CSRF failures, expired tokens, archived list blocks)
- [x] Large data structures are not logged
- [x] Metrics are available for monitoring

## Notes

- All tests adhere to the `do-testing` contract: explicit `pytest.mark.timeout(30)` markers and structured `caplog` validations.
- Regression suite `tests/test_wishlist_management_observability.py` covers full observability coverage across Mini App, Wishlist endpoints, and Security middleware.
