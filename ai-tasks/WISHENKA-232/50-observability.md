# WISHENKA-232: Observability Implementation

## Logging Implementation

### Added Logs

No new log. This task changes two Alembic statements:
`add_notice_uncertain` names the three `notice_receipt_keys` columns, and
`add_receipt_delivery_fence` creates both fence tables with
`CREATE TABLE IF NOT EXISTS`. Those revisions do not log today, and this
task does not add logging inside them. The outbox rebuild and the runtime
writer are unchanged.

A failed upgrade is already covered by the history runner.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none added. `apply_history_sync` in `wishenka/db/migrations.py`
  catches any upgrade failure, including an Alembic or SQLite error from a
  revision, and logs it with `logger.exception`. The logger is
  `wishenka.wishlists.migrations`. The message is
  `Wishlist database migration failed` and the structured field is
  `event="wishlist_migration_failed"`. The exception traceback is attached,
  then the error is raised again. `wishlist_migration_completed` is not
  written. The second pass of `test_upgrade_is_repeatable` uses
  `upgrade_to_head_sync`, so that same path is what a failed second upgrade
  hits.
- **WARNING**: none
- **NOTICE**: none
- **INFO**: none added. A finished upgrade still logs
  `wishlist_migration_started` and `wishlist_migration_completed`
  (`duration_ms`) from the same runner.
- **DEBUG**: none

### Log Structure

Log format used:

- Structured logs: unchanged (`extra={"event": ...}` on
  `wishenka.wishlists.migrations`)
- Includes context: unchanged (the failure event plus the exception
  traceback; `duration_ms` only on success)
- Log levels: none added. The existing failure record is `ERROR`.

## Metrics Implementation (if applicable)

No new metric.

### Performance Metrics

None added. A successful upgrade still records `duration_ms` on
`wishlist_migration_completed`.

### Business Metrics

None.

### System Health Metrics

None.

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

No integration is added. Existing structured migration logs are unchanged.

## Validation Results

Validation results:

- [x] Logs are correctly formatted — no new log line was added
- [x] Metrics are collected correctly — no new metric
- [x] Logging works in error scenarios — a failed upgrade still logs
  `wishlist_migration_failed` with the Alembic/SQL exception
- [x] Large data structures are not logged — no new log
- [x] Metrics are available for monitoring — no new metric

## Notes

No new production logs or metrics are required. The change is idempotent SQL
inside two revisions. Operators already see a failed upgrade as
`wishlist_migration_failed` on `wishenka.wishlists.migrations`, with the SQL
error in the traceback. A successful second pass logs the existing start and
completion events and does not need a new signal for notice keys, gift
receipts, archive flags, or fence state.
