# WISHENKA-219: Technical Debt Analysis

## Shortcuts Taken

- **Duplicated delivery lock and fence check across route and service layers:**
  `wishenka/web/routes/reservations.py` (`complete_reservation`) acquires
  `delivery_lock(store.database_url, item_id, user.telegram_id)` and calls `has_fence(...)`
  before calling `execute(...)`, while `wishenka/wishlists/service.py` (`_transactional`)
  also acquires `delivery_lock` and calls `has_fence(...)` when `self._store` is present.
  This currently avoids self-deadlock only because `execute_idempotent` runs the action
  against a transient `WishlistService` without `self._store`; if `execute_idempotent` ever
  attached `store` to that service instance, the nested non-reentrant `delivery_lock` would
  fail with `BlockingIOError` (HTTP 503).
- **Queue validation omitted in `wishenka/notices/fence.py`:**
  `claim_key`, `begin_attempt`, and `defer_claim` select `notification_outbox` when
  `queue == "gift"` and otherwise fall through to `reminder_outbox` instead of validating
  `queue in ("gift", "reminder")` explicitly.
- **Store-coupled notice suppression:**
  Pending receipt-notice suppression on promise completion lives in
  `wishenka/wishlists/store.py` (`_persist_wish`), so an injected in-memory
  `WishlistService` (without `WishlistStore`) does not suppress outbox rows.

## Code Quality Issues

- **Asymmetric fence lookup in `wishenka/notices/operator.py` (`resolve`):**
  `find_key` queries `receipt_delivery_fence` before acquiring `delivery_lock`, then
  acquires `delivery_lock` only if a key was found. Consolidating key resolution and
  deletion under a single lock/transaction boundary would make the invariant easier to
  reason about.
- **Unvalidated URL `item_id` used for route-level lock key:**
  In `wishenka/web/routes/reservations.py`, `complete_reservation` locks on the URL
  `item_id` before `execute(...)` verifies that `reservation.wish_item_id == item_id`.
  A mismatched URL `item_id` still fails safely with 404 without mutating state, but
  acquiring the lock inside `WishlistStore.execute_idempotent` / `_transactional` after
  resolving the reservation's actual `wish_item_id` would avoid locking an unrelated key.

## Missing Tests

- **Timeout markers:** No missing timeout blockers — all WISHENKA-219 test files and
  modified notice test files (`tests/test_wishenka_219_repro.py`,
  `tests/test_wishenka_219_badge.py`, `tests/test_wishenka_219_fence.py`,
  `tests/test_wishenka_219_observability.py`, `tests/test_notice_operator.py`,
  `tests/test_receipt_notices_extra.py`) declare module-level `pytestmark = pytest.mark.timeout(...)`.
- **Fail-closed lock namespace edge cases:**
  `wishenka/notices/fence.py` (`_lock_path`) fails closed on non-SQLite URLs, symlinked
  lock directories, wrong UID, or permissive directory modes (`0o077`), but there is no
  dedicated test exercising those rejection paths or `:memory:` SQLite URLs.

## Performance Concerns

- **Per-reservation check in `_persist_wish`:**
  `wishenka/wishlists/store.py` (`_persist_wish`) runs an extra `SELECT 1` and two
  `UPDATE` statements per newly completed reservation. Because completion is a low-frequency
  single-reservation action, this is negligible in practice, though it adds one round-trip
  per completion.

## Follow-up Tasks

- **Refactor `delivery_lock` + `has_fence` acquisition into a single boundary** (either
  `WishlistStore.execute_idempotent` or `WishlistService._transactional`) so
  `wishenka/web/routes/reservations.py` and `wishenka/wishlists/service.py` do not
  duplicate lock acquisition, fence checks, and busy-error logging. — Jira: [WISHENKA-269](https://pypost.atlassian.net/browse/WISHENKA-269)
- **Validate `queue` in `wishenka/notices/fence.py`** (`Literal["gift", "reminder"]` with an
  explicit `ValueError` on unknown values) and add unit tests for `_lock_path` fail-closed
  checks. — Jira: [WISHENKA-268](https://pypost.atlassian.net/browse/WISHENKA-268)
- **Pre-existing test failure (`NON-BLOCKER — pre-existing`):**
  `tests/test_receipt_notices_extra.py::test_cleanup_cycle_survives_a_failing_notice_purge`
  fails (`AssertionError: assert 'TypeError' == 'RuntimeError'`) because the `_Broken`
  stub's `purge_finished(self, threshold: datetime)` signature does not accept the `now`
  and `reminder_threshold` keyword arguments passed by `wishenka/wishlists/cleanup.py`.
  Pre-existing failures in the suite are already tracked in Jira (`WISHENKA-220`,
  `WISHENKA-226`, `WISHENKA-232`, `WISHENKA-235`, `WISHENKA-245`, `WISHENKA-264`–`WISHENKA-267`);
  no duplicate Jira issue should be created.
