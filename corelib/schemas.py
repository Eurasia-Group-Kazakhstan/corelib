from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ServiceRegistrationPayload(BaseModel):
    name: str
    display_name: str
    description: str
    base_url: str
    health_url: str
    path_prefix: str
    version: str = "1.0.0"
    openapi_schema: dict[str, Any] = {}


class TokenPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    sub: str
    iss: str
    aud: str | list[str]
    exp: int
    iat: int
    jti: str | None = None
    preferred_username: str | None = None
    email: str | None = None
    realm_access: dict[str, Any] | None = None
    resource_access: dict[str, Any] | None = None
