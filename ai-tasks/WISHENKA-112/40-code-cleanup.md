# WISHENKA-112: Code Cleanup Report

## Linter Fixes

- `make analyze`: Ruff linter "All checks passed", Ruff format check "105 files already formatted", Mypy "no issues found in 105 source files". No findings, nothing to fix.

## Code Formatting

- [x] Automatic code formatting: Ruff format clean for the whole scope.
- [x] Indentation and alignment fixes: none needed.
- [x] Line length correction: none needed (100 characters observed).

## Code Cleanup

- Removed unused imports: 0 (Ruff F401 clean; `WishlistService` is still used in `items_ui.py`).
- Removed unused variables: 0.
- Stale references: none. No remaining `_NOT_FOUND_ERRORS` or `_svc` callback argument anywhere in `wishenka/`, `tests/` or `doc/` apart from the structure test that asserts their absence. The new comment above `_DOMAIN_ERRORS` is accurate (archived -> 409, others -> 404).
- Remaining `hasattr`/`getattr` column probes in `store.py` and `repository.py`: none (pinned by `test_no_column_presence_checks_for_guaranteed_columns`).
- Debug output / commented-out code / TODO: none in the diff or the two new test modules.
- Test helpers: `make_user` / `auth_header` in `tests/test_items_ui_error_mapping.py` follow the per-module helper convention used by existing test modules (`make_user` is defined in 14 of them, `auth_header` in 6; none is shared in `conftest.py`); extracting them would touch unrelated modules, so left as is. No unused fixtures or parameters (`_wl`, `_ids` are intentionally discarded tuple parts).
- Docstrings: module and test docstrings present per lsr-python; public/private helpers in the diff keep their docstrings.
- Behaviour and all test assertions: unchanged. No source or test edits were required in this step.

## Validation Results

- [x] All tests passed: `PYTHONDONTWRITEBYTECODE=1 make test` (foreground-requested, harness backgrounded it, single run): 616 passed, 0 failed, 1 warning (third-party httpx/starlette deprecation), 504.19 s.
- [x] All tests have explicit timeout markers: `tests/test_wishenka_112_structure.py:28` and `tests/test_items_ui_error_mapping.py:27` both `pytestmark = pytest.mark.timeout(30)`.
- [x] No merge conflicts.
- [x] Syntax is valid (mypy).
- [x] Types are correct (mypy).

## Notes

- Count reconciliation: 589 (HEAD 121692e) + 3 structure + 24 characterization = 616; `pytest --collect-only -q` reports 616 tests collected.
- No failures, so no triage and no baseline worktree were needed. No stray chromium/uvicorn/pytest processes after the run. The untracked `core` file was left alone.
