# Roadmap: WISHENKA-88

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-88/10-requirements.md` — documented business goals, user stories, Definition of Done, scope, functional/non-functional requirements, and business entities for public-link rate limiting (`/share/{token}`, `/invite/{token}`, `/invite/{token}/join`).
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-88/20-architecture.md` — high-level architecture, module interfaces, sliding-window rate limiter design, middleware placement, configuration, and Step 3 failing repro plan.
- [x] **STEP 3: Failing Repro Test**
  - [ ] `tests/test_public_link_rate_limit.py`
- [x] **STEP 4: Development**
  - [x] Iteration 1: Added `public_rate_limit_*` settings to `wishenka/config.py` and `web.rate_limit.title` / `web.rate_limit.message` (EN/RU) keys to `wishenka/i18n/catalog.py`.
  - [x] Iteration 2: Implemented `RateLimitDecision`, `SlidingWindowRateLimiter`, `match_public_link_route`, `resolve_client_ip`, and `PublicLinkRateLimitMiddleware` in `wishenka/web/rate_limit.py`.
  - [x] Iteration 3: Wired `app.state.public_link_rate_limiter` and `PublicLinkRateLimitMiddleware` into `wishenka/web/app.py` (between `RequestLoggingMiddleware` and route handlers).
  - [x] Iteration 4: Verified all 6 Step 3 tests pass and added unit/integration tests in `tests/test_public_link_rate_limit.py` for bounded `max_clients` eviction, localized RU/EN 429 responses, disabled rate limiting, and `Settings` validation.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-88/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-88/50-observability.md` — verified `public_link_rate_limited` structured warning log in `wishenka/web/rate_limit.py` (`route`, `method`, `client_ip`, `retry_after`, zero token leakage) and added `caplog` observability test in `tests/test_public_link_rate_limit.py`.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-88/60-tech-debt.md` — documented trade-offs (in-memory single-process store, inline HTML 429, `HEAD` bypass edge case, leftmost `X-Forwarded-For`, unthrottled `/api/public/wishlists/*`), missing unit-test edge cases, `O(max_clients)` eviction scan, and follow-up tasks.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md` — documented `PublicLinkRateLimitMiddleware` & `SlidingWindowRateLimiter` (`wishenka/web/rate_limit.py`), protected routes (`GET /share/{token}`, `GET /invite/{token}`, `POST /invite/{token}/join`), `429` + `Retry-After` + localized RU/EN safe body, `X-Forwarded-For` trust gating, `public_rate_limit_*` settings in `wishenka/config.py`, `public_link_rate_limited` audit event, and troubleshooting.
  - `doc/dev/architecture.md` — updated `doc/dev/wishlists.md` subsystem summary to reference public-link rate limiting (`PublicLinkRateLimitMiddleware`).
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-88/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-88/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-88/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-88/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-88/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
