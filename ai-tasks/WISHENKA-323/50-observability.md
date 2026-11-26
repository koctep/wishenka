# WISHENKA-323: Observability Implementation

Shared wishlist actions already emit their domain events from
`RepoWishlistOps`. Screens and bot capture stay on that path. The new
in-memory refusal had no event, so it now logs one warning. No metric
system was added.

## Logging Implementation

### Added Logs

- **EMERG**: none. This service does not use that level.
- **ALERT**: none. This service does not use that level.
- **CRIT**: none. This service does not use that level.
- **ERR**: none added.
- **WARNING**: `WishlistService` wrapper `_repository_forward` in
  `wishenka/wishlists/service.py`, when the service has no store.
  Message: `Wishlist action refused because the repository path is required`.
  `extra`: `event` `wishlist_repository_path_required`, `operation` (the
  shared method name). Arguments are not logged. A public token, a title,
  and a user name are absent.
- **NOTICE**: none. This service does not use that level.
- **INFO**: none added. Successful shared actions keep the `RepoWishlistOps`
  events listed below.
- **DEBUG**: none added. `WishlistService.in_memory` still logs
  `wishlist_service_in_memory_created` when the instance is built. That
  line is not the refusal.

### Records that already cover this change

Logger `wishenka.wishlists` unless noted. Each line uses `extra` with an
`event` field. Payloads stay identifiers and counts. Titles, descriptions,
tokens, and wish text are not fields on these records.

Screen requests build `RepoWishlistOps` on the request repository
(`get_wishlist_repository` in `wishenka/web/dependencies.py`). After a
successful commit that dependency flushes deferred logs on that same
repository. On `SQLAlchemyError` it clears them and logs
`wishlist_store_error` (`error_type` included) from
`wishenka.web.dependencies`. On any other failure it clears them and
re-raises without a second domain line.

`WishlistStore.run_repository` is the same commit-then-flush unit for a
store-backed `WishlistService` shared method and for bot capture. A
database error goes through `_raise_for_storage_error`:
`wishlist_store_error` at ERROR when the failure is not a lock wait, and
`wishlist_inventory_busy` at WARNING when SQLite reports busy. That busy
name is the existing helper. This step does not add a retry. Other
failures clear the queued commit logs and re-raise. Domain refusals stay
the `RepoWishlistOps` warnings already emitted inside the transaction.
Deferred records (`share_access_granted`, `favorite_access_revoked`,
`view_history_access_revoked`, `share_access_revoked`) are written only
after commit.

Events a person-facing shared action already uses:

- Create and lifecycle: `wishlist_created`, `wishlist_status_changed`,
  `wishlist_deleted_listed`, `wishlist_restore_retention_expired`,
  `wishlist_restored_from_deleted`
- Links and join: `public_token_not_found`,
  `deleted_wishlist_access_attempt`, `public_wishlist_resolved`,
  `wishlist_invite_join_failed`, `wishlist_member_joined`,
  `public_token_rotate_denied`, `public_token_rotated`,
  `invite_token_rotate_denied`, `invite_token_rotated`
- Items: `item_access_denied`, `item_created`, `item_reorder_invalid`,
  `items_reordered`, `item_archived`, `item_restored`
- Favorites and history: `favorite_deleted_wishlist_denied`,
  `favorite_own_wishlist_denied`, `favorite_access_denied`,
  `view_history_deleted_wishlist_denied`, `view_history_access_denied`,
  `view_history_user_missing`, `view_history_recorded`,
  `view_history_listed`, `view_history_cleared`

Route `execute()` in `wishenka/web/routes/wishlists.py` still logs
`wishlist_mutation_committed` only after `create_wishlist`,
`update_wishlist`, `change_status`, `reset_share`,
`restore_deleted_wishlist`, or `delete_wishlist` returns. A refusal does
not emit it. `wishlist_view_projected` stays off the screen path.

Bot capture save (`wishenka/bot/capture.py`, logger `wishenka.bot.capture`)
still logs `bot_capture_save` with `outcome`, and `bot_capture_action_error`
when `run_repository` raises. The wish itself is `item_created` from
`RepoWishlistOps.add_wish_item`. An archived list still refuses with
`item_access_denied`, not a second archive event.

Store snapshot lines `wishlist_store_read` and `wishlist_store_write` are
not the shared-action record. Those actions no longer hydrate or
snapshot-write. Settings and ownership transfer still use that snapshot
path. Reservation and receipt commits still use
`wishlist_inventory_committed`.

### Log Structure

- Structured logs: yes (`extra` event fields; `JsonFormatter` places extras
  under `extra` when `log_json` is on)
- Includes context: `operation` on the new refusal; existing events keep
  their ids and counts
- Log levels: WARNING for the new refusal. Existing INFO and WARNING domain
  events and the existing ERROR storage event are unchanged

## Metrics Implementation (if applicable)

No metric system exists in this repository (no Prometheus client, no
counters or histograms). None was added.

### Performance Metrics

- **Response time**: none added. Screen requests still carry `duration_ms`
  on the completed-request INFO from `RequestLoggingMiddleware`.
- **Throughput**: none
- **Error rate**: none. A storage failure remains `wishlist_store_error`.
  The new refusal is the WARNING above.

### Business Metrics

None added. Shared-action outcomes stay the domain events above.

### System Health Metrics

None added.

- **Resource usage**: none
- **Component status**: none

## Monitoring Integration

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [x] Log aggregation (existing JSON logs). New event:
  `wishlist_repository_path_required`.

## Validation Results

Checked `run_repository`, `get_wishlist_repository`, `_repository_forward`,
and the `RepoWishlistOps` event sites by reading them.
`tests/test_wishlists_sqlite_repo_observability.py::test_in_memory_shared_action_logs_repository_path_required`
asserts the warning for `record_view` and `get_wishlist_by_public_token`,
and that the token and the user name are absent.
`tests/test_wishenka_323_one_wishlist_rule_set.py` was run after the
logging change. `make analyze` was run.

- [x] Logs are correctly formatted (`event` plus `operation` only on the
  new warning)
- [ ] Metrics are collected correctly (no metrics system on this path)
- [x] Logging works in error scenarios (in-memory `record_view` and
  `get_wishlist_by_public_token` each emit one warning, then
  `WishlistNotFoundError`)
- [x] Large data structures are not logged (the new record is the method
  name; the public token and the user name are absent)
- [ ] Metrics are available for monitoring (not applicable)

## Notes

`wishlist_repository_path_required` means the shared rule set was invoked
on a service with no store. It is not `wishlist_not_found` and it is not a
commit. `record_share_view_if_authenticated` still swallows
`WishlistNotFoundError`; the warning is what remains when that helper is
given an in-memory service. Screen handlers pass `RepoWishlistOps`, so a
normal share view does not take this branch.
