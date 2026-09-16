"""The orders adapter."""
import json

from printful_core.errors import PrintfulError
from printful_mcp.models.inputs import (
    CancelOrderInput,
    ConfirmOrderInput,
    CreateOrderInput,
    ListOrderItemsInput,
    ListOrderShipmentsInput,
    ListOrdersInput,
    UpdateOrderInput,
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


async def test_an_update_sends_a_patch_with_only_the_changed_fields(transport):
    """A PUT-shaped update would blank every field the caller omitted."""
    # Queue a renderable body: update_order renders markdown.order(), which reads
    # id/status/created_at/updated_at unguarded. The empty-queue default
    # {"data": {}} would raise KeyError inside the tool's try, and `except
    # PrintfulError` does not catch it -- the failure would read as a tool bug.
    transport._responses.append({"data": {"id": 42, "status": "draft",
                                          "created_at": "2026-01-01",
                                          "updated_at": "2026-01-01"}})
    await orders.update_order(transport, UpdateOrderInput(
        order_id="42", changes_json='{"recipient":{"address1":"2 New Street"}}'))
    assert transport.last.method == "PATCH"
    assert transport.last.path == "/orders/42"
    assert transport.last.json == {"recipient": {"address1": "2 New Street"}}


async def test_an_empty_update_is_refused_before_sending(transport):
    """The core refuses a no-op PATCH; the tool must report it, not crash.

    `update_order` raises ValueError on an empty change set, which is not a
    PrintfulError and escapes a body that catches only that.
    """
    out = await orders.update_order(
        transport, UpdateOrderInput(order_id="42", changes_json="{}"))
    assert out.startswith("Error:")
    assert transport.sent == []


async def test_malformed_update_json_is_reported_not_raised(transport):
    out = await orders.update_order(
        transport, UpdateOrderInput(order_id="42", changes_json="not json"))
    assert "valid JSON" in out
    assert transport.sent == []


async def test_cancel_sends_a_delete(transport):
    """Cancel is destructive; the verb is what makes it so."""
    transport._responses.append({"data": {"id": 42}})
    out = await orders.cancel_order(transport, CancelOrderInput(order_id="42"))
    assert transport.last.method == "DELETE"
    assert transport.last.path == "/orders/42"
    assert "cancelled" in out


async def test_an_unshipped_order_says_so_rather_than_showing_an_empty_heading(transport):
    """`{"data": []}` is the normal answer for an order still in production."""
    transport._responses.append({"data": []})
    out = await orders.list_order_shipments(
        transport, ListOrderShipmentsInput(order_id="42"))
    assert "No shipments yet" in out


async def test_order_items_show_the_variant_and_quantity_needed_to_reorder(transport):
    """`markdown.order_items` reads every field through `.get()`, so a wrong or
    dropped key would not KeyError -- it would silently render 'N/A' and pass.
    Without this test, someone restocking or debugging a mis-shipped order could
    be shown the wrong variant or quantity and never know the renderer was broken.
    """
    transport._responses.append({"data": [{"id": 99, "name": "Bella Canvas Tee",
                                           "catalog_variant_id": 4012, "quantity": 3,
                                           "price": "12.00", "currency": "USD"}]})
    out = await orders.list_order_items(transport, ListOrderItemsInput(order_id="42"))
    assert transport.last.method == "GET"
    assert transport.last.path == "/orders/42/order-items"
    assert "**Variant:** 4012" in out
    assert "**Quantity:** 3" in out
