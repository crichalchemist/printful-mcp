"""Shipping tools for the Printful MCP server."""

import json

from printful_core.endpoints import shipping
from printful_core.errors import PrintfulError
from printful_core.format import markdown
from printful_core.pagination import collect_pages_async
from printful_core.transport import AsyncTransport

from ..models.inputs import CalculateShippingInput, CalculateTaxInput


async def calculate_shipping_rates(transport: AsyncTransport,
                                   params: CalculateShippingInput) -> str:
    """
    Calculate shipping rates for an order.

    Provides available shipping methods and costs based on recipient location
    and order items. Returns estimated delivery times and customs fee information.
    """
    try:
        items = json.loads(params.items_json)
    except json.JSONDecodeError:
        return ('Error: items_json must be valid JSON array. Example: '
                '[{"catalog_variant_id": 4011, "quantity": 1, "source": "catalog"}]')
    if not isinstance(items, list) or not items:
        return "Error: items_json must be a non-empty JSON array of order items."

    recipient = {"country_code": params.recipient_country_code}
    if params.recipient_state_code:
        recipient["state_code"] = params.recipient_state_code
    if params.recipient_city:
        recipient["city"] = params.recipient_city
    if params.recipient_zip:
        recipient["zip"] = params.recipient_zip

    try:
        request = shipping.calculate_rates(recipient, items, currency=params.currency)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.rates(data)
    except ValueError as e:
        return f"Error: {e}"
    except PrintfulError as e:
        return f"Error: {e.message}"


async def list_countries(transport: AsyncTransport) -> str:
    """
    List all countries where Printful is available.

    Returns country codes and state codes needed for order creation.

    This walks every page. /v2/countries paginates at 20 of roughly 239 rows,
    and a single request drops everything after the first page -- which is how
    a previous version of this tool reported that Printful does not ship to the
    United States.
    """
    try:
        data = await collect_pages_async(shipping.list_countries(), transport.send)
        return markdown.countries(data)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def calculate_tax(transport: AsyncTransport, params: CalculateTaxInput) -> str:
    """
    Get the tax rate for a destination.

    This uses API v1; v2 exposes no tax endpoint.
    """
    try:
        request = shipping.calculate_tax(
            params.country_code, state_code=params.state_code,
            city=params.city, zip_code=params.zip_code)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.tax(data)
    except PrintfulError as e:
        return f"Error: {e.message}"
