from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from .auth import KeycloakTokenVerifier

_VALID_CALLER_TYPES = {"user", "User", "backend", "Backend"}
_USER_CALLER_TYPES = {"user", "User"}


class AuthMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        service_key: str,
        verifier: KeycloakTokenVerifier,
    ) -> None:
        super().__init__(app)
        self._service_key = service_key
        self._verifier = verifier

    async def dispatch(self, request: Request, call_next):
        x_service_key = request.headers.get("X-Service-Key")
        if x_service_key != self._service_key:
            return JSONResponse(
                status_code=403,
                content={"detail": "Invalid or missing X-Service-Key"},
            )

        caller_type = request.headers.get("X-Caller-Type")
        if caller_type not in _VALID_CALLER_TYPES:
            return JSONResponse(
                status_code=422,
                content={"detail": "Invalid or missing X-Caller-Type"},
            )

        if caller_type in _USER_CALLER_TYPES:
            authorization = request.headers.get("Authorization", "")
            if not authorization.startswith("Bearer ") or len(authorization) <= len("Bearer "):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Invalid or missing Authorization header"},
                )

            token = authorization[len("Bearer "):]
            try:
                token_payload = await self._verifier.verify(token)
            except Exception as exc:
                from fastapi import HTTPException
                if isinstance(exc, HTTPException):
                    return JSONResponse(
                        status_code=exc.status_code,
                        content={"detail": exc.detail},
                    )
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Token verification failed"},
                )
            request.state.token_payload = token_payload
        else:
            request.state.token_payload = None

        return await call_next(request)
