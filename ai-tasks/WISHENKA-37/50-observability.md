# WISHENKA-37: Observability Implementation

## Logging Implementation

### Added Logs

No log was added. This task is a verification matrix. It does not change
runtime logging.

- **EMERG**: none added.
- **ALERT**: none added.
- **CRIT**: none added.
- **ERR**: none added.
- **WARNING**: none added.
- **NOTICE**: none added.
- **INFO**: none added.
- **DEBUG**: none added.

Existing logs are already indexed in `doc/dev/verification-matrix.md`.

- **S5. Logs.** Recipient-facing logs omit a gifter. That covers a
  recipient wish view, a client promise-route action, a refused
  recipient create (the same log whether a promise exists or not), and
  a refused recipient change (path identifier, no gifter). Modules:
  `wishenka/web/routes/reservations.py` (`wishenka.web.reservations`),
  `wishenka/wishlists/service.py` (`wishenka.wishlists`),
  `wishenka/wishlists/store.py` (commit and rollback omit the row and
  the gifter), `wishenka/web/routes/items.py` (`wishenka.web.items`),
  and `wishenka/web/routes/items_ui.py`.
- **S5 operator stream.** The same row records that operator logs of a
  gifter's own booking may contain `gifter_id`. That stream is checked
  by `tests/test_reservation_observability.py`
  `test_item_reserved_observability_event` and the sibling booking
  events in that module, and by `tests/test_wishlist_roles_lifecycle.py`
  `test_reservation_audit_logging`. The matrix leaves that stream on
  the stories that shipped it. It is a recipient exit only if a
  recipient path emits it.
- **A7. The link stays out of access logs.** A public-open log does not
  print the share token. Modules: `wishenka/web/app.py`
  (`ShareTokenAccessFilter`, `RequestLoggingMiddleware`),
  `wishenka/web/routes/sharing.py` (`wishlist_shared_view` records the
  wishlist id), and `wishenka/web/routes/wishlists.py`
  (`public_wishlist_viewed` records the wishlist id).

The **Logs** section under **Modules this matrix indexes** names the
same loggers. It is an index, not a new emitter.

### Log Structure

Log format used:

- Structured logs: unchanged. `wishenka/logging.py` already provides
  `JsonFormatter` and `configure_logging`. This step did not change
  them.
- Includes context: unchanged. Recipient-facing records indexed by S5
  omit a gifter. The operator stream indexed on S5 may include
  `gifter_id`.
- Log levels: none added.

## Metrics Implementation (if applicable)

No metric was added. The service gained no counter, histogram, or
exporter from this task.

### Performance Metrics

Added performance metrics:

- **Response time**: none
- **Throughput**: none
- **Error rate**: none

### Business Metrics

Business metrics:

- None. This task does not count requests or conversions.

### System Health Metrics

System health metrics:

- **Resource usage**: none added
- **Component status**: none added

## Monitoring Integration

Integration with monitoring systems:

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

No monitoring client was added. Existing records stay on the loggers
the matrix already names.

## Validation Results

Validation results:

- [ ] Logs are correctly formatted
- [ ] Metrics are collected correctly
- [ ] Logging works in error scenarios
- [ ] Large data structures are not logged
- [ ] Metrics are available for monitoring

No new log line or metric was emitted, so these checks were not run
against new instrumentation. Coverage of the existing logs is the
matrix: S5 for recipient-facing omission and the operator stream, A7
for share-token redaction.

## Notes

WISHENKA-37 records where surprise invariants are already checked. It
does not add a production log. The combined recipient-answer-plus-log
walk on S5, and S6 notifications, stay with WISHENKA-38. This step does
not close that gap and does not write a sender.
