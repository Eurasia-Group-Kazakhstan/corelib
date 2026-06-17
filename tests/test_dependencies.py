from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from corelib import TokenPayload, get_token_payload, has_role, require_token_payload
from corelib.auth import KeycloakTokenVerifier

from .conftest import SERVICE_KEY, make_app

FAKE_PAYLOAD = TokenPayload(
    sub="user-abc",
    iss="http://keycloak:8080/realms/testrealm",
    aud="test-client",
    exp=9999999999,
    iat=1000000000,
    preferred_username="testuser",
    realm_access={"roles": ["viewer", "admin"]},
    resource_access={"orders": {"roles": ["order-manager"]}},
)

USER_HEADERS = {
    "X-Service-Key": SERVICE_KEY,
    "X-Caller-Type": "user",
    "Authorization": "Bearer fake.token",
}

BACKEND_HEADERS = {
    "X-Service-Key": SERVICE_KEY,
    "X-Caller-Type": "backend",
}


def make_client_with_routes(extra_routes_fn):
    app = make_app()
    router = APIRouter()
    extra_routes_fn(router)
    app.include_router(router)
    return app


def test_get_token_payload_user():
    app = make_client_with_routes(lambda r: r.add_api_route(
        "/payload",
        lambda payload: {"sub": payload.sub} if payload else {"sub": None},
        dependencies=[],
        response_model=None,
    ))

    @app.get("/payload-test")
    async def _ep(payload: TokenPayload | None = Depends(get_token_payload)):
        return {"sub": payload.sub if payload else None}

    with patch.object(KeycloakTokenVerifier, "verify", new=AsyncMock(return_value=FAKE_PAYLOAD)):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/payload-test", headers=USER_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["sub"] == "user-abc"


def test_get_token_payload_backend():
    app = make_app()

    @app.get("/payload-test")
    async def _ep(payload: TokenPayload | None = Depends(get_token_payload)):
        return {"has_payload": payload is not None}

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/payload-test", headers=BACKEND_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["has_payload"] is False


def test_require_token_payload_user():
    app = make_app()

    @app.get("/require-test")
    async def _ep(payload: TokenPayload = Depends(require_token_payload)):
        return {"sub": payload.sub}

    with patch.object(KeycloakTokenVerifier, "verify", new=AsyncMock(return_value=FAKE_PAYLOAD)):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/require-test", headers=USER_HEADERS)
    assert resp.status_code == 200
    assert resp.json()["sub"] == "user-abc"


def test_require_token_payload_backend_returns_401():
    app = make_app()

    @app.get("/require-test")
    async def _ep(payload: TokenPayload = Depends(require_token_payload)):
        return {"sub": payload.sub}

    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.get("/require-test", headers=BACKEND_HEADERS)
    assert resp.status_code == 401


def test_has_role_realm_present():
    app = make_app()

    @app.get("/admin-test")
    async def _ep(_: None = Depends(has_role("admin"))):
        return {"ok": True}

    with patch.object(KeycloakTokenVerifier, "verify", new=AsyncMock(return_value=FAKE_PAYLOAD)):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/admin-test", headers=USER_HEADERS)
    assert resp.status_code == 200


def test_has_role_realm_absent():
    app = make_app()

    @app.get("/superuser-test")
    async def _ep(_: None = Depends(has_role("superuser"))):
        return {"ok": True}

    with patch.object(KeycloakTokenVerifier, "verify", new=AsyncMock(return_value=FAKE_PAYLOAD)):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/superuser-test", headers=USER_HEADERS)
    assert resp.status_code == 403


def test_has_role_client_present():
    app = make_app()

    @app.get("/client-role-test")
    async def _ep(_: None = Depends(has_role("order-manager", client_id="orders"))):
        return {"ok": True}

    with patch.object(KeycloakTokenVerifier, "verify", new=AsyncMock(return_value=FAKE_PAYLOAD)):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/client-role-test", headers=USER_HEADERS)
    assert resp.status_code == 200


def test_has_role_client_absent():
    app = make_app()

    @app.get("/client-role-test")
    async def _ep(_: None = Depends(has_role("nonexistent-role", client_id="orders"))):
        return {"ok": True}

    with patch.object(KeycloakTokenVerifier, "verify", new=AsyncMock(return_value=FAKE_PAYLOAD)):
        with TestClient(app, raise_server_exceptions=False) as c:
            resp = c.get("/client-role-test", headers=USER_HEADERS)
    assert resp.status_code == 403
