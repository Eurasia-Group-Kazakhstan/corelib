from __future__ import annotations

import logging

import httpx
from fastapi import HTTPException
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWKError, JWTClaimsError, JWTError

from .schemas import TokenPayload

logger = logging.getLogger(__name__)


class KeycloakTokenVerifier:
    def __init__(
        self,
        server_url: str,
        realm: str,
        client_id: str,
        audience: str,
        client_secret: str | None = None,
        public_key: str | None = None,
        issuer: str | None = None,
    ) -> None:
        self._server_url = server_url.rstrip("/")
        self._realm = realm
        self._client_id = client_id
        self._audience = audience
        self._client_secret = client_secret
        self._static_public_key = public_key
        self._issuer = issuer or f"{self._server_url}/realms/{self._realm}"
        self._jwks: dict | None = None

    @property
    def _certs_url(self) -> str:
        return f"{self._server_url}/realms/{self._realm}/protocol/openid-connect/certs"

    async def _get_jwks(self) -> dict:
        if self._jwks is not None:
            return self._jwks
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(self._certs_url, timeout=10.0)
                response.raise_for_status()
                self._jwks = response.json()
                return self._jwks
            except Exception as exc:
                logger.error("Failed to fetch JWKS from %s: %s", self._certs_url, exc)
                raise HTTPException(
                    status_code=401,
                    detail="Unable to fetch token verification keys",
                ) from exc

    async def verify(self, token: str) -> TokenPayload:
        if self._static_public_key:
            key: str | dict = self._static_public_key
        else:
            jwks = await self._get_jwks()
            try:
                unverified_header = jwt.get_unverified_header(token)
            except JWTError as exc:
                raise HTTPException(
                    status_code=401,
                    detail="Token signature verification failed",
                ) from exc

            kid = unverified_header.get("kid")
            key = None
            for jwk_key in jwks.get("keys", []):
                if jwk_key.get("kid") == kid:
                    key = jwk_key
                    break

            if key is None:
                self._jwks = None
                raise HTTPException(
                    status_code=401,
                    detail="Token signature verification failed",
                )

        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                audience=self._audience,
                issuer=self._issuer,
            )
        except ExpiredSignatureError as exc:
            raise HTTPException(
                status_code=401,
                detail="Token has expired",
            ) from exc
        except JWTClaimsError as exc:
            raise HTTPException(
                status_code=401,
                detail="Token claims validation failed",
            ) from exc
        except (JWTError, JWKError) as exc:
            raise HTTPException(
                status_code=401,
                detail="Token signature verification failed",
            ) from exc

        return TokenPayload(**payload)
