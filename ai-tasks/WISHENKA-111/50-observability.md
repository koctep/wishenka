# WISHENKA-111: Observability Implementation

## Logging Implementation

### Added Logs

- **ERR**: `wishenka.wishlists.migrations.upgrade_to_head_sync` records migration failures with
  exception context and the `wishlist_migration_failed` event.
- **INFO**: `wishenka.wishlists.migrations.upgrade_to_head_sync` records migration start and
  completion through `wishlist_migration_started` and `wishlist_migration_completed` events.
- **INFO**: `wishenka.wishlists.migrations._adopt_known_schema` records validated legacy-schema
  adoption with its selected revision through `wishlist_migration_legacy_schema_adopted`.

### Log Structure

- Structured logs: yes, through `logging` `extra` fields.
- Includes context: yes; events include the adopted revision and completion duration. Database
  paths and user data are intentionally excluded.
- Log levels: INFO and ERROR.

## Metrics Implementation

### Performance Metrics

- **Migration duration**: `duration_ms` on `wishlist_migration_completed` in
  `wishenka.wishlists.migrations.upgrade_to_head_sync`.

### Business Metrics

- No new business metric is applicable: schema migrations are an operator startup concern and do
  not process customer-facing business events.

### System Health Metrics

- **Migration outcome**: the started, completed, and failed event names expose migration health
  to the application's configured log aggregation.

## Monitoring Integration

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [x] Log aggregation (via the application's configured Python logging handlers)

## Validation Results

Verified by `tests/test_wishlist_migrations_observability.py` (caplog on
`wishenka.wishlists.migrations`, per-module `pytest.mark.timeout(30)`, no unbounded waits):

- [x] `test_fresh_database_logs_started_and_completed`: a fresh database emits exactly
  `wishlist_migration_started` then `wishlist_migration_completed` at INFO, and `duration_ms` is
  a non-negative `int`.
- [x] `test_legacy_database_logs_adoption_with_revision`: a legacy database emits exactly one
  `wishlist_migration_legacy_schema_adopted` with a valid `revision` extra that also appears in
  the message, between the started and completed events.
- [x] `test_unsupported_schema_logs_failure_and_reraises`: an unsupported schema emits
  `wishlist_migration_failed` at ERROR with `exc_info` (`RuntimeError`), the exception is
  re-raised, and neither the adoption nor the completed event is logged.
- [x] All three tests assert that no record's message or extras contain the database path, file
  name, URL, or seeded user data.
- [ ] Prometheus/Grafana/alerting: not applicable; metrics are log-based only.

The adoption event is logged after a successful `command.stamp`, so it means adoption completed.

## Notes

The migration implementation is synchronous but runs from `asyncio.to_thread`; the elapsed time
therefore measures the complete migration operation without blocking the application event loop.
