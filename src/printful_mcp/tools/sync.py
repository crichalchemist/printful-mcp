"""v1 API fallback tools for features not yet available in v2."""

import json
from typing import Literal, Optional

from pydantic import BaseModel, Field

from printful_core.endpoints import sync
from printful_core.errors import PrintfulError
from printful_core.format import markdown
from printful_core.transport import AsyncTransport


# v1 Sync Product Models
class ListSyncProductsInput(BaseModel):
    """Input for listing sync products (v1 only)."""

    limit: Optional[int] = Field(default=20, ge=1, le=100, description="Number of results per page")
    offset: Optional[int] = Field(default=0, ge=0, description="Number of results to skip")
    format: Literal["markdown", "json"] = Field(default="markdown", description="Output format")


class GetSyncProductInput(BaseModel):
    """Input for getting sync product (v1 only)."""

    sync_product_id: int = Field(..., description="Sync product ID")
    format: Literal["markdown", "json"] = Field(default="markdown", description="Output format")


async def list_sync_products(transport: AsyncTransport, params: ListSyncProductsInput) -> str:
    """
    List sync products using v1 API (not available in v2 yet).

    Sync products are pre-configured product templates with saved designs
    that can be quickly added to orders. This uses the v1 API as sync
    products are not yet available in v2.
    """
    try:
        request = sync.list_products(limit=params.limit, offset=params.offset)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.sync_products(data)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_sync_product(transport: AsyncTransport, params: GetSyncProductInput) -> str:
    """
    Get sync product details using v1 API (not available in v2 yet).

    Returns full details of a sync product including variants and designs.
    This uses the v1 API as sync products are not yet available in v2.
    """
    try:
        data = await transport.send(sync.get_product(params.sync_product_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.sync_product(data)
    except PrintfulError as e:
        return f"Error: {e.message}"
