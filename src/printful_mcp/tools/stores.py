"""Store tools for the Printful MCP server."""

import json

from printful_core.endpoints import stores
from printful_core.errors import PrintfulError
from printful_core.format import markdown
from printful_core.transport import AsyncTransport

from ..models.inputs import GetStoreStatsInput, ListStoresInput, ListStoreTemplatesInput


async def list_stores(transport: AsyncTransport, params: ListStoresInput) -> str:
    """
    List all stores available to the API token.

    Returns store IDs and names. Store-level tokens return one store,
    account-level tokens return all stores.
    """
    try:
        data = await transport.send(stores.list_stores())
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.stores(data)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_store_statistics(transport: AsyncTransport, params: GetStoreStatsInput) -> str:
    """
    Get store statistics for a date range.

    Returns sales, costs, profit, and other metrics. Available report types:
    - sales_and_costs: Detailed sales/costs by date
    - profit: Total profit in period
    - total_paid_orders: Number of paid orders
    - average_fulfillment_time: Avg fulfillment time
    """
    try:
        request = stores.get_statistics(
            params.store_id, params.date_from, params.date_to,
            report_types=params.report_types, currency=params.currency)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.store_statistics(data, params.date_from, params.date_to)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def list_store_templates(transport: AsyncTransport,
                               params: ListStoreTemplatesInput) -> str:
    """
    List the store's saved product templates.

    Templates are designs already placed on a product, ready to reuse.
    """
    try:
        request = stores.list_templates(limit=params.limit, offset=params.offset)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.store_templates(data)
    except PrintfulError as e:
        return f"Error: {e.message}"
