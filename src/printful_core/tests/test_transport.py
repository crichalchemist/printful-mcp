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

    def request(self, **kwargs):
        self.calls.append(kwargs)
        return self.responses.pop(0)

    def close(self):
        pass


def make_sync(responses, store_id=None):
    transport = SyncTransport(Credentials("tok", store_id))
    transport.client = FakeHTTPClient(responses)
    return transport


class TestUrlAndHeaders:
    def test_v2_base_url(self):
        t = make_sync([FakeHTTPResponse(200, {"data": []})])
        t.send(Request("GET", "/countries"))
        assert t.client.calls[0]["url"] == "https://api.printful.com/v2/countries"

    def test_v1_base_url(self):
        t = make_sync([FakeHTTPResponse(200, {"code": 200, "result": []})])
        t.send(Request("GET", "/store/products", version="v1"))
        assert t.client.calls[0]["url"] == "https://api.printful.com/store/products"

    def test_authorization_header(self):
        t = make_sync([FakeHTTPResponse(200, {"data": []})])
        t.send(Request("GET", "/countries"))
        assert t.client.calls[0]["headers"]["Authorization"] == "Bearer tok"

    def test_store_header_when_configured(self):
        t = make_sync([FakeHTTPResponse(200, {"data": []})], store_id="777")
        t.send(Request("GET", "/orders"))
        assert t.client.calls[0]["headers"]["X-PF-Store-Id"] == "777"


class TestResponseNormalization:
    def test_v2_body_unchanged(self):
        t = make_sync([FakeHTTPResponse(200, {"data": {"id": 1}})])
        assert t.send(Request("GET", "/orders/1")) == {"data": {"id": 1}}

    def test_v1_unwraps_result(self):
        t = make_sync([FakeHTTPResponse(200, {"code": 200, "result": [{"id": 9}]})])
        assert t.send(Request("GET", "/store/products", version="v1")) == [{"id": 9}]

    def test_204_returns_empty_dict(self):
        t = make_sync([FakeHTTPResponse(204, {}, text="")])
        assert t.send(Request("DELETE", "/orders/1")) == {}

    def test_invalid_json_raises(self):
        t = make_sync([FakeHTTPResponse(200, _INVALID)])
        with pytest.raises(PrintfulError, match="Invalid JSON"):
            t.send(Request("GET", "/x"))


class TestErrors:
    def test_error_message_surfaces(self):
        body = {"data": "nope", "error": {"reason": "BadRequest", "message": "nope"}}
        t = make_sync([FakeHTTPResponse(400, body)])
        with pytest.raises(PrintfulError, match="nope"):
            t.send(Request("GET", "/x"))

    def test_rate_limit(self):
        t = make_sync([FakeHTTPResponse(429, {}, headers={"Retry-After": "12"})])
        with pytest.raises(PrintfulRateLimitError) as exc:
            t.send(Request("GET", "/x"))
        assert exc.value.retry_after == "12"


@pytest.mark.asyncio
async def test_async_transport_shares_behavior():
    class FakeAsyncClient:
        def __init__(self, responses):
            self.responses = list(responses)
            self.calls = []

        async def request(self, **kwargs):
            self.calls.append(kwargs)
            return self.responses.pop(0)

        async def aclose(self):
            pass

    transport = AsyncTransport(Credentials("tok", None))
    transport.client = FakeAsyncClient([FakeHTTPResponse(200, {"data": [1]})])
    assert await transport.send(Request("GET", "/countries")) == {"data": [1]}
    assert transport.client.calls[0]["url"].endswith("/v2/countries")
