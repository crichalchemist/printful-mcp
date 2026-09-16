import inspect

import httpx
import pytest

from printful_core.auth import Credentials
from printful_core.errors import PrintfulError, PrintfulRateLimitError
from printful_core.request import Request
from printful_core.transport import AsyncTransport, SyncTransport


class FakeHTTPResponse:
    def __init__(self, status_code=200, body=None, headers=None, text="x"):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._body is _INVALID:
            raise ValueError("not json")
        return self._body


_INVALID = object()


class FakeHTTPClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def _next(self, kwargs):
        self.calls.append(kwargs)
        queued = self.responses.pop(0)
        # A queued exception stands in for a connection that never produced a
        # response, which is how httpx reports a timeout or a refused socket.
        if isinstance(queued, Exception):
            raise queued
        return queued

    def request(self, **kwargs):
        return self._next(kwargs)

    def close(self):
        pass


class FakeAsyncHTTPClient(FakeHTTPClient):
    async def request(self, **kwargs):
        return self._next(kwargs)

    async def aclose(self):
        pass


def make_sync(responses, store_id=None):
    transport = SyncTransport(Credentials("tok", store_id))
    transport.client = FakeHTTPClient(responses)
    return transport


def make_async(responses, store_id=None):
    transport = AsyncTransport(Credentials("tok", store_id))
    transport.client = FakeAsyncHTTPClient(responses)
    return transport


# The MCP server reaches the API through the async transport exclusively, so a
# guarantee proved against the sync half alone is not proved. Every case below
# runs against both.
both_transports = pytest.mark.parametrize(
    "make", [make_sync, make_async], ids=["sync", "async"]
)


async def send(transport, request):
    """Send through either transport: await the async one, return the sync one."""
    result = transport.send(request)
    if inspect.isawaitable(result):
        return await result
    return result


@both_transports
class TestUrlAndHeaders:
    async def test_v2_base_url(self, make):
        t = make([FakeHTTPResponse(200, {"data": []})])
        await send(t, Request("GET", "/countries"))
        assert t.client.calls[0]["url"] == "https://api.printful.com/v2/countries"

    async def test_v1_base_url(self, make):
        t = make([FakeHTTPResponse(200, {"code": 200, "result": []})])
        await send(t, Request("GET", "/store/products", version="v1"))
        assert t.client.calls[0]["url"] == "https://api.printful.com/store/products"

    async def test_authorization_header(self, make):
        t = make([FakeHTTPResponse(200, {"data": []})])
        await send(t, Request("GET", "/countries"))
        assert t.client.calls[0]["headers"]["Authorization"] == "Bearer tok"

    async def test_store_header_when_configured(self, make):
        t = make([FakeHTTPResponse(200, {"data": []})], store_id="777")
        await send(t, Request("GET", "/orders"))
        assert t.client.calls[0]["headers"]["X-PF-Store-Id"] == "777"


@both_transports
class TestResponseNormalization:
    async def test_v2_body_unchanged(self, make):
        t = make([FakeHTTPResponse(200, {"data": {"id": 1}})])
        assert await send(t, Request("GET", "/orders/1")) == {"data": {"id": 1}}

    async def test_v1_unwraps_result(self, make):
        t = make([FakeHTTPResponse(200, {"code": 200, "result": [{"id": 9}]})])
        assert await send(t, Request("GET", "/store/products", version="v1")) == [{"id": 9}]

    async def test_204_returns_empty_dict(self, make):
        t = make([FakeHTTPResponse(204, {"data": "x"}, text="")])
        assert await send(t, Request("DELETE", "/orders/1")) == {}

    async def test_invalid_json_raises(self, make):
        t = make([FakeHTTPResponse(200, _INVALID)])
        with pytest.raises(PrintfulError, match="Invalid JSON"):
            await send(t, Request("GET", "/x"))


@both_transports
class TestErrors:
    async def test_error_message_surfaces(self, make):
        body = {"data": "nope", "error": {"reason": "BadRequest", "message": "nope"}}
        t = make([FakeHTTPResponse(400, body)])
        with pytest.raises(PrintfulError, match="nope"):
            await send(t, Request("GET", "/x"))

    async def test_rate_limit(self, make):
        t = make([FakeHTTPResponse(429, {}, headers={"Retry-After": "12"})])
        with pytest.raises(PrintfulRateLimitError) as exc:
            await send(t, Request("GET", "/x"))
        assert exc.value.retry_after == "12"


@both_transports
class TestUnreachableAPI:
    """A caller handles one exception family, so httpx's must not escape."""

    async def test_timeout_is_reported_as_a_printful_error(self, make):
        t = make([httpx.TimeoutException("took too long")])
        with pytest.raises(PrintfulError, match="timed out"):
            await send(t, Request("GET", "/countries"))

    async def test_connection_failure_is_reported_as_a_printful_error(self, make):
        t = make([httpx.ConnectError("connection refused")])
        with pytest.raises(PrintfulError, match="Request error: connection refused"):
            await send(t, Request("GET", "/countries"))
