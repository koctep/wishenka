# WISHENKA-340: Observability Implementation

Favorites, recently deleted lists, the bot list offer, and recording a
visit load list headers (and this person's membership where the role or
permission needs it). A finished header load is the common case. This step
does not log it. A failed load and the refusals those paths already raise
keep the records they already write. No production logger or metric was
added. Wishlist titles, descriptions, and user names stay off these
records.

## Logging Implementation

### Added Logs

None.

- **EMERG**: none. This service does not use that level.
- **ALERT**: none. This service does not use that level.
- **CRIT**: none. This service does not use that level.
- **ERR**: none added. A database failure stays the existing storage error
  below.
- **WARNING**: none added. A deleted list, a refused visit, a person who
  is not stored, a lock wait, and an in-memory refusal stay on the events
  they already write.
- **NOTICE**: none. This service does not use that level.
- **INFO**: none added. The screen results and the stored visit stay on
  the events they already write. The header read itself does not.
- **DEBUG**: none added. A non-empty header or membership batch still logs
  `wishlist_repo_batch_read`. `get_wishlist_header` still writes nothing.

### Records that already cover these openings

#### Favorites

`favorites_listed` (`INFO`), logger `wishenka.web.wishlists`,
`GET /api/favorites` in `wishenka/web/routes/wishlists.py`.

Message: `Favorites listed for user %s (count=%s)`.

`extra`: `event`, `user_id` (the telegram id), `count` (length of the
list returned).

The line is written after `RepoWishlistOps.list_favorites` returns,
including an empty bookmark list (`count` 0). An empty id list returns
before either batch and does not log a batch read. The message and
`extra` carry the id and the count. They do not carry a wishlist title,
a description, an occasion, or the row list. `list_favorites` itself
writes no line.

#### Recently deleted lists

`wishlist_deleted_listed` (`INFO`) is written twice on the HTTP path, as
it was before this task.

`RepoWishlistOps.list_deleted_wishlists` in
`wishenka/wishlists/repo_ops.py` (logger `wishenka.wishlists`) logs
`Listed %s deleted wishlists for actor %s` with `extra` `event`,
`actor_id`, `count`, and `retention_days`.

`GET /api/wishlists/deleted` then logs `Deleted wishlists listed for user
%s` with `extra` `event`, `user_id`, `count`, and `retention_days`
(logger `wishenka.web.wishlists`).

Both lines run after the retention filter, including an empty result
(`count` 0). An empty moment list does not call the header batch. Neither
record carries a title, a description, or an occasion. The JSON body may
include `name` and `description`. Those fields are absent from the logs.
`list_deleted_owner_moments` writes no line.

#### Bot list offer

`_allowed` in `wishenka/bot/capture.py` writes no line. An empty id list
returns before either batch. When the person has accessible lists, the
header and membership batches still write the DEBUG records below. The
keyboard titles stay out of the log.

The callback that loads the offer inside its transaction still logs ERROR
`bot_capture_action_error` (`Bot capture action failed`, logger
`wishenka.bot.capture`) when that transaction raises. The `extra` is
`event` only. A storage failure on that path is also logged by
`run_repository` before the exception leaves the store (see database
failure). The preview paths that call `lists_for` do not write
`bot_capture_action_error`. They still get the store record.

`bot_capture_save` stays the save outcome after the person picks a list.
That save still opens the chosen list in full. This task does not change
that log.

#### Recording a visit

`record_view` in `wishenka/wishlists/repo_ops.py` (logger
`wishenka.wishlists`) keeps the same order and the same events:

- A deleted list: WARNING `view_history_deleted_wishlist_denied`, then
  `WishlistNotFoundError`. Message: `View history record denied: wishlist
  %s is deleted`. `extra`: `event`, `wishlist_id`, `user_id`.
- A list the person may not see: WARNING `view_history_access_denied`,
  then `WishlistNotFoundError`. Message: `Unauthorized view history
  attempt on wishlist %s by user %s denied`. Same `extra` keys.
- A person who is not stored (WISHENKA-351): WARNING
  `view_history_user_missing`, then `WishlistNotFoundError`. Message:
  `View history record skipped: user %s is not stored`. Same `extra`
  keys.
- A stored visit: INFO `view_history_recorded`. Message: `Wishlist %s view
  recorded for user %s`. Same `extra` keys. This is the write, not the
  header read.

A missing list raises `WishlistNotFoundError` and writes no warning. That
is the same silence as `get_wishlist` returning no row.
`get_wishlist_header` writes no line on a hit or a miss. `POST
/api/history/{wishlist_id}` does not add its own event.

#### Header and membership batches

`wishlist_repo_batch_read` (`DEBUG`), logger
`wishenka.wishlists.repository`.

`get_wishlist_headers_by_ids` message: `Wishlist repository batch read:
%d/%d wishlist headers (%d chunks)`. `extra`: `event`, `entity`
`wishlist_header`, `requested_count`, `chunks_count`, `found_count`.

`list_user_memberships_by_wishlist_ids` message: `Wishlist repository
batch read: %d/%d wishlist members (%d chunks)`. `extra`: `event`,
`entity` `wishlist_member`, and the same three counts.

Both lines are written after every chunk returns. An empty id list
returns `{}` and does not log. Titles, descriptions, roles, and
`joined_at` are absent. Favorites and the bot offer call both batches
when the id list is non-empty. Recently deleted lists call the header
batch only, and only for lists still inside the recovery window.
Recording a visit calls the membership batch for that one id after the
list is present and not deleted. It does not call the header batch.
`get_wishlist_header` is a single-row select and does not log.

#### Omissions

An id whose header is absent is skipped. `found_count` on the header
debug line can be lower than `requested_count`. The wishlist title is
absent. A share-only favorite has no membership row, so membership
`found_count` can be lower than `requested_count`. That gap is the access
shape, and it is already on the debug record.

Rows the bot filter drops stay out of the keyboard. They are not a
second error event. `_allowed` has no count line.

#### Database failure

A `SQLAlchemyError` in a batch or in `get_wishlist_header` raises inside
the repository method. The debug line sits after the chunk loop, so that
successful-read line is absent. The screen INFO lines sit after the
load, so they are absent too. `view_history_recorded` sits after the
write, so it is absent too.

Screen routes run through `execute()` in
`wishenka/web/routes/wishlists.py` (logger `wishenka.web.wishlists`).
That handler logs ERROR `Wishlist storage operation failed due to
database error` with `extra` `event` `wishlist_store_error`, then raises
`RuntimeError`. A busy error is re-raised there without that ERROR.
`get_wishlist_repository` in `wishenka/web/dependencies.py` rolls the
`RuntimeError` back and does not write a second `wishlist_store_error`.
A busy error there logs WARNING `wishlist_inventory_busy` and raises
`InventoryBusyError`. The route error extra has no `error_type`. The
dependency error extra adds `error_type` and no title.

A store-backed service call and the bot's `lists_for` use
`WishlistStore.run_repository`. `_raise_for_storage_error` in
`wishenka/wishlists/store.py` (logger `wishenka.wishlists.store`) logs
WARNING `wishlist_inventory_busy` when SQLite reports a lock wait, and
ERROR `wishlist_store_error` for any other `SQLAlchemyError`. The generic
error extra is `event` only. The busy extra adds the wish scope, which
is empty for these reads and for recording a visit.

An in-memory `WishlistService` call of `list_favorites`,
`list_deleted_wishlists`, or `record_view` logs WARNING
`wishlist_repository_path_required` with `operation` set to that method
name (`wishenka.wishlists`, `_repository_forward`), then raises
`WishlistNotFoundError`. The record has the method name. It has no title
and no user name. The bot offer does not use that forward.

`get_wishlist_store` logs ERROR `wishlist_store_uninitialized` when the
app has no store. The header reads do not run.

#### Request line

`RequestLoggingMiddleware` (logger `wishenka.web`) logs INFO
`HTTP request completed` with `method`, `path`, `status_code`, and
`duration_ms`. An exception that leaves the app logs
`HTTP request unhandled exception` via `logger.exception` with `method`,
`path`, and `duration_ms`. Those records have no wishlist title and no
user name.

History listing and clearing were not part of this change. They still
log `view_history_listed` and `view_history_cleared`.

### Log Structure

- Structured logs: yes (`extra` event fields; `JsonFormatter` places
  extras under `extra` when `log_json` is on)
- Includes context: `user_id` or `actor_id` and `count` on the screen
  results; `wishlist_id` and `user_id` on a visit refusal or a stored
  visit; `entity` and the three counts on each batch; `event` on the
  storage error
- Log levels: existing DEBUG, INFO, WARNING, and ERROR. None added

## Metrics Implementation (if applicable)

No metric system exists in this repository (no Prometheus client, no
counters or histograms). None was added. A successful header load is not
counted.

### Performance Metrics

- **Response time**: none added. The favorites, deleted-list, and visit
  routes still carry `duration_ms` on the completed-request INFO from
  `RequestLoggingMiddleware`.
- **Throughput**: none
- **Error rate**: none. A storage failure remains `wishlist_store_error`
  or `wishlist_inventory_busy`.

### Business Metrics

None added. `favorites_listed` and `wishlist_deleted_listed` already
carry `count`. `view_history_recorded` already marks one stored visit.

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

Checked by reading `list_favorites`, `list_deleted_wishlists`,
`record_view`, `_allowed`, `lists_for`, `get_wishlist_header`,
`get_wishlist_headers_by_ids`, `list_user_memberships_by_wishlist_ids`,
`list_favorite_wishlist_ids`, `list_deleted_owner_moments`,
`list_accessible_wishlist_ids`, `execute()`, `get_wishlist_repository`,
`run_repository`, and `_raise_for_storage_error`. Python was left
unchanged, so `make analyze` and the repro were not run.

- [x] Logs are correctly formatted (existing `extra` dicts are ids,
  counts, `entity`, `event`, and `retention_days`)
- [ ] Metrics are collected correctly (no metrics system on this path)
- [x] Logging works in error scenarios (a `SQLAlchemyError` raises before
  the success lines; the screen path logs `wishlist_store_error` or
  `wishlist_inventory_busy`; the store path logs those same events; a
  deleted list, a refused visit, and a missing person keep their
  warnings)
- [x] Large data structures are not logged (counts and ids; titles and
  user names are absent)
- [ ] Metrics are available for monitoring (not applicable)

## Notes

A successful header load happens on every opening of favorites, recently
deleted lists, the bot list offer, and on every visit that is prepared.
Logging each of those would record ordinary traffic. The screen already
logs the list the person receives, and a stored visit already logs
`view_history_recorded`. `found_count` below `requested_count` on
`wishlist_repo_batch_read` is the existing signal for a header the id
list named and for a list this person does not belong to. It is not a
second error event. Operators still get the screen count that was
returned, and a database failure still gets `wishlist_store_error` or
`wishlist_inventory_busy`.
