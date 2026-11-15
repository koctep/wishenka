"""WISHENKA-166 contract tests: the suite must be runnable in parallel, safely and fast.

These tests describe the capability that Step 4 (P1..P6) delivers. They fail today because
the capability is missing (see ``ai-tasks/WISHENKA-166/30-failing-repro.md``). They never
run the suite, start Chromium or touch the network.
"""

from __future__ import annotations

import ast
import importlib
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import tomllib
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.timeout(30)

ROOT = Path(__file__).resolve().parent.parent
SUBPROCESS_TIMEOUT = 15


def _make(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["make", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT,
        check=False,
    )


def _support() -> ModuleType:
    try:
        return importlib.import_module("tests.xdist_support")
    except ModuleNotFoundError as error:
        pytest.fail(
            f"tests/xdist_support.py is missing ({error}): the pure helpers "
            "choose_workers / pick_fast_basetemp / fsync_is_fast must exist (plan P2)"
        )


# --- 1. Makefile ---------------------------------------------------------------------


def test_make_test_runs_in_parallel() -> None:
    result = _make("-n", "test")
    assert result.returncode == 0, result.stderr
    assert re.search(r"(^|\s)-n\s+\S+", result.stdout), (
        f"`make test` must run pytest with xdist `-n <jobs>` (plan P6), got:\n{result.stdout}"
    )
    assert "--dist" in result.stdout, (
        f"`make test` must pass `--dist load` (decision D4), got:\n{result.stdout}"
    )


def test_make_test_serial_target_exists() -> None:
    result = _make("-n", "test-serial")
    assert result.returncode == 0, (
        f"`make test-serial` target is missing (decision D7): {result.stderr.strip()}"
    )
    assert re.search(r"-n\s+0\b", result.stdout), (
        f"`make test-serial` must run pytest with `-n 0`, got:\n{result.stdout}"
    )
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^\.PHONY:\s*test-serial\s*$", makefile, re.MULTILINE), (
        "`test-serial` must be declared .PHONY"
    )
    helped = _make("help")
    assert "test-serial" in helped.stdout, "`make help` must list test-serial"


def test_make_check_still_depends_on_analyze_and_test() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert re.search(r"^check:\s*analyze\s+test\b", makefile, re.MULTILINE), (
        "`check` must keep depending on `analyze test`"
    )
    # Guard against a vacuous pass: the parallel contract must hold in the same Makefile.
    assert re.search(r"^test-serial:", makefile, re.MULTILINE), (
        "`test-serial` is missing while `check` is meant to use the parallel `test`"
    )


# --- 2. pyproject --------------------------------------------------------------------


def _pytest_config() -> tuple[dict[str, object], list[str]]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    ini = data["tool"]["pytest"]["ini_options"]
    dev = data["project"]["optional-dependencies"]["dev"]
    return ini, dev


def test_pyproject_declares_xdist_in_dev_extras() -> None:
    _, dev = _pytest_config()
    assert any(re.match(r"pytest-xdist\b", item) for item in dev), (
        f"`pytest-xdist>=3.6` must be in the dev extras (plan P1), got: {dev}"
    )


def test_pyproject_retention_policy_and_addopts() -> None:
    ini, _ = _pytest_config()
    assert ini.get("tmp_path_retention_policy") == "failed", (
        '`tmp_path_retention_policy = "failed"` must be set (hazard H10), '
        f"got: {ini.get('tmp_path_retention_policy')!r}"
    )
    addopts = str(ini.get("addopts", ""))
    assert not re.search(r"(^|\s)-n\b", addopts), "addopts must not hard-code -n (decision D7)"


# --- 3. pure helpers (tests/xdist_support.py) ------------------------------------------


@pytest.mark.parametrize(
    ("cpu", "mem_mb", "fast", "expected"),
    [
        (6, 4900, True, {5, 6}),
        (6, 1500, True, {1}),
        (2, 8000, True, {2}),
        (6, 4900, False, {1}),
    ],
)
def test_choose_workers(cpu: int, mem_mb: int, fast: bool, expected: set[int]) -> None:
    support = _support()
    workers = support.choose_workers(cpu=cpu, mem_mb=mem_mb, fast_storage=fast)
    assert workers in expected, (
        f"choose_workers(cpu={cpu}, mem_mb={mem_mb}, fast_storage={fast}) -> {workers}, "
        f"expected one of {sorted(expected)} (decisions D2, D5)"
    )


def test_pick_fast_basetemp_rejects_unusable_directories(tmp_path: Path) -> None:
    support = _support()
    assert support.pick_fast_basetemp(candidate=tmp_path / "missing") is None, "missing dir"
    assert support.pick_fast_basetemp(candidate=tmp_path, min_free_mb=10**9) is None, "too small"
    if os.geteuid() != 0:
        locked = tmp_path / "locked"
        locked.mkdir()
        locked.chmod(stat.S_IRUSR | stat.S_IXUSR)
        try:
            assert support.pick_fast_basetemp(candidate=locked) is None, "read-only dir"
        finally:
            locked.chmod(stat.S_IRWXU)


def test_pick_fast_basetemp_returns_unique_path(tmp_path: Path) -> None:
    support = _support()
    first = support.pick_fast_basetemp(candidate=tmp_path, min_free_mb=1)
    assert first is not None, "a writable directory with enough space must be accepted"
    assert Path(first).parent == tmp_path
    assert Path(first).name.startswith("wishenka-pytest-"), first
    assert str(os.getpid()) in Path(first).name, "the name must carry the pid (decision D3)"


def test_fsync_probe_is_fast_on_tmpfs() -> None:
    support = _support()
    shm = Path("/dev/shm")
    assert shm.is_dir(), "this contract assumes a tmpfs at /dev/shm"
    started = time.monotonic()
    fast = support.fsync_is_fast(shm)
    assert fast is True, "fsync on tmpfs must count as fast (decision D2)"
    assert time.monotonic() - started < 1.0, "the probe itself must take under 1 s"


# --- 4. CDP port-file race -------------------------------------------------------------

FAKE_CHROMIUM = f"""#!{sys.executable}
import os, sys, time
profile = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("--user-data-dir="))
os.makedirs(profile, exist_ok=True)
port_file = os.path.join(profile, "DevToolsActivePort")
open(port_file, "w").close()  # file exists but is still empty
time.sleep(0.3)
with open(port_file, "w") as handle:
    handle.write("45678\\n/devtools/browser/fake\\n")
time.sleep(30)
"""


@pytest.fixture
def disk_tmp_path() -> Iterator[Path]:
    """Exec-capable disk directory (the fast tmpfs base is ``noexec``, decision D12)."""
    base = os.environ.get("WISHENKA_TEST_DISK_TMPDIR") or tempfile.gettempdir()
    path = Path(tempfile.mkdtemp(prefix="wk-contract-", dir=base))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


def test_cdp_launch_waits_for_complete_port_file(disk_tmp_path: Path) -> None:
    from tests.browser_cdp import CdpBrowser

    fake = disk_tmp_path / "fake-chromium"
    fake.write_text(FAKE_CHROMIUM, encoding="utf-8")
    fake.chmod(0o755)
    browser = CdpBrowser()
    try:
        try:
            browser.start(str(fake), disk_tmp_path / "profiles")
        except IndexError as error:
            pytest.fail(
                "CdpBrowser._launch read DevToolsActivePort while it was still empty "
                f"({error!r}); it must wait for a non-empty first line (hazard H2, plan P3)"
            )
        assert browser._debug_url == "http://127.0.0.1:45678"
    finally:
        browser.stop()


# --- 5. default database isolation -----------------------------------------------------


def test_default_settings_do_not_point_at_repository_database() -> None:
    from wishenka.config import Settings

    settings = Settings()
    repo_db = (ROOT / "data" / "wishenka.db").resolve()
    for name, value in (
        ("database_url", settings.database_url),
        ("sqlite_db_path", settings.sqlite_db_path),
    ):
        raw = value.split(":///", 1)[-1]
        resolved = (Path.cwd() / raw).resolve()
        assert resolved != repo_db, (
            f"Settings().{name} = {value!r} resolves to data/wishenka.db: the autouse "
            "fixture must set WISHENKA_DATABASE_URL / WISHENKA_SQLITE_DB_PATH per test "
            "(hazard H1, plan P5)"
        )


# --- 6. pytest without xdist -----------------------------------------------------------


def _worker_cap_hook_decorators() -> list[ast.expr] | None:
    tree = ast.parse((ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "pytest_xdist_auto_num_workers":
            return node.decorator_list
    return None


def test_worker_cap_hook_is_registered_as_optional() -> None:
    decorators = _worker_cap_hook_decorators()
    assert decorators is not None, (
        "tests/conftest.py must define `pytest_xdist_auto_num_workers` (decision D5, plan P2)"
    )
    source = " ".join(ast.unparse(item) for item in decorators)
    assert "optionalhook=True" in source, (
        "the worker-cap hook must be `@pytest.hookimpl(optionalhook=True)`, otherwise pytest "
        f"without xdist fails with PluginValidationError (B3); decorators: {source!r}"
    )


def test_pytest_collects_without_xdist() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:xdist",
            "-p",
            "no:cacheprovider",
            "--collect-only",
            "-q",
            "tests/test_infra.py",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=SUBPROCESS_TIMEOUT,
        check=False,
    )
    assert result.returncode == 0, (
        f"collection without xdist failed (hook not optional?):\n{result.stdout[-800:]}"
        f"\n{result.stderr[-800:]}"
    )
