# WISHENKA-61: Technical Debt Analysis

## Shortcuts Taken

- **Injected `wishlist_service` test path bypasses idempotency:** In
  [`wishenka/web/routes/reservations.py`](../../wishenka/web/routes/reservations.py) (`execute`),
  [`wishenka/web/routes/receipts.py`](../../wishenka/web/routes/receipts.py) (`_run`), and
  [`wishenka/web/routes/receipts_ui.py`](../../wishenka/web/routes/receipts_ui.py)
  (`record_receipt_ui`), when `request.app.state.wishlist_service` is injected (used by unit tests
  that bypass `WishlistStore`), `idempotency_key` is ignored and the action runs directly against
  the injected service without deduplication.
- **Duplicated client-side `Idempotency-Key` generation across three frontend files:**
  [`wishenka/web/templates/base.html`](../../wishenka/web/templates/base.html),
  [`wishenka/web/static/receipt.js`](../../wishenka/web/static/receipt.js), and
  [`wishenka/web/static/miniapp.js`](../../wishenka/web/static/miniapp.js) each inline their own
  `nextIdempotencyKey` (`window.crypto.randomUUID()` with `Date.now()`/`Math.random()` fallback)
  instead of sharing a single frontend helper.
- **No non-JS HTML fallback for `receipts_ui` idempotency:**
  [`wishenka/web/routes/receipts_ui.py`](../../wishenka/web/routes/receipts_ui.py) relies on
  [`wishenka/web/static/receipt.js`](../../wishenka/web/static/receipt.js) to attach the
  `Idempotency-Key` header via `htmx.ajax(...)`; a plain browser form post without JS omits the
  header and executes non-idempotently.
- **Account deletion / anonymization scope:** `wl_idempotency_records` stores `actor_id` and
  serialized `response_body` for `idempotency_retention_hours` (default 24 hours). While bounded
  by TTL cleanup, `wl_idempotency_records` should also be included when implementing full account
  deletion / anonymization, already tracked under
  [WISHENKA-35](https://pypost.atlassian.net/browse/WISHENKA-35).

## Code Quality Issues

- **Duplicate `receipt_recorded_http` log on HTMX replay:** In
  [`wishenka/web/routes/receipts_ui.py`](../../wishenka/web/routes/receipts_ui.py),
  `record_receipt_ui` logs `receipt_recorded_http` unconditionally after
  `execute_wish_idempotent(...)` returns, even when `outcome.replayed` is `True`. By contrast,
  [`wishenka/web/routes/reservations.py`](../../wishenka/web/routes/reservations.py) logs
  completion inside `serialized_action` (only on initial execution), while
  [`wishenka/wishlists/store.py`](../../wishenka/wishlists/store.py) emits `idempotency_replay_hit`
  on replay.
- **Repeated route-level idempotency wiring:** All eight protected endpoints across
  [`wishenka/web/routes/reservations.py`](../../wishenka/web/routes/reservations.py),
  [`wishenka/web/routes/wishlists.py`](../../wishenka/web/routes/wishlists.py),
  [`wishenka/web/routes/receipts.py`](../../wishenka/web/routes/receipts.py), and
  [`wishenka/web/routes/receipts_ui.py`](../../wishenka/web/routes/receipts_ui.py) repeat
  `parse_idempotency_key(request)` and `compute_request_hash(...)` boilerplate; this is clear and
  explicit today, though a FastAPI dependency or shared route helper could reduce repetition if
  more idempotent endpoints are added later.

## Missing Tests

- **Per-test timeout marker audit (`do-testing`):** Audited across the entire repository via
  `.venv/bin/pytest --collect-only -q -m "not timeout" -p no:cacheprovider -n 0`: **1031 collected
  tests, 1031 deselected, 0 tests missing explicit `pytest.mark.timeout` markers** (no BLOCKER). No
  pre-existing test failures were encountered.
- **DOM/browser execution of `base.html` and `miniapp.js` retry key reuse:** Server-side replay,
  concurrency, cleanup, and observability are thoroughly covered in
  [`tests/test_booking_idempotency.py`](../../tests/test_booking_idempotency.py),
  [`tests/test_booking_idempotency_extended.py`](../../tests/test_booking_idempotency_extended.py),
  and [`tests/test_wishenka_61_observability.py`](../../tests/test_wishenka_61_observability.py),
  but `base.html` (`htmx:configRequest` / `htmx:afterRequest`) and `miniapp.js` (`publicView`
  Reserve button) do not yet have a headless-browser/DOM test executing actual `503`/network-error
  retries end-to-end.

## Performance Concerns

- **Unbatched `DELETE` in `WishlistStore.cleanup_expired_idempotency_records`:** In
  [`wishenka/wishlists/store.py`](../../wishenka/wishlists/store.py),
  `cleanup_expired_idempotency_records` runs `DELETE FROM wl_idempotency_records WHERE expires_at <= :now`
  in a single transaction without a `LIMIT` batch size. Under normal 24-hour retention traffic this
  uses `idx_wl_idempotency_expires_at` and completes quickly, but after prolonged cleanup-worker
  downtime a large backlog could hold the SQLite write lock longer than necessary.
- **Full HTMX HTML fragment stored in `response_body` for `record_receipt_ui`:** For UI receipt
  submissions, `wl_idempotency_records.response_body` stores the full rendered OOB HTML fragment for
  up to 24 hours. Row sizes are small for typical wishlists, though very large wishlists increase
  per-record storage footprint within the retention window.

## Follow-up Tasks

1. **NON-BLOCKER, Low:** Extract a shared frontend `Idempotency-Key` helper (UUID generation and
   retry-preserving lifecycle) for
   [`wishenka/web/templates/base.html`](../../wishenka/web/templates/base.html),
   [`wishenka/web/static/receipt.js`](../../wishenka/web/static/receipt.js), and
   [`wishenka/web/static/miniapp.js`](../../wishenka/web/static/miniapp.js), and add DOM/browser
   tests covering `503`/network-error key reuse and rotation.
   Jira: [WISHENKA-187](https://pypost.atlassian.net/browse/WISHENKA-187).
2. **NON-BLOCKER, Low:** Emit `receipt_recorded_http` in
   [`wishenka/web/routes/receipts_ui.py`](../../wishenka/web/routes/receipts_ui.py) only when
   `outcome.replayed` is `False` so HTMX replay logging matches
   [`wishenka/web/routes/reservations.py`](../../wishenka/web/routes/reservations.py).
   Jira: [WISHENKA-185](https://pypost.atlassian.net/browse/WISHENKA-185).
3. **NON-BLOCKER, Low:** Add bounded `LIMIT` batching to
   `WishlistStore.cleanup_expired_idempotency_records` in
   [`wishenka/wishlists/store.py`](../../wishenka/wishlists/store.py) to cap SQLite write-lock
   duration during backlog purges.
   Jira: [WISHENKA-186](https://pypost.atlassian.net/browse/WISHENKA-186).
4. **NON-BLOCKER, High:** Include `wl_idempotency_records` (`actor_id`) in account deletion /
   anonymization alongside other user-scoped tables. Existing scope:
   [WISHENKA-35](https://pypost.atlassian.net/browse/WISHENKA-35).
