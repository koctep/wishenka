# WISHENKA-320: Code Cleanup Report

## Linter Fixes

- Fixed: `_create_named` returned `response.json()` (`Any`). The body is now
  checked to be a dict and cast to `dict[str, Any]`.
- Fixed: `TestClient.app` has no `state` on the stub type. The seed helper
  casts the app to `FastAPI` before reading `domain_service`.

## Code Formatting

Applied formatting changes:

- [x] Automatic code formatting (`make format`: 292 files already formatted)
- [x] Indentation and alignment fixes (none required)
- [x] Line length correction (none required; limit is 100)

`node --check wishenka/web/static/miniapp.js` passed. The Makefile analyzer
does not cover JavaScript.

## Code Cleanup

Cleanup actions performed:

- Removed unused imports: 0
- Removed unused variables: 0
- Removed commented-out code: none
- Removed debug prints: none
- The required-name and too-long messages are one pair of strings, used both
  by the Pydantic errors and by the omitted-name 422 detail.
- `wishlistNameDecision` walks the trimmed name once. An empty result is still
  "required" before the length check.
- Stale "still red" notes in the name-contract test modules now describe the
  rule the tests lock. Assertions are unchanged.

## Validation Results

Validation results:

- [x] Name-contract modules passed (216). The full suite was not started.
- [x] All tests have explicit timeout markers
- [x] No merge conflicts
- [x] Syntax is valid
- [x] Types are correct (Mypy, 292 files)

## Notes

Description and event title still have no character ceiling. A blank detail
still means unset. The name-contract assertions were not weakened.
