"""Catalog endpoints (v2)."""

from __future__ import annotations

from typing import Optional

from ..request import Request


def list_products(
    limit: int = 20,
    offset: int = 0,
    category_ids: Optional[str] = None,
    colors: Optional[str] = None,
    techniques: Optional[str] = None,
    types: Optional[str] = None,
) -> Request:
    return Request(
        "GET",
        "/catalog-products",
        params={
            "limit": limit,
            "offset": offset,
            "category_ids": category_ids,
            "colors": colors,
            "techniques": techniques,
            "types": types,
        },
    )


def get_product(product_id: int) -> Request:
    return Request("GET", f"/catalog-products/{product_id}")


def list_variants(product_id: int, limit: int = 20, offset: int = 0) -> Request:
    return Request(
        "GET",
        f"/catalog-products/{product_id}/catalog-variants",
        params={"limit": limit, "offset": offset},
    )


def get_variant_prices(variant_id: int, currency: Optional[str] = None) -> Request:
    return Request("GET", f"/catalog-variants/{variant_id}/prices", params={"currency": currency})


def get_availability(product_id: int, techniques: Optional[str] = None) -> Request:
    return Request(
        "GET", f"/catalog-products/{product_id}/availability", params={"techniques": techniques}
    )


def list_categories(limit: int = 20, offset: int = 0) -> Request:
    return Request("GET", "/catalog-categories", params={"limit": limit, "offset": offset})


def get_category(category_id: int) -> Request:
    return Request("GET", f"/catalog-categories/{category_id}")


def get_size_guide(product_id: int, unit: Optional[str] = None) -> Request:
    return Request("GET", f"/catalog-products/{product_id}/sizes", params={"unit": unit})
