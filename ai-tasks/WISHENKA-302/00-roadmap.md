# Roadmap: WISHENKA-302

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-302/00-roadmap.md`
  - `ai-tasks/WISHENKA-302/10-requirements.md`
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-302/20-architecture.md`
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_favorites_access_control.py`
- [x] **STEP 4: Development**
  - [x] Added `ShareAccessRow` (`wl_share_access`) in `wishenka/wishlists/db_models.py` and Alembic migration `wishenka/wishlists/alembic/versions/add_share_access_and_purge_favorites.py` (with reversible schema downgrade and irreversible purge of legacy non-member `wl_favorites` rows).
  - [x] Added `ShareAccessGrant` in `wishenka/wishlists/models.py` and updated `WishlistAccessPolicy.can_favorite` in `wishenka/wishlists/policy.py` to require membership or valid active share-link access.
  - [x] Implemented `wl_share_access` persistence, access-filtered favorites listing, revocation helpers, and scoped `_load_wish`/`_persist_wish` support in `wishenka/wishlists/repository.py`, `wishenka/wishlists/store.py`, and `wishenka/wishlists/deletion.py`.
  - [x] Enforced Favorites access control, share-access grants on `get_wishlist_by_public_token`, revocation on `remove_member` / `regenerate_public_token` / `transfer_ownership` / `restore_deleted_wishlist`, and uniform 404 anti-enumeration in `wishenka/wishlists/repo_ops.py`, `wishenka/wishlists/service.py`, and `wishenka/web/routes/wishlists.py`.
  - [x] Updated affected tests and added comprehensive tests in `tests/test_favorites_access_control.py` covering stranger denial, legacy row filtering, participant access, giver share-link access via view and reservation (`execute_wish_idempotent`), revocation on member removal/token rotation/restore/transfer, and migration upgrade/downgrade.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-302/40-code-cleanup.md`
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-302/50-observability.md`
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-302/60-tech-debt.md`
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md`
  - `doc/dev/migrations.md`
  - `doc/dev/infrastructure.md`
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-302/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-302/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-302/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-302/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-302/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
