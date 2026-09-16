"""Sync product operations. v1 only — not yet available in v2."""
from __future__ import annotations

from typing import Any, Dict

from ..utils.printful_backend import PrintfulBackend


def list_sync_products(
    backend: PrintfulBackend, limit: int = 20, offset: int = 0
) -> Dict[str, Any]:
    result = backend.get(
        "/store/products", version="v1", params={"limit": limit, "offset": offset}
    )
    items = result if isinstance(result, list) else result.get("items", [])
    return {"sync_products": items, "count": len(items)}


def get_sync_product(backend: PrintfulBackend, sync_product_id: int) -> Dict[str, Any]:
    result = backend.get(f"/store/products/{sync_product_id}", version="v1")
    return result if isinstance(result, dict) else {"result": result}
