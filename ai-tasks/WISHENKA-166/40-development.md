# WISHENKA-166: Step 4 Development log

Reference machine: 6 cores, 5909 MiB (`nproc`, `free -m`), `/dev/shm` 64 MiB `noexec`. All numbers below were measured
on the final configuration unless stated. Raw run logs/JUnit files are in the session scratchpad (not in the repo).

## Implemented per plan step

| Step | Status | What was done | Check result |
| --- | --- | --- | --- |
| P1 | done | `pyproject.toml`: `pytest-xdist>=3.6` in `dev`; `tmp_path_retention_policy = "failed"`; `addopts` unchanged. Installed with `make deps` (network was available; xdist 3.8.0, execnet 2.1.2) | `import xdist` works; addopts guard tests green |
| P2 | done | `tests/xdist_support.py` (pure stdlib: `choose_workers`, `pick_fast_basetemp`, `fsync_is_fast`, `remove_stale`, `remove_stale_disk_dirs`, `available_memory_mb`, `plan_storage`, `plan_workers`, `disk_mkdtemp`). `tests/conftest.py`: `pytest_xdist_auto_num_workers` with `optionalhook=True` (prints the slow-storage warning), `pytest_configure` (tryfirst, controller only: fast `basetemp` `/dev/shm/wishenka-pytest-<uid>-<pid>`, `TMPDIR` and `tempfile.tempdir` on `...-tmp`, `WISHENKA_TEST_DISK_TMPDIR`, stale cleanup), `pytest_sessionfinish` (arms `faulthandler.dump_traceback_later(120)`), `pytest_unconfigure` (removes dirs after exit 0, keeps them and prints the path otherwise). User `--basetemp` is respected | `-n 2` run leaves `/dev/shm` empty; a run with exit code 5 kept `/dev/shm/wishenka-pytest-501-<pid>`; a fake stale `...-999999` dir was removed by the next run; `-p no:xdist --collect-only` works |
| P3 | done | `tests/browser_cdp.py`: `read_debug_port` (waits for a non-empty numeric first line), `launch_chromium` (`setpriv --pdeathsig KILL` wrapper when present, `start_new_session`, no `preexec_fn`), `stop_chromium` (terminate, bounded wait, kill, then `killpg`), `atexit` killpg of live browsers; `CdpBrowser._launch/stop` use them. `conftest.py`: `chromium_browser` profile on disk (`disk_mkdtemp("chromium")`, removed in teardown); new fixture `chromium_profile_dir`. Both own-`Popen` tests (`test_wishlist_management_browser.py`, `test_wishlist_sections_ui.py`) use `launch_chromium`/`stop_chromium`/`chromium_profile_dir` | contract CDP test green; `kill -9` of pytest during a browser test (twice): 0 Chromium processes remain; profile dir `/tmp/wk-chromium-<pid>-*` and `/dev/shm` dir left by the killed run are removed by the next run (pid in the name) |
| P4 | done | `tests/test_browser_prerequisites.py`: module-level `tmp_path` fixture override on the disk directory (`disk_mkdtemp("prereq")`), removed after each test | module green with the fast base active |
| P5 | done | autouse `_isolated_default_database` (+ session dir `_default_db_dir`): `WISHENKA_DATABASE_URL` and `WISHENKA_SQLITE_DB_PATH` per test | contract test 5 green; `data/wishenka.db` mtime/size unchanged (`2026-11-15 18:33:42.06`, 200704 B) after every full run. No production seam (Q-2) |
| P6 | done | `Makefile`: `PYTEST_JOBS`, `PYTEST_ARGS`, `TEST_WALL_LIMIT` (600 s `timeout -k 30` guard), targets `test` (`-n auto --dist loadfile`), `test-serial` (`-n 0`), `test-bench` (`python -m tests.bench_suite --budget 120`), `help` lists them; `check: analyze test` unchanged. `tests/bench_suite.py`: runs `make test` with JUnit, prints nproc/`free -m`/wall/min `MemAvailable`/`/dev/shm` peak/counts, `--compare` passed-set equality, exit 1 on failure, skipped test or budget breach | `make -n test` has `-n`, `--dist`, no `apt-get`; bench exits 0 |
| P7 | done | Distribution measured 3 runs each (pytest wall time, same machine, one at a time): `load` 48.2, 49.4, 49.8 s (median 49.4); `loadfile` 46.2, 45.3, 48.7 s (median 46.2). Lower median is `loadfile` and it keeps modules on one worker (fewer Chromium instances), so **`loadfile` is chosen** (D4 left this open). Headroom audit (JUnit time over `timeout` marker, both modes): worst ratio **0.174** (`test_receipt_is_not_capped_by_occupied_units` 10.5 s of 60 s), next 0.151, 0.139; none above 0.5, so **no limit raised** | table above |
| P8 | done | see DoD table | see below |
| P9 | skipped | `doc/dev/testing.md` is Step 8; the run is understandable from `make help` and the Makefile comments | |

## Deviations from the architecture

1. **`--dist loadfile` instead of `load`** (D4 explicitly deferred the choice to P7; evidence above, differences of about 3 s are close to noise, loadfile has the lower median and lower memory risk). The contract test only requires `--dist`.
2. **The two own-`Popen` browser tests also use `read_debug_port`** (same port-file race H2 as `CdpBrowser`; their assertions and messages are unchanged: "debugging endpoint did not start"). The architecture listed only `launch_chromium` for them. `chromium_profile_dir` fixture added (test signature gains one fixture parameter) because profiles must be on disk (H3).
3. `disk_mkdtemp(kind)` names directories `wk-<kind>-<pid>-<random>` and `conftest.pytest_configure` removes stale ones of dead pids (the architecture only required cleanup at teardown; this also covers `kill -9`).
4. `test-bench` has no `deps` prerequisite (it runs `make test`, which has it).
5. No test edits in `tests/test_parallel_run_contract.py` (assertions untouched, file not modified).

## DoD evidence

Final configuration (`make test` = `-n auto --dist loadfile`, workers chosen by the cap hook: 6 on this machine). "Wall" is
`tests.bench_suite` (includes `make deps`, about 4 to 5 s); "pytest" is pytest's own time.

| Run | Command | Wall | pytest | Result | Min `MemAvailable` (start about 4800 MiB) | `/dev/shm` peak |
| --- | --- | ---: | ---: | --- | ---: | ---: |
| P1 | `make test` via bench (loadfile) | 54.4 s | 48.9 s | 814 passed | 2124 MiB | 5.0 MiB |
| P2 | same, compared with run 1 | 53.8 s | 48.7 s | 814 passed, set equal | 1960 MiB | 3.8 MiB |
| P3 | same | 52.7 s | 47.5 s | 814 passed, set equal | 2118 MiB | 5.3 MiB |
| P1' | repeat after the last code change (stale-dir naming) | 55.3 s | n/a | 814 passed | 1965 MiB | 4.9 MiB |
| P2' | repeat | 54.0 s | n/a | 814 passed, set equal | 1908 MiB | 4.4 MiB |
| P3' | repeat | 48.9 s | n/a | 814 passed, set equal | 2157 MiB | 4.5 MiB |
| serial | `make test-serial` (final) | 119 s | 114.08 s | 814 passed, set equal to parallel | n/a | n/a |
| serial (earlier) | same | 123 s | 117.41 s | 814 passed | n/a | n/a |
| `make check` | analyze + parallel test | 51 s | 45.4 s | ruff, ruff format, mypy clean; 814 passed | n/a | n/a |

* Peak memory in use is about 2.7 to 2.9 GiB (drop of `MemAvailable`); minimum available 1908 MiB; no OOM seen (no worker died).
* Collected counts: `pytest --collect-only` = **814** = 798 existing + 16 contract tests; serial and parallel passed sets are identical (814 each, 0 skipped, 0 failed).
* Worst `duration/timeout` 0.174; no timeout raised; `git grep` finds no `reruns`/retry plugin (only test names containing "flaky").
* Budget: parallel 48.9 to 55.3 s wall against 120 s (margin about 65 s); serial on tmpfs about 114 s pytest time (just inside the budget, no claim made).
* Leftovers after the final series: `/dev/shm` empty, `/tmp` listing identical to the snapshot taken before the runs, no `wk-*` dirs, no Chromium processes, `data/wishenka.db` unchanged.
* Failure/kill paths: killed run keeps `/dev/shm/wishenka-pytest-*` and the Chromium profile dir until the next run, which removes them; no orphan Chromium (pdeathsig).
* The end-of-run hang (H8) did not occur in 14 full runs (3 `load`, 3 `loadfile` measurements, 3+3 series, check, plus first bench).

## Files changed

`Makefile`, `pyproject.toml`, `tests/conftest.py`, `tests/browser_cdp.py`, `tests/test_browser_prerequisites.py`,
`tests/test_wishlist_management_browser.py`, `tests/test_wishlist_sections_ui.py`, new `tests/xdist_support.py`,
new `tests/bench_suite.py`. `wishenka/` untouched. Not committed.

## Open risks

* Without `setpriv` a SIGKILLed worker can leave an orphan Chromium (documented in `launch_chromium`).
* The worker count follows `MemAvailable` and is not cgroup-aware beyond a finite `memory.max`.
* The pid-based stale cleanup can in theory skip a directory whose pid was reused.
* Full docs (`doc/dev/testing.md`) are Step 8; the `-n 0`/tmpfs/`WISHENKA_TEST_*` switches are described only in code comments and A4 of the architecture.
