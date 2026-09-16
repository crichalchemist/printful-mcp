"""Catalog tools for the Printful MCP server."""

import json

from printful_core.endpoints import catalog
from printful_core.errors import PrintfulError
from printful_core.format import markdown
from printful_core.transport import AsyncTransport

from ..models.inputs import (
    GetCategoryInput,
    GetProductAvailabilityInput,
    GetProductInput,
    GetProductVariantsInput,
    GetSizeGuideInput,
    GetVariantPricesInput,
    ListCatalogProductsInput,
    ListCategoriesInput,
)


async def list_catalog_products(transport: AsyncTransport, params: ListCatalogProductsInput) -> str:
    """
    List catalog products with optional filters.

    Browse Printful's product catalog with filtering by category, color, technique, etc.
    Returns product IDs, names, types, and available variants.
    """
    try:
        request = catalog.list_products(
            limit=params.limit,
            offset=params.offset,
            category_ids=params.category_ids,
            colors=params.colors,
            techniques=params.techniques,
            types=params.types,
        )
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.products(data)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_product(transport: AsyncTransport, params: GetProductInput) -> str:
    """
    Get detailed information about a specific catalog product.

    Returns full product details including placements, techniques, design options,
    available sizes, colors, and product options.
    """
    try:
        data = await transport.send(catalog.get_product(params.product_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.product(data.get("data", {}))
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_product_variants(transport: AsyncTransport, params: GetProductVariantsInput) -> str:
    """
    Get all variants (size/color combinations) for a catalog product.

    Returns variant IDs, names, sizes, colors, and images needed for ordering.
    """
    try:
        request = catalog.list_variants(params.product_id, limit=params.limit, offset=params.offset)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.variants(data, params.product_id)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_variant_prices(transport: AsyncTransport, params: GetVariantPricesInput) -> str:
    """
    Get pricing information for a specific catalog variant.

    Returns prices for different techniques, placements, and quantity discounts.
    """
    try:
        request = catalog.get_variant_prices(params.variant_id, currency=params.currency)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.variant_prices(data, params.variant_id)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_product_availability(
    transport: AsyncTransport, params: GetProductAvailabilityInput
) -> str:
    """
    Check stock availability for a catalog product.

    Returns availability status for each variant and technique.
    """
    try:
        request = catalog.get_availability(params.product_id, techniques=params.techniques)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.availability(data, params.product_id)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def list_categories(transport: AsyncTransport, params: ListCategoriesInput) -> str:
    """
    List the catalog's product categories.

    Category IDs are what printful_list_catalog_products filters on, so this is
    the tool that makes that filter usable.
    """
    try:
        request = catalog.list_categories(limit=params.limit, offset=params.offset)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.categories(data)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_category(transport: AsyncTransport, params: GetCategoryInput) -> str:
    """
    Get one catalog category by ID.
    """
    try:
        data = await transport.send(catalog.get_category(params.category_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.category(data)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_size_guide(transport: AsyncTransport, params: GetSizeGuideInput) -> str:
    """
    Get the size tables for a catalog product.

    Returns measurements per size, in inches or centimetres.
    """
    try:
        request = catalog.get_size_guide(params.product_id, unit=params.unit)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.size_guide(data, params.product_id)
    except PrintfulError as e:
        return f"Error: {e.message}"
