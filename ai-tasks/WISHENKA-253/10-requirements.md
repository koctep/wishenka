# WISHENKA-253: Direct Unit Tests for `WishlistStore.execute_read` and `ensure_private_bot_user` Edge Cases

## Goals

Ensure reliable, regression-free behavior for two core shared mechanisms introduced in `WISHENKA-182`:

1. **Non-blocking, side-effect-free read access (`WishlistStore.execute_read`)**: Read-only queries (such as diagnostic context collection and rate-limit checks) must never persist unintended mutations and must not block or be blocked by concurrent write transactions, keeping the system responsive for users under concurrent load.
2. **Safe private-chat user and destination resolution (`ensure_private_bot_user`)**: Bot interactions must accurately resolve or provision user records and activate private notification destinations only in valid private-chat contexts, avoiding erroneous writes on missing inputs or group chats and normalizing timestamps consistently.

Currently, these contracts are only covered indirectly through higher-level integration tests. Adding dedicated unit tests provides fast, isolated verification of every boundary condition and prevents silent regressions during future refactoring.

**Programming Language**: Python

## User Stories

- **As a developer / maintainer**, I want dedicated unit tests for `WishlistStore.execute_read` verifying rollback on normal exit and on exception, as well as non-blocking concurrent reads alongside an active write transaction, so that read-only paths remain safe and non-contending.
- **As a developer / maintainer**, I want dedicated unit tests for all guard, pre-resolved record, and timestamp-normalization branches of `ensure_private_bot_user`, so that edge cases in bot user/destination activation are explicitly verified and protected against regressions.
- **As a bot user**, I want private-chat bot interactions to reliably register my notification destination without leaking group-chat contexts or failing on varied clock formats.

## Definition of Done

1. **Programming language**: Implemented in Python, consistent with the repository's automated test suite.
2. **`WishlistStore.execute_read` contract verified by direct unit tests**:
   - **Rollback on normal return**: Any uncommitted state changes attempted inside the read callback are rolled back when the callback returns normally and are not visible to subsequent reads.
   - **Rollback on exception**: When the read callback raises an exception, the exception propagates to the caller and any uncommitted state changes are rolled back.
   - **Non-blocking WAL concurrency**: A read via `execute_read` completes without blocking and returns consistent committed data while a concurrent exclusive write transaction (`BEGIN IMMEDIATE`) is held open.
3. **`ensure_private_bot_user` edge cases verified by direct unit tests**:
   - **Missing user (`user=None`)**: Returns `None` without performing any user lookup, user creation, or destination activation.
   - **Missing user store (`user_store=None` / absent)**: Returns `None` without raising an error or attempting persistence.
   - **Group-chat guard (`chat_id != user.id`)**: Returns `None` without performing user lookup, user creation, or destination activation.
   - **Pre-resolved `user_record`**: When `user_record` is provided, skips user lookup (`get_by_telegram_id`) and user creation (`upsert_from_bot`), activates the bot destination for that user and `chat_id`, and returns the provided record.
   - **Clock / `now` normalization**:
     - Explicit `now` integer takes precedence over `dependencies.clock()`.
     - When `now` is `None`, `dependencies.clock()` returning a `datetime` is normalized to Unix epoch seconds.
     - When `now` is `None`, `dependencies.clock()` returning an `int` is passed through as Unix epoch seconds.
     - When `now` is `None` and `dependencies.clock` is absent or not callable, `None` is passed as the effective timestamp.
4. **Test suite quality**:
   - All new unit tests pass deterministically with bounded execution timeouts.
   - Existing test suite and static analysis checks continue to pass without regressions.

## Task Description

### Problem
During the technical debt analysis of `WISHENKA-182` (`ai-tasks/WISHENKA-182/60-tech-debt.md`), two missing-test gaps were identified:
- `WishlistStore.execute_read` is only exercised indirectly through `_submit_support_message`, leaving its rollback guarantees and non-blocking WAL concurrency behavior without direct unit test coverage.
- `ensure_private_bot_user` has multiple guard and normalization branches (`user=None`, `user_store=None`, `chat_id != user.id`, pre-injected `user_record`, and `now` / `dependencies.clock()` normalization) that lack direct unit tests.

### Scope and Constraints
- **In Scope**:
  - Direct unit tests for `WishlistStore.execute_read` covering rollback on normal exit, rollback on exception, and non-blocking concurrency against an active `BEGIN IMMEDIATE` transaction.
  - Direct unit tests for `ensure_private_bot_user` covering all guard conditions, pre-resolved `user_record` handling, and timestamp normalization cases.
- **Out of Scope**:
  - Production behavior changes to `WishlistStore.execute_read` (e.g., `PRAGMA query_only` hardening or `SQLITE_BUSY` retry policies — tracked separately in `WISHENKA-254`).
  - Refactoring duplicate clock helpers or narrowing dependency type protocols (tracked separately in `WISHENKA-255`).
  - Query consolidation in `collect_diagnostic_context` (tracked separately in `WISHENKA-256`).
- **Constraints**:
  - Tests must be deterministic, isolated, and adhere to project testing standards (including bounded execution timeouts).
  - Production code should remain unchanged unless a defect in the documented contract is uncovered by the new tests.

## Q&A

1. **Q: Why is this task needed if the features already work in `WISHENKA-182`?**
   **A:** Existing tests in `WISHENKA-182` only exercise `execute_read` and `ensure_private_bot_user` indirectly via higher-level support flows. Direct unit tests are needed to guarantee that rollback semantics, WAL concurrency, guard clauses, and clock normalization cannot silently break in future changes (especially ahead of follow-up refactorings in `WISHENKA-254` and `WISHENKA-255`).
2. **Q: Should `execute_read` be modified to enforce `PRAGMA query_only` or retry on `SQLITE_BUSY` as part of this task?**
   **A:** No. Those enhancements are tracked separately in `WISHENKA-254`. This task strictly covers testing the existing contract of `WishlistStore.execute_read`.
3. **Q: Should `ensure_private_bot_user` be refactored to share clock helpers or use a `Protocol`?**
   **A:** No. That refactoring is tracked separately in `WISHENKA-255`.
