# WISHENKA-304: Observability Implementation

## Logging Implementation

### Added Logs

No production log line was added or removed. History titles are not in any
history log field, so nothing was stripped. `recorded_seq` was not added as a
second event.

Existing events already cover record and list. Their fields are small. The
order key is the integer `recorded_seq` (counter `view_history_seq`). It is
not a wishlist title, and it is not a field on these events.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none for this order key
- **WARNING**: none added. Denial events below already exist and do not carry
  a title or `recorded_seq`.
- **NOTICE**: none
- **INFO**: existing record and list events, unchanged
- **DEBUG**: none added

### Record and list events

`view_history_recorded` (`INFO`) covers a recorded view.

- `wishenka.wishlists` in `WishlistService.record_view`: message
  `Wishlist %s view recorded for user %s`. Extra: `event`, `wishlist_id`,
  `user_id`. Emitted with `logger.info` inside the service method. It is not
  queued through `_emit_or_defer_commit_log`.
- `wishenka.web.wishlists` in `POST /api/history/{wishlist_id}`: same message
  and the same extra, after `await service.record_view` returns. This is the
  route handler line.
- `RepoWishlistOps.record_view` does not emit `view_history_recorded`.

`view_history_listed` (`INFO`) covers a history list.

- `wishenka.wishlists` in `WishlistService.get_history`: message
  `Viewing history listed for user %s (count=%s)`. Extra: `event`, `user_id`,
  `count`. The entries themselves are not logged.
- `wishenka.web.wishlists` in `GET /api/history`: same message and the same
  extra, after the response rows are built. The HTTP body includes `name` and
  `event_title`. The log extra does not.
- `RepoWishlistOps.get_history` and `WishlistRepository.list_view_history` do
  not emit `view_history_listed`.

Neither event's message or extra contains `title`, `name`, `event_title`,
`description`, or the history list. `recorded_seq` is the tie-break used by
`_history_rank` and by `ORDER BY viewed_at DESC, recorded_seq DESC`. It is an
integer sequence, not a title.

### What those lines are not

A handler event is not the middleware line, and neither line is proof that
the transaction committed.

- `RequestLoggingMiddleware.dispatch` (`wishenka.web`) logs
  `HTTP request completed` only after `call_next` returns, and before it
  returns that response. Extra: `method`, `path`, `status_code`,
  `duration_ms`. No history event name, no `recorded_seq`, no title.
- `get_wishlist_repository` commits with `await conn.commit()` when the
  endpoint has returned and the connection is still in a transaction, then
  calls `flush_commit_logs()`. Record and list do not queue a pending commit
  log, so commit emits no history event.
- `wishlist_mutation_committed` is logged in `execute` only for
  `create_wishlist`, `update_wishlist`, `change_status`, `reset_share`,
  `restore_deleted_wishlist`, and `delete_wishlist`. History record and list
  are not in that set.
- `WishlistRepository.record_view` logs `wishlist_repo_mutation` immediately
  (`entity=view_history`, `operation=record`, `user_id`, `wishlist_id`)
  through `logger.info`, before `conn.commit()`. That line is not
  `view_history_recorded` and not a commit record. It has no title and no
  `recorded_seq`.

Related denial lines, unchanged, also omit titles and `recorded_seq`:
`view_history_access_denied` and `view_history_deleted_wishlist_denied`
(`WARNING`: `wishlist_id`, `user_id`) in the service and in `RepoWishlistOps`.

### Log Structure

Log format used:

- Structured logs: yes (`extra`, rendered by `JsonFormatter` when JSON logging
  is on)
- Includes context: yes (`event`, ids, and `count` on list)
- Log levels: `INFO` for record and list; `WARNING` for the existing denials

## Metrics Implementation (if applicable)

### Performance Metrics

No new metrics. Request duration stays on the middleware line
`duration_ms` only.

- **Response time**: existing `duration_ms` on `HTTP request completed`
- **Throughput**: none added
- **Error rate**: none added

### Business Metrics

No business metric was added. `view_history_listed` already carries `count`.
`recorded_seq` stays an order key in storage and in the sort, not a metric.

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

No exporter or dashboard was added for this task.

## Validation Results

Validation results:

- [x] Large data structures are not logged
- [ ] Logs are correctly formatted
- [ ] Metrics are collected correctly
- [ ] Logging works in error scenarios
- [ ] Metrics are available for monitoring

Checked by reading the history log call sites. The test suite was not started.
The checked item is the extra dicts and message arguments: ids and `count`
only. Format, metrics, and error-path runs were not executed in this step.

## Notes

Equal view times order by `recorded_seq`, not by wishlist title and not by
row id. Putting that integer on the existing `view_history_recorded` extra
would repeat a small context field the event already has room for. This step
does not do that, and it does not add another event beside
`view_history_recorded` or `view_history_listed`.
