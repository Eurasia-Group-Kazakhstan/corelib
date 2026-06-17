from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from corelib import create_app

SERVICE_KEY = "test-secret"
REALM = "testrealm"
SERVER_URL = "http://keycloak:8080"
CLIENT_ID = "test-client"
AUDIENCE = "test-client"


def make_app(**extra):
    with patch("corelib.registry.register_service", new=AsyncMock()):
        with patch("corelib.registry.deregister_service", new=AsyncMock()):
            app = create_app(
                name="test-service",
                display_name="Test Service",
                description="Test",
                base_url="http://localhost:8000",
                health_url="http://localhost:8000/health",
                path_prefix="/test",
                version="1.0.0",
                registry_url="http://registry:8000/api/services",
                service_key=SERVICE_KEY,
                keycloak_server_url=SERVER_URL,
                keycloak_realm=REALM,
                keycloak_client_id=CLIENT_ID,
                keycloak_audience=AUDIENCE,
                **extra,
            )

    from fastapi import APIRouter
    router = APIRouter()

    @router.get("/ping")
    async def ping():
        return {"pong": True}

    app.include_router(router)
    return app


@pytest.fixture
def app():
    return make_app()


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def valid_headers():
    return {
        "X-Service-Key": SERVICE_KEY,
        "X-Caller-Type": "backend",
    }
