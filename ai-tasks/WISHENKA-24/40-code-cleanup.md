# WISHENKA-24: Code Cleanup Report

## Linter Fixes

- `ruff check wishenka tests`: clean before and after (0 findings, nothing to fix).
- `ruff format --check wishenka tests`: 132 files already formatted, before and after.
- `mypy wishenka tests`: no issues in 132 source files, before and after.
- Wider scan over the changed/added Python files (`--select F,ERA,T20,ARG,RUF100,C90,PLR0913`,
  `--isolated`, not enabled globally): F, ERA, T20, RUF100, C90 = 0 findings. Not fixed, on purpose:
  - `ARG001` `env` in `tests/test_receipt_ui_routes.py::test_modal_template_oob_switch`: `env` is a
    fixture requested only for its set-up side effect (the same pattern as the neighbouring tests).
  - `PLR0913` on `receipts_ui._blocked_dialog` (6 args) and `_effect_fragments` (7 args), on FastAPI
    handlers `sharing.get_item_card_partial` (7) and the old `items_ui` handlers (13 to 16, not
    this task): a request/dependency signature, the rule is not enforced by the project, and
    bundling the arguments would change the code shape for no behavioural gain.

## Code Formatting

- [x] Automatic code formatting (`ruff format` reports nothing to change)
- [x] Indentation and alignment fixes (none needed)
- [x] Line length correction: scan of all 25 changed/added files (.py, .js, .html, .css) for lines
      longer than 100 characters (characters, not bytes). Only lines this task wrote were touched:
  - wrapped 6 lines: `item_card.html` root tag (the `card_oob` attribute moved to its own line;
    the rendered attribute text is unchanged, only whitespace inside the tag differs),
    `gifted_items_section.html` (3 lines: the count span, the act `<li>`, and the
    approximate-date conditional, rewrapped after the review with Jinja whitespace control so the
    rendered text is byte-identical; verified for both branches),
    `miniapp.css` (2 rules, `#list-notice:not(:empty)` and `.gifted-items-details summary`,
    now multi-line blocks).
  - left as is (not written by this task, 5 lines): `wishlist.js` lines 143 and 200 (WISHENKA-109),
    `htmx_stub.js` line 132 and `browser_helpers.py` line 218 (WISHENKA-110),
    `archived_items_section.html` line 14 (older template).

## Code Cleanup

- Removed unused imports: 0 (ruff F clean).
- Removed unused variables/functions/constants: 0. Every helper of `gifted_view.py`
  (`oob_text`, `GiftedAct`, `GiftedRow`, `utc_day`, `build_gifted_rows`, `read_gifted_rows`,
  both constants) and of `receipts_ui.py` has a caller; every context variable of the new
  templates (`gifted_rows`, `oob`, `blocked`, `feedback`, `selected`, `remaining`, `card_oob`,
  `is_member`) is read.
- Unused CSS: 0. Every class and id selector added to `miniapp.css` is emitted by a template,
  a route or a script (checked by a scan of `wishenka/` sources).
- Removed commented-out code, debug prints, `console.*`, TODO/FIXME, `debugger`: 0 found in the
  added lines; no new `# noqa` / `# type: ignore`.
- JS hygiene (`receipt.js`, additions to `wishlist.js`): `const`/`let` only, strict equality only,
  no console output, server text goes through `textContent`; the one `innerHTML` is on the inert
  `<template>` of the `swapWishCard` wrapper (accepted).
- Docstrings and type hints of the new Python modules: complete, nothing to add.
- `base.html`: the only change is the `<script src="/static/receipt.js" defer>` tag; the inline
  script is untouched (SHA-256 guard test is green).

### Added test (carry-over from the Step 4 review)

`tests/test_receipt_modal_browser.py::test_unmarked_error_neither_shows_notice_nor_reloads` (+36 lines).
It sends an htmx ajax `POST .../items/999999/archive` (answered 404 without marker headers), waits until a
`htmx:responseError` listener recorded `[404, null]` (so the error provably reached the page),
then watches for 2 s that `window.__beforeReload` survives (no reload), `#list-notice` stays
empty, and the item order is intact.
- Green on the current code.
- Mutation proof: in a scratch copy of the repository (session scratchpad, nothing changed in
  `/home/src`) the check `getResponseHeader(REORDER_REFUSAL_HEADER) !== 'stale_order'` was removed
  from `wishlist.js`; the new test went RED (`assert 'Список изменился. Обновляем.' == ''`),
  while B-6 `test_stale_reorder_keeps_list_and_shows_notice` stayed green, i.e. the hole is closed
  by exactly this test.

## Validation Results

- [x] All tests passed: full suite `make test` = 797 passed, 0 failed (16m41s); touched files re-run inside it
- [x] All tests have explicit timeout markers (every new/changed test module has a module-level
      `pytest.mark.timeout`; no skip/xfail in new modules)
- [x] No merge conflicts (no conflict markers in `wishenka/` or `tests/`)
- [x] Syntax is valid
- [x] Types are correct (`mypy wishenka tests`: no issues)

## Notes

- No genuine bug found while cleaning.
- Carried review items 2 to 6 (stub-vs-real htmx divergences, no focus return after a successful
  receipt, edit-modal archive button without `hx-target`, covered archive confirm button) are
  not cleanup items and were left for Step 7.
- Untracked `core` and `ai-tasks/sprint-2110/` were not touched.
