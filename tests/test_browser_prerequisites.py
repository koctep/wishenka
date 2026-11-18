"""Failing repro for WISHENKA-124: reproducible Chromium prerequisite for browser UI tests.

Contract under test (see ai-tasks/WISHENKA-124/20-architecture.md):
- ``tests/browser_support.py`` resolves and probes a browser (``check_chromium``), and exposes a
  CLI (``python -m tests.browser_support``) with exit codes 0/2/3.
- ``tests/conftest.py`` provides the session fixture ``chromium_executable``.
- ``make deps-browser``, the ``browser`` pytest marker, the explicit ``websockets`` dev
  dependency and the CI step ``make deps-browser`` exist.
- Guards: nothing may hide the browser tests (``-m``/``-k``/``--deselect``).

No network and no real Chromium are needed: browsers are fake shell scripts in ``tmp_path``.
"""

import ast
import importlib
import importlib.util
import re
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests import xdist_support

pytestmark = pytest.mark.timeout(30)


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Override: the fake browsers are executed, so they live on the exec-capable disk area.

    The fast pytest base (tmpfs) is mounted ``noexec`` (WISHENKA-166, hazard H3).
    """
    path = xdist_support.disk_mkdtemp("prereq")
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


ROOT = Path(__file__).resolve().parents[1]
CI_YML = ROOT / ".github" / "workflows" / "ci.yml"
MAKEFILE = ROOT / "Makefile"
PYPROJECT = ROOT / "pyproject.toml"

FORBIDDEN = re.compile(
    r"""(?:^|\s)(?:
        -m\s*["']?[^"'\n]*\bnot\s+browser
      | -k\s*["']?[^"'\n]*\bbrowser
      | --deselect(?:\s|=)
      | --ignore(?:-glob)?[\s=]\S*browser
    )""",
    re.M | re.X,
)


def _bs() -> ModuleType:
    """Lazily import ``tests.browser_support`` after asserting that it exists."""
    spec = importlib.util.find_spec("tests.browser_support")
    assert spec is not None, "tests/browser_support.py отсутствует: Step 4 должен создать модуль"
    return importlib.import_module("tests.browser_support")


def _fake(directory: Path, name: str, body: str) -> Path:
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def _good(directory: Path, name: str = "chromium") -> Path:
    return _fake(directory, name, 'echo "Chromium 1.2.3"')


def _shim(directory: Path, name: str = "chromium") -> Path:
    return _fake(
        directory, name, "echo \"Command 'chromium' requires the chromium snap\" >&2\nexit 1"
    )


def _empty_dir(tmp_path: Path) -> Path:
    directory = tmp_path / "empty"
    directory.mkdir()
    return directory


def _run(args: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=ROOT, capture_output=True, text=True, timeout=timeout, check=False
    )


def _run_cli(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "tests.browser_support"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )


def _make_n(*targets: str) -> subprocess.CompletedProcess[str]:
    return _run(["make", "-n", *targets])


def _pyproject() -> dict[str, Any]:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


# --- Group A: the module exists ---------------------------------------------------------------


def test_browser_support_module_exists() -> None:
    spec = importlib.util.find_spec("tests.browser_support")
    assert spec is not None, "tests/browser_support.py не существует; Step 4 должен его создать"


# --- Group B: check_chromium behaviour --------------------------------------------------------


def test_no_browser_is_fail_with_actionable_message(tmp_path: Path) -> None:
    result = _bs().check_chromium(env={}, path=str(_empty_dir(tmp_path)))
    assert result.action == "fail"
    for needle in (
        "Chromium",
        "chromium",
        "chromium-browser",
        "google-chrome",
        "make deps-browser",
        "doc/dev/testing.md",
    ):
        assert needle in result.message, f"{needle!r} not in: {result.message}"


@pytest.mark.parametrize("flag", ["1", " 1 "])
def test_skip_only_with_explicit_opt_out(tmp_path: Path, flag: str) -> None:
    bs = _bs()
    empty = str(_empty_dir(tmp_path))
    skipped = bs.check_chromium(env={"WISHENKA_SKIP_BROWSER_TESTS": flag}, path=empty)
    assert skipped.action == "skip"
    assert skipped.message
    assert bs.check_chromium(env={}, path=empty).action == "fail"


@pytest.mark.parametrize("flag", ["0", "true", "yes", ""])
def test_other_opt_out_values_do_not_skip(tmp_path: Path, flag: str) -> None:
    result = _bs().check_chromium(
        env={"WISHENKA_SKIP_BROWSER_TESTS": flag}, path=str(_empty_dir(tmp_path))
    )
    assert result.action == "fail"


@pytest.mark.parametrize("ci_value", ["true", "1", "True", " yes "])
def test_ci_disables_opt_out(tmp_path: Path, ci_value: str) -> None:
    result = _bs().check_chromium(
        env={"WISHENKA_SKIP_BROWSER_TESTS": "1", "CI": ci_value}, path=str(_empty_dir(tmp_path))
    )
    assert result.action == "fail"


@pytest.mark.parametrize("ci_value", ["", "0", "False", "no", "  "])
def test_falsy_ci_keeps_opt_out(tmp_path: Path, ci_value: str) -> None:
    result = _bs().check_chromium(
        env={"WISHENKA_SKIP_BROWSER_TESTS": "1", "CI": ci_value}, path=str(_empty_dir(tmp_path))
    )
    assert result.action == "skip"


def test_good_chromium_on_path_is_ok(tmp_path: Path) -> None:
    fake = _good(tmp_path)
    result = _bs().check_chromium(env={}, path=str(tmp_path))
    assert result.action == "ok"
    assert result.executable == str(fake)


def test_google_chrome_alone_is_ok(tmp_path: Path) -> None:
    fake = _good(tmp_path, "google-chrome")
    result = _bs().check_chromium(env={}, path=str(tmp_path))
    assert result.action == "ok"
    assert result.executable == str(fake)


def test_explicit_binary_variable_is_used(tmp_path: Path) -> None:
    fake = _good(tmp_path, "my-browser")
    result = _bs().check_chromium(
        env={"WISHENKA_CHROMIUM_BIN": str(fake)}, path=str(_empty_dir(tmp_path))
    )
    assert result.action == "ok"
    assert result.executable == str(fake)


def test_explicit_binary_variable_missing_has_no_path_fallback(tmp_path: Path) -> None:
    _good(tmp_path)  # a good chromium exists on PATH but must not be used
    result = _bs().check_chromium(
        env={"WISHENKA_CHROMIUM_BIN": str(tmp_path / "nope")}, path=str(tmp_path)
    )
    assert result.action == "fail"
    assert "WISHENKA_CHROMIUM_BIN" in result.message


def test_snap_shim_is_fail_with_path_and_snap_hint(tmp_path: Path) -> None:
    shim = _shim(tmp_path)
    result = _bs().check_chromium(env={}, path=str(tmp_path))
    assert result.action == "fail"
    assert str(shim) in result.message
    assert "snap" in result.message


def test_hanging_browser_is_bounded_by_probe_timeout(tmp_path: Path) -> None:
    _fake(tmp_path, "chromium", "exec /bin/sleep 30")
    started = time.monotonic()
    result = _bs().check_chromium(env={}, path=str(tmp_path), probe_timeout=0.5)
    assert time.monotonic() - started < 10
    assert result.action == "fail"


def test_non_executable_file_is_not_a_candidate(tmp_path: Path) -> None:
    plain = tmp_path / "chromium"
    plain.write_text('#!/bin/sh\necho "Chromium 1.2.3"\n', encoding="utf-8")
    plain.chmod(0o644)
    result = _bs().check_chromium(env={}, path=str(tmp_path))
    assert result.action == "fail"


def test_bad_chromium_next_to_good_chrome_picks_chrome(tmp_path: Path) -> None:
    _shim(tmp_path, "chromium")
    chrome = _good(tmp_path, "google-chrome")
    result = _bs().check_chromium(env={}, path=str(tmp_path))
    assert result.action == "ok"
    assert result.executable == str(chrome)


def test_symlinks_to_same_shim_are_probed_separately(tmp_path: Path) -> None:
    shim = _shim(tmp_path, "real-shim")
    (tmp_path / "chromium").symlink_to(shim)
    (tmp_path / "chromium-browser").symlink_to(shim)
    candidates = _bs().find_candidates({}, path=str(tmp_path))
    names = {Path(item).name for item in candidates}
    assert {"chromium", "chromium-browser"} <= names
    result = _bs().check_chromium(env={}, path=str(tmp_path))
    assert result.action == "fail"
    assert str(tmp_path / "chromium") in result.message
    assert str(tmp_path / "chromium-browser") in result.message


def test_is_snap_path_classification() -> None:
    bs = _bs()
    assert bs.is_snap_path("/snap/bin/chromium") is True
    assert bs.is_snap_path("/usr/bin/chromium") is False


# --- Group C: CLI exit codes ------------------------------------------------------------------


def test_cli_good_browser_exits_zero_and_prints_path_and_version(tmp_path: Path) -> None:
    fake = _good(tmp_path)
    proc = _run_cli({"PATH": str(tmp_path)})
    assert proc.returncode == 0, proc.stderr
    assert str(fake) in proc.stdout
    assert "1.2.3" in proc.stdout


def test_cli_nothing_found_exits_two(tmp_path: Path) -> None:
    proc = _run_cli({"PATH": str(_empty_dir(tmp_path))})
    assert proc.returncode == 2, proc.stderr
    assert "chromium" in proc.stderr


def test_cli_broken_shim_exits_three(tmp_path: Path) -> None:
    shim = _shim(tmp_path)
    proc = _run_cli({"PATH": str(tmp_path)})
    assert proc.returncode == 3, proc.stderr
    assert str(shim) in proc.stderr
    assert "snap" in proc.stderr


def test_cli_ignores_opt_out(tmp_path: Path) -> None:
    proc = _run_cli({"PATH": str(_empty_dir(tmp_path)), "WISHENKA_SKIP_BROWSER_TESTS": "1"})
    assert proc.returncode == 2, proc.stderr


# --- Group D: chromium_executable fixture (nested pytest) -------------------------------------


def _nested_pytest(
    tmp_path: Path, path_dir: Path, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    work = tmp_path / "nested"
    work.mkdir()
    (work / "conftest.py").write_text(
        "from tests.conftest import chromium_executable  # noqa: F401\n", encoding="utf-8"
    )
    (work / "test_x.py").write_text(
        "def test_one(chromium_executable):\n"
        "    assert chromium_executable\n"
        "\n"
        "\n"
        "def test_two(chromium_executable):\n"
        "    assert chromium_executable\n",
        encoding="utf-8",
    )
    env = {"PATH": str(path_dir), "PYTHONPATH": str(ROOT)}
    env.update(extra_env or {})
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-rs",
            "--rootdir",
            str(work),
            str(work),
        ],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def test_fixture_missing_browser_errors_at_setup(tmp_path: Path) -> None:
    proc = _nested_pytest(tmp_path, _empty_dir(tmp_path))
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, out
    assert out.count("ERROR at setup of test_") == 2, out
    assert "2 errors" in out, out
    assert "passed" not in out, out
    assert "make deps-browser" in out, out


def test_fixture_opt_out_skips_with_reason(tmp_path: Path) -> None:
    proc = _nested_pytest(tmp_path, _empty_dir(tmp_path), {"WISHENKA_SKIP_BROWSER_TESTS": "1"})
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "2 skipped" in out, out
    assert "SKIPPED" in out and "chromium" in out.lower(), out


def test_fixture_opt_out_is_ignored_in_ci(tmp_path: Path) -> None:
    proc = _nested_pytest(
        tmp_path, _empty_dir(tmp_path), {"WISHENKA_SKIP_BROWSER_TESTS": "1", "CI": "true"}
    )
    out = proc.stdout + proc.stderr
    assert proc.returncode != 0, out
    assert out.count("ERROR at setup of test_") == 2, out
    assert "skipped" not in out, out


def test_fixture_gives_fake_browser_path_to_tests(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _good(bin_dir)
    proc = _nested_pytest(tmp_path, bin_dir)
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, out
    assert "2 passed" in out, out


# --- Group E: pyproject.toml ------------------------------------------------------------------


def test_pyproject_declares_websockets_dev_dependency() -> None:
    dev = _pyproject()["project"]["optional-dependencies"]["dev"]
    names = {m.group(0).lower() for item in dev if (m := re.match(r"^[A-Za-z0-9_.-]+", item))}
    assert "websockets" in names, f"websockets missing in dev extras: {dev}"


def test_pyproject_declares_browser_marker() -> None:
    markers = _pyproject()["tool"]["pytest"]["ini_options"].get("markers", [])
    assert any(str(item).startswith("browser") for item in markers), markers


# --- Group F: Makefile ------------------------------------------------------------------------


def test_make_deps_browser_dry_run_succeeds_without_pip() -> None:
    proc = _make_n("deps-browser")
    assert proc.returncode == 0, proc.stderr
    assert "pip install" not in proc.stdout


def test_make_help_lists_deps_browser() -> None:
    proc = _run(["make", "help"])
    assert proc.returncode == 0, proc.stderr
    assert "deps-browser" in proc.stdout


def test_makefile_declares_phony_deps_browser() -> None:
    assert ".PHONY: deps-browser" in MAKEFILE.read_text(encoding="utf-8")


def test_deps_browser_is_not_a_prerequisite_of_test_or_check() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    for target in ("test", "check"):
        match = re.search(rf"^{target}:([^#\n]*)", text, re.M)
        assert match, f"target {target} not found"
        assert "deps-browser" not in match.group(1)
        dry = _make_n(target)
        assert "apt-get" not in dry.stdout
        assert "tests.browser_support" not in dry.stdout


def test_deps_browser_has_no_venv_or_deps_prerequisite_and_guards_python() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    match = re.search(r"^deps-browser:([^#\n]*)", text, re.M)
    assert match, "target deps-browser not found in Makefile"
    prerequisites = match.group(1).split()
    assert "venv" not in prerequisites and "deps" not in prerequisites, prerequisites
    recipe = re.search(r"^deps-browser:.*\n((?:\t.*\n?)+)", text, re.M)
    assert recipe is not None and "test -x" in recipe.group(1)


def test_deps_browser_recipe_lines_start_with_tab() -> None:
    text = MAKEFILE.read_text(encoding="utf-8")
    assert re.search(r"^deps-browser:.*\n(\t.*\n?)+", text, re.M), (
        "deps-browser recipe missing or not TAB-indented"
    )


# --- Group G: CI ------------------------------------------------------------------------------


def test_ci_installs_browser_between_deps_and_check() -> None:
    text = CI_YML.read_text(encoding="utf-8")
    assert "make deps-browser" in text, "ci.yml has no 'make deps-browser' step"
    assert "make check" in text
    match = re.search(r"make deps(?![-\w])", text)
    assert match, "ci.yml has no plain 'make deps' step"
    assert match.start() < text.index("make deps-browser") < text.index("make check")


# --- Group H: guards (green by construction) --------------------------------------------------


def test_addopts_do_not_deselect_tests() -> None:
    addopts = _pyproject()["tool"]["pytest"]["ini_options"].get("addopts", "")
    tokens = shlex.split(addopts) if isinstance(addopts, str) else list(addopts)
    bad = [t for t in tokens if t.startswith(("-m", "-k", "--deselect"))]
    assert not bad, f"addopts hide tests: {bad}"


def test_ci_and_makefile_do_not_hide_browser_tests() -> None:
    for sample in (
        'pytest -m "not browser"',
        "pytest -m 'not browser'",
        "pytest -k browser",
        "pytest --deselect tests/x.py::t",
        "pytest --ignore=tests/test_browser_x.py",
    ):
        assert FORBIDDEN.search(sample), sample
    for sample in ("make deps-browser", "$(PYTHON) -m tests.browser_support"):
        assert not FORBIDDEN.search(sample), sample
    for path in (CI_YML, MAKEFILE):
        found = FORBIDDEN.search(path.read_text(encoding="utf-8"))
        assert found is None, f"{path.name} hides browser tests: {found and found.group(0)!r}"


# --- Group I: browser test modules declare marker and timeout (WISHENKA-110) -------------------

BROWSER_MODULE_TIMEOUT = 45
NEW_BROWSER_MODULES = {
    "test_wishlist_cards_browser.py",
    "test_wishlist_mouse_reorder_browser.py",
    "test_wishlist_touch_reorder_browser.py",
}


def _mark_name(node: ast.expr) -> tuple[str, ast.Call | None] | None:
    """Return ``(name, call)`` for ``pytest.mark.<name>`` or ``pytest.mark.<name>(...)``."""
    call = node if isinstance(node, ast.Call) else None
    target = call.func if call is not None else node
    if (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Attribute)
        and target.value.attr == "mark"
        and isinstance(target.value.value, ast.Name)
        and target.value.value.id == "pytest"
    ):
        return target.attr, call
    return None


def _module_marks(tree: ast.Module) -> list[tuple[str, ast.Call | None]]:
    """Marks assigned to module-level ``pytestmark`` (single mark, list or tuple)."""
    marks: list[tuple[str, ast.Call | None]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
        ):
            values = (
                node.value.elts if isinstance(node.value, ast.List | ast.Tuple) else [node.value]
            )
            marks.extend(m for v in values if (m := _mark_name(v)) is not None)
    return marks


def _tests_marked_browser(tree: ast.Module) -> bool:
    """True when every top-level ``test_*`` function carries ``@pytest.mark.browser``."""
    tests = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_")]
    return bool(tests) and all(
        any((m := _mark_name(d)) is not None and m[0] == "browser" for d in fn.decorator_list)
        for fn in tests
    )


def test_new_browser_modules_declare_marker_and_timeout() -> None:
    """Every ``tests/test_*_browser.py`` is marked ``browser`` with ``timeout(45)`` (no Chromium).

    Green by design once the WISHENKA-110 modules comply: this is a guard, not a repro. The
    ``browser`` mark may be module-level (``pytestmark``) or on every test function (the older
    ``test_wishlist_management_browser.py`` style); the timeout must be the module-level 45 s.
    """
    tests_dir = Path(__file__).resolve().parent
    modules = sorted(tests_dir.glob("test_*_browser.py"))
    missing = NEW_BROWSER_MODULES - {m.name for m in modules}
    assert not missing, f"browser test modules not found: {sorted(missing)}"
    problems: list[str] = []
    for module in modules:
        tree = ast.parse(module.read_text(encoding="utf-8"), filename=str(module))
        marks = _module_marks(tree)
        has_browser = any(name == "browser" for name, _ in marks) or _tests_marked_browser(tree)
        timeouts = [
            call.args[0].value
            for name, call in marks
            if name == "timeout"
            and call is not None
            and call.args
            and isinstance(call.args[0], ast.Constant)
        ]
        if not has_browser:
            problems.append(f"{module.name}: no 'browser' marker")
        if BROWSER_MODULE_TIMEOUT not in timeouts:
            problems.append(f"{module.name}: pytestmark lacks timeout({BROWSER_MODULE_TIMEOUT})")
    assert not problems, "; ".join(problems)


def test_browser_cdp_urls_match_base_template() -> None:
    """External script URLs intercepted in ``tests/browser_cdp.py`` match ``base.html``."""
    from tests.browser_cdp import HTMX_URL, JSON_ENC_URL, TELEGRAM_URL

    base_html = (
        Path(__file__).resolve().parent.parent / "wishenka" / "web" / "templates" / "base.html"
    ).read_text(encoding="utf-8")
    template_urls = set(re.findall(r'<script\s+src="(https://[^"]+)"', base_html))
    cdp_urls = {TELEGRAM_URL, HTMX_URL, JSON_ENC_URL}
    assert template_urls == cdp_urls, (
        f"base.html external script URLs {sorted(template_urls)} != "
        f"browser_cdp.py URLs {sorted(cdp_urls)}"
    )
