from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

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

    @asynccontextmanager
    async def lifespan(application: FastAPI):
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

    return app
