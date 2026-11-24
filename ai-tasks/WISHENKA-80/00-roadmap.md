# Roadmap: WISHENKA-80

## Task Metadata

- **Implementation language**: python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-80/00-roadmap.md` — roadmap initialized, implementation language set (`python`)
  - `ai-tasks/WISHENKA-80/10-requirements.md` — business goals, user stories, functional/non-functional requirements, domain entities, and acceptance criteria documented
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-80/20-architecture.md` — architecture design, module diagram, dependency provider contract, repository extensions, and Step 3 failing-repro plan documented
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_web_repository_di_repro.py` — red repro tests verifying `wishenka.web.dependencies.get_wishlist_repository` contract and asserting representative endpoints across `wishlists.py`, `items.py`, `sharing.py`, `receipts.py`, `items_ui.py`, and `receipts_ui.py` do not call `WishlistStore.execute` / `WishlistStore._read`
- [x] **STEP 4: Development**
  - [x] Iteration 1: Created `wishenka/web/dependencies.py` (`get_wishlist_store`, `get_wishlist_repository`, `WishlistRepo` `Annotated[..., Depends(...)]`) and moved `TokenCollision` to `wishenka/wishlists/exceptions.py` (re-exported in `store.py`).
  - [x] Iteration 2: Extended `WishlistRepository` in `wishenka/wishlists/repository.py` with targeted ID allocation (`_allocate_id` via `wl_counters`), `create_wishlist`, `rotate_public_token`, `rotate_invite_token`, `list_accessible_wishlists`, `list_deleted_by_owner`, `upsert_member`, `delete_member`, `update_member_role`, `create_item`, `reorder_items`, `list_item_receipts`, `list_receipts_for_wishlist`, `is_favorite`, `list_favorite_ids`, `list_favorite_wishlists`, and created `wishenka/wishlists/repo_ops.py` (`RepoWishlistOps`) for targeted domain operations with `EventProducer` outbox integration.
  - [x] Iteration 3: Migrated `wishenka/web/routes/` (`sharing.py`, `receipts.py`, `items.py`, `wishlists.py`, `items_ui.py`, `receipts_ui.py`) to inject `WishlistRepo` via `Depends(get_wishlist_repository)` and eliminate all `WishlistStore.execute(...)` calls while preserving `execute_wish` / `execute_wish_idempotent` and `app.state.wishlist_service` test compatibility.
  - [x] Iteration 4: Verified `tests/test_web_repository_di_repro.py` (10/10 passed; updated `receipt` repro case user from non-member 202 to owner 101 so it exercises the 200 OK path), `ruff check`, and `mypy` on production modules.
  - [x] Iteration 5: Fixed WISHENKA-80 regressions: added `SQLAlchemyError` sanitization in `wishenka/web/dependencies.py` (`get_wishlist_repository`) and updated `test_storage_error_traceback_does_not_expose_tokens`; returned `removed_count` from `WishlistRepository.clear_view_history` and logged it in `RepoWishlistOps.clear_history`; emitted `favorite_own_wishlist_denied` / `favorite_deleted_wishlist_denied` on `wishenka.web.wishlists` in `wishlists.py`; emitted `wish_archive_refused` in `RepoWishlistOps.archive_wish_item` / `restore_wish_item`; separated single-item mutation from full-wishlist read in `receipts_ui.py` (`_execute_receipt_mutation_ui`, `correct_receipt_ui`, `cancel_receipt_ui`).
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-80/40-code-cleanup.md` — ran `ruff check`, `ruff format`, `mypy`, timeout-marker & conflict/debug-print checks on all 17 WISHENKA-80 files (6 files reformatted; `ruff check`, `ruff format --check`, and `mypy` all pass)
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-80/50-observability.md` — audited logging & token/PII sanitization across DI, repository, `RepoWishlistOps`, and web routes; added missing structured logs in `dependencies.py`, `repository.py`, and `repo_ops.py`; fixed `is_recipient` logging for anonymous guests in `sharing.py` (`134 passed` across DI repro & observability suites)
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-80/60-tech-debt.md` — documented shortcuts (`RepoWishlistOps` adapter, `app.state.wishlist_service` test fallbacks, `receipts_ui.py` `_repo_ctx` fallback, generic `SQLAlchemyError` mapping), code quality/duplication notes, N+1 `get_history` performance concern, follow-up tasks, and pre-existing Jira-linked failures (`WISHENKA-245`, `WISHENKA-232`, `WISHENKA-264`, `WISHENKA-235`, `WISHENKA-298`, `WISHENKA-220`, `WISHENKA-265`, `WISHENKA-267`)
- [x] **STEP 8: Dev Docs**
  - `doc/dev/architecture.md` — documented `wishenka/web/dependencies.py` (`get_wishlist_repository`, `WishlistRepo`) DI pattern and `RepoWishlistOps` / `WishlistRepository` usage in `wishenka/web/routes/`
  - `doc/dev/wishlists.md` — updated storage overview and added `Web Route DI & RepoWishlistOps (WISHENKA-80)` section covering `get_wishlist_store`, `get_wishlist_repository`, `WishlistRepo`, `RepoWishlistOps`, and route integration
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-80/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-80/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-80/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-80/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-80/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
