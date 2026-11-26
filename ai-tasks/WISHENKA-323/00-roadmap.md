# Roadmap: WISHENKA-323

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-323/10-requirements.md`: one set of wishlist rules for
    Mini App screens. Access, share notices, link uniqueness, and what a
    viewer is shown are not kept in two copies. Screens no longer prefer an
    attached older in-memory capability over the path real requests already
    use. Person-facing outcomes stay those of that real path. Sibling debt
    (history lookup cost, receipt-screen storage lookup, busy-storage retry,
    extra collision checks) stays out of scope.
  - Implementation language determined and recorded above.
  - Correction: one rule set covers every duplicated wishlist action (lists,
    wishes, membership, archive, delete, restore, favorites, viewing history,
    and invite join). Screens follow the product people already use and do
    not prefer a second copy. Checks prove the same person-facing results on
    the path a real Mini App request already uses. Reservation and receipt
    outcomes stay, a repeat does not apply twice, and they do not gain a
    second copy. Where a shared rule disagrees, the Mini App outcome a person
    already gets stands, including for bot capture. WISHENKA-324 stays the
    separate receipt-screen reach to wishlist data, not that preference.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-323/20-architecture.md`: `RepoWishlistOps` is the only
    shared wishlist rule set. Screens stop reading `app.state.wishlist_service`.
    Store-backed shared methods forward through `WishlistStore.run_repository`.
    Bot capture save uses that path so the snapshot diff cannot apply a second
    add. Reservation and receipt rules stay on `execute_wish`. Step 3 red
    tests are specified in that document and are not written yet.
  - Correction: store-backed shared methods return a `run_repository` forward
    and do not enter `execute` or `_write`. Removing a name from
    `_SINGLE_WISHLIST_METHODS` only drops the wishlist id; methods already
    outside that set still snapshot. `update_wishlist_settings` and
    `transfer_ownership` stay on the snapshot wrapper. Screen removal also
    covers the receipt-UI idempotent-replay skip and the
    `complete_reservation` delivery-lock skip. `run_repository` receives the
    `WishlistRepository` it constructs and flushes that instance after commit.
    `receipts_ui._repo_ctx` stays with WISHENKA-324.
  - Correction: `update_wishlist_settings` and `transfer_ownership` look up
    the hydrated wishlist through a private in-memory method. The class
    wrapper does not replace that method. Public `get_wishlist_by_id` still
    forwards through `run_repository` and does not enter `execute` or
    `_write`. When `_store` is None, that public method still fails closed.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishenka_323_one_wishlist_rule_set.py`: screens still prefer
    `app.state.wishlist_service`; a store-backed `record_view` drops an older
    history row; capture save does not call `RepoWishlistOps.add_wish_item`.
- [x] **STEP 4: Development**
  - [x] Shared store-backed actions go through `WishlistStore.run_repository`; screens and capture no longer prefer `app.state.wishlist_service` or the snapshot write.
  - [x] In-memory bodies stay for a service with no store. Public `get_wishlist_by_id` fail-closes there so snapshot code uses `_lookup_wishlist`.
  - [x] Screen, history, capture, and token tests follow the repository outcome. Settings and transfer still hydrate one wishlist.
  - Correction: shared public methods fail closed on an in-memory service and no longer keep a second rule body. An idempotent receipt UI response reads the list and the viewer through the repository after the wish mutation. Lifecycle and history checks follow that repository outcome or the fail-closed path.
  - Correction: a public-link reservation resolves the loaded list inside the wish transaction. Reservation, archive, favorite, and history checks use the repository outcome or an in-memory inventory graph.
  - Correction: shared actions are no longer invoked on the hydrated service inside `execute`. Seeds and other callers use a store-backed `WishlistService` or `RepoWishlistOps` inside `run_repository`. Inventory callbacks stay on `execute`.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-323/40-code-cleanup.md`: removed three unused
    `WishlistService` helpers. Analyze is clean. The task repro tests pass.
    The full suite still has the filed WISHENKA-232 failure and other
    failures outside this cleanup.
  - Correction: callers that still ran a shared action on the hydrated
    service inside `execute`, or on an in-memory service, now use the
    store-backed `WishlistService`. Inventory callbacks stay on `execute`.
    Recording a view skips a visitor who has no `users` row, so a share or
    public view is not aborted by that foreign key. Step 5 was accepted after review.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-323/50-observability.md`: screen and capture actions
    keep the repository events they already emit. An in-memory shared action
    logs `wishlist_repository_path_required` and does not include arguments.
    No metrics system was added.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-323/60-tech-debt.md`: no blockers. Two new follow-ups
    (shared-method set lock, Medium; missing-user history skip, Low) have no
    Jira key yet. Sibling debt stays on WISHENKA-324, WISHENKA-325,
    WISHENKA-326, and WISHENKA-327. Pre-existing failures are recorded,
    including the cookie test with no Jira key. Developer docs stay for
    Step 8.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/wishlists.md`: `RepoWishlistOps` is the only shared rule set.
    Store-backed `WishlistService` forwards those names through
    `WishlistStore.run_repository` (commit, then flush on that repository).
    Screens use the request repository. In-memory shared methods fail closed
    with `wishlist_repository_path_required`; settings and transfer use
    `_lookup_wishlist`. `record_view` does not drop older rows. A visitor
    with no `users` row logs `view_history_user_missing` and the share page
    still renders. Capture save calls `RepoWishlistOps.add_wish_item` inside
    `run_repository`. Reservations and receipts stay on `execute_wish`.
    `receipts_ui._repo_ctx` stays with WISHENKA-324.
  - Correction: item and reservation samples set up lists and wishes with `RepoWishlistOps` inside `run_repository`; public share screens resolve on the request repository.
  - Also aligned: `doc/dev/architecture.md`, `doc/dev/miniapp.md`,
    `doc/dev/items.md`, `doc/dev/reservations.md`, `doc/dev/idempotency.md`,
    `doc/dev/bot-scenarios.md`, `doc/dev/testing.md`, `doc/dev/gift-receipt.md`.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-323/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-323/20-architecture.md`

### STEP 3: Failing Repro

- Automated red test(s) under `tests/` (or N/A note in roadmap)

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-323/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-323/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-323/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
