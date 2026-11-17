# WISHENKA-86: Observability Implementation

## Logging Implementation

### Added Logs

- **WARNING**: `wishenka/wishlists/service.py` (`restore_deleted_wishlist`) - emits `event="wishlist_restore_retention_expired"` with `wishlist_id`, `actor_id`, `retention_days` when a restore attempt is rejected because the retention window has expired.
- **WARNING**: `wishenka/wishlists/service.py` (`restore_deleted_wishlist`) - emits `event="access_denied"` with `actor_id`, `wishlist_id`, `action="restore_deleted_wishlist"` on unauthorized restore attempts (existing from Step 4).
- **WARNING**: `wishenka/web/routes/wishlists.py` (`execute`) - emits `event="wishlist_retention_expired"` (`410 Gone`), `event="wishlist_permission_denied"` (`404`), and `event="wishlist_archived_mutation_blocked"` (`409`) with `operation` (existing from Step 4).
- **INFO**: `wishenka/wishlists/service.py` (`list_deleted_wishlists`) - emits `event="wishlist_deleted_listed"` with `actor_id`, `count`, `retention_days`.
- **INFO**: `wishenka/web/routes/wishlists.py` (`list_deleted_wishlists`) - emits `event="wishlist_deleted_listed"` with `user_id`, `count`, `retention_days`.
- **INFO**: `wishenka/wishlists/service.py` (`restore_deleted_wishlist`) - emits `event="wishlist_restored_from_deleted"` with `wishlist_id`, `actor_id`, `from_status`, `to_status`, `retention_days`.
- **INFO**: `wishenka/web/routes/wishlists.py` (`restore_deleted_wishlist`) - emits `event="wishlist_restored_from_deleted"` with `wishlist_id`, `user_id`, `retention_days`.
- **INFO**: `wishenka/web/routes/wishlists.py` (`execute`) - emits `event="wishlist_mutation_committed"` for `operation="restore_deleted_wishlist"` (existing from Step 4).

### Log Structure

Log format used:
- Structured logs: yes (`wishenka.logging.JsonFormatter` in production JSON mode)
- Includes context: yes (scalar `extra` fields: `event`, `wishlist_id`, `actor_id` / `user_id`, `count`, `retention_days`, `from_status`, `to_status`, `operation`)
- Log levels: `INFO`, `WARNING`
- PII / secret protection: no wishlist titles, descriptions, user names, `public_token`, or `invite_token` values are logged.

## Metrics Implementation (if applicable)

Not applicable — the project uses structured JSON logging without a Prometheus/StatsD metrics backend.

### Performance Metrics

- N/A (not configured in this repository)

### Business Metrics

- N/A (trackable via log aggregation on `event="wishlist_deleted_listed"`, `event="wishlist_restored_from_deleted"`, `event="wishlist_restore_retention_expired"`)

### System Health Metrics

- N/A

## Monitoring Integration

Integration with monitoring systems:
- [ ] Prometheus metrics (N/A)
- [ ] Grafana dashboards (N/A)
- [ ] Alerting rules (N/A)
- [x] Log aggregation (structured JSON via `wishenka.logging.JsonFormatter`)

## Validation Results

Validation results:
- [x] Logs are correctly formatted (verified with `JsonFormatter` in `tests/test_wishlist_deleted_restore.py::test_deleted_restore_observability_logs`)
- [x] Metrics are collected correctly (N/A)
- [x] Logging works in error scenarios (`wishlist_restore_retention_expired` verified on `410 Gone`)
- [x] Large data structures are not logged (all `extra` values asserted to be scalar primitives; wishlist titles and rotated tokens asserted absent)
- [x] `make analyze` and `make test` pass

## Notes

- All new log events follow `wishenka/logging.py` conventions (`extra` dict with scalar values only, no PII or capability tokens).
