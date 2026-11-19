# WISHENKA-156: Technical Debt Analysis

## Shortcuts Taken

- **Happy-path-only multi-process worker race (`tests/test_notice_worker_concurrency.py`):**
  - `_seed_pending_notices` creates `_GIVER_COUNT = 10` distinct givers (`_BASE_GIVER_ID = 2001..2010`) so `notice_chat_interval_seconds` (minimum `1`s per `chat_id`) does not defer claims, and `_drain_in_process` uses `FakeNoticeSender(sleep=0.01)`.
  - This intentionally exercises cross-process SQLite WAL `BEGIN IMMEDIATE` serialization on `claim_next` -> `refresh_claim` -> `complete`, but does not exercise multi-process contention on `reschedule`, `fail`, `uncertain`, or stale-claim takeover (`reclaim_after`).
- **Live Telegram smoke tests not executed in offline CI (`tests/test_telegram_notice_smoke.py`):**
  - `test_telegram_smoke_delivers_plain_text_with_special_chars_and_truncation` and `test_telegram_smoke_rejects_invalid_chat` are `skipif`-gated on `WISHENKA_TELEGRAM_SMOKE_TOKEN` and `WISHENKA_TELEGRAM_SMOKE_CHAT_ID`. In offline runs they are skipped (`2 passed, 2 skipped` in Step 5), so real Bot API execution remains an operator-triggered pre-release check.
  - The positive smoke test hardcodes `locale="ru"` rather than parameterizing across supported locales (e.g., `"en"`).

## Code Quality Issues

- **Tight child-process join timeout headroom (`tests/test_notice_worker_concurrency.py`):**
  - `pytestmark = pytest.mark.timeout(120)` allows 120s for the test, yet `_BARRIER_TIMEOUT = 10` and `_JOIN_TIMEOUT = 15` are significantly tighter than the sibling spawned-process race test `tests/test_receipt_concurrency.py` (`_BARRIER_TIMEOUT = 20`, `_JOIN_TIMEOUT = 25`, `pytestmark = pytest.mark.timeout(120)`).
  - As observed in Step 5 (`ai-tasks/WISHENKA-156/40-code-cleanup.md`), running `tests/test_notice_worker_concurrency.py` while `make analyze` was running concurrently caused `test_two_spawned_worker_processes_claim_and_deliver_once` to fail on `assert not proc.is_alive()` after `_JOIN_TIMEOUT = 15` seconds, whereas running it in isolation passed in `39.43s`. Under heavy `pytest-xdist` parallel load in `make test`, `15s` leaves little headroom for `multiprocessing.get_context("spawn")` child interpreter startup and SQLite WAL initialization.
- **Repeated sender setup/teardown boilerplate (`tests/test_telegram_notice_smoke.py`):**
  - `test_telegram_smoke_delivers_plain_text_with_special_chars_and_truncation` and `test_telegram_smoke_rejects_invalid_chat` duplicate the `_smoke_credentials()` -> `Settings(...)` -> `build_sender(...)` -> `try/finally: await sender.close()` lifecycle block. Extracting a small async context manager helper would keep both tests concise.
- **Timeout marker compliance (`do-testing` check):**
  - Both `tests/test_telegram_notice_smoke.py` (`pytest.mark.timeout(60)`) and `tests/test_notice_worker_concurrency.py` (`pytest.mark.timeout(120)`) declare explicit module-level `pytestmark` timeouts. No `do-testing` blocker present.

## Missing Tests

- **Live Telegram Bot API execution:** `test_telegram_smoke_delivers_plain_text_with_special_chars_and_truncation` and `test_telegram_smoke_rejects_invalid_chat` have not been executed against a live Telegram bot token in this environment (skipped without `WISHENKA_TELEGRAM_SMOKE_TOKEN` / `WISHENKA_TELEGRAM_SMOKE_CHAT_ID`).
- **Multi-process failure/reclaim paths:** No spawned-process race test covers two OS processes racing on stale-claim recovery (`reclaim_after`) or `SendOutcome.AMBIGUOUS` / `SendOutcome.RETRYABLE` settlement (covered only in single-process tests).

## Performance Concerns

- **Spawned-process race test duration:** `tests/test_notice_worker_concurrency.py` took `39.43s` in isolation (driven by Alembic migrations during DB seeding and two `spawn` child processes). Under concurrent CPU load (e.g., `pytest -n auto`), `_JOIN_TIMEOUT = 15` risks transient timeout failures.

## Follow-up Tasks

- **T1 (`NON-BLOCKER` — Test Reliability):** Increase `_JOIN_TIMEOUT` (e.g. `15` -> `25`–`30`s) and `_BARRIER_TIMEOUT` (e.g. `10` -> `20`s) in `tests/test_notice_worker_concurrency.py` to match `tests/test_receipt_concurrency.py` and prevent `SpawnProcess` timeout flakes under `pytest-xdist` CPU contention. — Jira: [WISHENKA-244](https://pypost.atlassian.net/browse/WISHENKA-244)
- **T2 (`NON-BLOCKER` — Test Maintainability):** Extract a small async context-manager helper in `tests/test_telegram_notice_smoke.py` for `Settings` + `build_sender` + `await sender.close()` cleanup. — Jira: [WISHENKA-243](https://pypost.atlassian.net/browse/WISHENKA-243)
- **T3 (`NON-BLOCKER` — Pre-Release Verification):** Run `.venv/bin/pytest -m telegram_smoke` with real `WISHENKA_TELEGRAM_SMOKE_TOKEN` and `WISHENKA_TELEGRAM_SMOKE_CHAT_ID` and complete the manual checklist in `doc/dev/notifications.md` prior to release.
