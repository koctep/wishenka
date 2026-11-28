# WISHENKA-283: Failing repro (Step 3)

N/A — no behavioral change. `20-architecture.md` finds no shared catalog,
locale cache, or file write that would make the three language checks fail
while other tests run. A new test written to go red first would be green on
the first run, so it would not demonstrate a defect. No test file was added.
Product code and existing tests were not edited.

The three named checks already live in `tests/test_i18n_unit.py`:

- `test_anonymous_share_and_invite_locale_priority_chain`
- `test_reminders_fallback_to_en_for_missing_user_locale_and_legacy_schema`
- `test_miniapp_js_localizes_home_nav_shell_and_settings_label`

The 600-second full-suite kill stays WISHENKA-285. This step does not run
the full suite.

## Command

```sh
.venv/bin/pytest -n 4 --dist loadfile tests/test_i18n_unit.py -q --tb=line
```

## Result

Orchestrator run: **37 passed in 5.57s**.

Confirmation run of the same command: **37 passed, 4 warnings in 5.30s**
(exit 0). Pytest created 4 workers and collected 37 items from
`tests/test_i18n_unit.py`, including the three named checks. The warnings
are `StarletteDeprecationWarning` from `fastapi/testclient.py`, not test
failures.
