"""Order tools for the Printful MCP server."""

import json

from printful_core.endpoints import orders
from printful_core.errors import PrintfulError
from printful_core.format import markdown
from printful_core.transport import AsyncTransport

from ..models.inputs import (
    CancelOrderInput,
    ConfirmOrderInput,
    CreateOrderInput,
    GetOrderInput,
    ListOrderItemsInput,
    ListOrdersInput,
    ListOrderShipmentsInput,
    UpdateOrderInput,
)

PLACEMENTS_HINT = (
    'Add placements, e.g. [{"placement":"front","technique":"dtg",'
    '"layers":[{"type":"file","url":"https://example.com/art.png"}]}]'
)


async def create_order(transport: AsyncTransport, params: CreateOrderInput) -> str:
    """
    Create a new draft order.

    Creates an order in draft status with its items. Drafts are not charged.
    Confirm the order with printful_confirm_order to start fulfillment.
    """
    recipient = {
        "name": params.recipient_name,
        "address1": params.recipient_address1,
        "city": params.recipient_city,
        "country_code": params.recipient_country_code,
        "zip": params.recipient_zip,
    }
    if params.recipient_state_code:
        recipient["state_code"] = params.recipient_state_code
    if params.recipient_email:
        recipient["email"] = params.recipient_email
    if params.recipient_phone:
        recipient["phone"] = params.recipient_phone

    try:
        items = json.loads(params.items_json)
    except json.JSONDecodeError as e:
        return f"Error: items_json must be valid JSON array ({e})."
    if not isinstance(items, list) or not items:
        return "Error: items_json must be a non-empty JSON array of order items."

    try:
        request = orders.create_order(recipient, items, external_id=params.external_id)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.order(data.get("data", {}))
    except ValueError as e:
        # The core validates items and names the offending index and variant.
        # It cannot carry this hint: the shape of a placements block is an
        # MCP-surface concern, and the core must stay free of either caller's
        # vocabulary (the same reason `_mockup_timeout` takes `recovery_hint`).
        return f"Error: {e} {PLACEMENTS_HINT}"
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_order(transport: AsyncTransport, params: GetOrderInput) -> str:
    """
    Get details of a specific order.

    Use order ID or external ID (prefix with @) to retrieve order information,
    including status, recipient, costs, and items.
    """
    try:
        data = await transport.send(orders.get_order(params.order_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.order(data.get("data", {}))
    except PrintfulError as e:
        return f"Error: {e.message}"


async def confirm_order(transport: AsyncTransport, params: ConfirmOrderInput) -> str:
    """
    Confirm an order to start fulfillment.

    Moves the order from draft to pending and begins production. This charges
    the account. The order must have items and calculated costs first.
    """
    try:
        data = await transport.send(orders.confirm_order(params.order_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        body = data.get("data", {})
        return f"✓ Order {body['id']} confirmed successfully!\n\n" + markdown.order(body)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def list_orders(transport: AsyncTransport, params: ListOrdersInput) -> str:
    """
    List orders from the store.

    Returns a paginated list of orders with basic information. Filter by status
    to find drafts awaiting confirmation.
    """
    try:
        request = orders.list_orders(
            limit=params.limit, offset=params.offset, status=params.status)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.orders(data)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def update_order(transport: AsyncTransport, params: UpdateOrderInput) -> str:
    """
    Update a draft order.

    Only draft orders can be changed. Pass the fields to change as JSON.
    """
    try:
        changes = json.loads(params.changes_json)
    except json.JSONDecodeError as e:
        return f"Error: changes_json must be valid JSON ({e})."
    if not isinstance(changes, dict):
        return "Error: changes_json must be a JSON object of fields to change."

    try:
        data = await transport.send(orders.update_order(params.order_id, changes))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.order(data.get("data", {}))
    except ValueError as e:
        return f"Error: {e}"
    except PrintfulError as e:
        return f"Error: {e.message}"


async def cancel_order(transport: AsyncTransport, params: CancelOrderInput) -> str:
    """
    Cancel an order.

    A draft is discarded. A confirmed order is cancelled if it has not yet
    entered fulfillment. This cannot be undone.
    """
    try:
        data = await transport.send(orders.cancel_order(params.order_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        body = data.get("data", {})
        return f"✓ Order {body.get('id', params.order_id)} cancelled."
    except PrintfulError as e:
        return f"Error: {e.message}"


async def list_order_items(transport: AsyncTransport, params: ListOrderItemsInput) -> str:
    """
    List the items on an order.
    """
    try:
        data = await transport.send(orders.list_items(params.order_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.order_items(data, params.order_id)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def list_order_shipments(transport: AsyncTransport,
                               params: ListOrderShipmentsInput) -> str:
    """
    List the shipments for an order, with tracking numbers.
    """
    try:
        data = await transport.send(orders.list_shipments(params.order_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.shipments(data, params.order_id)
    except PrintfulError as e:
        return f"Error: {e.message}"
