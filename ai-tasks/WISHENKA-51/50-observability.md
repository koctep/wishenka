# WISHENKA-51: Observability Implementation

## Logging Implementation

### Added Logs

Structured logs have been implemented for all sharing, invite, and member operations:
- **INFO**: `wishenka.web.sharing` - `wishlist_shared_view`: public share page accessed.
- **INFO**: `wishenka.web.sharing` - `invite_preview_accessed`: previewing collaborator invite.
- **INFO**: `wishenka.web.sharing` - `invite_joined`: user accepted invitation and joined wishlist.
- **INFO**: `wishenka.web.sharing` - `member_removed`: owner removed collaborator from wishlist.
- **INFO**: `wishenka.web.sharing` - `invite_regenerated`: owner regenerated invitation token.
- **INFO**: `wishenka.web` - `RequestLoggingMiddleware`: request timing, method, sanitized path,
  and status code.
- **WARNING**: `wishenka.web.sharing` - `wishlist_shared_view_failed`: not found / deleted access.
- **WARNING**: `wishenka.web.sharing` - `invite_join_failed`: invalid or expired token join attempt.

### Log Structure

Log format used:
- Structured logs: Yes (`extra={...}`)
- Includes context: Yes (`wishlist_id`, `user_id`, `role`, `status`, `is_recipient`,
  `is_collaborative`, `removed_user_id`, `removed_by`)
- Log levels: INFO, WARNING, DEBUG
- Zero token leakage: capability tokens (`public_token`, `invite_token`) are strictly excluded
  from log messages, event arguments, and error payloads.
- Access log filtering: `ShareTokenAccessFilter` automatically redacts `/share/{token}`,
  `/invite/{token}`, and `/invite/{token}/join` routes in Uvicorn access records.

### Event Schema Reference

- `wishlist_shared_view`:
  - Logger: `wishenka.web.sharing`
  - Attributes: `wishlist_id`, `is_recipient`, `is_collaborative`
  - Redaction: Public capability token is omitted
- `invite_preview_accessed`:
  - Logger: `wishenka.web.sharing`
  - Attributes: `wishlist_id`, `status` ("valid", "expired", "not_found")
  - Redaction: Invite capability token is omitted
- `invite_joined`:
  - Logger: `wishenka.web.sharing`
  - Attributes: `wishlist_id`, `user_id`, `role`
  - Redaction: Token and auth session secrets omitted
- `member_removed`:
  - Logger: `wishenka.web.sharing`
  - Attributes: `wishlist_id`, `removed_user_id`, `removed_by`
  - Redaction: Collaborator IDs preserved, secrets omitted
- `invite_regenerated`:
  - Logger: `wishenka.web.sharing`
  - Attributes: `wishlist_id`, `user_id`
  - Redaction: Both old and new invite capability tokens omitted

## Metrics Implementation

### Performance Metrics

- **HTTP Request Duration**: Tracked per endpoint in `RequestLoggingMiddleware` via `duration_ms`
  in `wishenka.web` logs.
- **HTMX Route Latency**: Sub-millisecond to low millisecond database and rendering overhead
  tracked via structured middleware fields (`method`, `path`, `status_code`, `duration_ms`).

### Business Metrics

- **Share Views**: Aggregable from count of `wishlist_shared_view` logs grouped by `wishlist_id`.
- **Invite Conversion Rate**: Ratio of `invite_joined` events to `invite_preview_accessed`
  events with status `valid`.
- **Invite Churn / Revocation**: Count of `invite_regenerated` and `member_removed` events.

### System Health Metrics

- **Error Rates**: Monitored via HTTP 4xx/5xx counts in `RequestLoggingMiddleware` and
  `wishlist_shared_view_failed` / `invite_join_failed` WARNING logs.
- **Capability Token Integrity**: Monitored via count of `invite_preview_accessed` logs with
  `status="not_found"` or `status="expired"`.

## Monitoring Integration

- [x] Structured JSON / Syslog log formatting via `wishenka.logging`
- [x] Access log filtering via `ShareTokenAccessFilter`
- [x] Request execution timing middleware (`RequestLoggingMiddleware`)
- [ ] Prometheus metrics endpoint (future follow-up)
- [ ] Loki / Grafana dashboards for sharing funnels (future follow-up)

## Validation Results

- [x] Logs are correctly formatted with syslog-compatible log levels
- [x] Capability tokens are 100% sanitized across access logs and route logs
- [x] Caplog automated verification suite in `tests/test_wishlists_htmx_observability.py`:
  - `test_wishlist_shared_view_observability`: passes with guest, owner, and gifter contexts
  - `test_invite_preview_accessed_observability`: passes for valid, expired, and not found tokens
  - `test_invite_joined_observability`: passes with correct role and user attribution
  - `test_member_removed_observability`: passes with actor and removed user validation
  - `test_invite_regenerated_observability`: passes with zero leakage of old or new tokens
  - `test_share_token_access_filter_redaction`: passes for share, invite, and join paths
- [x] All lines <= 100 characters.

## Notes

All operations strictly honor the Surprise Invariant: recipient status is computed dynamically
and never exposes reservation ownership or purchaser details in log events or HTML templates.
