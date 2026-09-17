"""Shipping rates and countries (v2); tax rates (v1 only)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..request import Request


def list_countries() -> Request:
    """Paginated. Pass the result through pagination.collect_pages."""
    return Request("GET", "/countries")


def calculate_rates(
    recipient: Dict[str, Any],
    items: List[Dict[str, Any]],
    currency: Optional[str] = None,
    locale: Optional[str] = None,
) -> Request:
    """Live shipping rates. Artwork is not required to quote a rate."""
    if not items:
        raise ValueError("Shipping rate calculation requires at least one item.")

    # The endpoint rejects an item without `source`: "Property
    # /order_items/0/source must be of type `string`, `null` provided".
    normalized = [{**item, "source": item.get("source") or "catalog"} for item in items]

    body: Dict[str, Any] = {"recipient": dict(recipient), "order_items": normalized}
    if currency:
        body["currency"] = currency
    if locale:
        body["locale"] = locale
    return Request("POST", "/shipping-rates", json=body)


def calculate_tax(
    country_code: str,
    state_code: Optional[str] = None,
    city: Optional[str] = None,
    zip_code: Optional[str] = None,
) -> Request:
    """Tax rate. v1 only — v2 exposes no tax endpoint."""
    recipient: Dict[str, Any] = {"country_code": country_code}
    if state_code:
        recipient["state_code"] = state_code
    if city:
        recipient["city"] = city
    if zip_code:
        recipient["zip"] = zip_code
    return Request("POST", "/tax/rates", version="v1", json={"recipient": recipient})
