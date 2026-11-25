# Roadmap: WISHENKA-303

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-303/00-roadmap.md`
  - `ai-tasks/WISHENKA-303/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-303/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_history_access_control.py`
- [x] **STEP 4: Development**
  - [x] Implemented `WishlistAccessPolicy.can_view_history`, SQL-scoped `WishlistRepository.list_view_history`, `delete_non_member_history`, and `delete_history_if_no_share_access`
  - [x] Enforced `can_view_history` in `RepoWishlistOps` and `WishlistService` (`record_view`, `get_history`, and revocation on `remove_member`, `regenerate_public_token`, `restore_deleted_wishlist`, `transfer_ownership`), and auto-recorded authenticated share-link visits in `wishenka/web/routes/wishlists.py` and `wishenka/web/routes/sharing.py`
  - [x] Added one-way Alembic migration `purge_legacy_non_member_view_history` (`ROLLBACK_POLICY = "one-way"`) purging unverified non-member `wl_view_history` rows
  - [x] Expanded `tests/test_history_access_control.py` and updated affected tests; `make analyze` and targeted tests pass
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-303/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-303/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-303/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md` — Viewing History access model (overview, architecture, usage, configuration, troubleshooting)
  - `doc/dev/migrations.md` — `purge_legacy_non_member_view_history` head revision and one-way downgrade
  - `doc/dev/miniapp.md` — history screen contract aligned with the access model
  - `doc/dev/architecture.md` — pointer to the viewing-history access section
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-303/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-303/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-303/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-303/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-303/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/wishlists.md`
- `doc/dev/migrations.md`
- `doc/dev/miniapp.md`
- `doc/dev/architecture.md`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
