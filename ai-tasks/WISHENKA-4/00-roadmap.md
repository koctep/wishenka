# Roadmap: WISHENKA-4

## Task Metadata

- **Implementation language**: Python (FastAPI + aiogram v3 + Jinja2 + HTMX)

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - [x] Document business requirements and acceptance criteria for Telegram WebApp initData validation, session management, and user authentication context: `ai-tasks/WISHENKA-4/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - [x] Design Telegram WebApp initData cryptographic validator (HMAC-SHA256, constant-time comparison, auth_date expiration)
  - [x] Design stateless session token serializer & cookie manager (HttpOnly, Secure, SameSite=None, dual-mode cookie + Bearer)
  - [x] Design FastAPI dependencies (`get_current_user`, `get_optional_current_user`) and auth endpoint `/api/auth/telegram`
  - [x] Formulate failing repro test plan for Step 3 in `ai-tasks/WISHENKA-4/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - [x] Create red failing repro tests in `tests/test_auth.py` verifying Telegram initData validation, session token issuance, and protected endpoint access controls
- [x] **STEP 4: Development**
  - [x] Configure auth settings in `wishenka/config.py` (bot_token, secret_key, session_secret_key, session_cookie_name, session_ttl_seconds, etc.)
  - [x] Implement domain models and exceptions in `wishenka/auth/models.py` (`TelegramUser`, `TelegramInitData`, `SessionClaims`, `AuthenticatedUser`, `TelegramAuthRequest`, `AuthResponse`, and custom validation errors)
  - [x] Implement HMAC-SHA256 Telegram WebApp `initData` parser and validator with constant-time comparison and expiration checks in `wishenka/auth/init_data.py`
  - [x] Implement stateless signed token service and cookie helpers in `wishenka/auth/session.py`
  - [x] Implement FastAPI authentication dependencies (`get_current_user`, `get_optional_current_user`) in `wishenka/auth/dependencies.py` supporting dual cookie/bearer mode
  - [x] Expose authentication API in `wishenka/auth/__init__.py`
  - [x] Implement authentication router (`POST /api/auth/telegram`, `POST /api/auth/logout`, `GET /api/auth/me`) in `wishenka/web/routes/auth.py` and mount in `wishenka/web/app.py`
  - [x] Verify that Step 3 repro tests in `tests/test_auth.py` turn green and pass all Quality Gate checks (`make check`)
- [x] **STEP 5: Code Cleanup**
  - [x] Code formatting, static type checking, unused import auditing, test timeout checks: `ai-tasks/WISHENKA-4/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - [x] Structured authentication logging and audit events: `ai-tasks/WISHENKA-4/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - [x] Analyzed technical debt and planned follow-up tasks: `ai-tasks/WISHENKA-4/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-4/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-4/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-4/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-4/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-4/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/auth.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
