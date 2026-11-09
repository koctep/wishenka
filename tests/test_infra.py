"""Tests for Wishenka repository infrastructure and baseline web application."""

import pytest

pytestmark = pytest.mark.timeout(10)


def test_package_version() -> None:
    """Package wishenka must be importable and expose __version__ 0.1.0."""
    import wishenka

    assert hasattr(wishenka, "__version__")
    assert wishenka.__version__ == "0.1.0"


def test_application_settings() -> None:
    """Settings must be loadable and have app_name configured as 'wishenka'."""
    from wishenka.config import Settings

    s = Settings()
    assert s.app_name == "wishenka"


def test_healthcheck_endpoint() -> None:
    """Application factory create_app must expose GET /healthz returning status ok."""
    from fastapi.testclient import TestClient

    from wishenka.web.app import create_app

    client = TestClient(create_app())
    res = client.get("/healthz")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}
