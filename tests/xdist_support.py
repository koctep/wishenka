"""Helpers that decide where and how wide the test suite runs (WISHENKA-166).

Pure standard-library functions, no pytest import: they are unit-tested by
``tests/test_parallel_run_contract.py`` and used by the hooks in ``tests/conftest.py``.

Why storage matters: on a virtiofs ``/tmp`` one ``fsync`` costs 11 ms alone and 75 ms with six
concurrent writers, so the per-test SQLite migrations dominate the run. On tmpfs the same suite
needs about a minute with several workers (see ``ai-tasks/WISHENKA-166/20-architecture.md``).
"""

from __future__ import annotations

import contextlib
import os
import shutil
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FAST_BASE = Path("/dev/shm")
MIN_FREE_MB = 48
RESERVE_MB = 1200
PER_WORKER_MB = 600
FSYNC_SAMPLES = 5
FSYNC_FAST_SECONDS = 0.002
BASE_PREFIX = "wishenka-pytest-"

ENV_FAST_TMPDIR = "WISHENKA_TEST_TMPDIR"
ENV_DISK_TMPDIR = "WISHENKA_TEST_DISK_TMPDIR"
ENV_WORKERS = "WISHENKA_TEST_WORKERS"
ENV_DISK_VALUE = "disk"

SLOW_STORAGE_WARNING = (
    "slow test storage: running with one worker; expected about 16 minutes; "
    f"set {ENV_FAST_TMPDIR} to a fast directory (for example /dev/shm)"
)


def choose_workers(
    cpu: int,
    mem_mb: int,
    fast_storage: bool,
    reserve_mb: int = RESERVE_MB,
    per_worker_mb: int = PER_WORKER_MB,
) -> int:
    """Number of xdist workers: bounded by CPUs and memory, one on slow storage (never zero)."""
    if not fast_storage:
        return 1
    return max(1, min(cpu, (mem_mb - reserve_mb) // per_worker_mb))


def pick_fast_basetemp(
    candidate: Path = DEFAULT_FAST_BASE, min_free_mb: int = MIN_FREE_MB
) -> Path | None:
    """Unique per-run directory name under ``candidate``, or ``None`` if it is unusable.

    The directory is not created. ``candidate`` must exist, be writable and have enough room.
    """
    candidate = Path(candidate)
    if not candidate.is_dir() or not os.access(candidate, os.W_OK | os.X_OK):
        return None
    if shutil.disk_usage(candidate).free < min_free_mb * 1024 * 1024:
        return None
    return candidate / f"{BASE_PREFIX}{os.getuid()}-{os.getpid()}"


def fsync_is_fast(path: Path) -> bool:
    """True if the median of five 4 KB ``fsync`` calls in ``path`` takes at most 2 ms."""
    samples: list[float] = []
    with tempfile.TemporaryFile(dir=path) as handle:
        for _ in range(FSYNC_SAMPLES):
            handle.write(b"x" * 4096)
            handle.flush()
            started = time.perf_counter()
            os.fsync(handle.fileno())
            samples.append(time.perf_counter() - started)
    return sorted(samples)[len(samples) // 2] <= FSYNC_FAST_SECONDS


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def remove_stale(base: Path) -> list[Path]:
    """Remove run directories of this user whose owning process is gone; return what was removed."""
    removed: list[Path] = []
    prefix = f"{BASE_PREFIX}{os.getuid()}-"
    try:
        entries = list(base.iterdir())
    except OSError:
        return removed
    for entry in entries:
        if not entry.name.startswith(prefix):
            continue
        pid_text = entry.name[len(prefix) :].split("-", 1)[0]
        if not pid_text.isdigit() or _pid_alive(int(pid_text)):
            continue
        shutil.rmtree(entry, ignore_errors=True)
        removed.append(entry)
    return removed


def remove_stale_disk_dirs(base: Path) -> list[Path]:
    """Remove ``wk-<kind>-<pid>-*`` directories (see ``disk_mkdtemp``) of dead processes."""
    removed: list[Path] = []
    try:
        entries = list(base.iterdir())
    except OSError:
        return removed
    for entry in entries:
        parts = entry.name.split("-")
        if len(parts) < 4 or parts[0] != "wk" or not parts[2].isdigit():
            continue
        if entry.stat().st_uid != os.getuid() or _pid_alive(int(parts[2])):
            continue
        shutil.rmtree(entry, ignore_errors=True)
        removed.append(entry)
    return removed


def available_memory_mb(
    meminfo: Path = Path("/proc/meminfo"), cgroup_max: Path = Path("/sys/fs/cgroup/memory.max")
) -> int:
    """``MemAvailable`` in MiB, capped by a finite cgroup ``memory.max``; large if unknown."""
    available = 10**6
    with contextlib.suppress(OSError, ValueError, IndexError):
        for line in meminfo.read_text(encoding="ascii").splitlines():
            if line.startswith("MemAvailable:"):
                available = int(line.split()[1]) // 1024
    with contextlib.suppress(OSError, ValueError):
        limit = cgroup_max.read_text(encoding="ascii").strip()
        if limit.isdigit():
            available = min(available, int(limit) // (1024 * 1024))
    return available


def cpu_count() -> int:
    """CPUs this process may use (affinity-aware)."""
    return len(os.sched_getaffinity(0))


@dataclass(frozen=True)
class StoragePlan:
    """Where the run keeps its temporary files."""

    basetemp: Path | None  # ``tmp_path`` root (fast), ``None`` keeps pytest's default
    tmpdir: Path | None  # ``TMPDIR`` for ``tempfile`` users (fast), ``None`` keeps the default
    fast: bool  # fast storage available (tmpfs chosen or the default directory passed the probe)


def plan_storage(environ: Mapping[str, str]) -> StoragePlan:
    """Choose the fast directory: ``$WISHENKA_TEST_TMPDIR``, else tmpfs, else probe the default."""
    requested = environ.get(ENV_FAST_TMPDIR, "")
    if requested != ENV_DISK_VALUE:
        base = pick_fast_basetemp(Path(requested) if requested else DEFAULT_FAST_BASE)
        if base is not None:
            return StoragePlan(base, base.with_name(base.name + "-tmp"), True)
    default = Path(tempfile.gettempdir())
    try:
        fast = fsync_is_fast(default)
    except OSError:
        fast = False
    return StoragePlan(None, None, fast)


def plan_workers(environ: Mapping[str, str]) -> tuple[int, str | None]:
    """Worker count for ``-n auto`` plus an optional warning for the terminal."""
    override = environ.get(ENV_WORKERS, "")
    if override.isdigit() and int(override) > 0:
        return int(override), None
    storage = plan_storage(environ)
    workers = choose_workers(cpu_count(), available_memory_mb(), storage.fast)
    return workers, None if storage.fast else SLOW_STORAGE_WARNING


def disk_mkdtemp(kind: str) -> Path:
    """Directory ``wk-<kind>-<pid>-*`` on the original (disk, exec-capable) temp area.

    The pid in the name lets ``remove_stale_disk_dirs`` clean up after a killed run.
    """
    base = os.environ.get(ENV_DISK_TMPDIR) or tempfile.gettempdir()
    return Path(tempfile.mkdtemp(prefix=f"wk-{kind}-{os.getpid()}-", dir=base))
