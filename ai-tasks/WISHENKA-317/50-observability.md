# WISHENKA-317: Observability Implementation

## Scope and Decision

No production code changed. This task is the owner's return after a delete
that can no longer be restored, and a distinct accessible name on the delete
Cancel. The 410 branch in `confirmDelete`
(`wishenka/web/static/miniapp.js`, `deleteWishlistControls`) already tells
the owner through `#status`. The server path that answers 410 already logs
`wishlist_retention_expired`. A second server record would not be what the
owner sees, and it was not added.

## What the owner gets on a 410 delete

`pending()` writes `miniapp.wishlist_delete.pending` into `#status` before
the DELETE returns. `showHome()` then replaces `#app` and, when the home
lists load, ends by clearing `#status`. After that await returns, the 410
branch is the write that remains:

- `status(t('miniapp.wishlist_delete.failed'), 'error')` on `#status`
  (`wishenka/web/routes/miniapp.py`, `role="status"`).
- `textContent` and `aria-label` are that catalog sentence. English:
  "Could not delete the wishlist. Nothing was changed. Try again." The
  Russian value is the same key in `wishenka/i18n/catalog.py`.
  `status()` clears `aria-label` first. The branch sets it again so the
  name is the sentence. The error marker is a CSS `::before` on
  `[data-kind="error"]` and is not part of that name.
- `data-kind` is `error`. `aria-live` is `assertive`.
- The home `h1` (`tabindex="-1"`) gets `aria-describedby="status"` and
  `focus()`. The description the owner hears with that heading is the same
  `#status` sentence.

The in-panel `role="alert"` is removed at the start of `confirmDelete` and
is not put back on this branch. The owner does not get
`miniapp.wishlist_delete.done`. A failed home load sets
`miniapp.home.load_failed` inside `showHome`, and the 410 branch then
replaces it with `miniapp.wishlist_delete.failed`.

The owner does not receive a server log. Operators already get one WARNING
from `execute()` in `wishenka/web/routes/wishlists.py`: event
`wishlist_retention_expired`, `operation` `delete_wishlist`, then HTTP 410.
The route itself writes nothing on `OwnerDeleteKind.EXPIRED`. That WARNING
is a rejection. It is not `wishlist_mutation_committed`, not
`wishlist_deleted_by_owner`, and not `wishlist_status_changed`. The
repository dependency rolls the transaction back. The WARNING does not mean
a delete was committed.

## Logging Implementation

### Added Logs

None.

- **EMERG**: none
- **ALERT**: none
- **CRIT**: none
- **ERR**: none added
- **WARNING**: none added. The 410 delete already logs
  `wishlist_retention_expired`.
- **NOTICE**: none
- **INFO**: none added. `wishlist_mutation_committed` is written only after
  the delete action returns. The 410 path raises before that.
- **DEBUG**: none added

### Log Structure

- Structured logs: yes, on the existing server WARNING (`extra` event and
  `operation`). The owner-facing signal is `#status`, not a log line.
- Includes context: the WARNING includes `operation` (`delete_wishlist`).
  It does not include the wishlist title. The client status is the fixed
  failure sentence and does not include the title.
- Log levels: WARNING on the existing 410 rejection. No new level.

The delete Cancel's accessible name (`miniapp.wishlist_delete.cancel_name`,
`aria-label` on that button) is a static name, not an execution result. It
is not logged. The settings Cancel is unchanged and is not logged.

## Metrics Implementation (if applicable)

### Performance Metrics

None. This client has no metrics client, and the change does not add one.

- **Response time**: none
- **Throughput**: none
- **Error rate**: none

### Business Metrics

None. A 410 delete is already distinguishable in server logs by
`wishlist_retention_expired` with `operation` `delete_wishlist`, and by the
absence of `wishlist_mutation_committed`.

### System Health Metrics

None added.

- **Resource usage**: none
- **Component status**: none

## Monitoring Integration

- [ ] Prometheus metrics
- [ ] Grafana dashboards
- [ ] Alerting rules
- [x] Log aggregation (existing JSON logs). No new event to aggregate.
  The owner-facing signal is `#status`, not a log stream.

## Validation Results

Checked against the current `confirmDelete` 410 branch and `status()`. No
new logger call, so there is no new format to test.

- [x] Logs are correctly formatted (no new record; existing WARNING unchanged)
- [ ] Metrics are collected correctly (no metrics on this path)
- [x] Logging works in error scenarios (existing 410 WARNING already covers
  the server rejection; the owner is left with the `#status` sentence above)
- [x] Large data structures are not logged (no new log; the status sentence
  has no list body)
- [ ] Metrics are available for monitoring (not applicable)

## Notes

Product behavior was left as Step 4 implemented it. The critical path for
the owner already has `#status`. The critical server path for a 410 delete
already has `wishlist_retention_expired`. WISHENKA-316 records the commit
order: that WARNING is not a successful commit.
