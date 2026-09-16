"""Error-parsing tests for the Printful client. No network."""
import pytest

from printful_mcp.client import PrintfulClient, PrintfulAPIError


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("PRINTFUL_API_KEY", "test-token")
    return PrintfulClient()


@pytest.mark.asyncio
async def test_v2_error_reads_live_envelope(client):
    """The live v2 API returns error.message, not RFC 9457 detail/title."""
    response = FakeResponse(404, {
        "data": "Product 99999999 does not exist or is inactive.",
        "error": {"reason": "NotFound",
                  "message": "Product 99999999 does not exist or is inactive."},
    })
    with pytest.raises(PrintfulAPIError) as exc:
        await client._handle_error(response, "v2")
    assert "does not exist or is inactive" in exc.value.message
    assert exc.value.message != "Unknown error"


@pytest.mark.asyncio
async def test_v2_error_still_reads_documented_shape(client):
    """RFC 9457 is documented, so keep supporting it."""
    response = FakeResponse(400, {"detail": "Bad variant", "title": "Invalid"})
    with pytest.raises(PrintfulAPIError) as exc:
        await client._handle_error(response, "v2")
    assert exc.value.message == "Bad variant"


@pytest.mark.asyncio
async def test_v1_error_unchanged(client):
    response = FakeResponse(404, {"code": 404, "error": {"message": "Not Found"}})
    with pytest.raises(PrintfulAPIError) as exc:
        await client._handle_error(response, "v1")
    assert exc.value.message == "Not Found"
