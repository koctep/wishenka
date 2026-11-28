# WISHENKA-283: Technical Debt Analysis

No new technical debt. This task did not change product code or tests.
The three language checks already pass beside other tests. There is no
new follow-up.

Reviewed: `tests/test_i18n_unit.py` (the three named checks and their
timeout marks), `10-requirements.md`, `20-architecture.md`,
`30-failing-repro.md`, `40-code-cleanup.md`, and `50-observability.md`.

## Shortcuts Taken

None. Architecture found no shared catalog, locale cache, or file write
that would make these checks fail under `pytest -n 4 --dist loadfile`.
No cache, lock, copied catalog, or raised `TEST_WALL_LIMIT` was added.
`wishenka/web/static/app.js` was not given `receipt`.

## Code Quality Issues

None. No source file was edited. Locale stays per request, `CATALOG`
stays process-local, and each check keeps its own database under
`tmp_path`.

## Missing Tests

No `do-testing` blocker. No new test was added.

`tests/test_i18n_unit.py` already declares
`pytestmark = pytest.mark.timeout(20)`. The three checks also set a
closer mark:

- `test_anonymous_share_and_invite_locale_priority_chain` — 15 seconds
- `test_reminders_fallback_to_en_for_missing_user_locale_and_legacy_schema` — 15 seconds
- `test_miniapp_js_localizes_home_nav_shell_and_settings_label` — 10 seconds

Step 4 ran those checks with the neighbor files under
`.venv/bin/pytest -n 4 --dist loadfile`. The three checks passed in
that set. Summary: `508 passed, 4 warnings in 33.17s`. The file alone
was `37 passed, 4 warnings in 5.53s`.

## Performance Concerns

None introduced. The neighbor proof finished in 33.17 seconds. A
600-second full-suite cutoff is not a performance defect of this change.

## Follow-up Tasks

None. There is no new follow-up.

The 600-second full-suite hang is already WISHENKA-285. It is not a new
follow-up. `NON-BLOCKER — pre-existing`. `make test` wraps pytest in
`timeout -k 30 600` (`TEST_WALL_LIMIT`). The WISHENKA-98 run stopped at
that limit before pytest printed a traceback. This task did not re-run
the full suite and did not file a second issue.

User documentation under `doc/` was left unchanged. There is no
user-facing change. Developer docs still belong to Step 8.
