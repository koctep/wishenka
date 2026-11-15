# WISHENKA-166: Step 3 — Failing repro

## Artifact

`tests/test_parallel_run_contract.py` (module `pytestmark = pytest.mark.timeout(30)`; subprocess calls use
`timeout=15`; no Chromium, no network, no suite run; whole file about 0.5 s). Only a new test file was added; no
production code, `Makefile`, `pyproject.toml`, `conftest.py`, `browser_cdp.py` or existing tests changed; nothing was
installed into `.venv` (no xdist).

## How to run

```
.venv/bin/pytest -q -p no:cacheprovider tests/test_parallel_run_contract.py
```

Today: **15 failed, 1 passed in about 0.5 s**.

## Public API fixed by the contract (Step 4 must provide it)

`tests/xdist_support.py`:
- `choose_workers(cpu: int, mem_mb: int, fast_storage: bool, reserve_mb=1200, per_worker_mb=600) -> int`
  (called with keywords `cpu=`, `mem_mb=`, `fast_storage=`)
- `pick_fast_basetemp(candidate: Path, min_free_mb: int = 48) -> Path | None` (keyword `candidate=`; returns `None` for
  a missing, read-only or too small directory, else `<candidate>/wishenka-pytest-<uid>-<pid>`, name contains the pid)
- `fsync_is_fast(path: Path) -> bool`

`tests/conftest.py`: function `pytest_xdist_auto_num_workers` decorated `@pytest.hookimpl(optionalhook=True)`.

## Tests and observed red reasons

| Test | Observed failure |
| --- | --- |
| `test_make_test_runs_in_parallel` | `make test` must run pytest with xdist -n <jobs> (plan P6), got: `.venv/bin/pytest` |
| `test_make_test_serial_target_exists` | `make test-serial` target is missing (D7): No rule to make target 'test-serial' |
| `test_make_check_still_depends_on_analyze_and_test` | `test-serial` is missing while `check` is meant to use the parallel `test` (the `check: analyze test` regex itself holds) |
| `test_pyproject_declares_xdist_in_dev_extras` | `pytest-xdist>=3.6` must be in the dev extras (P1), got the six current extras |
| `test_pyproject_retention_policy_and_addopts` | `tmp_path_retention_policy = "failed"` must be set (H10), got: None |
| `test_choose_workers[6-4900-True]`, `[6-1500-True]`, `[2-8000-True]`, `[6-4900-False]` | `tests/xdist_support.py is missing (No module named 'tests.xdist_support')` (P2) |
| `test_pick_fast_basetemp_rejects_unusable_directories`, `..._returns_unique_path`, `test_fsync_probe_is_fast_on_tmpfs` | same: module missing |
| `test_cdp_launch_waits_for_complete_port_file` | `CdpBrowser._launch read DevToolsActivePort while it was still empty (IndexError('list index out of range'))` (H2, P3); fake Chromium in an own `mkdtemp` disk dir, removed by finalizer |
| `test_default_settings_do_not_point_at_repository_database` | `Settings().database_url = 'sqlite+aiosqlite:///data/wishenka.db' resolves to data/wishenka.db` (H1, P5) |
| `test_worker_cap_hook_is_registered_as_optional` | `tests/conftest.py must define pytest_xdist_auto_num_workers` (D5, P2); AST check, also fails if `optionalhook=True` is absent |
| `test_pytest_collects_without_xdist` | **passes today by construction** (architecture contract 6: subprocess `pytest -p no:xdist --collect-only -q tests/test_infra.py` exits 0); it turns red if the P2 hook is added without `optionalhook=True`. The AST test above is its red-today companion |

## Red reasons (summary)

1. Makefile `test` is plain `pytest` (no `-n`, no `--dist`); no `test-serial` target.
2. `pytest-xdist` absent from dev extras; no `tmp_path_retention_policy`.
3. `tests/xdist_support.py` does not exist.
4. `CdpBrowser._launch` raises `IndexError` on an empty port file (race).
5. Default `Settings()` points at the repository database `data/wishenka.db`.
6. Worker-cap hook is not defined (and must be `optionalhook`).

## Notes

- Cases skipped inside the contract by design: the read-only directory case is not run as root.
- `test_pick_fast_basetemp_*` and `choose_workers` signatures are specified here; the architecture gave only the
  `choose_workers` signature, `pick_fast_basetemp(candidate, min_free_mb)` is the Step 3 reading of D2/D3.
- The suite-wide benchmark `tests/bench_suite.py` is **not** a red test: it is created in P6 and used as acceptance
  evidence in P8. The documented one-off serial baseline is 971.7 s (`21-baseline-data.md`).
