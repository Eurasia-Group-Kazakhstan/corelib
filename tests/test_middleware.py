from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from .conftest import SERVICE_KEY, make_app


@pytest.fixture
def client(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_missing_service_key(client):
    resp = client.get("/ping", headers={"X-Caller-Type": "backend"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Invalid or missing X-Service-Key"


def test_wrong_service_key(client):
    resp = client.get("/ping", headers={"X-Service-Key": "wrong", "X-Caller-Type": "backend"})
    assert resp.status_code == 403


def test_missing_caller_type(client):
    resp = client.get("/ping", headers={"X-Service-Key": SERVICE_KEY})
    assert resp.status_code == 422
    assert resp.json()["detail"] == "Invalid or missing X-Caller-Type"


def test_invalid_caller_type(client):
    resp = client.get("/ping", headers={"X-Service-Key": SERVICE_KEY, "X-Caller-Type": "admin"})
    assert resp.status_code == 422


@pytest.mark.parametrize("caller_type", ["backend", "Backend"])
def test_backend_without_authorization(client, caller_type):
    resp = client.get("/ping", headers={"X-Service-Key": SERVICE_KEY, "X-Caller-Type": caller_type})
    assert resp.status_code == 200


@pytest.mark.parametrize("caller_type", ["user", "User"])
def test_user_without_authorization(client, caller_type):
    resp = client.get("/ping", headers={"X-Service-Key": SERVICE_KEY, "X-Caller-Type": caller_type})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid or missing Authorization header"


def test_user_empty_bearer(client):
    resp = client.get("/ping", headers={
        "X-Service-Key": SERVICE_KEY,
        "X-Caller-Type": "user",
        "Authorization": "Bearer ",
    })
    assert resp.status_code == 401


def test_user_invalid_jwt(client):
    resp = client.get("/ping", headers={
        "X-Service-Key": SERVICE_KEY,
        "X-Caller-Type": "user",
        "Authorization": "Bearer not.a.jwt",
    })
    assert resp.status_code == 401


def test_user_valid_jwt(app):
    from corelib.auth import KeycloakTokenVerifier
    from corelib.schemas import TokenPayload

    fake_payload = TokenPayload(
        sub="user-123",
        iss="http://keycloak:8080/realms/testrealm",
        aud="test-client",
        exp=9999999999,
        iat=1000000000,
    )

    with patch.object(KeycloakTokenVerifier, "verify", new=AsyncMock(return_value=fake_payload)):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/ping", headers={
                "X-Service-Key": SERVICE_KEY,
                "X-Caller-Type": "user",
                "Authorization": "Bearer valid.token.here",
            })
    assert resp.status_code == 200


def test_user_expired_jwt(app):
    from fastapi import HTTPException
    from corelib.auth import KeycloakTokenVerifier

    async def raise_expired(_self, token):
        raise HTTPException(status_code=401, detail="Token has expired")

    with patch.object(KeycloakTokenVerifier, "verify", new=raise_expired):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/ping", headers={
                "X-Service-Key": SERVICE_KEY,
                "X-Caller-Type": "user",
                "Authorization": "Bearer expired.token",
            })
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Token has expired"
