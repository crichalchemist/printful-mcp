"""Catalog operations (v2)."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..utils.printful_backend import PrintfulBackend


def list_products(
    backend: PrintfulBackend,
    limit: int = 20,
    offset: int = 0,
    category_ids: Optional[str] = None,
    colors: Optional[str] = None,
    techniques: Optional[str] = None,
    types: Optional[str] = None,
) -> Dict[str, Any]:
    return backend.get(
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


def get_product(backend: PrintfulBackend, product_id: int) -> Dict[str, Any]:
    return backend.get(f"/catalog-products/{product_id}")


def list_variants(
    backend: PrintfulBackend, product_id: int, limit: int = 20, offset: int = 0
) -> Dict[str, Any]:
    return backend.get(
        f"/catalog-products/{product_id}/catalog-variants",
        params={"limit": limit, "offset": offset},
    )


def get_variant_prices(
    backend: PrintfulBackend, variant_id: int, currency: Optional[str] = None
) -> Dict[str, Any]:
    return backend.get(
        f"/catalog-variants/{variant_id}/prices", params={"currency": currency}
    )


def get_availability(
    backend: PrintfulBackend, product_id: int, techniques: Optional[str] = None
) -> Dict[str, Any]:
    return backend.get(
        f"/catalog-products/{product_id}/availability",
        params={"techniques": techniques},
    )


def list_categories(
    backend: PrintfulBackend, limit: int = 20, offset: int = 0
) -> Dict[str, Any]:
    return backend.get(
        "/catalog-categories", params={"limit": limit, "offset": offset}
    )


def get_category(backend: PrintfulBackend, category_id: int) -> Dict[str, Any]:
    return backend.get(f"/catalog-categories/{category_id}")


def get_size_guide(
    backend: PrintfulBackend, product_id: int, unit: Optional[str] = None
) -> Dict[str, Any]:
    return backend.get(
        f"/catalog-products/{product_id}/sizes", params={"unit": unit}
    )


def summarize_products(data: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce a product list response to table-friendly rows."""
    products = data.get("data", []) or []
    paging = data.get("paging", {}) or {}
    rows = []
    for p in products:
        techniques = p.get("techniques") or []
        rows.append(
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "type": p.get("type"),
                "brand": p.get("brand"),
                "variants": p.get("variant_count"),
                "techniques": ",".join(
                    t.get("key", "") for t in techniques if isinstance(t, dict)
                ),
            }
        )
    return {"products": rows, "paging": paging, "count": len(rows)}


def summarize_variants(data: Dict[str, Any]) -> Dict[str, Any]:
    variants = data.get("data", []) or []
    rows = [
        {
            "id": v.get("id"),
            "name": v.get("name"),
            "size": v.get("size"),
            "color": v.get("color"),
        }
        for v in variants
    ]
    return {"variants": rows, "paging": data.get("paging", {}), "count": len(rows)}
