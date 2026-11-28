# Roadmap: WISHENKA-298

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-298/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-298/20-architecture.md`
  - No further product change. The two standing checks already pass.
    The anonymous share shows the free remainder. A missing caller is
    logged as `anonymous_gifter` with `is_recipient` false.
    Step 3 is N/A: no behavioral change.
- [x] **STEP 3: Failing Repro Test**
  - [/] N/A — no behavioral change
  - `ai-tasks/WISHENKA-298/30-failing-repro.md`
  - Standing checks re-run: 2 passed, 1 warning in 0.87s (exit 0)
- [x] **STEP 4: Development**
  - [x] No product change. The contract already holds, so
    `project_wish_item`, `WishlistAccessPolicy`, `view_public_share`,
    `item_card.html`, the i18n catalog, and `app.js` stay as they are.
    WISHENKA-356, WISHENKA-357, and WISHENKA-311 stay out of this step.
    Re-ran the two standing checks: 2 passed, 1 warning in 0.85s (exit 0).
    - `tests/test_surprise_role_context.py::test_share_link_visit_creates_no_account`
    - `tests/test_wishlists_htmx_observability.py::test_wishlist_shared_view_observability`
    The warning is `StarletteDeprecationWarning` from `fastapi/testclient.py`.
- [x] **STEP 5: Code Cleanup**
  - No product edit. `make analyze` exit 0: Ruff all checks passed,
    306 files already formatted, Mypy no issues in 306 source files.
  - `ai-tasks/WISHENKA-298/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - No new log. The share-view log already records `is_recipient` false
    for a missing caller, and `public_wishlist_resolved` records
    `projection_mode` `anonymous_gifter`. The secret token is not logged.
  - `ai-tasks/WISHENKA-298/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - No new technical debt. No product change. No new follow-up.
    WISHENKA-356, WISHENKA-357, and WISHENKA-311 stay existing tickets.
  - `ai-tasks/WISHENKA-298/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - No `doc/dev` edit. The pages already say an anonymous share shows the
    free remainder and that a missing caller is not the recipient
    (`anonymous_gifter` on `public_wishlist_resolved`). Nothing still says
    the share hides the remainder or logs the guest as the recipient.
    WISHENKA-356, WISHENKA-357, and WISHENKA-311 stay existing tickets.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-298/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-298/20-architecture.md`

### STEP 3: Failing Repro

- N/A — no behavioral change
- `ai-tasks/WISHENKA-298/30-failing-repro.md`

### STEP 4: Development

- No product change. Standing checks re-run: 2 passed, 1 warning in 0.85s (exit 0).

### STEP 5: Code Cleanup

- No product edit. `make analyze` exit 0: Ruff all checks passed,
  306 files already formatted, Mypy no issues in 306 source files.
- `ai-tasks/WISHENKA-298/40-code-cleanup.md`

### STEP 6: Observability

- No new log. The share-view log already records `is_recipient` false
  for a missing caller, and `public_wishlist_resolved` records
  `projection_mode` `anonymous_gifter`. The secret token is not logged.
- `ai-tasks/WISHENKA-298/50-observability.md`

### STEP 7: Technical Debt

- No new technical debt. No product change. No new follow-up.
  WISHENKA-356, WISHENKA-357, and WISHENKA-311 stay existing tickets.
  User docs under `doc/` were left unchanged.
- `ai-tasks/WISHENKA-298/60-tech-debt.md`

### STEP 8: Dev Docs

- No edit. `doc/dev` already matches the WISHENKA-235 contract: the
  anonymous share shows the free remainder, and a missing caller is logged
  as not the recipient (`anonymous_gifter`). WISHENKA-356, WISHENKA-357,
  and WISHENKA-311 stay existing tickets.

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
