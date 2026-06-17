from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from corelib.registry import RegistryConfig, deregister_service, register_service

CONFIG = RegistryConfig(
    name="svc",
    display_name="Svc",
    description="desc",
    base_url="http://svc:8000",
    health_url="http://svc:8000/health",
    path_prefix="/svc",
    version="1.0.0",
    registry_url="http://registry:8000/api/services",
    service_key="secret",
)

OPENAPI = {"openapi": "3.0.0", "info": {"title": "Svc", "version": "1.0.0"}, "paths": {}}


@pytest.mark.asyncio
async def test_register_sends_post():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.status_code = 201

    mock_post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = mock_post
        mock_client_cls.return_value = mock_client

        await register_service(OPENAPI, CONFIG)

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    assert call_kwargs.args[0] == CONFIG.registry_url
    sent_body = call_kwargs.kwargs["json"]
    assert sent_body["name"] == CONFIG.name
    assert sent_body["openapi_schema"] == OPENAPI
    assert call_kwargs.kwargs["headers"]["X-Service-Key"] == CONFIG.service_key


@pytest.mark.asyncio
async def test_deregister_sends_delete():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.status_code = 200

    mock_delete = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.delete = mock_delete
        mock_client_cls.return_value = mock_client

        await deregister_service(CONFIG)

    mock_delete.assert_called_once()
    call_kwargs = mock_delete.call_args
    assert call_kwargs.args[0] == f"{CONFIG.registry_url}/{CONFIG.name}"
    assert call_kwargs.kwargs["headers"]["X-Service-Key"] == CONFIG.service_key


@pytest.mark.asyncio
async def test_register_network_error_does_not_raise():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client_cls.return_value = mock_client

        await register_service(OPENAPI, CONFIG)


@pytest.mark.asyncio
async def test_deregister_network_error_does_not_raise():
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.delete = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client_cls.return_value = mock_client

        await deregister_service(CONFIG)
