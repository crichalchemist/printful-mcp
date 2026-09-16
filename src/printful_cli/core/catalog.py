"""Catalog operations for the CLI."""

from __future__ import annotations

from typing import Any, Dict, Optional

from printful_core.endpoints import catalog as endpoints
from printful_core.format import summary
from printful_core.transport import SyncTransport


def list_products(
    transport: SyncTransport,
    limit: int = 20,
    offset: int = 0,
    category_ids: Optional[str] = None,
    colors: Optional[str] = None,
    techniques: Optional[str] = None,
    types: Optional[str] = None,
) -> Dict[str, Any]:
    response = transport.send(
        endpoints.list_products(limit, offset, category_ids, colors, techniques, types)
    )
    return summary.products(response)


def get_product(transport: SyncTransport, product_id: int) -> Dict[str, Any]:
    return transport.send(endpoints.get_product(product_id))


def list_variants(
    transport: SyncTransport, product_id: int, limit: int = 20, offset: int = 0
) -> Dict[str, Any]:
    return summary.variants(transport.send(endpoints.list_variants(product_id, limit, offset)))


def get_variant_prices(
    transport: SyncTransport, variant_id: int, currency: Optional[str] = None
) -> Dict[str, Any]:
    return transport.send(endpoints.get_variant_prices(variant_id, currency))


def get_availability(
    transport: SyncTransport, product_id: int, techniques: Optional[str] = None
) -> Dict[str, Any]:
    return transport.send(endpoints.get_availability(product_id, techniques))


def list_categories(transport: SyncTransport, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    return transport.send(endpoints.list_categories(limit, offset))


def get_category(transport: SyncTransport, category_id: int) -> Dict[str, Any]:
    return transport.send(endpoints.get_category(category_id))


def get_size_guide(
    transport: SyncTransport, product_id: int, unit: Optional[str] = None
) -> Dict[str, Any]:
    return transport.send(endpoints.get_size_guide(product_id, unit))
