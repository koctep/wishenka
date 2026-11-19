# WISHENKA-178: Technical Debt Analysis

## Shortcuts Taken

1. **Conditional `order_retention_days` forwarding in `wishenka/bot/__main__.py`:**
   - In `wishenka/bot/__main__.py` (`run()` and `cleanup_loop()`), `order_retention_days` is converted to `None` when `settings.bot_capture_order_retention_days == 30`, and `cleanup_loop` branches on `if order_retention_days is None: await cleanup_drafts(store)` vs. passing `order_retention_days=...`.
   - This was done to stay compatible with an existing single-argument `cleanup_drafts` monkeypatch in `tests/test_bot_capture_repro.py` (`async def cleanup(store: WishlistStore) -> int:`).
   - As a side effect, `bot_draft_cleanup_failed` logs `"order_retention_days": None` when using the default 30-day retention.
2. **Direct wall-clock calls in `cleanup_drafts` (`wishenka/bot/capture.py`):**
   - `cleanup_drafts()` reads `datetime.now(UTC)` and `int(time.time())` directly rather than accepting an optional `now` timestamp/clock parameter (unlike `create_capture_router`, which supports `deps.now`). Tests must backdate database rows directly instead of injecting a clock.

## Code Quality Issues

1. **Duplicated magic default `30`:**
   - The default retention of `30` days is repeated across `wishenka/config.py` (`bot_capture_order_retention_days: int = Field(default=30, ge=2)`), `wishenka/bot/capture.py` (`order_retention_days: int = 30`), and `wishenka/bot/__main__.py` (`if settings.bot_capture_order_retention_days == 30`). Defining a shared constant would prevent drift if the default changes.
2. **Hardcoded batch size (`LIMIT 100`) and `86400` seconds-per-day constant:**
   - `cleanup_drafts()` in `wishenka/bot/capture.py` hardcodes `LIMIT 100` for all five cleanup queries and `86400` inline.
3. **Duplicated test harness boilerplate:**
   - `tests/test_bot_capture_order_retention_repro.py` (`_Harness`, `_setup`) and `tests/test_bot_capture_order_retention.py` (`_BotHarness`, `_setup`) duplicate similar `aiogram` `Dispatcher`/`Bot` test setup code.

## Missing Tests

- **Timeout marker check (per `do-testing`):** Both `tests/test_bot_capture_order_retention_repro.py` and `tests/test_bot_capture_order_retention.py` declare `pytestmark = pytest.mark.timeout(30)` at module scope. No missing-timeout blockers.
- **Unverified edge cases:**
  1. `reserve()` redelivery/older `message_id` non-refresh: no explicit test asserts that `bot_capture_order.updated_at` is *not* updated when `excluded.message_id <= bot_capture_order.message_id`.
  2. `cleanup_drafts()` `updated_at IS NULL` fallback: no dedicated test seeds a `NULL` `updated_at` row directly into `bot_capture_order` to exercise the `o.updated_at IS NULL` branch in `cleanup_drafts()` (Alembic backfill prevents `NULL` for migrated rows).
  3. `wishenka/bot/__main__.py:run()` wiring: `Settings.bot_capture_order_retention_days` forwarding from `run()` into `cleanup_loop()` is not exercised by an integration test (only `cleanup_loop()` is tested directly).

## Performance Concerns

- **Single `LIMIT 100` batch per hourly tick:** `cleanup_loop()` runs `cleanup_drafts()` once per `interval=3600` seconds, deleting at most `100` `bot_capture_order` rows per run (max 2,400 rows/day). Under normal traffic this bounds SQLite WAL write-lock duration well, but if a large backlog of stale rows ever accumulates (>2,400/day), draining it will take multiple days unless the batch limit or loop drains until `< 100` rows remain.
- **Correlated `NOT EXISTS` subquery:** `cleanup_drafts()` evaluates `NOT EXISTS (SELECT 1 FROM bot_drafts d WHERE d.owner = o.owner AND d.chat = o.chat AND d.state = 'active' AND d.expires > :now)` for up to 100 rows selected via `idx_bot_capture_order_updated_at`. Bounded by `LIMIT 100`, so impact per pass is minimal.

## Follow-up Tasks

- **Non-blocking:** Extract a shared `DEFAULT_BOT_CAPTURE_ORDER_RETENTION_DAYS = 30` constant, update the `cleanup_drafts` monkeypatch in `tests/test_bot_capture_repro.py` to accept `order_retention_days` (or `**_: Any`), and pass `order_retention_days=settings.bot_capture_order_retention_days` unconditionally in `wishenka/bot/__main__.py` so `bot_draft_cleanup_failed` always logs the numeric retention value. — Jira: [WISHENKA-242](https://pypost.atlassian.net/browse/WISHENKA-242)
- **Non-blocking:** Add unit tests for `reserve()` leaving `updated_at` untouched on older/redelivered `message_id` and for `cleanup_drafts()` handling `updated_at IS NULL` when no active draft exists. — Jira: [WISHENKA-241](https://pypost.atlassian.net/browse/WISHENKA-241)
