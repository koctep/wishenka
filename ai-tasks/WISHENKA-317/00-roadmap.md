# Roadmap: WISHENKA-317

## Task Metadata

- **Implementation language**: JavaScript, Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-317/10-requirements.md`: when a deleted wishlist can no
    longer be restored, the owner is told on the home screen and focus lands
    there. The delete confirmation's Cancel has its own accessible name in
    Russian and English. Interface and browser coverage is part of the work.
    Not a blocker for other work.
  - Implementation language determined and recorded above.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-317/20-architecture.md`: a 410 delete returns to the
    home screen, puts the existing failure in `#status`, exposes that same
    text as the home heading's description, and focuses the heading. The
    delete Cancel gets its own accessible name in Russian and English. The
    settings Cancel is unchanged. The Step 3 failing-repro plan is included.
- [x] **STEP 3: Failing Repro Test**
  - `tests/test_wishlist_delete_ui.py`: interface checks, Russian and English,
    for the expired return (home heading focused, `aria-describedby="status"`,
    assertive `#status`) and for the delete Cancel accessible name.
  - `tests/test_wishlist_delete_browser.py`: browser checks, Russian and
    English, for that same return (including the accessibility-tree
    description) and for distinct Cancel names.
- [x] **STEP 4: Development**
  - [x] A 410 delete returns home, shows the existing failure, describes the
    home heading with that sentence, and focuses the heading. The delete
    Cancel keeps Cancel / Отмена and takes its accessible name from
    `miniapp.wishlist_delete.cancel_name`. The settings Cancel is unchanged.
    `tests/test_wishlist_delete_ui.py` and
    `tests/test_wishlist_delete_browser.py` are green.
  - [x] Full `make test PYTEST_ARGS='-q --tb=no'`: 2495 passed, 2 skipped,
    26 failed in 247.78s. The 26 are the filed set: WISHENKA-311 (history
    flake, absent from the previous completed suite), WISHENKA-348, 264, 265,
    220, 235, 245, 232, 298, 267, and 212. No delete-panel test failed.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-317/40-code-cleanup.md`: `make analyze` passed (Ruff
    check, Ruff format, Mypy) with no warnings. Comment-only cleanup in
    `tests/test_wishlist_delete_ui.py`. Product behavior unchanged. Scoped
    delete modules: 78 passed. Full suite was not re-run; Step 4 recorded
    2495 passed, 2 skipped, 26 failed (filed).
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-317/50-observability.md`: on a 410 delete the owner is
    left with `#status` set to `miniapp.wishlist_delete.failed` (`error`,
    assertive) and that same sentence as the focused home heading's
    description. No new server log. Product code unchanged.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-317/60-tech-debt.md`: C-1, C-2, and T-2 from
    WISHENKA-295 are addressed. The 410 branch focuses the home heading and
    describes it with `#status`. The delete Cancel has
    `miniapp.wishlist_delete.cancel_name`. Both delete test modules keep
    their timeouts (20 and 45). No new follow-up. Developer-doc sentences
    that still describe the old 410 path and the shared Cancel name stay
    for Step 8. Full suite: 2495 passed, 2 skipped, 26 failed, all filed
    and NON-BLOCKER.
- [x] **STEP 8: Dev Docs**
  - `doc/dev/miniapp.md`: a 410 delete returns the owner to the home screen,
    announces `miniapp.wishlist_delete.failed`, and focuses the home heading.
    The delete Cancel keeps "Cancel" / "Отмена" and uses `cancel_name` in both
    languages. The settings Cancel is unchanged. The expired path does not
    emit `wishlist_mutation_committed`; that event means the action returned,
    not that the commit succeeded.
  - `doc/dev/i18n.md`: thirteen `miniapp.wishlist_delete.*` keys, including
    `cancel_name`. The visible `cancel` label still matches settings.
  - `doc/dev/testing.md`: 117 delete tests (57 UI, 21 browser). The 410 focus
    and announcement checks are covered.
  - `tests/test_wishlist_delete_browser.py`: module docstring describes the
    WISHENKA-317 checks as they stand.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-317/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-317/20-architecture.md`

### STEP 3: Failing Repro

- `tests/test_wishlist_delete_ui.py`
- `tests/test_wishlist_delete_browser.py`

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-317/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-317/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-317/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/miniapp.md`
- `doc/dev/i18n.md`
- `doc/dev/testing.md`
- `tests/test_wishlist_delete_browser.py` (module docstring)

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
