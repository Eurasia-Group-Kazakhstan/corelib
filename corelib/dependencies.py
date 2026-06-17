from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, Request

from .schemas import TokenPayload

_SENTINEL = object()


async def get_token_payload(request: Request) -> TokenPayload | None:
    payload = getattr(request.state, "token_payload", _SENTINEL)
    if payload is _SENTINEL:
        raise HTTPException(
            status_code=500,
            detail="token_payload was not set by middleware",
        )
    return payload


async def require_token_payload(request: Request) -> TokenPayload:
    payload = await get_token_payload(request)
    if payload is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication required",
        )
    return payload


def has_role(role: str, client_id: str | None = None) -> Callable:
    async def _dependency(request: Request) -> None:
        payload = await require_token_payload(request)

        if client_id is not None:
            resource_access = payload.resource_access or {}
            client_roles: list[str] = (
                resource_access.get(client_id, {}).get("roles", [])
            )
            if role not in client_roles:
                raise HTTPException(
                    status_code=403,
                    detail=f"Role '{role}' required for client '{client_id}'",
                )
        else:
            realm_roles: list[str] = (
                (payload.realm_access or {}).get("roles", [])
            )
            if role not in realm_roles:
                raise HTTPException(
                    status_code=403,
                    detail=f"Realm role '{role}' required",
                )

    return _dependency
