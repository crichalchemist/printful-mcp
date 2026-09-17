"""Store operations. Store list/stats are v2; product templates are v1 only."""

from __future__ import annotations

from typing import Any, Dict, Optional

from printful_core.endpoints import stores as endpoints
from printful_core.format import summary
from printful_core.transport import SyncTransport


def list_stores(transport: SyncTransport) -> Dict[str, Any]:
    return summary.stores(transport.send(endpoints.list_stores()))


def get_statistics(
    transport: SyncTransport,
    store_id: int,
    date_from: str,
    date_to: str,
    report_types: str = "sales_and_costs,profit",
    currency: Optional[str] = None,
) -> Dict[str, Any]:
    """Store statistics. Printful caps the range at 6 months."""
    return transport.send(
        endpoints.get_statistics(store_id, date_from, date_to, report_types, currency)
    )


def list_templates(transport: SyncTransport, limit: int = 20, offset: int = 0) -> Dict[str, Any]:
    """Product templates. v1 only — not available in v2.

    Keyword arguments deliberately: this builder takes (limit, offset), unlike
    the same-named mockup builder, which takes a product ID.
    """
    result = transport.send(endpoints.list_templates(limit=limit, offset=offset))
    return result if isinstance(result, dict) else {"items": result}
