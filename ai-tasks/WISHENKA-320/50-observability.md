# WISHENKA-320: Observability Implementation

A refused create or edit is already covered by one existing request log.
No production log line was added or removed. The wishlist name was not a
field on that record, so nothing was deleted. No metric system was added.

## Logging Implementation

### Added Logs

None.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none added. `RequestLoggingMiddleware` still logs an unhandled
  exception with `logger.exception` (`method`, `path`, `duration_ms`). A
  name-contract `422` is a response, so that branch does not run.
- **WARNING**: none added
- **NOTICE**: none
- **INFO**: none added. The existing completed-request INFO is the record
  for a refused create or edit.
- **DEBUG**: none added. `HTTP request started` is still written before
  `call_next`, with `method` and `path` only. It has no status, so it does
  not record the refusal.

### The record for a refused create or edit

Logger `wishenka.web`, level INFO, `RequestLoggingMiddleware.dispatch` in
`wishenka/web/app.py`.

Message:

`HTTP request completed: %s %s status=%d duration=%.2fms`

`extra` fields:

- `method`
- `path` (`sanitize_log_path`; the query string is removed)
- `status_code` (`422` for this refusal)
- `duration_ms` (rounded to two decimal places)

The wishlist name, the description, and the event title are absent from
the message and from `extra`. `wishlist_name_required` and
`wishlist_name_too_long` stay in the HTTP body. They are absent from this
record.

`wishenka/wishlists/name_contract.py` has no logger. A create whose name
fails, and an edit that sends a failing name, stop in
`WishlistCreateInput` / `WishlistInput` (`coerce_wishlist_name`) before
`create_wishlist` or `update_wishlist` runs. An edit that omits `name`
while the stored title fails reaches `update_wishlist`, and
`classify_stored_name` raises `HTTPException` `422` inside the `execute()`
action, before any field is assigned and before `wishlist_updated`.

`wishlist_created`, `wishlist_updated`, and `wishlist_mutation_committed`
run only after a successful action return. A `422` does not emit them.
Those success records carry `wishlist_id` and `user_id`, or `operation`.
The name, description, and event title are absent there as well. No field
was removed.

### Order

The `422` is produced first. `call_next` returns that response.
`RequestLoggingMiddleware` then logs `HTTP request completed`, and only
after that log returns the response. That INFO line is the request log.
It is not a commit. `execute()` writes `wishlist_mutation_committed` only
after the inner action returns, which this refusal does not do.
`get_wishlist_repository` commits on a normal resume of its yield. A raised
`422` takes the rollback branch of that dependency. No second event was
added beside the request log.

### Log Structure

- Structured logs: yes (`extra` on the completed-request record;
  `JsonFormatter` places extras under `extra` when `log_json` is on)
- Includes context: `method`, `path`, `status_code`, `duration_ms`
- Log levels: INFO for the completed `422`

## Metrics Implementation (if applicable)

No metric system was added.

### Performance Metrics

- **Response time**: existing `duration_ms` on the completed-request INFO
- **Throughput**: none added
- **Error rate**: none added. A refused save is the same INFO line with
  `status_code` `422`

### Business Metrics

None added. The contract type stays in the response body.

### System Health Metrics

None added.

- **Resource usage**: none
- **Component status**: none

## Monitoring Integration

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [x] Log aggregation (existing JSON logs). No new event to aggregate.

## Validation Results

Checked `RequestLoggingMiddleware.dispatch`, `create_wishlist`,
`update_wishlist`, `execute()`, and `name_contract.py` by reading them.
The full test suite was not run.

- [x] Logs are correctly formatted (no new record; the completed-request
  INFO is unchanged)
- [ ] Metrics are collected correctly (no metrics on this path)
- [x] Logging works in error scenarios (the completed-request INFO carries
  `status_code` `422` after the refusal response is formed)
- [x] Large data structures are not logged (the record is method, path,
  status, and duration; the name, description, and event title are absent)
- [ ] Metrics are available for monitoring (not applicable)

## Notes

Accepted architecture for this task: do not add the wishlist name,
description, or event title to log records. A `422` from the name contract
stays this HTTP request log only.
