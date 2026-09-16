"""Order endpoints (v2).

confirm_order submits an order for fulfillment and charges the account. Every
caller must gate it behind an explicit confirmation from the operator.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..request import Request


def _require_placements(items: List[Dict[str, Any]]) -> None:
    """Printful rejects a catalog item with no artwork; fail before sending."""
    for index, item in enumerate(items):
        if item.get("source", "catalog") == "catalog" and not item.get("placements"):
            raise ValueError(
                f"order_items[{index}] (variant "
                f"{item.get('catalog_variant_id')}) has no placements. Printful "
                "rejects a catalog item with no artwork."
            )


def build_catalog_item(catalog_variant_id: int, quantity: int = 1,
                       image_url: Optional[str] = None,
                       placement: str = "front", technique: str = "dtg",
                       external_id: Optional[str] = None) -> Dict[str, Any]:
    """Build one catalog order item in the shape the live API accepts."""
    if quantity < 1:
        raise ValueError(f"quantity must be >= 1, got {quantity}")

    item: Dict[str, Any] = {
        "source": "catalog",
        "catalog_variant_id": int(catalog_variant_id),
        "quantity": int(quantity),
    }
    if external_id:
        item["external_id"] = external_id
    if image_url:
        item["placements"] = [{
            "placement": placement,
            "technique": technique,
            "layers": [{"type": "file", "url": image_url}],
        }]
    return item


def list_orders(limit: int = 20, offset: int = 0,
                status: Optional[str] = None) -> Request:
    return Request("GET", "/orders",
                   params={"limit": limit, "offset": offset, "status": status})


def get_order(order_id: str) -> Request:
    """Accepts an order ID, or an external ID prefixed with '@'."""
    return Request("GET", f"/orders/{order_id}")


def create_order(recipient: Dict[str, Any], items: List[Dict[str, Any]],
                 external_id: Optional[str] = None,
                 shipping: Optional[str] = None) -> Request:
    """Create a DRAFT order. Drafts are not charged until confirmed."""
    if not items:
        raise ValueError("Creating an order requires at least one item.")
    _require_placements(items)

    body: Dict[str, Any] = {"recipient": dict(recipient),
                            "order_items": [dict(item) for item in items]}
    if external_id:
        body["external_id"] = external_id
    if shipping:
        body["shipping"] = shipping
    return Request("POST", "/orders", json=body)


def update_order(order_id: str, changes: Dict[str, Any]) -> Request:
    if not changes:
        raise ValueError("Update requires at least one field to change.")
    return Request("PATCH", f"/orders/{order_id}", json=changes)


def cancel_order(order_id: str) -> Request:
    """Destructive. Callers must require explicit confirmation."""
    return Request("DELETE", f"/orders/{order_id}")


def confirm_order(order_id: str) -> Request:
    """CHARGES THE ACCOUNT. Callers must require explicit confirmation."""
    return Request("POST", f"/orders/{order_id}/confirmation")


def list_items(order_id: str) -> Request:
    return Request("GET", f"/orders/{order_id}/order-items")


def list_shipments(order_id: str) -> Request:
    return Request("GET", f"/orders/{order_id}/shipments")


def create_estimation_task(recipient: Dict[str, Any],
                           items: List[Dict[str, Any]]) -> Request:
    """Start an asynchronous cost estimate. Free; places no order."""
    if not items:
        raise ValueError("Estimation requires at least one item.")
    return Request("POST", "/order-estimation-tasks",
                   json={"recipient": dict(recipient),
                        "order_items": [dict(item) for item in items]})


def get_estimation_task(task_id: str) -> Request:
    return Request("GET", "/order-estimation-tasks", params={"id": task_id})
