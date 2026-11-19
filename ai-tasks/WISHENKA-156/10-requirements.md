# WISHENKA-156: Opt-in Real Telegram Smoke Test and Multi-Process Notice Worker Race Test

Programming language for implementation: **Python 3.12+** (see `00-roadmap.md`).

Source context: follow-up item **T2** from `ai-tasks/WISHENKA-23/60-tech-debt.md`.

## Goals

Why this task is needed:

1. **Confidence in real Telegram notification delivery.** Gift-receipt notifications to givers are currently verified only against a simulated (mocked) Telegram client. Without a repeatable way to verify against the real Telegram service, configuration issues, formatting/escaping mistakes, message-length limits, or real network/error-handling mismatches could go undetected until production.
2. **Confidence in multi-process notification coordination.** In production, multiple application processes can run side by side and compete for the same queued gift-receipt notifications. Currently, concurrent claiming of queued notifications is verified only within a single process. Without a true multi-process contention check, process-level locking or coordination defects could cause duplicate notifications to givers or stalled deliveries.
3. **Safe, non-blocking test runs by default.** Standard automated test runs in CI and local development must remain fast, offline, and deterministic, running without real Telegram credentials while still allowing operators and developers to run live verification on demand.

## User Stories

- **As a developer / QA engineer**, I want an opt-in smoke test that sends a real gift-receipt notification through Telegram when valid credentials are provided, and is automatically skipped otherwise, so that I can verify real delivery before release without breaking offline CI runs.
- **As a QA engineer / operator**, I want a concise manual verification checklist for real Telegram delivery, so that I can consistently check aspects that require human or live-environment inspection (such as message appearance in a real chat, plain-text rendering of special characters, and behavior with invalid/unreachable targets).
- **As a developer / operator**, I want an automated test where two separate worker processes concurrently compete for the same queued notifications, so that I can be confident each queued notification is claimed and delivered once without cross-process interference.

## Task Description

### Problem

Following the implementation of gift-receipt notifications (WISHENKA-23), two verification gaps remain:

1. **Real Telegram sender path is unverified end-to-end:** token handling, plain-text delivery without formatting parse mode, handling of special characters (such as HTML-like characters) and long wish titles, and real error/timeout classification against Telegram are only covered with mocks.
2. **Multi-process worker claim race is verified only indirectly:** contention between two workers for the same queued notification rows has only been exercised in a single process, whereas production deployments may run multiple concurrent processes sharing the same persistent storage.

### Scope

#### In Scope

- **FR-1: Opt-in real Telegram smoke test**
  - Verify real notification delivery to a configured Telegram chat using real bot credentials.
  - Skip cleanly and automatically during standard test runs when real credentials are not provided.
  - Cover both successful delivery of a realistic gift-receipt notification (including special characters and title truncation boundaries) and expected rejection/error handling when targeting an invalid or unreachable chat (or equivalent safe negative check) if feasible without harming real users.
- **FR-2: Manual verification checklist**
  - Provide a clear, repeatable manual checklist for verifying live Telegram notification behavior (setup prerequisites, positive delivery check, special-character/plain-text check, error-handling check, and cleanup/safety notes so real users are never spammed).
- **FR-3: Multi-process notice-worker race test**
  - Spawn two independent OS processes that concurrently run notice workers against the same shared queue/storage containing pending notifications.
  - Verify that across both processes, every eligible notification is claimed and processed without duplicate delivery, lost rows, or unhandled database-lock failures.

#### Out of Scope

- Changing production notification business logic, message templates, or delivery semantics (unless a defect is uncovered by the new multi-process test, which would be handled separately or noted).
- Continuous/scheduled execution of live Telegram tests in offline CI without opt-in credentials.
- Multi-host distributed coordination beyond single-host multi-process shared storage.
- Observability/log-contract hardening items (covered by WISHENKA-157) and code-splitting refactors (covered by WISHENKA-158).

### Constraints & Assumptions

- **Safety & Privacy:** The opt-in live test must only send messages to an explicit test chat/recipient configured by the person running it, never to real users. Credentials must never be committed to the repository.
- **Default Suite Compatibility:** The default automated test suite must remain green and fast without network access or Telegram credentials; the opt-in smoke test must be skipped cleanly when unconfigured.
- **Bounded Execution:** All automated tests (including the multi-process race test and the opt-in smoke test) must have bounded execution times and clean up spawned processes and temporary data.
- **Main Business Entities:**
  - *Gift-Receipt Notification* — a queued message informing a giver that a promised wish was received.
  - *Notification Worker* — an independent worker instance that claims due notifications and dispatches them.
  - *Test Credentials / Target Chat* — opt-in configuration supplied by the operator/developer to authorize live Telegram verification.

## Definition of Done

1. An opt-in automated smoke test exists for real Telegram notification delivery and is skipped automatically when credentials are not configured (verified in the default test run).
2. The opt-in smoke test passes when run with valid test credentials and a target chat (or its execution path and skip behavior are verified).
3. A manual verification checklist is documented for live Telegram notification checks.
4. An automated multi-process race test exists where two separate worker processes concurrently claim and process the same queued notifications, asserting no duplicate deliveries, no lost notifications, and consistent final queue state.
5. The full automated test suite and repository quality checks pass without regressions.

## Q&A

- **Q1: Why is this task needed if unit tests already pass?**
  - **A:** Unit tests mock the Telegram client and run workers in a single process. Real Telegram API behavior (token validation, plain-text escaping, error responses) and real OS-process file/database locking during concurrent claims are not exercised by those unit tests (`ai-tasks/WISHENKA-23/60-tech-debt.md`, Missing Tests).
- **Q2: Will the live Telegram test break CI or local runs without internet/tokens?**
  - **A:** No. It is strictly opt-in and must be skipped automatically when the required test credentials are absent.
- **Q3: Does this task change how notifications are formatted or sent in production?**
  - **A:** No. This task adds verification infrastructure (opt-in smoke test, manual checklist, and multi-process race test) for existing behavior.
