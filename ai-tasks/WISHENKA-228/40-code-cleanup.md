# WISHENKA-228: Code Cleanup Report

## Linter Fixes

No linter errors or warnings in the Step 4 change. `make analyze` (ruff check,
ruff format --check, mypy) reported a clean tree: 286 files formatted, mypy
found no issues in 286 source files. Nothing was rewritten.

## Code Formatting

- [x] Automatic code formatting: already compliant (`ruff format --check`).
- [x] Indentation and alignment: no fixes. The predicate stays one condition.
- [x] Line length: no line in `wishenka/web/rate_limit.py` or
  `tests/test_public_link_rate_limit.py` exceeds 100 characters.

## Code Cleanup

- Removed unused imports: 0. New test imports (`Any`, `Request`, `Response`,
  `PublicLinkRateLimitMiddleware`, `resolve_client_ip`) are used.
- Removed unused variables: 0. `_request` and `_invite_token` / `_public_token`
  are intentional unused names.
- Removed commented-out code: none in the new tests or the predicate.
- Removed debug prints: none.
- The matcher still admits only `GET` and `HEAD` for `/share/{token}` and
  `/invite/{token}`, plus the existing `POST` join route. It was not widened.

## Validation Results

- [x] In-scope tests passed: `make test-serial
  PYTEST_ARGS="tests/test_public_link_rate_limit.py -q"` — 22 passed in 2.17s.
- [x] Full `make test` on this tree: 2480 passed, 2 skipped, 26 failed.
  No failure is in `tests/test_public_link_rate_limit.py`.
  - `tests/test_history_screen_browser.py::test_control_opening_an_entry_moves_it_to_the_top_and_navigation_works`
    failed under the parallel run and passed on an immediate serial re-run.
    Already filed: [WISHENKA-311](https://pypost.atlassian.net/browse/WISHENKA-311).
  - Eight share-page and public-view tests fail at base commit `7e7b7f1` with
    `sqlite3.IntegrityError: FOREIGN KEY constraint failed` and HTTP 500.
    Filed: [WISHENKA-348](https://pypost.atlassian.net/browse/WISHENKA-348).
  - The other 17 failures match the set already filed on WISHENKA-303
    (WISHENKA-264, WISHENKA-265, WISHENKA-220, WISHENKA-235, WISHENKA-245,
    WISHENKA-232, WISHENKA-298, WISHENKA-267, WISHENKA-212).
- [x] Every test has an explicit timeout: module
  `pytestmark = pytest.mark.timeout(30)`.
- [x] No merge conflicts (`git diff --check` clean).
- [x] Syntax is valid (ruff and the passing pytest run).
- [x] Types are correct (mypy clean on `wishenka` and `tests`).

## Notes

No production edit in this step. `match_public_link_route` already counts
`HEAD` with `GET` for the two public-link templates. Review can focus on that
predicate and the HEAD / `X-Real-IP` / missing-peer tests.
