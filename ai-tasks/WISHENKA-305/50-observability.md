# WISHENKA-305: Observability Implementation

## Logging Implementation

### Added Logs

No production log line was added or removed. Step 4 already moved the
success events onto the domain operations. This step records the resulting
events. Wishlist titles and the full history are not in those extras, so
nothing was stripped.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none for these history events
- **WARNING**: existing denials, unchanged (see below)
- **NOTICE**: none
- **INFO**: existing record and list events, one each, on the domain logger
- **DEBUG**: none added

### Record and list events

`view_history_recorded` (`INFO`) is written once per recorded view, from the
domain record operation. Logger: `wishenka.wishlists`.

- `WishlistService.record_view` (`wishenka/wishlists/service.py`): message
  `Wishlist %s view recorded for user %s`. Extra: `event`, `wishlist_id`,
  `user_id`. Emitted with `logger.info` after the in-memory entry is stored.
- `RepoWishlistOps.record_view` (`wishenka/wishlists/repo_ops.py`): the same
  message and the same extra, after `await self.repo.record_view(entry)`.
  Same logger.

`view_history_listed` (`INFO`) is written once per history list, from the
domain list operation. Same logger.

- `WishlistService.get_history`: message
  `Viewing history listed for user %s (count=%s)`. Extra: `event`, `user_id`,
  `count`. The entries themselves are not logged.
- `RepoWishlistOps.get_history`: the same message and the same extra, after
  the returned rows are filtered. Same logger.

`GET /api/history` and `POST /api/history/{wishlist_id}` in
`wishenka/web/routes/wishlists.py` do not write `view_history_recorded` or
`view_history_listed`. They call `get_history` and `record_view` and shape
the HTTP body. The body may include `name` and `event_title`. The log extra
does not.

Neither event's message or extra contains `title`, `name`, `event_title`,
`description`, or the history list.

### Denials

`view_history_deleted_wishlist_denied` (`WARNING`) stays on recording a view
of a deleted wishlist. Both `record_view` methods write it on
`wishenka.wishlists` when the wishlist exists and its status is deleted,
then raise `WishlistNotFoundError`. Extra: `event`, `wishlist_id`,
`user_id`. The history route does not write it.

`favorite_deleted_wishlist_denied` (`WARNING`) stays on adding a favorite of
a deleted wishlist. Both `add_favorite` methods write it on
`wishenka.wishlists`. Extra: `event`, `wishlist_id`, `user_id`. Recording a
view does not write this event. The history route does not write it.

### What those lines are not

A handler event is not the middleware line, and that middleware line is not
a commit.

- `RequestLoggingMiddleware.dispatch` (`wishenka.web` in
  `wishenka/web/app.py`) logs `HTTP request completed` after `call_next`
  returns and before it returns that response. Extra: `method`, `path`,
  `status_code`, `duration_ms`. No history event name and no title.
- `get_wishlist_repository` commits with `await conn.commit()` when the
  endpoint has returned and the connection is still in a transaction, then
  calls `flush_commit_logs()`. Record and list use `logger.info` directly.
  They do not queue a pending commit log.
- `wishlist_mutation_committed` is logged in `execute` only for
  `create_wishlist`, `update_wishlist`, `change_status`, `reset_share`,
  `restore_deleted_wishlist`, and `delete_wishlist`. History record and list
  are not in that set.
- `WishlistRepository.record_view` logs `wishlist_repo_mutation` immediately
  (`entity=view_history`, `operation=record`, `user_id`, `wishlist_id`) on
  `wishenka.wishlists.repository`, before `conn.commit()`. That line is not
  `view_history_recorded` and not a commit record. It has no title.

### Log Structure

Log format used:

- Structured logs: yes (`extra`, rendered by `JsonFormatter` when JSON
  logging is on)
- Includes context: yes (`event`, ids, and `count` on list)
- Log levels: `INFO` for record and list; `WARNING` for the denials above

## Metrics Implementation (if applicable)

### Performance Metrics

No new metrics. Request duration stays on the middleware line
`duration_ms` only.

- **Response time**: existing `duration_ms` on `HTTP request completed`
- **Throughput**: none added
- **Error rate**: none added

### Business Metrics

No business metric was added. `view_history_listed` already carries `count`.

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

Checked by reading the history log call sites. The test suite was not
started. The checked item is the extra dicts and message arguments: ids and
`count` only. Format, metrics, and error-path runs were not executed in
this step.

## Notes

One recorded view produces one `view_history_recorded` on
`wishenka.wishlists`. One history list produces one `view_history_listed` on
the same logger. A deleted wishlist on `record_view` produces
`view_history_deleted_wishlist_denied` and does not produce
`favorite_deleted_wishlist_denied`. That favorites denial stays on
`add_favorite`.
