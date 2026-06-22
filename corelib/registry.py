from __future__ import annotations

import dataclasses
import logging
from typing import Any

import httpx

from .schemas import ServiceRegistrationPayload

logger = logging.getLogger("uvicorn.error")


@dataclasses.dataclass
class RegistryConfig:
    name: str
    display_name: str
    description: str
    base_url: str
    health_url: str
    path_prefix: str
    version: str
    registry_url: str
    service_key: str


async def register_service(
    openapi_schema: dict[str, Any],
    config: RegistryConfig,
) -> None:
    payload = ServiceRegistrationPayload(
        name=config.name,
        display_name=config.display_name,
        description=config.description,
        base_url=config.base_url,
        health_url=config.health_url,
        path_prefix=config.path_prefix,
        version=config.version,
        openapi_schema=openapi_schema,
    )

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                config.registry_url,
                json=payload.model_dump(),
                headers={"X-Service-Key": config.service_key},
                timeout=10.0,
            )
            response.raise_for_status()
            logger.info(
                "Service '%s' registered at %s (status %s)",
                config.name,
                config.registry_url,
                response.status_code,
            )
        except Exception as exc:
            logger.error(
                "Failed to register service '%s' at %s: %s",
                config.name,
                config.registry_url,
                exc,
            )


async def deregister_service(config: RegistryConfig) -> None:
    url = f"{config.registry_url.rstrip('/')}/{config.name}"

    async with httpx.AsyncClient() as client:
        try:
            response = await client.delete(
                url,
                headers={"X-Service-Key": config.service_key},
                timeout=10.0,
            )
            response.raise_for_status()
            logger.info(
                "Service '%s' deregistered from %s (status %s)",
                config.name,
                url,
                response.status_code,
            )
        except Exception as exc:
            logger.error(
                "Failed to deregister service '%s' from %s: %s",
                config.name,
                url,
                exc,
            )
