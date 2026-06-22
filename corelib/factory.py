from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from importlib.metadata import version as _pkg_version

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from .auth import KeycloakTokenVerifier
from .middleware import AuthMiddleware
from .registry import RegistryConfig, deregister_service, register_service


def create_app(
    *,
    name: str,
    display_name: str,
    description: str = "",
    base_url: str,
    health_url: str,
    path_prefix: str = "",
    version: str = "1.0.0",
    registry_url: str,
    service_key: str,
    keycloak_server_url: str,
    keycloak_realm: str,
    keycloak_client_id: str,
    keycloak_audience: str,
    keycloak_client_secret: str | None = None,
    keycloak_public_key: str | None = None,
    keycloak_issuer: str | None = None,
) -> FastAPI:
    registry_config = RegistryConfig(
        name=name,
        display_name=display_name,
        description=description,
        base_url=base_url,
        health_url=health_url,
        path_prefix=path_prefix,
        version=version,
        registry_url=registry_url,
        service_key=service_key,
    )

    verifier = KeycloakTokenVerifier(
        server_url=keycloak_server_url,
        realm=keycloak_realm,
        client_id=keycloak_client_id,
        audience=keycloak_audience,
        client_secret=keycloak_client_secret,
        public_key=keycloak_public_key,
        issuer=keycloak_issuer,
    )

    _log = logging.getLogger("uvicorn.error")

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            corelib_ver = _pkg_version("corelib")
        except Exception:
            corelib_ver = "unknown"
        _log.info(
            "corelib v%s | starting service '%s' v%s | registry: %s",
            corelib_ver,
            name,
            version,
            registry_url,
        )
        await register_service(application.openapi(), registry_config)
        yield
        await deregister_service(registry_config)

    app = FastAPI(
        title=display_name,
        description=description,
        version=version,
        lifespan=lifespan,
    )

    app.add_middleware(
        AuthMiddleware,
        service_key=service_key,
        verifier=verifier,
    )

    def _custom_openapi():
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=display_name,
            version=version,
            description=description,
            routes=app.routes,
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {}).update({
            "ServiceKey": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Service-Key",
                "description": "Общий ключ доступа к сервису",
            },
            "CallerType": {
                "type": "apiKey",
                "in": "header",
                "name": "X-Caller-Type",
                "description": "Тип вызывающей стороны: user, User, backend, Backend",
            },
            "BearerAuth": {
                "type": "http",
                "scheme": "bearer",
                "description": "JWT-токен Keycloak (только для X-Caller-Type: user)",
            },
        })
        security = [{"ServiceKey": [], "CallerType": [], "BearerAuth": []}]
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if isinstance(operation, dict):
                    operation.setdefault("security", security)
        app.openapi_schema = schema
        return schema

    app.openapi = _custom_openapi

    return app
