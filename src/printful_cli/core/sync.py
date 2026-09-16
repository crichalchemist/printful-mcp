"""Sync product operations. v1 only — not yet available in v2."""
from __future__ import annotations

from typing import Any, Dict

from printful_core.endpoints import sync as endpoints
from printful_core.transport import SyncTransport


def list_sync_products(transport: SyncTransport, limit: int = 20,
                       offset: int = 0) -> Dict[str, Any]:
    # v1 unwraps to a bare list, so there is no summary.* helper for this shape.
    result = transport.send(endpoints.list_products(limit, offset))
    items = result if isinstance(result, list) else result.get("items", [])
    return {"sync_products": items, "count": len(items)}


def get_sync_product(transport: SyncTransport,
                     sync_product_id: int) -> Dict[str, Any]:
    result = transport.send(endpoints.get_product(sync_product_id))
    return result if isinstance(result, dict) else {"result": result}
