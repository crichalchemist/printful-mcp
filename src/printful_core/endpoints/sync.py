"""Sync product endpoints. v1 only — not yet available in v2."""

from __future__ import annotations

from ..request import Request


def list_products(limit: int = 20, offset: int = 0) -> Request:
    return Request(
        "GET", "/store/products", version="v1", params={"limit": limit, "offset": offset}
    )


def get_product(sync_product_id: int) -> Request:
    return Request("GET", f"/store/products/{sync_product_id}", version="v1")
