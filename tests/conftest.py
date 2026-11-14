"""Shared pytest fixtures."""

import os

import pytest

from tests.browser_support import check_chromium


@pytest.fixture(scope="session")
def chromium_executable() -> str:
    """Path of a usable Chromium/Chrome; ERROR at setup if absent, SKIP only by local opt-out."""
    result = check_chromium(os.environ)
    if result.action == "ok" and result.executable is not None:
        return result.executable
    if result.action == "skip":
        pytest.skip(result.message)
    pytest.fail(result.message, pytrace=False)
