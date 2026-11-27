# WISHENKA-335: Observability Implementation

## Logging Implementation

### Added Logs

No new log and no new event. The apply procedure moved to
`wishenka.db.migrations.apply_history_sync`. Start, failure, and completion
still go out on the product history logger
`wishenka.wishlists.migrations` (`PRODUCT_HISTORY.log`), with the same event
names, messages, and extras. A successful apply still emits one completion
record. The runner does not also log on `wishenka.db.migrations`.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none added. `wishlist_migration_failed` stays an exception log
  (`ERROR`, traceback, `extra={"event": "wishlist_migration_failed"}`) in
  `wishenka/db/migrations.py` (`apply_history_sync`), then the exception is
  re-raised. The message is still `Wishlist database migration failed`.
- **WARNING**: none
- **NOTICE**: none
- **INFO**: none added. The same two apply records stay:
  - `wishlist_migration_started` —
    `wishenka/db/migrations.py` (`apply_history_sync`), message
    `Starting wishlist database migration`,
    `extra={"event": "wishlist_migration_started"}`.
  - `wishlist_migration_completed` — same function, message
    `Wishlist database migration completed in %d ms`,
    `extra={"event": "wishlist_migration_completed", "duration_ms": duration_ms}`.
  - `wishlist_migration_legacy_schema_adopted` stayed in
    `wishenka/wishlists/migrations.py` (`_adopt_known_schema`), with
    `revision`. That line was not part of the move.
- **DEBUG**: none

### Log Structure

Log format used:

- Structured logs: yes, unchanged (`extra={"event": ...}` on
  `wishenka.wishlists.migrations`)
- Includes context: yes, unchanged (`duration_ms` on completion; `revision`
  on adoption). Database path and URL are still absent.
- Log levels: `INFO`, `ERROR` (existing apply events). This step adds none.

## Metrics Implementation (if applicable)

No new metric. `duration_ms` on `wishlist_migration_completed` remains the
timing field for one apply.

### Performance Metrics

None added. Existing `duration_ms` covers the whole apply, including the
file lock wait.

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

- [x] Logs are correctly formatted — shared `upgrade_to_head_sync` on a new
  file logged `wishlist_migration_started` then `wishlist_migration_completed`
  on `wishenka.wishlists.migrations`, with the existing messages. A second
  apply logged only those two events.
- [x] Metrics are collected correctly — no new metric; `duration_ms` is still
  the integer on the completion record
- [x] Logging works in error scenarios — an unsupported wishlist schema logged
  `wishlist_migration_started` and `wishlist_migration_failed` (`ERROR`) and
  re-raised `RuntimeError`. Completion was absent.
- [x] Large data structures are not logged — the three apply records carry the
  event name and, on success, `duration_ms` only
- [x] Metrics are available for monitoring — no new metric; the existing
  completion extra is unchanged

## Notes

Wishlist startup and person startup both call
`wishenka.db.migrations.upgrade_to_head`. That binding loads
`PRODUCT_HISTORY` and logs through it, so both startups keep the wishlist
logger and the same four migration events (start, adoption, completion,
failure). Revision-local logs (downgrade refusal, user-key rebuild, and the
rest) stay in the Alembic versions and were not moved.

`tests/test_wishlist_migrations_observability.py` still asserts those events
on `wishenka.wishlists.migrations`. Collecting that file alone currently fails
on a circular import through `wishenka.web.app` that is already present on
`master`. The checks above called `upgrade_to_head_sync` directly.
