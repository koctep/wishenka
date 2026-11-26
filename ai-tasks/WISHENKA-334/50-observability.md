# WISHENKA-334: Observability Implementation

## Logging Implementation

### Added Logs

No new log. This task adds the downgrade test
`test_downgrade_from_unify_user_keys_restores_earlier_identity` in
`tests/test_wishenka_188_user_key_unification_repro.py`. It does not change
`wishenka/wishlists/alembic/versions/unify_user_keys_and_cascades.py` or any
other production logger.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none added. A failed downgrade still surfaces as the existing
  migration error. `downgrade` does not catch the failure. Alembic raises the
  exception from the revision, and the success event
  `unify_user_keys_downgrade_completed` is not written.
- **WARNING**: none added. `unify_user_keys_orphans_cleaned` stays as it is.
- **NOTICE**: none
- **INFO**: none added. A finished downgrade still logs
  `unify_user_keys_downgrade_completed` (`tables=8`) from
  `unify_user_keys_and_cascades.downgrade`.
- **DEBUG**: none

### Log Structure

Log format used:

- Structured logs: unchanged (`extra={"event": ...}` on the existing logger
  `wishenka.wishlists.migrations`)
- Includes context: unchanged (table name and row counts on rebuild; `tables`
  on downgrade completion)
- Log levels: none added

## Metrics Implementation (if applicable)

No new metric.

### Performance Metrics

None.

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
- [x] Logging works in error scenarios — a failed downgrade still surfaces as
  the existing migration error
- [x] Large data structures are not logged — no new log
- [x] Metrics are available for monitoring — no new metric

## Notes

The migration and its logs are unchanged. The new check calls
`command.downgrade` on a temporary database and does not open a production
logging or metrics path.
