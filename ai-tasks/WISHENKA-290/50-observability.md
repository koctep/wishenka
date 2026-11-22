# WISHENKA-290: Observability Implementation

## Scope and Logging

This change reorganizes an existing Mini App screen and calls existing API endpoints. It adds no
server operation, background worker, or new telemetry endpoint. Existing structured server logs
cover the persistent operations; adding duplicate browser logs would not improve server-side
diagnostics and could expose wishlist data or capability URLs.

- `wishenka/web/app.py` logs each HTTP request at DEBUG on entry and INFO on completion with
  method, sanitized path, status code, and elapsed milliseconds; unhandled exceptions use ERROR.
  Public share and invitation token paths are masked before logging.
- `wishenka/web/routes/wishlists.py` records INFO events including `wishlist_updated`,
  `wishlist_share_token_reset`, `invite_token_reset`, `member_role_updated`, `member_removed`,
  `favorite_added`, `favorite_removed`, and `wishlist_status_changed`. It records WARNING events
  for access denial and invalid or archived operations. Structured context uses operation and
  identifiers rather than wishlist titles, request bodies, or capability tokens.
- The browser reports save, cancellation, refresh, clipboard, and Telegram failures to the user.
  Client-only failures are not sent to the server; existing request logs only cover requests that
  reach it. No new client telemetry or logging of private links was introduced.

## Metrics and Monitoring

No new metrics, Prometheus exporter, dashboard, or alert were added. Request completion logs
already include duration and status for operational analysis, but they are not a metrics system.
The presentation-only change creates no new server performance or business metric; introducing a
monitoring stack or tracking client interactions is outside this task. Existing infrastructure
remains responsible for log collection and any aggregation.

## Validation

The following existing observability tests passed (19 tests):

```text
make test PYTEST_JOBS=2 PYTEST_ARGS='tests/test_observability.py \
  tests/test_wishlist_management_observability.py \
  tests/test_wishlist_sections_observability.py -q'
```

These exercise structured formatting, request and error logging, wishlist and member operations,
favorites and history, and token/data redaction. Step 4 browser tests additionally cover user-facing
failure and retry behavior after refresh failures. No new log or metric was added in this step.
