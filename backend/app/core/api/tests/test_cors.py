"""CORS policy tests for browser access from the local Genesis frontend."""

import re

import pytest
from fastapi.testclient import TestClient

from backend.app.core.core_services.config.settings import Settings, settings
from backend.app.main import app


@pytest.fixture
def client() -> TestClient:
    """Provide a client with the application lifespan active."""
    with TestClient(app) as test_client:
        yield test_client


def _allowed_origin(client: TestClient, origin: str) -> str | None:
    response = client.get("/api/system/services", headers={"Origin": origin})
    assert response.status_code == 200
    return response.headers.get("access-control-allow-origin")


def test_default_frontend_origins_are_allowed(client: TestClient) -> None:
    """Both spellings of the default Next.js address can call the API."""
    for origin in ("http://localhost:3000", "http://127.0.0.1:3000"):
        assert _allowed_origin(client, origin) == origin


def test_foreign_origins_are_not_allowed(client: TestClient) -> None:
    """Non-loopback sites never receive CORS permission."""
    assert _allowed_origin(client, "https://example.com") is None
    assert _allowed_origin(client, "http://localhost.example.com:3000") is None


@pytest.mark.skipif(settings.ENVIRONMENT != "development", reason="requires development settings")
def test_development_allows_fallback_frontend_port(client: TestClient) -> None:
    """Next.js on 3001 (when 3000 is busy) can still reach the backend."""
    assert _allowed_origin(client, "http://localhost:3001") == "http://localhost:3001"


def test_loopback_port_regex_is_development_only() -> None:
    """Any-port loopback access is disabled outside development."""
    development = Settings(ENVIRONMENT="development", _env_file=None)
    production = Settings(ENVIRONMENT="production", _env_file=None)

    assert production.cors_origin_regex is None
    pattern = development.cors_origin_regex
    assert pattern is not None
    for origin in ("http://localhost:3001", "http://127.0.0.1:4000", "http://[::1]:3000", "http://localhost"):
        assert re.fullmatch(pattern, origin)
    for origin in ("https://localhost:3000", "http://localhost.evil.com", "http://192.168.1.5:3000"):
        assert re.fullmatch(pattern, origin) is None


def test_cors_origins_are_configurable_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deployments can replace the default origin list without code changes."""
    monkeypatch.setenv("CORS_ORIGINS", '["https://genesis.example.com"]')

    assert Settings(_env_file=None).CORS_ORIGINS == ["https://genesis.example.com"]
