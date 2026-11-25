# Roadmap: WISHENKA-228

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-228/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-228/20-architecture.md`
  - Decision: count `HEAD` with `GET` in `match_public_link_route` only. Do not rewrite
    `HEAD` into `GET`. Lock `X-Real-IP` and `request.client is None` with tests; those
    branches already exist in `resolve_client_ip`.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_public_link_rate_limit.py` — red HEAD allowance on `/share/{token}` and
    `/invite/{token}`; locks trusted `X-Real-IP` and the shared unknown-visitor allowance
- [x] **STEP 4: Development**
  - [x] Count `HEAD` with `GET` in `match_public_link_route` for `/share/{token}` and
    `/invite/{token}`. In-budget `HEAD` still reaches the router. Over-limit `HEAD` is
    `429` before routing.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-228/40-code-cleanup.md`
  - `make analyze` clean. No production edits. In-scope tests: 22 passed.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-228/50-observability.md`
  - No new log event. Over-limit `HEAD` already emits `public_link_rate_limited`
    with `method=HEAD` and a token-free route template, and request completion
    logs record `status_code=429`.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-228/60-tech-debt.md`
  - No new debt blocks close. Pre-existing suite failures stay on the issues
    already filed. No user-facing doc names the limited methods. The route
    list in `doc/dev/wishlists.md` still omits `HEAD`; Step 8 owns that file.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md` — public-link limiter counts `HEAD` with `GET` on
    `/share/{token}` and `/invite/{token}`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-228/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-228/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_public_link_rate_limit.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-228/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-228/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-228/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/wishlists.md` — Public Link Rate Limiting: `HEAD` shares the `GET` bucket
  on `/share/{token}` and `/invite/{token}`. In-budget `HEAD` stays `HEAD` (`405`
  when the router has no `HEAD` handler). Over-limit `HEAD` is a token-free `429`
  before routing, logged as `public_link_rate_limited` with `method=HEAD`.
  `POST /invite/{token}/join` is unchanged. Leading-slash stripping applies to
  `HEAD` the same way as `GET`.

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
