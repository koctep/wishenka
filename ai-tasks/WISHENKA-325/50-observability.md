# WISHENKA-325: Observability Implementation

Opening history loads one header batch and one membership batch, then
logs the list the person receives. Both batches already log a successful
read. A database error on either batch raises before those success lines
and is already logged. A missing header and a missing membership are the
omissions this opening already makes. No log was added. No metric system
was added. Wishlist titles and user names stay off these records.

## Logging Implementation

### Added Logs

None.

- **EMERG**: none. This service does not use that level.
- **ALERT**: none. This service does not use that level.
- **CRIT**: none. This service does not use that level.
- **ERR**: none added. A database failure stays the existing storage error
  below.
- **WARNING**: none added. A lock wait on the store path stays
  `wishlist_inventory_busy`. An in-memory `get_history` stays
  `wishlist_repository_path_required`.
- **NOTICE**: none. This service does not use that level.
- **INFO**: none added. `RepoWishlistOps.get_history` still logs
  `view_history_listed`.
- **DEBUG**: none added. Each successful batch still logs
  `wishlist_repo_batch_read`.

### Records that already cover this open

#### List result

`view_history_listed` (`INFO`), logger `wishenka.wishlists`,
`RepoWishlistOps.get_history` in `wishenka/wishlists/repo_ops.py`.

Message: `Viewing history listed for user %s (count=%s)`.

`extra`: `event`, `user_id` (the telegram id), `count` (length of the
list returned after the access check).

The line is written after filtering, including an empty visit list
(`count` 0). An empty visit list does not call either batch. The message
and `extra` carry the id and the count. They do not carry a wishlist
title, a description, an event title, a user name, or the row list.

`GET /api/history` in `wishenka/web/routes/wishlists.py` does not write
this event. The JSON body may include `name` and `event_title`. Those
fields are absent from the log.

#### Header batch

`wishlist_repo_batch_read` (`DEBUG`), logger
`wishenka.wishlists.repository`,
`WishlistRepository.get_wishlist_headers_by_ids`.

Message: `Wishlist repository batch read: %d/%d wishlist headers (%d chunks)`.

`extra`: `event`, `entity` `wishlist_header`, `requested_count`,
`chunks_count`, `found_count`.

The line is written after every chunk returns. An empty id list returns
`{}` and does not log. Titles and descriptions from the selected rows are
absent.

#### Membership batch

`wishlist_repo_batch_read` (`DEBUG`), same logger,
`WishlistRepository.list_user_memberships_by_wishlist_ids`.

Message: `Wishlist repository batch read: %d/%d wishlist members (%d chunks)`.

`extra`: `event`, `entity` `wishlist_member`, `requested_count`,
`chunks_count`, `found_count`.

The line is written after every chunk returns. An empty id list returns
`{}` and does not log. The query filters on `user_id`. That id, the role,
and `joined_at` are absent from the message and from `extra`.

#### Omissions

A visit whose header is absent is skipped. That is the same omission as
`get_wishlist` returning no row. `found_count` on the header debug line
can be lower than `requested_count`. The wishlist title is absent.

A wishlist with no membership row for this person is absent from the
membership map. Owners and share-only viewers are that case.
`found_count` on the membership debug line can be lower than
`requested_count`. That gap is the access shape, and it is already on the
debug record.

Rows the policy drops stay out of `view_history_listed` `count`.

#### Database failure

A `SQLAlchemyError` in a chunk raises inside the batch method. The debug
line sits after the chunk loop, so that successful-read line is absent.
`view_history_listed` is later in `get_history`, so it is absent too.

Screen `GET /api/history` runs through `execute()` in
`wishenka/web/routes/wishlists.py` (logger `wishenka.web.wishlists`).
That handler logs ERROR
`Wishlist storage operation failed due to database error` with `extra`
`event` `wishlist_store_error`, then raises `RuntimeError`.
`get_wishlist_repository` rolls that `RuntimeError` back and does not
write a second `wishlist_store_error`. The route handler's extra has no
`error_type`, no title, and no user name.

A store-backed `WishlistService.get_history` uses
`WishlistStore.run_repository`. `_raise_for_storage_error` in
`wishenka/wishlists/store.py` (logger `wishenka.wishlists.store`) logs
WARNING `wishlist_inventory_busy` when SQLite reports a lock wait, and
ERROR `wishlist_store_error` for any other `SQLAlchemyError`. The generic
error extra is `event` only. The busy extra adds the wish scope, which is
empty for this read.

An in-memory `WishlistService.get_history` logs WARNING
`wishlist_repository_path_required` with `operation` `get_history`
(`wishenka.wishlists`, `_repository_forward`), then raises
`WishlistNotFoundError`. The record has the method name. It has no title
and no user name.

`get_wishlist_store` logs ERROR `wishlist_store_uninitialized` when the
app has no store. The batches do not run.

#### Request line

`RequestLoggingMiddleware` (logger `wishenka.web`) logs INFO
`HTTP request completed` with `method`, `path`, `status_code`, and
`duration_ms`. An exception that leaves the app logs
`HTTP request unhandled exception` via `logger.exception` with `method`,
`path`, and `duration_ms`. Those records have no wishlist title and no
user name.

### Log Structure

- Structured logs: yes (`extra` event fields; `JsonFormatter` places
  extras under `extra` when `log_json` is on)
- Includes context: `user_id` and `count` on the list; `entity` and the
  three counts on each batch; `event` on the storage error
- Log levels: existing DEBUG, INFO, WARNING, and ERROR. None added

## Metrics Implementation (if applicable)

No metric system exists in this repository (no Prometheus client, no
counters or histograms). None was added.

### Performance Metrics

- **Response time**: none added. `GET /api/history` still carries
  `duration_ms` on the completed-request INFO from
  `RequestLoggingMiddleware`.
- **Throughput**: none
- **Error rate**: none. A storage failure remains `wishlist_store_error`.

### Business Metrics

None added. `view_history_listed` already carries `count`.

### System Health Metrics

None added.

- **Resource usage**: none
- **Component status**: none

## Monitoring Integration

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [ ] Log aggregation (ELK, Loki, etc.)

No exporter or dashboard was added. Existing JSON logs already include
the events above.

## Validation Results

Checked by reading `RepoWishlistOps.get_history`,
`get_wishlist_headers_by_ids`, `list_user_memberships_by_wishlist_ids`,
`execute()`, `get_wishlist_repository`, `run_repository`, and
`_raise_for_storage_error`. Python was left unchanged, so `make analyze`
and the history test were not run.

- [x] Logs are correctly formatted (existing `extra` dicts are ids,
  counts, `entity`, and `event`)
- [ ] Metrics are collected correctly (no metrics system on this path)
- [x] Logging works in error scenarios (a `SQLAlchemyError` in a batch
  raises before both success logs; the screen path logs
  `wishlist_store_error`, and the store path logs that event or
  `wishlist_inventory_busy`)
- [x] Large data structures are not logged (counts and ids; titles and
  user names are absent)
- [ ] Metrics are available for monitoring (not applicable)

## Notes

`found_count` below `requested_count` on `wishlist_repo_batch_read` is the
existing signal for a header the visit list named and for a wishlist this
person does not belong to. That is the omission `get_history` already
applies. It is not a second error event. Operators still get
`view_history_listed` with the count actually returned, and a database
failure still gets `wishlist_store_error` or `wishlist_inventory_busy`.
