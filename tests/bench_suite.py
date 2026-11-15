"""Wall-clock benchmark of ``make test`` against the time budget (WISHENKA-166).

Usage::

    python -m tests.bench_suite --budget 120
    python -m tests.bench_suite --budget 120 --junit run1.xml --compare run2.xml

Runs ``make test`` once, prints CPU count, memory, wall time, memory low-water mark, test counts
and the exit code, and exits non-zero if the suite failed or the budget was exceeded. With
``--compare`` the set of passed test ids is compared with earlier JUnit files.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_INTERVAL = 1.0
SHM = Path("/dev/shm")


@dataclass(frozen=True)
class JunitResult:
    """Outcome of one JUnit file."""

    passed: frozenset[str]
    failed: frozenset[str]
    skipped: int

    @property
    def total(self) -> int:
        return len(self.passed) + len(self.failed) + self.skipped


def parse_junit(path: Path) -> JunitResult:
    """Passed/failed test ids and the skipped count of a pytest JUnit XML file."""
    passed: set[str] = set()
    failed: set[str] = set()
    skipped = 0
    for case in ET.parse(path).getroot().iter("testcase"):
        name = f"{case.get('classname', '')}::{case.get('name', '')}"
        if case.find("skipped") is not None:
            skipped += 1
        elif case.find("failure") is not None or case.find("error") is not None:
            failed.add(name)
        else:
            passed.add(name)
    return JunitResult(frozenset(passed), frozenset(failed), skipped)


def mem_available_mb() -> int:
    """``MemAvailable`` in MiB (0 if unreadable)."""
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) // 1024
    except (OSError, ValueError):
        pass
    return 0


def shm_used_mb() -> float:
    """Used space of ``/dev/shm`` in MiB (0 if absent)."""
    try:
        return shutil.disk_usage(SHM).used / (1024 * 1024)
    except OSError:
        return 0.0


class Sampler(threading.Thread):
    """Samples the memory low-water mark and the ``/dev/shm`` peak once per second."""

    def __init__(self) -> None:
        super().__init__(daemon=True)
        self._stop_event = threading.Event()
        self.min_available_mb = mem_available_mb()
        self.peak_shm_mb = 0.0

    def run(self) -> None:
        while not self._stop_event.wait(SAMPLE_INTERVAL):
            self.min_available_mb = min(self.min_available_mb, mem_available_mb())
            self.peak_shm_mb = max(self.peak_shm_mb, shm_used_mb())

    def finish(self) -> None:
        self._stop_event.set()
        self.join(5)


def _run(command: Sequence[str]) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=10)
    return result.stdout.strip()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--budget", type=float, default=120.0, help="wall-time budget in seconds")
    parser.add_argument("--junit", type=Path, default=None, help="where to keep the JUnit file")
    parser.add_argument(
        "--compare", type=Path, nargs="*", default=[], help="earlier JUnit files to compare with"
    )
    parser.add_argument("--target", default="test", help="Makefile target to run (default: test)")
    args = parser.parse_args(argv)

    workdir = None if args.junit else Path(tempfile.mkdtemp(prefix="wk-bench-"))
    junit = args.junit or (workdir / "junit.xml" if workdir else Path())
    print(f"nproc: {_run(['nproc'])}")
    print(_run(["free", "-m"]))
    command = ["make", args.target, f"PYTEST_ARGS=--junitxml={junit}"]
    print("command:", " ".join(command), flush=True)
    sampler = Sampler()
    sampler.start()
    started = time.monotonic()
    code = subprocess.run(command, cwd=ROOT, check=False).returncode
    wall = time.monotonic() - started
    sampler.finish()

    ok = code == 0
    print(f"\nexit code: {code}")
    print(f"wall time: {wall:.1f} s (budget {args.budget:.0f} s)")
    print(f"memory low-water mark (MemAvailable): {sampler.min_available_mb} MiB")
    print(f"/dev/shm peak used: {sampler.peak_shm_mb:.1f} MiB")
    if junit.exists():
        current = parse_junit(junit)
        print(
            f"tests: {current.total} total, {len(current.passed)} passed, "
            f"{len(current.failed)} failed/errors, {current.skipped} skipped"
        )
        ok = ok and not current.failed and not current.skipped
        for name in sorted(current.failed)[:10]:
            print(f"FAILED: {name}")
        if current.skipped:
            print("FAIL: skipped tests are not allowed in the benchmark run")
        for other_path in args.compare:
            other = parse_junit(other_path)
            same = other.passed == current.passed
            print(f"passed set equals {other_path}: {same}")
            ok = ok and same
    else:
        print("no JUnit file written")
        ok = False
    if wall > args.budget:
        print(f"FAIL: wall time above the {args.budget:.0f} s budget")
        ok = False
    if workdir is not None:
        shutil.rmtree(workdir, ignore_errors=True)
    print("RESULT:", "OK" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
