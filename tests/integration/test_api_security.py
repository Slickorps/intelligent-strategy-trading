"""Integration tests for API security hardening.

Covers settings-driven CORS, optional API-key authentication, and the
unified (non-leaking) error response format.
"""

import pytest
from fastapi.testclient import TestClient

from ist.api.main import create_app
from ist.core import config


@pytest.fixture
def app():
    """Create a fresh app using the default settings."""
    return create_app()


@pytest.fixture
def secure_app(monkeypatch):
    """Create an app with API-key authentication enabled."""
    monkeypatch.setattr(
        config, "_settings", config.Settings(api_key="secret-key"),
    )
    return create_app()


class TestSettingsSecurity:
    def test_cors_origin_list_parsing(self) -> None:
        settings = config.Settings(cors_origins="http://a.com, http://b.com ,")
        assert settings.cors_origin_list == ["http://a.com", "http://b.com"]

    def test_cors_defaults_to_localhost(self) -> None:
        origins = config.Settings().cors_origin_list
        assert "http://localhost:3000" in origins
        assert "http://localhost:8000" in origins


class TestApiKeyAuth:
    def test_open_when_no_key_configured(self, app) -> None:
        with TestClient(app) as client:
            assert client.get("/strategies").status_code == 200

    def test_protected_route_requires_key(self, secure_app) -> None:
        with TestClient(secure_app) as client:
            response = client.get("/strategies")

        assert response.status_code == 401
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "unauthorized"

    def test_valid_api_key_header(self, secure_app) -> None:
        with TestClient(secure_app) as client:
            response = client.get(
                "/strategies", headers={"X-API-Key": "secret-key"},
            )
        assert response.status_code == 200

    def test_valid_bearer_token(self, secure_app) -> None:
        with TestClient(secure_app) as client:
            response = client.get(
                "/strategies",
                headers={"Authorization": "Bearer secret-key"},
            )
        assert response.status_code == 200

    def test_invalid_api_key_rejected(self, secure_app) -> None:
        with TestClient(secure_app) as client:
            response = client.get(
                "/strategies", headers={"X-API-Key": "wrong"},
            )
        assert response.status_code == 401

    def test_health_and_version_are_exempt(self, secure_app) -> None:
        with TestClient(secure_app) as client:
            assert client.get("/health").status_code == 200
            assert client.get("/version").status_code == 200


class TestErrorResponses:
    def test_404_uses_unified_format(self, app) -> None:
        with TestClient(app) as client:
            response = client.get("/strategies/missing-id")

        assert response.status_code == 404
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "http_404"
        assert "missing-id" in body["error"]["message"]

    def test_validation_error_uses_unified_format(self, app) -> None:
        with TestClient(app) as client:
            response = client.post(
                "/strategies", json={"description": "missing name"},
            )

        assert response.status_code == 422
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "validation_error"
        assert body["error"]["details"]["errors"]

    def test_unhandled_exception_is_sanitized(self, app) -> None:
        @app.get("/_boom")
        async def boom():
            raise RuntimeError("sensitive internal detail")

        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.get("/_boom")

        assert response.status_code == 500
        body = response.json()
        assert body["success"] is False
        assert body["error"]["message"] == "An internal error occurred"
        assert "sensitive internal detail" not in response.text
