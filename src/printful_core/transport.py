"""Executes a Request. The only module in the core that touches the network.

httpx ships Client and AsyncClient with matching APIs, so one module serves the
synchronous CLI and the asynchronous MCP server without duplicating URL
construction, header handling, or response normalization.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from .auth import Credentials
from .errors import PrintfulError, raise_for_status
from .request import Request

BASE_URLS = {
    "v2": "https://api.printful.com/v2",
    "v1": "https://api.printful.com",
}

DEFAULT_TIMEOUT = 30.0


def _url(request: Request) -> str:
    return f"{BASE_URLS[request.version]}{request.path}"


def _normalize(request: Request, response) -> Dict[str, Any]:
    """Turn a successful response into a body, or raise for a failure."""
    if 200 <= response.status_code < 300:
        if response.status_code == 204 or not response.text:
            return {}
        try:
            body = response.json()
        except ValueError:
            raise PrintfulError(
                f"Invalid JSON in response from {_url(request)} "
                f"(status {response.status_code})",
                status_code=response.status_code,
            )
        if request.version == "v2":
            return body
        # v1 wraps its payload in {"code": ..., "result": ...}
        return body.get("result", body) if isinstance(body, dict) else body

    try:
        body = response.json()
    except ValueError:
        body = response.text

    raise_for_status(response.status_code, body, _url(request),
                     headers=response.headers)


class SyncTransport:
    """Executes requests synchronously. Used by the CLI."""

    def __init__(self, credentials: Credentials, timeout: float = DEFAULT_TIMEOUT):
        self.credentials = credentials
        self.client = httpx.Client(timeout=timeout)

    def send(self, request: Request,
             extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        try:
            response = self.client.request(
                method=request.method,
                url=_url(request),
                params=request.params or None,
                json=request.json,
                headers=self.credentials.headers(extra_headers),
            )
        except httpx.TimeoutException:
            raise PrintfulError(f"Request to {_url(request)} timed out.")
        except httpx.RequestError as exc:
            raise PrintfulError(f"Request error: {exc}")
        return _normalize(request, response)

    def close(self) -> None:
        self.client.close()


class AsyncTransport:
    """Executes requests asynchronously. Used by the MCP server."""

    def __init__(self, credentials: Credentials, timeout: float = DEFAULT_TIMEOUT):
        self.credentials = credentials
        self.client = httpx.AsyncClient(timeout=timeout)

    async def send(self, request: Request,
                   extra_headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        try:
            response = await self.client.request(
                method=request.method,
                url=_url(request),
                params=request.params or None,
                json=request.json,
                headers=self.credentials.headers(extra_headers),
            )
        except httpx.TimeoutException:
            raise PrintfulError(f"Request to {_url(request)} timed out.")
        except httpx.RequestError as exc:
            raise PrintfulError(f"Request error: {exc}")
        return _normalize(request, response)

    async def close(self) -> None:
        await self.client.aclose()
