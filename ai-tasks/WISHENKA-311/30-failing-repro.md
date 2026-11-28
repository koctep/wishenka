# WISHENKA-311: Failing repro (Step 3)

N/A — no new test and no product behavioral change. `20-architecture.md`
says the two checks already state the desired outcomes. This step does
not add a third test, does not edit `wishenka/` or `tests/`, and does
not lengthen `WAIT`, `CdpPage.wait_for`, `LOAD_TIMEOUT`,
`COMMAND_TIMEOUT`, or `pytest.mark.timeout(45)`.

The standing checks are:

- `tests/test_cross_screen_comfort_browser.py::`
  `test_htmx_pending_request_marks_the_form_busy`
- `tests/test_history_screen_browser.py::`
  `test_control_opening_an_entry_moves_it_to_the_top_and_navigation_works`

Step 4 still applies the hold-and-poll change named in the architecture.
One green parallel run is not that fix. The waits stay the short clocks
the architecture replaces.

## Why the modules need a priming import

`migrated_db_template` in `tests/conftest.py` imports `create_app` when
the fixture runs. Neither browser module imports `wishenka.web.app` or
`WishlistStore` at import time. `test_history_screen_browser.py` imports
helpers from `test_home_overview_browser.py`, which also stops at
`wishenka.i18n`. A worker that collects only those files hits the
WishlistStore cycle inside the fixture, before a page opens.

`tests/test_receipt_modal_browser.py` imports `tests.receipt_support`,
which imports `create_app` and `WishlistStore` while the package is
still consistent. That import has to happen in the worker process that
later runs the browser module.

`--dist loadfile` gives each worker its own process and assigns whole
files. A priming node in a file that a worker never collects does not
help that worker. Each xdist worker does collect every node listed on
the command line before files are scheduled. Listing the priming node
once therefore loads it in both workers. The node is harness priming
only. It is not a third product check, and this step does not edit
`tests/conftest.py` or any test.

## Unprimed command (WISHENKA-357)

This is not this ticket's failure. Both workers collected only the two
browser modules, so both died on the import cycle tracked as
WISHENKA-357. This step does not fix that cycle.

From `/home/src`, through `td-log` (run-test), using `.venv` via
`make test`. `make test` reinstalled the editable package before pytest.

```sh
td-log run test --task WISHENKA-311 -- \
  make test PYTEST_JOBS=2 PYTEST_ARGS="\
tests/test_cross_screen_comfort_browser.py \
tests/test_history_screen_browser.py -q"
```

That is the architecture parallel proof without a priming node: both
browser modules, two workers, `--dist loadfile` (the `test` target).
Wall clock of the process was about 11 s, of which pytest reports
5.00 s.

**Red, import cycle (WISHENKA-357).** `make test` exited 1
(`make: *** [Makefile:62: test] Error 1`). The `td-log` wrapper then
exited 2. Pytest: `2 workers [80 items]`, then `80 errors`,
`2 warnings`, `5.00s`. No item passed. No item failed an assertion.
Both workers (`gw0`, `gw1`) died in the session fixture
`migrated_db_template` before a page opened.

The two named checks are in that set:

- `ERROR tests/test_cross_screen_comfort_browser.py::`
  `test_htmx_pending_request_marks_the_form_busy`
- `ERROR tests/test_history_screen_browser.py::`
  `test_control_opening_an_entry_moves_it_to_the_top_and_navigation_works`

Same setup error on every item, including those two:

```text
tests/conftest.py:210: in migrated_db_template
    from wishenka.web.app import create_app
wishenka/web/app.py:24: in <module>
    from wishenka.notices.store import NoticeStore
wishenka/notices/store.py:30: in <module>
    from wishenka.wishlists.store import WishlistStore
wishenka/wishlists/store.py:58: in <module>
    from wishenka.wishlists.repository import WishlistRepository
wishenka/wishlists/repository.py:28: in <module>
    from wishenka.wishlists.service import PendingCommitLog, flush_pending_commit_logs
wishenka/wishlists/service.py:16: in <module>
    from wishenka.auth.models import AuthenticatedUser
wishenka/auth/__init__.py:3: in <module>
    from wishenka.auth.dependencies import (
wishenka/auth/dependencies.py:18: in <module>
    from wishenka.wishlists.store import WishlistStore
E   ImportError: cannot import name 'WishlistStore' from partially
initialized module 'wishenka.wishlists.store' (most likely due to a
circular import) (/home/src/wishenka/wishlists/store.py)
```

The two warnings are `StarletteDeprecationWarning` from
`fastapi/testclient.py`, not the failure.

This is not the parallel-load timeout in `doc/dev/testing.md`, and it
is not evidence that the busy-form hold or the history poll is already
in place.

## Primed parallel run

`TEST_WALL_LIMIT=1800` only raises the Makefile hang guard so a long
browser run is not cut at 600 s. Pytest finished well inside that.
`--tb=line` only shortens tracebacks. The worker count and dist mode
are still `PYTEST_JOBS=2` and `--dist loadfile`.

```sh
td-log run test --task WISHENKA-311 -- \
  make test TEST_WALL_LIMIT=1800 PYTEST_JOBS=2 PYTEST_ARGS="\
tests/test_receipt_modal_browser.py::test_stale_giver_card_is_neutral \
tests/test_cross_screen_comfort_browser.py \
tests/test_history_screen_browser.py -q --tb=line"
```

**Green.** `make test` exited 0 (the `td-log` wrapper exited 0).
Pytest: `created: 2/2 workers`, `2 workers [81 items]`, then
`81 passed, 2 warnings in 31.57s`. The 81 items are the unprimed 80
plus `test_stale_giver_card_is_neutral`. Both named checks are in that
set and passed. They got past `WishlistStore` and ran while the other
checks in these two modules ran on the two workers. No assertion
failed. The two warnings are the same `StarletteDeprecationWarning`.

One green run is not the fix. Step 4 still applies the hold-and-poll
change. WISHENKA-357 is not fixed. WISHENKA-285 (`TEST_WALL_LIMIT` on a
full `make test`) was not run and is not changed.
