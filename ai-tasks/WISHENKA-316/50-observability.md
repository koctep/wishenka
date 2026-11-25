# WISHENKA-316: Observability Implementation

## Scope and Decision

No new log was added. Delete, list, restore, and cleanup already emit the
event names the existing tests assert. `wishenka/wishlists/retention.py` has
no logger. `classify_owner_delete` and `get_wishlist_or_none` write nothing
on `WishlistService` and on `RepoWishlistOps`.

The expired delete path logs `wishlist_retention_expired`. The route raises
`WishlistRetentionExpiredError` with no log of its own. `execute()` in
`wishenka/web/routes/wishlists.py` catches that exception, writes the
WARNING, then raises HTTP 410. The message text is still "Wishlist restore
rejected because retention window expired". WISHENKA-318 owns that wording.

Shipping HTTP uses `RepoWishlistOps`. `execute()` takes that branch when
`app.state.wishlist_service` is unset, which is how the application is built.
The handler still depends on `WishlistRepo`.

## When records fire

`get_wishlist_repository()` in `wishenka/web/dependencies.py` is a yield
dependency on the request exit stack (the default scope). FastAPI enters it
before the handler and resumes it after the response has been sent.

Order on a normal return:

1. The dependency begins a transaction and yields the repository.
2. The handler runs. Every delete, list, and restore event below is written
   in this step, with `logger.info` or `logger.warning`. None of them is
   queued with `defer_commit_log`.
3. The handler returns.
4. `RequestLoggingMiddleware` writes `HTTP request completed` (INFO, logger
   `wishenka.web`) with `method`, `path`, `status_code`, and `duration_ms`
   after `call_next()` returns and before that middleware returns the
   response onward. This record is not the repository commit, and it does
   not mean the client has finished receiving the body.
5. `get_wishlist_repository()` commits when its yield resumes, after the
   handler has returned, if the connection is still in a transaction, then
   calls `flush_commit_logs()`. These paths queued nothing, so the flush
   adds no delete or restore record.

`wishlist_mutation_committed` is step 2. `execute()` writes it after the
inner action returns and before `execute()` returns to the handler. The
commit is step 5, after the handler has returned. A commit failure at step 5
logs `wishlist_store_error`
from the dependency (`error_type` set), rolls back, and raises
`RuntimeError`. The INFO records from step 2 are already written.

When the handler raises, including the `HTTPException` `execute()` uses for
404, 409, and 410, the exception is thrown back into the yield. The
dependency rolls the transaction back and does not commit. `execute()`
writes `wishlist_mutation_committed` only after the inner action returns, so
those error paths do not emit it.

## Logging Implementation

### Added Logs

None.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none added. `execute()` logs `wishlist_store_error` (no
  `error_type`) when the action raises `SQLAlchemyError`, then raises
  `RuntimeError`. That record is during the handler. The dependency logs
  `wishlist_store_error` with `error_type` when the commit after a normal
  return raises `SQLAlchemyError`. A missing `WishlistStore` logs
  `wishlist_store_uninitialized` from `get_wishlist_store` before the
  handler runs.
- **WARNING**: none added. Expired delete already logs
  `wishlist_retention_expired`.
- **NOTICE**: none. These modules call the standard library levels INFO,
  WARNING, ERROR, and DEBUG.
- **INFO**: none added.
- **DEBUG**: none added. The request middleware still logs
  `HTTP request started` at DEBUG before the handler.

### Events the shipping handlers emit

Route logger: `wishenka.web.wishlists`. Domain logger: `wishenka.wishlists`.
Levels are the standard library levels the calls use.

**First delete, 200.** `RepoWishlistOps.delete_wishlist` upserts the row and
cancels reservations on the open connection, then logs
`wishlist_status_changed` (INFO, `wishlist_id`, `actor_id`, `from_status`,
`to_status`) before that method returns. The route then logs
`wishlist_deleted_by_owner` (INFO, `wishlist_id`, `user_id`,
`retention_days`, `outcome` `deleted`) and returns the JSON body.
`execute()` then logs `wishlist_mutation_committed` (INFO, `operation`
`delete_wishlist`). All three are before the handler returns. The dependency
commits when its yield resumes, after the handler returns.

**Repeat inside the window, 200.** The route does not call
`delete_wishlist`, so there is no `wishlist_status_changed`. It logs
`wishlist_deleted_by_owner` with `outcome` `already_deleted`. `execute()`
still logs `wishlist_mutation_committed` because the action returned. The
handler writes no row. The dependency commits that transaction when its
yield resumes, after the handler returns.

**Unknown id, 404.** The route logs `wishlist_delete_not_found` (WARNING,
`wishlist_id`, `user_id`) and raises `WishlistNotFoundError`. `execute()`
maps that to 404 and adds no event. The dependency rolls back.

**Non-owner, 404.** The route logs `wishlist_delete_denied` (WARNING,
`wishlist_id`, `user_id`) and raises `PermissionDeniedError`. `execute()`
then logs `wishlist_permission_denied` (WARNING, `operation`
`delete_wishlist`) and raises HTTP 404. The body matches the unknown-id
response. The dependency rolls back.

**Archived, 409.** Classification is `apply` and writes nothing.
`delete_wishlist` raises `WishlistArchivedError` before its status log.
`execute()` logs `wishlist_archived_mutation_blocked` (WARNING, `operation`
`delete_wishlist`). There is no `wishlist_deleted_by_owner`, no
`wishlist_status_changed`, and no `wishlist_mutation_committed`. The
dependency rolls back.

**Retention ended on delete, 410.** The route raises
`WishlistRetentionExpiredError` and writes nothing. `execute()` logs
`wishlist_retention_expired` (WARNING, `operation` `delete_wishlist`) and
raises HTTP 410. There is no `wishlist_deleted_by_owner`, no
`wishlist_status_changed`, and no `wishlist_mutation_committed`. The
dependency rolls back.

**Recently deleted, 200.** `list_deleted_wishlists` logs
`wishlist_deleted_listed` on `wishenka.wishlists` (INFO, `actor_id`,
`count`, `retention_days`) before it returns. The route then logs the same
event name (INFO, `user_id`, `count`, `retention_days`) before the action
returns. This handler is not in the `wishlist_mutation_committed` set. The
dependency commits the read transaction when its yield resumes, after the
handler returns.

**Restore inside the window, 200.** `RepoWishlistOps.restore_deleted_wishlist`
rotates tokens and upserts on the open connection, then logs
`wishlist_restored_from_deleted` (INFO, `wishlist_id`, `actor_id`,
`from_status`, `to_status`, `retention_days`) before it returns. The route
then logs the same event name (INFO, `wishlist_id`, `user_id`,
`retention_days`). `execute()` then logs `wishlist_mutation_committed` with
`operation` `restore_deleted_wishlist`. All three are before the handler
returns. The dependency commits when its yield resumes, after the handler
returns. An already
active list returns before the domain record; the route record and
`wishlist_mutation_committed` still fire because the action returned.

**Retention ended on restore, 410.** The domain method logs
`wishlist_restore_retention_expired` (WARNING, `wishlist_id`, `actor_id`,
`retention_days`) and raises `WishlistRetentionExpiredError`. `execute()`
then logs `wishlist_retention_expired` with `operation`
`restore_deleted_wishlist` and raises HTTP 410. There is no
`wishlist_mutation_committed`. The dependency rolls back.

**Unexpected error inside `delete_wishlist`, 500.** The method raises before
the route success log. There is no `wishlist_deleted_by_owner` and no
`wishlist_mutation_committed`. The dependency rolls back. The middleware
logs `HTTP request unhandled exception` (ERROR, `method`, `path`,
`duration_ms`) with a traceback.

`WishlistService` uses the same event names for the status change, the list,
the restore, and `wishlist_restore_retention_expired`. A direct non-owner
call on that class also logs `access_denied` (WARNING, `actor_id`,
`wishlist_id`, `action`) before `PermissionDeniedError`. The shipping delete
route classifies `forbidden` first, so that record is not on the HTTP path.
`RepoWishlistOps.delete_wishlist` raises `PermissionDeniedError` for a direct
non-owner call and does not log `access_denied`.

### Cleanup

`retention.py` is silent on the purge path as well. `run_cleanup_cycle` in
`wishenka/wishlists/cleanup.py` (logger `wishenka.wishlists.cleanup`) calls
`purge_archived_wishlists` with `purge_threshold` of
`wishlist_retention_days(settings)`. That store method commits inside
`engine.begin()` before it returns the purged count. After the token purge,
the wishlist purge, and the other cycle steps have returned, the cycle logs
`background_cleanup_completed` (INFO, including `wishlists_purged` and
`duration_ms`). A notice-purge exception is caught inside `_purge_notices`:
it logs `receipt_notice_purge_failed` (WARNING, `error_class`) and returns
zero counts, and the cycle can still log `background_cleanup_completed`.
An exception that escapes the cycle's own `try` logs
`background_cleanup_failed` (ERROR, `error`, `duration_ms`, traceback) and
returns stats with `wishlists_purged` 0. The worker logs
`background_worker_started` and
`background_worker_stopped` (INFO) and uses `logger.exception` for an
unexpected loop error.

### Log Structure

- Structured logs: yes. `extra` is rendered by `JsonFormatter`.
- Includes context: yes. `event`, ids, `operation`, `outcome`, counts,
  `retention_days`, and status names. Titles, share tokens, invite tokens,
  and reservation detail stay out of these records.
- Log levels: INFO, WARNING, ERROR, DEBUG.

## Metrics Implementation (if applicable)

### Performance Metrics

None added.

- **Response time**: the existing request line carries `duration_ms`. Cleanup
  completion carries `duration_ms`. No new metric.
- **Throughput**: none
- **Error rate**: none

### Business Metrics

None added. A repeat delete is `outcome` `already_deleted` on
`wishlist_deleted_by_owner`. Purge volume is `wishlists_purged` on
`background_cleanup_completed`.

### System Health Metrics

None added.

- **Resource usage**: none
- **Component status**: `background_worker_started` and
  `background_worker_stopped` already mark the cleanup loop.

## Monitoring Integration

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [x] Log aggregation: existing JSON logs. Expired delete is
  `wishlist_retention_expired` with `operation` `delete_wishlist`. A burst of
  `wishlist_delete_denied` per `user_id`, and 5xx on
  `DELETE /api/wishlists/{id}`, remain the operator signals.

## Validation Results

- [x] Logs are correctly formatted. Existing tests format the captured
  records with `JsonFormatter` and read `extra`.
- [x] Metrics are collected correctly. No new metric. Existing `duration_ms`
  and `wishlists_purged` fields are unchanged.
- [x] Logging works in error scenarios. Delete observability covers 404,
  409, 410, and the unhandled 500. Restore observability covers 410.
- [x] Large data structures are not logged. The pinned events carry ids,
  counts, enums, and `retention_days`.
- [ ] Metrics are available for monitoring. No metrics backend was added.

Re-ran for this step: `tests/test_wishlist_delete_observability.py`,
`tests/test_wishlist_retention_single_rule.py`, and
`tests/test_wishlist_deleted_restore.py::test_deleted_restore_observability_logs`.
10 passed.

## Notes

`wishlist_mutation_committed` means the named handler's action returned. It
is written before the handler returns. The connection commit runs later,
when the yield dependency resumes. `HTTP request completed` is the
middleware record after `call_next()` returns; it is not that commit. A
repeat delete emits the same mutation event and writes no row.

Event names and fields the delete tests already assert are unchanged,
including `wishlist_retention_expired` on the expired delete path.
