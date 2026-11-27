# Roadmap: WISHENKA-264

## Task Metadata

- **Implementation language**: Python

## Step Status

- [x] **STEP 1: Requirements Gathering and Documentation**
  - `ai-tasks/WISHENKA-264/10-requirements.md`
  - Opening archive confirmation and confirming archive must answer the four
    refusals with the existing HTML list notice. An archived wishlist is
    status 409 and `web.item.archived_wishlist_error`. An unknown wishlist,
    a non-member, and an unknown wish are each status 404 and
    `web.item.resource_not_found`. A missing wish writes «Желание или
    вишлист больше недоступны.» into `#list-notice` and closes the dialog.
    The page swaps that fragment and clears the error flag, so
    `htmx:responseError` does not fire. `{"detail": ...}` stays the contract
    for reorder, move, and restore. The eight archive nodes in
    `tests/test_items_ui_error_mapping.py` still call `resp.json()` and fail
    on the fragment.
  - Correction: an earlier blurb required detail "Wishlist is archived" and
    detail "Resource not found" as the archive response. That JSON shape is
    not the acceptance criterion for these two archive actions.
- [x] **STEP 2: High-Level Architecture Design**
  - `ai-tasks/WISHENKA-264/20-architecture.md`
  - Both archive actions already return the HTML list notice for all four
    refusals. Routes, catalog, `app.js`, and reorder, move, and restore
    stay unchanged. The only edit is the eight archive nodes in
    `tests/test_items_ui_error_mapping.py`: assert that notice and status
    with `Accept-Language: ru`, and do not call `resp.json()`.
  - Step 3 is N/A — no runtime behavioral change. An HTML assertion would
    already pass, so the assertion change belongs to Step 4.
- [x] **STEP 3: Failing Repro Test**
  - N/A — no behavioral change. Both archive actions already return the HTML
    list notice, so the eight nodes were not rewritten and product code was
    not changed. A new HTML assertion would already pass; Step 4 replaces
    the JSON assertion.
  - Existing red nodes, left as they are, in
    `tests/test_items_ui_error_mapping.py` (8 selected, 16 deselected):
    `test_archived_wishlist_gives_409[archive-confirm]`,
    `test_archived_wishlist_gives_409[archive]`,
    `test_unknown_wishlist_gives_404[archive-confirm]`,
    `test_unknown_wishlist_gives_404[archive]`,
    `test_non_member_gives_404[archive-confirm]`,
    `test_non_member_gives_404[archive]`,
    `test_unknown_item_gives_404[archive-confirm]`,
    `test_unknown_item_gives_404[archive]`.
  - Command: `td-log run test --task WISHENKA-264 -- make test-serial PYTEST_ARGS="tests/test_items_ui_error_mapping.py -k '(archive-confirm or archive) and not reorder and not move and not restore'"`.
  - Result: 8 failed. Pytest collected and ran them. Each failure is
    `json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)`
    from `resp.json()` on an HTML fragment (`#item-modal-container` and
    `#list-notice`). The status assertion above that call passed.
    `make test-serial` exited 1. The `td-log` wrapper exited 2.
- [x] **STEP 4: Development**
  - [x] Aligned the eight archive nodes in `tests/test_items_ui_error_mapping.py` with the HTML list notice. Those requests send `Accept-Language: ru` and assert status, `text/html`, the Russian catalog sentence in `#list-notice`, and an empty `#item-modal-container`. Reorder, move, and restore still assert JSON detail. Product routes are unchanged.
- [x] **STEP 5: Code Cleanup**
  - `ai-tasks/WISHENKA-264/40-code-cleanup.md`
  - `tests/test_items_ui_error_mapping.py` needed no edits. Ruff check, Ruff
    format check, and Mypy reported no issues. Lines stay within 100
    characters, and the module timeout marker is present. Product code was
    not changed. The test file was not rewritten, so the suite was not
    re-run.
- [x] **STEP 6: Observability**
  - `ai-tasks/WISHENKA-264/50-observability.md`
  - No new logs or metrics. Archive confirmation and archive already emit
    `ui_modal_domain_error` at WARNING from `_modal_domain_error_response`
    for the 409 archived-wishlist refusal and the 404 refusals (unknown
    wishlist, non-member, unknown wish). Product code was not changed.
- [x] **STEP 7: Technical Debt Analysis**
  - `ai-tasks/WISHENKA-264/60-tech-debt.md`
  - No new technical debt and no follow-up. The eight archive assertions
    match the HTML list notice. Product code was not changed. User docs
    were left unchanged because the refusal a person sees did not change.
  - Module timeout confirmed: `pytestmark = pytest.mark.timeout(30)` covers
    every collected test in `tests/test_items_ui_error_mapping.py` (24
    tests, each `timeout(30)`, no function override), including the eight
    archive nodes.
- [x] **STEP 8: Dev Docs**
  - Searched `doc/dev` for archive confirmation and archive returning JSON
    detail on an archived wishlist, an unknown wishlist, a non-member, or an
    unknown wish.
  - Those two actions are already documented as the HTML list notice:
    `doc/dev/items.md` (archive `404`/`409` is an OOB `#list-notice` and a
    closed modal), `doc/dev/miniapp.md` (`_modal_domain_error_response`
    writes a localized notice into `#list-notice`), and
    `doc/dev/gift-receipt.md` (unknown wish: «Желание или вишлист больше
    недоступны.» in `#list-notice`, dialog closes, `htmx:responseError`
    does not fire).
  - No doc change. Reorder, move, and restore stay JSON. Product code was
    not changed.
- [x] **COMMIT: Commit Changes**

## Status Legend

- `[ ]` — step not started
- `[/]` — step in progress
- `[x]` — step completed and accepted (acceptance gate passed)

See the `td-roadmap` skill for who writes which mark and when.

## Artifacts

### STEP 1: Requirements

- `ai-tasks/WISHENKA-264/10-requirements.md`

### STEP 2: Architecture

- `ai-tasks/WISHENKA-264/20-architecture.md`

### STEP 3: Failing Repro

- N/A — no new test. Existing red nodes in `tests/test_items_ui_error_mapping.py` (see STEP 3).

### STEP 4: Development

- Source code
- Tests
- Documentation updates

### STEP 5: Code Cleanup

- `ai-tasks/WISHENKA-264/40-code-cleanup.md`

### STEP 6: Observability

- `ai-tasks/WISHENKA-264/50-observability.md`

### STEP 7: Technical Debt

- `ai-tasks/WISHENKA-264/60-tech-debt.md`

### STEP 8: Dev Docs

- `doc/dev/`

### COMMIT

- No artifact recorded here beyond the `[x]` mark above. Branch name and commit hash are reported
  in chat only, never written to this file.
