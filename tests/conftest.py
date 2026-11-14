"""Shared pytest fixtures."""

from __future__ import annotations

import contextlib
import os
import shutil
import socket
import threading
import time
from collections.abc import Callable, Generator, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
import pytest

from tests.browser_support import check_chromium

if TYPE_CHECKING:
    from tests.browser_cdp import CdpBrowser, CdpPage
    from tests.browser_helpers import Seeded

BROWSER_TEST_SECRET = "wishenka-browser-tests-secret-key"
OWNER_TELEGRAM_ID = 101
VIEWER_TELEGRAM_ID = 202
SERVER_START_TIMEOUT = 8.0
SERVER_STOP_TIMEOUT = 8.0


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


@pytest.fixture(scope="session")
def chromium_browser(
    chromium_executable: str, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[CdpBrowser]:
    """One headless Chromium for the whole session (temp profile, bounded shutdown)."""
    from tests.browser_cdp import CdpBrowser

    browser = CdpBrowser()
    browser.start(chromium_executable, tmp_path_factory.mktemp("chromium-profile"))
    try:
        yield browser
    finally:
        browser.stop()


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
) -> CdpPage:
    browser.ensure_alive()
    page = browser.new_page(viewport)
    pages.append(page)
    if token is not None:
        page.set_bearer(token)
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
        seeded: Seeded, *, as_user: str = "owner", viewport: tuple[int, int] = (412, 800)
    ) -> CdpPage:
        token = seeded.owner_token if as_user == "owner" else seeded.viewer_token
        url = f"{wishlist_server.base_url}/web/wishlists/{seeded.wishlist_id}"
        return _open_page(chromium_browser, _browser_pages, url, token, viewport)

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
        seeded: Seeded, *, as_user: str | None = None, viewport: tuple[int, int] = (412, 800)
    ) -> CdpPage:
        token = seeded.viewer_token if as_user == "viewer" else None
        url = f"{wishlist_server.base_url}/share/{seeded.public_token}"
        return _open_page(chromium_browser, _browser_pages, url, token, viewport)

    return factory
