# WISHENKA-180: Technical Debt Analysis

## Shortcuts Taken

- **Dual entry points for reminder lifecycle operations**: `claim_reminder`, `refresh_reminder`, and `settle_reminder` are exposed both as methods on `NoticeStore` (`wishenka/notices/store.py`) and as module-level functions in `wishenka/notices/reminders.py`. Keeping the module-level functions was an intentional backward-compatibility trade-off (documented in `ai-tasks/WISHENKA-180/20-architecture.md`) so existing tests (`tests/test_wishenka_34_repro.py`, `tests/test_wishenka_34_preferences.py`, `tests/test_i18n_unit.py`) that pass `WishlistStore` directly did not need to be rewritten.
- **No temporary workarounds or crutches**: No `TODO`/`FIXME` hacks, hard-coded bypasses, or private-attribute fallbacks remain in `wishenka/notices/`. `NoticeWorker` (`wishenka/notices/worker.py`) interacts exclusively with `NoticeStore`'s public interface.

## Code Quality Issues

- **`NoticeStore.__init__` still typed against concrete `WishlistStore`**: In `wishenka/notices/store.py`, `NoticeStore.__init__(self, store: WishlistStore, settings: Settings)` requires concrete `WishlistStore`, even though every internal call on `self._store` (`lines 102, 176, 212, 304, 342, 411`) only uses `transaction(work)`. Typing `store` as `TransactionalStore` would make `NoticeStore` itself storage-implementation-agnostic.
- **Concrete `isinstance(store, NoticeStore)` guard in `NoticeWorker.__init__`**: In `wishenka/notices/worker.py` (line 50), `self._scheduler = ReminderScheduler(store, settings) if isinstance(store, NoticeStore) else None` still checks the concrete `NoticeStore` class rather than a `@runtime_checkable` `TransactionalStore` protocol (pre-existing pattern preserved to keep stub/fake stores in unit tests working).
- **Static AST guard in `tests/test_notice_store_transaction_repro.py`**: `test_notices_package_has_no_private_store_access` checks for `. _store` attribute access on non-`self` identifiers in `wishenka/notices/*.py` (excluding `store.py`), which is simple and effective for `._store`, though it would not catch `getattr(..., "_store")` or aliases.

## Missing Tests

- **Timeout markers (no blocker)**: `tests/test_notice_store_transaction_repro.py` declares `pytestmark = pytest.mark.timeout(30)` at module scope, and all other notice/reminder test modules (`test_notice_delivery_repro.py`, `test_receipt_notices.py`, `test_notice_operator.py`, `test_reminder_scan_paging.py`, `test_notice_worker_concurrency.py`) have explicit `pytest.mark.timeout(...)` markers.
- **Direct unit tests for `NoticeStore` reminder delegation**: `tests/test_notice_store_transaction_repro.py` directly tests `NoticeStore.transaction(work)` (commit and rollback) and the absence of `._store` access in `wishenka/notices/`, while `NoticeStore.claim_reminder`, `NoticeStore.refresh_reminder`, `NoticeStore.settle_reminder`, and `ReminderScheduler(notice_store, settings).run_once(now)` are only exercised indirectly via `NoticeWorker` integration tests (`tests/test_notice_delivery_repro.py`, `tests/test_notice_worker_concurrency.py`). Adding direct unit tests on `NoticeStore` for those three methods and `ReminderScheduler(notice_store, settings)` would tighten contract coverage.

## Performance Concerns

- **None**: `NoticeStore.transaction()` is a single-await delegation to `WishlistStore.transaction()`, and `NoticeStore.claim_reminder`, `refresh_reminder`, and `settle_reminder` pass `self` directly to `wishenka.notices.reminders` without introducing extra queries, transactions, or data copies.

## Follow-up Tasks

- **Optional / Low**: Generalize `NoticeStore.__init__` parameter `store` in `wishenka/notices/store.py` from `WishlistStore` to `TransactionalStore` (non-blocking; `WishlistStore` already satisfies `TransactionalStore`). — Jira: [WISHENKA-251](https://pypost.atlassian.net/browse/WISHENKA-251)
- **Optional / Low**: Add direct unit tests in `tests/test_notice_store_transaction_repro.py` for `NoticeStore.claim_reminder`, `NoticeStore.refresh_reminder`, `NoticeStore.settle_reminder`, and `ReminderScheduler(notice_store, settings).run_once(now)` (currently covered indirectly through `NoticeWorker`). — Jira: [WISHENKA-252](https://pypost.atlassian.net/browse/WISHENKA-252)
