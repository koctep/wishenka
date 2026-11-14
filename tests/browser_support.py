"""Locate and probe a Chromium/Chrome binary for browser UI tests.

This is the single place that knows how a browser is found and validated. It is used by the
``chromium_executable`` fixture (``tests/conftest.py``) and by ``make deps-browser`` through
``python -m tests.browser_support``. Standard library only.
"""

import os
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

BIN_VAR = "WISHENKA_CHROMIUM_BIN"
SKIP_VAR = "WISHENKA_SKIP_BROWSER_TESTS"
DEFAULT_PROBE_TIMEOUT = 10.0
_NOT_CI = frozenset({"", "0", "false", "no"})

EXIT_OK = 0
EXIT_NOT_FOUND = 2
EXIT_BROKEN = 3


@dataclass(frozen=True)
class ProbeResult:
    """Outcome of running ``<browser> --version``."""

    ok: bool
    version: str
    detail: str


@dataclass(frozen=True)
class BrowserCheck:
    """Decision of ``check_chromium``: use the browser, skip the tests or fail."""

    action: Literal["ok", "skip", "fail"]
    executable: str | None
    message: str


def candidate_names() -> tuple[str, ...]:
    """Executable names searched on ``PATH``, in priority order."""
    return ("chromium", "chromium-browser", "google-chrome-stable", "google-chrome")


def is_ci(env: Mapping[str, str]) -> bool:
    """Return True when ``CI`` is set to a truthy value."""
    return env.get("CI", "").strip().casefold() not in _NOT_CI


def skip_requested(env: Mapping[str, str]) -> bool:
    """Return True only for the explicit local opt-out ``WISHENKA_SKIP_BROWSER_TESTS=1``."""
    return env.get(SKIP_VAR, "").strip() == "1"


def is_snap_path(path: str) -> bool:
    """Return True for an unresolved path under ``/snap/`` (no ``realpath``: it hides the shim)."""
    return path.startswith("/snap/")


def find_candidates(env: Mapping[str, str], path: str | None = None) -> list[str]:
    """List browser candidates; an explicit ``WISHENKA_CHROMIUM_BIN`` has no ``PATH`` fallback."""
    explicit = env.get(BIN_VAR, "").strip()
    if explicit:
        usable = os.path.isfile(explicit) and os.access(explicit, os.X_OK)
        return [explicit] if usable else []
    found: list[str] = []
    for name in candidate_names():
        located = shutil.which(name, path=path)
        if located is None:
            continue
        absolute = os.path.abspath(located)
        if absolute not in found:
            found.append(absolute)
    return found


def probe(executable: str, timeout: float = DEFAULT_PROBE_TIMEOUT) -> ProbeResult:
    """Run ``--version`` with a bounded time; never raises."""
    try:
        done = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return ProbeResult(False, "", f"--version did not finish within {timeout:g}s")
    except (OSError, ValueError) as error:
        return ProbeResult(False, "", f"cannot execute: {error}")
    out = done.stdout.strip()
    if done.returncode == 0 and out:
        return ProbeResult(True, out.splitlines()[0], "")
    text = (done.stderr.strip() or out)[:300]
    return ProbeResult(False, "", f"exit code {done.returncode}: {text}")


def _failure_lines(failures: Mapping[str, str]) -> list[str]:
    lines: list[str] = []
    snap = False
    for executable, detail in failures.items():
        lines.append(f"  - {executable}: {detail}")
        snap = snap or is_snap_path(executable) or "snap" in detail.casefold()
    if snap:
        lines.append(
            "Found a browser that does not run: it is a snap stub or snap is not installed. "
            "Snap Chromium is not supported (confinement: private /tmp, the profile in "
            "tmp_path may be unreachable); install Chromium from Debian (make deps-browser) "
            f"or Google Chrome and set {BIN_VAR}."
        )
    return lines


def missing_message(env: Mapping[str, str], failures: Mapping[str, str]) -> str:
    """Explain what was not found or does not start and how to fix it."""
    explicit = env.get(BIN_VAR, "").strip()
    lines: list[str] = []
    if explicit:
        lines.append(f"{BIN_VAR}={explicit} is not a usable Chromium/Chrome executable.")
    else:
        lines.append(
            "Chromium is required for browser UI tests: no usable browser found on PATH "
            f"(searched: {', '.join(candidate_names())})."
        )
    lines.extend(_failure_lines(failures))
    lines.append(
        f"Fix: run 'make deps-browser', or install Chromium/Chrome and set {BIN_VAR}. "
        "See doc/dev/testing.md."
    )
    lines.append(f"Local opt-out (ignored when CI is set): {SKIP_VAR}=1.")
    return "\n".join(lines)


def _resolve(
    env: Mapping[str, str], path: str | None, probe_timeout: float
) -> tuple[str | None, str, dict[str, str]]:
    """Return (executable, version, failures) for the first usable candidate."""
    failures: dict[str, str] = {}
    for candidate in find_candidates(env, path):
        result = probe(candidate, probe_timeout)
        if result.ok:
            return candidate, result.version, failures
        failures[candidate] = result.detail
    return None, "", failures


def check_chromium(
    env: Mapping[str, str],
    path: str | None = None,
    probe_timeout: float = DEFAULT_PROBE_TIMEOUT,
) -> BrowserCheck:
    """Find a usable browser and apply the fail/skip policy."""
    executable, version, failures = _resolve(env, path, probe_timeout)
    if executable is not None:
        message = f"{executable} {version}"
        if is_snap_path(executable):
            message += " (snap path: confinement may hide the profile in tmp_path)"
        return BrowserCheck("ok", executable, message)
    message = missing_message(env, failures)
    if skip_requested(env) and not is_ci(env):
        return BrowserCheck("skip", None, f"{SKIP_VAR}=1: browser tests skipped. {message}")
    return BrowserCheck("fail", None, message)


def main() -> int:
    """CLI for ``make deps-browser``: strict, ignores the opt-out. Exit codes 0/2/3."""
    env = os.environ
    executable, version, failures = _resolve(env, None, DEFAULT_PROBE_TIMEOUT)
    if executable is not None:
        print(f"{executable} {version}")
        return EXIT_OK
    print(missing_message(env, failures), file=sys.stderr)
    return EXIT_BROKEN if failures else EXIT_NOT_FOUND


if __name__ == "__main__":
    sys.exit(main())
