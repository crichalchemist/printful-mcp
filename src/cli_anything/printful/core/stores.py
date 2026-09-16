"""Store operations. Store list/stats are v2; product templates are v1 only."""
from __future__ import annotations

from typing import Any, Dict, Optional

from ..utils.printful_backend import PrintfulBackend


def list_stores(backend: PrintfulBackend) -> Dict[str, Any]:
    return backend.get("/stores")


def get_statistics(
    backend: PrintfulBackend,
    store_id: int,
    date_from: str,
    date_to: str,
    report_types: str = "sales_and_costs,profit",
    currency: Optional[str] = None,
) -> Dict[str, Any]:
    """Store statistics. Printful caps the range at 6 months."""
    return backend.get(
        f"/stores/{store_id}/statistics",
        params={
            "date_from": date_from,
            "date_to": date_to,
            "report_types": report_types,
            "currency": currency,
        },
    )


def list_templates(
    backend: PrintfulBackend, limit: int = 20, offset: int = 0
) -> Dict[str, Any]:
    """Product templates. v1 only — not available in v2."""
    result = backend.get(
        "/product-templates", version="v1", params={"limit": limit, "offset": offset}
    )
    return result if isinstance(result, dict) else {"items": result}


def summarize_stores(data: Dict[str, Any]) -> Dict[str, Any]:
    stores = data.get("data", []) or []
    rows = [
        {
            "id": s.get("id"),
            "name": s.get("name"),
            "type": s.get("type"),
            "website": s.get("website"),
        }
        for s in stores
    ]
    return {"stores": rows, "count": len(rows)}
