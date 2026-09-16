"""The orders adapter."""
import json

from printful_core.errors import PrintfulError
from printful_mcp.models.inputs import (
    ConfirmOrderInput,
    CreateOrderInput,
    ListOrdersInput,
)
from printful_mcp.tools import orders


def _recipient():
    return dict(recipient_name="Ada Lovelace", recipient_address1="1 Analytical Way",
                recipient_city="London", recipient_country_code="GB",
                recipient_zip="EC1A 1BB")


async def test_a_draft_order_carries_its_items(transport):
    """An order created without items can never be filled.

    This is the defect the upstream fix exists for: the tool used to send a
    recipient and nothing else, and the resulting draft was a dead end.
    """
    items = [{"source": "catalog", "catalog_variant_id": 4012, "quantity": 2,
              "placements": [{"placement": "front", "technique": "dtg",
                              "layers": [{"type": "file", "url": "https://x/a.png"}]}]}]
    transport._responses.append({"data": {"id": 1, "status": "draft",
                                          "created_at": "", "updated_at": ""}})
    await orders.create_order(
        transport, CreateOrderInput(items_json=json.dumps(items), **_recipient()))
    sent = transport.last
    assert sent.method == "POST"
    assert sent.path == "/orders"
    assert sent.json["order_items"][0]["catalog_variant_id"] == 4012
    assert sent.json["order_items"][0]["quantity"] == 2


async def test_the_status_filter_reaches_the_query(transport):
    """Without this the tool cannot answer 'which drafts are waiting?'."""
    await orders.list_orders(transport, ListOrdersInput(status="draft"))
    assert transport.last.params["status"] == "draft"


async def test_an_unset_status_is_not_sent(transport):
    """A literal 'None' status would filter every order out."""
    await orders.list_orders(transport, ListOrdersInput())
    assert "status" not in transport.last.params


async def test_confirmation_posts_to_the_confirmation_path(transport):
    """Confirmation charges the account, so the path must be exact.

    This tool is never exercised against the live API. A fake transport is the
    only place its request shape can be checked at all.
    """
    transport._responses.append({"data": {"id": 42, "status": "pending",
                                          "created_at": "", "updated_at": ""}})
    out = await orders.confirm_order(transport, ConfirmOrderInput(order_id="42"))
    assert transport.last.method == "POST"
    assert transport.last.path == "/orders/42/confirmation"
    assert "confirmed successfully" in out


async def test_a_core_validation_error_does_not_escape_as_a_traceback(transport):
    """The core raises ValueError; PrintfulError alone would not catch it.

    An uncaught exception crosses the JSON-RPC boundary as a protocol error,
    so the calling model sees a transport failure rather than the reason its
    order was rejected.
    """
    items = [{"source": "catalog", "catalog_variant_id": 4012, "quantity": 1}]
    out = await orders.create_order(
        transport, CreateOrderInput(items_json=json.dumps(items), **_recipient()))
    assert out.startswith("Error: order_items[0] (variant 4012) has no placements.")
    assert '"placement":"front"' in out
    assert transport.sent == []


async def test_an_api_error_is_returned_as_text(transport):
    transport._responses.append(PrintfulError("Order 9 not found", status_code=404))
    out = await orders.list_orders(transport, ListOrdersInput())
    assert out == "Error: Order 9 not found"


async def test_the_order_list_shows_each_orders_status(transport):
    """'Which drafts are waiting?' is unanswerable if the row omits status."""
    transport._responses.append({"data": [{"id": 7, "status": "draft",
                                           "created_at": "2026-01-01"}],
                                 "paging": {"total": 1, "offset": 0, "limit": 20}})
    out = await orders.list_orders(transport, ListOrdersInput())
    assert "- **Status:** draft" in out
