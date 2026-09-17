"""Store endpoints. Stores and statistics are v2; product templates are v1."""

from __future__ import annotations

from typing import Optional

from ..request import Request


def list_stores() -> Request:
    return Request("GET", "/stores")


def get_statistics(
    store_id: int,
    date_from: str,
    date_to: str,
    report_types: str = "sales_and_costs,profit",
    currency: Optional[str] = None,
) -> Request:
    """Store statistics. Printful caps the range at six months."""
    return Request(
        "GET",
        f"/stores/{store_id}/statistics",
        params={
            "date_from": date_from,
            "date_to": date_to,
            "report_types": report_types,
            "currency": currency,
        },
    )


def list_templates(limit: int = 20, offset: int = 0) -> Request:
    """Product templates. v1 only — v2 exposes no equivalent."""
    return Request(
        "GET", "/product-templates", version="v1", params={"limit": limit, "offset": offset}
    )
