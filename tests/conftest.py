"""Shared pytest fixtures."""

from __future__ import annotations

import contextlib
import faulthandler
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid
from collections.abc import Callable, Generator, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from tests import xdist_support
from tests.browser_support import check_chromium

if TYPE_CHECKING:
    from tests.browser_cdp import CdpBrowser, CdpPage
    from tests.browser_helpers import Seeded

BROWSER_TEST_SECRET = "wishenka-browser-tests-secret-key"
OWNER_TELEGRAM_ID = 101
VIEWER_TELEGRAM_ID = 202
SERVER_START_TIMEOUT = 8.0
SERVER_STOP_TIMEOUT = 8.0
SESSION_END_DUMP_SECONDS = 120


@pytest.fixture(scope="session")
def chromium_executable() -> str:
    """Path of a usable Chromium/Chrome; ERROR at setup if absent, SKIP only by local opt-out."""
    result = check_chromium(os.environ)
    if result.action == "ok" and result.executable is not None:
        return result.executable
    if result.action == "skip":
        pytest.skip(result.message)
    pytest.fail(result.message, pytrace=False)


@dataclass(frozen=True)
class BrowserServer:
    """A running application instance on its own database copy (one per test)."""

    base_url: str
    owner_token: str
    viewer_token: str


# --- parallel run and fast test storage (WISHENKA-166) ----------------------------------------

_RUN_DIRS: pytest.StashKey[list[Path]] = pytest.StashKey()
_EXIT_STATUS: pytest.StashKey[int] = pytest.StashKey()


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_auto_num_workers(config: pytest.Config) -> int:
    """Cap ``-n auto`` by CPUs, free memory and storage speed (optional: xdist may be absent)."""
    workers, warning = xdist_support.plan_workers(os.environ)
    if warning is not None:
        sys.stderr.write(f"WARNING: {warning}\n")
    return workers


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Controller only: put ``tmp_path`` and ``tempfile`` on fast storage, keep a disk directory.

    Workers inherit ``TMPDIR`` and ``WISHENKA_TEST_DISK_TMPDIR`` from the controller and get their
    ``basetemp`` from it, so nothing is decided twice.
    """
    if hasattr(config, "workerinput"):
        return
    disk_base = os.environ.get(xdist_support.ENV_DISK_TMPDIR) or tempfile.gettempdir()
    os.environ[xdist_support.ENV_DISK_TMPDIR] = disk_base
    xdist_support.remove_stale_disk_dirs(Path(disk_base))
    plan = xdist_support.plan_storage(os.environ)
    if plan.basetemp is None or plan.tmpdir is None or config.option.basetemp:
        return  # no fast storage, or the user chose ``--basetemp``: leave pytest's defaults
    xdist_support.remove_stale(plan.basetemp.parent)
    plan.tmpdir.mkdir(parents=True, exist_ok=True)
    os.environ["TMPDIR"] = str(plan.tmpdir)
    tempfile.tempdir = str(plan.tmpdir)
    config.option.basetemp = str(plan.basetemp)
    config.stash[_RUN_DIRS] = [plan.basetemp, plan.tmpdir]


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Remember the result; arm a stack dump in case teardown or worker shutdown hangs."""
    session.config.stash[_EXIT_STATUS] = int(exitstatus)
    faulthandler.dump_traceback_later(SESSION_END_DUMP_SECONDS, exit=False)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Controller only: remove the fast directories after a green run, keep them on failure."""
    faulthandler.cancel_dump_traceback_later()
    directories = config.stash.get(_RUN_DIRS, [])
    if not directories:
        return
    if config.stash.get(_EXIT_STATUS, 1) == 0:
        for directory in directories:
            shutil.rmtree(directory, ignore_errors=True)


def pytest_terminal_summary(terminalreporter: Any, exitstatus: int, config: pytest.Config) -> None:
    """Controller only: after a failed run say where the test files were kept (in report order)."""
    directories = config.stash.get(_RUN_DIRS, [])
    if directories and exitstatus != 0:
        terminalreporter.write_line(
            f"test files kept for diagnosis: {directories[0]} "
            "(the next run removes it once this process is gone)"
        )


@pytest.fixture(scope="session")
def _default_db_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("default-db")


@pytest.fixture(autouse=True)
def _isolated_default_database(
    _default_db_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    """Keep ``Settings()`` away from the repository's ``data/wishenka.db`` (hazard H1).

    Tests that build ``Settings()`` without arguments would otherwise write one shared file, which
    is unsafe under xdist and mutates the working tree. Explicit ``database_url=`` still wins.
    """
    database = _default_db_dir / f"{uuid.uuid4().hex}.db"
    monkeypatch.setenv("WISHENKA_DATABASE_URL", f"sqlite+aiosqlite:///{database}")
    monkeypatch.setenv("WISHENKA_SQLITE_DB_PATH", str(database))
    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, Any, None]:
    """Remember each phase report on the item so fixtures can see whether the test failed."""
    outcome = yield
    report = outcome.get_result()
    item.stash.setdefault(_REPORTS, {})[report.when] = report
    if report.when == "call" and report.failed:
        for number, page in enumerate(item.stash.get(_PAGES, [])):
            with contextlib.suppress(Exception):
                report.sections.append((f"Page {number} diagnostics", page.snapshot()))


_REPORTS: pytest.StashKey[dict[str, pytest.TestReport]] = pytest.StashKey()
_PAGES: pytest.StashKey[Iterable[CdpPage]] = pytest.StashKey()


def _test_failed(request: pytest.FixtureRequest) -> bool:
    report = request.node.stash.get(_REPORTS, {}).get("call")
    return report is not None and report.failed


@pytest.fixture
def chromium_profile_dir() -> Iterator[Path]:
    """Chromium profile directory on disk (up to 100 MiB, tmpfs is small), removed after."""
    path = xdist_support.disk_mkdtemp("chromium")
    try:
        yield path / "profile"
    finally:
        shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session")
def chromium_browser(chromium_executable: str) -> Iterator[CdpBrowser]:
    """One headless Chromium for the whole session (disk profile, bounded shutdown)."""
    from tests.browser_cdp import CdpBrowser

    profile_root = xdist_support.disk_mkdtemp("chromium")
    browser = CdpBrowser()
    try:
        browser.start(chromium_executable, profile_root / "profile")
        yield browser
    finally:
        browser.stop()
        shutil.rmtree(profile_root, ignore_errors=True)


@pytest.fixture(scope="session")
def migrated_db_template(
    chromium_executable: str, tmp_path_factory: pytest.TempPathFactory
) -> Path:
    """Database file with all migrations applied, created once and copied per test."""
    from fastapi.testclient import TestClient

    from wishenka.config import Settings
    from wishenka.web.app import create_app

    template = tmp_path_factory.mktemp("db-template") / "template.db"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{template}", secret_key=BROWSER_TEST_SECRET
    )
    with TestClient(create_app(settings)):
        pass  # lifespan start runs the migrations, lifespan end disposes the engines
    for suffix in ("-wal", "-shm"):
        leftover = template.with_name(template.name + suffix)
        assert not leftover.exists() or leftover.stat().st_size == 0, f"{leftover} not checkpointed"
    return template


@pytest.fixture
def wishlist_server(migrated_db_template: Path, tmp_path: Path) -> Iterator[BrowserServer]:
    """Application on a random 127.0.0.1 port with a private copy of the migrated database."""
    import uvicorn

    from wishenka.auth.session import SessionTokenService
    from wishenka.config import Settings
    from wishenka.web.app import create_app

    database = tmp_path / "browser.db"
    shutil.copyfile(migrated_db_template, database)
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{database}", secret_key=BROWSER_TEST_SECRET
    )
    listen = socket.socket()
    listen.bind(("127.0.0.1", 0))
    listen.listen(128)
    port = listen.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(create_app(settings), log_level="error", lifespan="on"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listen]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + SERVER_START_TIMEOUT
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started, "local test server did not start"
        sessions = SessionTokenService(settings.secret_key)
        yield BrowserServer(
            base_url=f"http://127.0.0.1:{port}",
            owner_token=sessions.create_token(OWNER_TELEGRAM_ID, "Owner"),
            viewer_token=sessions.create_token(VIEWER_TELEGRAM_ID, "Viewer"),
        )
    finally:
        server.should_exit = True
        thread.join(SERVER_STOP_TIMEOUT)
        listen.close()
        assert not thread.is_alive(), "local test server did not stop"


@pytest.fixture
def seed_wishlist(wishlist_server: BrowserServer) -> Callable[..., Seeded]:
    """Factory ``seed_wishlist(titles, *, quantities=None) -> Seeded`` (own server and database).

    Creates the wishlist and its items over the REST API of the per-test server. Item ids in
    ``Seeded.item_ids`` are in display order.
    """
    from tests.browser_helpers import Seeded

    def factory(titles: Sequence[str], *, quantities: Sequence[int] | None = None) -> Seeded:
        headers = {"Authorization": f"Bearer {wishlist_server.owner_token}"}
        with httpx.Client(base_url=wishlist_server.base_url, headers=headers, timeout=10) as api:
            created = api.post("/api/wishlists", json={"name": "Browser wishlist"})
            created.raise_for_status()
            wishlist = created.json()
            item_ids: list[str] = []
            for index, wish_title in enumerate(titles):
                quantity = quantities[index] if quantities is not None else 1
                response = api.post(
                    f"/api/wishlists/{wishlist['id']}/items",
                    json={"title": wish_title, "quantity": quantity},
                )
                response.raise_for_status()
                item_ids.append(str(response.json()["id"]))
        return Seeded(
            wishlist_id=int(wishlist["id"]),
            public_token=str(wishlist["share_token"]),
            item_ids=item_ids,
            owner_token=wishlist_server.owner_token,
            viewer_token=wishlist_server.viewer_token,
        )

    return factory


@pytest.fixture
def _browser_pages(
    request: pytest.FixtureRequest, chromium_browser: CdpBrowser, tmp_path: Path
) -> Iterator[list[CdpPage]]:
    """Tabs opened by the factories; closed (and dumped when the test failed) at teardown."""
    pages: list[CdpPage] = []
    request.node.stash[_PAGES] = pages
    yield pages
    try:
        if _test_failed(request):
            for number, page in enumerate(pages):
                with contextlib.suppress(Exception):
                    diagnostics = page.snapshot()
                    (tmp_path / f"diagnostics-{number}.txt").write_text(diagnostics, "utf-8")
                with contextlib.suppress(Exception):
                    page.screenshot(tmp_path / f"failure-{number}.png")
    finally:
        for page in pages:
            page.close()


def _open_page(
    browser: CdpBrowser,
    pages: list[CdpPage],
    url: str,
    token: str | None,
    viewport: tuple[int, int],
    *,
    accept_language: str | None = None,
) -> CdpPage:
    browser.ensure_alive()
    page = browser.new_page(viewport)
    pages.append(page)
    if token is not None:
        page.set_bearer(token, accept_language=accept_language)
    page.navigate(url)
    return page


@pytest.fixture
def wishlist_page(
    chromium_browser: CdpBrowser, wishlist_server: BrowserServer, _browser_pages: list[CdpPage]
) -> Callable[..., CdpPage]:
    """Factory ``wishlist_page(seeded, *, as_user="owner", viewport=(412, 800)) -> CdpPage``.

    Opens ``/web/wishlists/<id>`` in a fresh tab with the Bearer token of ``as_user``
    (``"owner"`` or ``"viewer"``), offline stubs for the three external scripts and touch
    emulation disabled (tests call ``CdpPage.enable_touch`` when needed).
    """

    def factory(
        seeded: Seeded,
        *,
        as_user: str = "owner",
        viewport: tuple[int, int] = (412, 800),
        accept_language: str | None = None,
    ) -> CdpPage:
        token = seeded.owner_token if as_user == "owner" else seeded.viewer_token
        url = f"{wishlist_server.base_url}/web/wishlists/{seeded.wishlist_id}"
        return _open_page(
            chromium_browser,
            _browser_pages,
            url,
            token,
            viewport,
            accept_language=accept_language,
        )

    return factory


@pytest.fixture
def share_page(
    chromium_browser: CdpBrowser, wishlist_server: BrowserServer, _browser_pages: list[CdpPage]
) -> Callable[..., CdpPage]:
    """Factory ``share_page(seeded, *, as_user=None, viewport=(412, 800)) -> CdpPage``.

    Opens ``/share/<token>``: anonymous when ``as_user`` is ``None``, otherwise with the Bearer
    token of ``"viewer"`` (a logged-in non-owner).
    """

    def factory(
        seeded: Seeded,
        *,
        as_user: str | None = None,
        viewport: tuple[int, int] = (412, 800),
        accept_language: str | None = None,
    ) -> CdpPage:
        token = seeded.viewer_token if as_user == "viewer" else None
        url = f"{wishlist_server.base_url}/share/{seeded.public_token}"
        return _open_page(
            chromium_browser,
            _browser_pages,
            url,
            token,
            viewport,
            accept_language=accept_language,
        )

    return factory
