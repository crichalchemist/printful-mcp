"""Order-creation payload tests. No network."""
import json
import pytest

from printful_mcp.models.inputs import CreateOrderInput
from printful_mcp.tools.orders import create_order


class RecordingTransport:
    """Records the Request instead of the posted body."""

    def __init__(self):
        self.sent = []

    async def send(self, request, extra_headers=None):
        self.sent.append(request)
        return {"data": {"id": 1, "status": "draft",
                         "created_at": "2026-01-01", "updated_at": "2026-01-01"}}


def _recipient_kwargs():
    return dict(
        recipient_name="Jane Doe",
        recipient_address1="1 Main St",
        recipient_city="Charlotte",
        recipient_state_code="NC",
        recipient_country_code="US",
        recipient_zip="28273",
    )


@pytest.mark.asyncio
async def test_order_items_reach_the_request():
    transport = RecordingTransport()
    params = CreateOrderInput(
        items_json=json.dumps([
            {"source": "catalog", "catalog_variant_id": 4012, "quantity": 2,
             "placements": [{"placement": "front", "technique": "dtg",
                             "layers": [{"type": "file",
                                         "url": "https://example.com/a.png"}]}]}
        ]),
        **_recipient_kwargs(),
    )
    await create_order(transport, params)
    items = transport.sent[0].json["order_items"]
    assert len(items) == 1
    assert items[0]["catalog_variant_id"] == 4012
    assert items[0]["quantity"] == 2


@pytest.mark.asyncio
async def test_catalog_item_without_placements_is_rejected_before_sending():
    """Printful returns 'Property placements is required'. Fail early instead."""
    transport = RecordingTransport()
    params = CreateOrderInput(
        items_json=json.dumps([
            {"source": "catalog", "catalog_variant_id": 4012, "quantity": 1}
        ]),
        **_recipient_kwargs(),
    )
    result = await create_order(transport, params)
    assert "order_items[0]" in result
    assert "variant 4012" in result
    assert "no placements" in result
    assert '"placement":"front"' in result      # the hint the MCP surface adds
    assert transport.sent == []


@pytest.mark.asyncio
async def test_invalid_json_is_reported_clearly():
    transport = RecordingTransport()
    params = CreateOrderInput(items_json="not json", **_recipient_kwargs())
    result = await create_order(transport, params)
    assert "valid JSON" in result
    assert transport.sent == []
